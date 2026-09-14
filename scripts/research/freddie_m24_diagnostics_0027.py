#!/usr/bin/env python3
"""Build and certify Freddie M24 Diagnostics & Mechanisms."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.python.diagnostics.build import build_diagnostic_outputs, write_diagnostic_outputs
from research.python.diagnostics.load import load_diagnostic_inputs
from research.python.diagnostics.config import CLAIM_TYPE_COUNT_COLUMNS


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def resolve(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else root / p


def repo_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def verify_record(root: Path, record: dict[str, Any], label: str) -> Path:
    path = resolve(root, str(record["path"]))
    if not path.is_file():
        raise FileNotFoundError(f"{label}: {path}")
    if sha(path) != str(record["sha256"]):
        raise ValueError(f"{label} SHA mismatch: {path}")
    if "byte_count" in record and path.stat().st_size != int(record["byte_count"]):
        raise ValueError(f"{label} byte_count mismatch: {path}")
    return path


def reverify_lock(root: Path, lock: dict[str, Any]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for key, record in lock["inputs"].items():
        paths[key] = verify_record(root, record, key)
    for key, record in lock["parents"].items():
        verify_record(root, record, key)
    verify_record(root, lock["protocol"], "protocol")
    verify_record(root, lock["parent_analysis_input_lock"], "parent_analysis_input_lock")
    return paths


def file_record(root: Path, path: Path, rows: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": repo_path(root, path),
        "sha256": sha(path),
        "byte_count": path.stat().st_size,
    }
    if rows is not None:
        result["row_count"] = int(rows)
    return result


def dynamic_claim_type_columns(claim_types: list[str]) -> dict[str, str]:
    mapping = dict(CLAIM_TYPE_COUNT_COLUMNS)
    for claim_type in claim_types:
        mapping.setdefault(claim_type, f"{claim_type}_claim_count")
    return mapping


def build_profiles(
    outputs: dict[str, pd.DataFrame],
    input_data: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    generation = outputs["generation_diagnostics"].copy()
    claims = outputs["claim_diagnostics"].copy()
    source_claims = input_data["claims"].copy()

    failure_decomposition = generation[[
        "generation_id", "case_id", "model_id", "evidence_level", "selection_stratum", "usable",
        "end_to_end_faithfulness_yield", "supported_yield_component", "pipeline_loss",
        "not_verifiable_loss", "unsupported_loss", "contradiction_loss", "total_loss",
    ]].copy()

    claim_type_profile = (
        claims.groupby(["model_id", "evidence_level", "claim_type", "validation_status"], dropna=False)
        .size().rename("claim_count").reset_index()
        .sort_values(["model_id", "evidence_level", "claim_type", "validation_status"], kind="stable")
        .reset_index(drop=True)
    )

    reason_col = "primary_reason_code" if "primary_reason_code" in source_claims.columns else "reason_code"
    if reason_col in source_claims.columns:
        reason_profile = (
            source_claims.assign(reason_code_profile=source_claims[reason_col].fillna("<NONE>").astype(str))
            .groupby(["model_id", "evidence_level", "validation_status", "reason_code_profile"], dropna=False)
            .size().rename("claim_count").reset_index()
            .sort_values(["model_id", "evidence_level", "validation_status", "reason_code_profile"], kind="stable")
            .reset_index(drop=True)
        )
    else:
        reason_profile = pd.DataFrame(columns=["model_id", "evidence_level", "validation_status", "reason_code_profile", "claim_count"])

    case_failure_profile = (
        generation.groupby(["case_id", "selection_stratum"], dropna=False)
        .agg(
            planned_generation_count=("generation_id", "size"),
            usable_generation_count=("usable", "sum"),
            mean_end_to_end_yield=("end_to_end_faithfulness_yield", "mean"),
            mean_pipeline_loss=("pipeline_loss", "mean"),
            mean_not_verifiable_loss=("not_verifiable_loss", "mean"),
            mean_unsupported_loss=("unsupported_loss", "mean"),
            mean_contradiction_loss=("contradiction_loss", "mean"),
        ).reset_index()
        .sort_values(["selection_stratum", "case_id"], kind="stable").reset_index(drop=True)
    )
    case_failure_profile["unusable_generation_count"] = (
        case_failure_profile["planned_generation_count"] - case_failure_profile["usable_generation_count"]
    )

    unusable = generation.loc[~generation["usable"].astype(bool)].copy()
    pipeline_failures = outputs["pipeline_failures"].copy()
    if not unusable.empty:
        unusable = unusable.merge(
            pipeline_failures,
            on="generation_id",
            how="left",
            validate="one_to_one",
            suffixes=("", "_failure"),
        )

    safe_phrase_diagnostics = generation[[
        "generation_id", "case_id", "model_id", "evidence_level", "usable",
        "safe_phrase_exposed", "safe_phrase_item_count", "safe_phrase_match_eligible",
        "safe_phrase_matched_claim_count", "safe_phrase_matched_claim_rate",
        "narrative_any_safe_phrase_match", "narrative_max_safe_phrase_token_coverage",
    ]].copy()

    return {
        "failure_decomposition": failure_decomposition,
        "claim_type_profile": claim_type_profile,
        "reason_profile": reason_profile,
        "case_failure_profile": case_failure_profile,
        "unusable_generation_diagnostics": unusable,
        "safe_phrase_diagnostics": safe_phrase_diagnostics,
    }


def validate_release(
    outputs: dict[str, pd.DataFrame],
    profiles: dict[str, pd.DataFrame],
    input_data: dict[str, Any],
    lock: dict[str, Any],
    claim_type_columns: dict[str, str],
) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    def add(name: str, expected: Any, observed: Any, passed: bool) -> None:
        checks[name] = {"expected": expected, "observed": observed, "passed": bool(passed)}

    exp = lock["expected"]
    claims = outputs["claim_diagnostics"]
    generations = outputs["generation_diagnostics"]
    source_claims = input_data["claims"]
    source_generations = input_data["generations"]

    add("claim_row_count", int(exp["claims"]), len(claims), len(claims) == int(exp["claims"]))
    add("generation_row_count", int(exp["generations"]), len(generations), len(generations) == int(exp["generations"]))
    add("duplicate_claim_id_count", 0, int(claims["claim_id"].duplicated(keep=False).sum()), not claims["claim_id"].duplicated(keep=False).any())
    add("duplicate_generation_id_count", 0, int(generations["generation_id"].duplicated(keep=False).sum()), not generations["generation_id"].duplicated(keep=False).any())
    add("claim_id_set_match", True, set(claims["claim_id"].astype(str)) == set(source_claims["claim_id"].astype(str)), set(claims["claim_id"].astype(str)) == set(source_claims["claim_id"].astype(str)))
    add("generation_id_set_match", True, set(generations["generation_id"].astype(str)) == set(source_generations["generation_id"].astype(str)), set(generations["generation_id"].astype(str)) == set(source_generations["generation_id"].astype(str)))

    status_counts = claims["validation_status"].astype(str).value_counts().to_dict()
    add("validation_status_counts", exp["validation_status_counts"], status_counts, status_counts == exp["validation_status_counts"])
    actual_unusable = sorted(generations.loc[~generations["usable"].astype(bool), "generation_id"].astype(str))
    add("unusable_generation_ids", exp["unusable_generation_ids"], actual_unusable, actual_unusable == exp["unusable_generation_ids"])
    add("usable_generation_count", int(exp["usable_generations"]), int(generations["usable"].astype(bool).sum()), int(generations["usable"].astype(bool).sum()) == int(exp["usable_generations"]))

    component_sum = generations[[
        "supported_yield_component", "pipeline_loss", "not_verifiable_loss", "unsupported_loss", "contradiction_loss"
    ]].sum(axis=1)
    loss_mismatch = int((~np.isclose(component_sum, 1.0, atol=1e-12, rtol=0.0)).sum())
    add("loss_identity_mismatch_count", 0, loss_mismatch, loss_mismatch == 0)
    yield_mismatch = int((~np.isclose(
        generations["supported_yield_component"], generations["end_to_end_faithfulness_yield"], atol=1e-12, rtol=0.0
    )).sum())
    add("supported_yield_metric_mismatch_count", 0, yield_mismatch, yield_mismatch == 0)

    unusable = ~generations["usable"].astype(bool)
    unusable_rule = int(((generations.loc[unusable, "pipeline_loss"] != 1.0) | (generations.loc[unusable, "claim_count"] != 0)).sum())
    add("unusable_pipeline_rule_mismatch_count", 0, unusable_rule, unusable_rule == 0)
    semantic_loss_on_unusable = int((generations.loc[unusable, ["not_verifiable_loss", "unsupported_loss", "contradiction_loss"]].sum(axis=1) != 0).sum())
    add("unusable_semantic_loss_count", 0, semantic_loss_on_unusable, semantic_loss_on_unusable == 0)

    type_columns = list(claim_type_columns.values())
    missing_type_columns = [c for c in type_columns if c not in generations.columns]
    add("missing_claim_type_count_columns", [], missing_type_columns, not missing_type_columns)
    if not missing_type_columns:
        partition_mismatch = int((generations[type_columns].sum(axis=1) != generations["claim_count"]).sum())
    else:
        partition_mismatch = len(generations)
    add("claim_type_partition_mismatch_count", 0, partition_mismatch, partition_mismatch == 0)

    failures = outputs["pipeline_failures"]
    add("pipeline_failure_count", int(exp["unusable_generations"]), len(failures), len(failures) == int(exp["unusable_generations"]))
    add("pipeline_failure_id_set", exp["unusable_generation_ids"], sorted(failures["generation_id"].astype(str)), sorted(failures["generation_id"].astype(str)) == exp["unusable_generation_ids"])

    overall_claim = outputs["claim_mechanism_summary"].loc[lambda x: x["group_type"] == "overall"]
    overall_gen = outputs["generation_mechanism_summary"].loc[lambda x: x["group_type"] == "overall"]
    add("claim_summary_overall_count", int(exp["claims"]), int(overall_claim.iloc[0]["claim_count"]) if len(overall_claim)==1 else -1, len(overall_claim)==1 and int(overall_claim.iloc[0]["claim_count"]) == int(exp["claims"]))
    add("generation_summary_overall_count", int(exp["generations"]), int(overall_gen.iloc[0]["planned_generation_count"]) if len(overall_gen)==1 else -1, len(overall_gen)==1 and int(overall_gen.iloc[0]["planned_generation_count"]) == int(exp["generations"]))

    safe_ready = lock["safe_phrase_readiness"]
    if safe_ready["enabled"]:
        add("safe_phrase_exposure_contract_verified", True, safe_ready["exposure_contract_verified"], safe_ready["exposure_contract_verified"] is True)
    else:
        observed_matches = int(claims["safe_phrase_any_match"].astype(bool).sum()) + int(generations["narrative_any_safe_phrase_match"].astype(bool).sum())
        add("disabled_safe_phrase_match_count", 0, observed_matches, observed_matches == 0)

    numeric_frames = list(outputs.values()) + list(profiles.values())
    infinity = 0
    for frame in numeric_frames:
        numeric = frame.select_dtypes(include=[np.number])
        if numeric.size:
            infinity += int(np.isinf(numeric.to_numpy(dtype=float)).sum())
    add("infinite_value_count", 0, infinity, infinity == 0)

    rate_columns = ["end_to_end_faithfulness_yield", "supported_yield_component", "pipeline_loss", "not_verifiable_loss", "unsupported_loss", "contradiction_loss", "total_loss", "safe_phrase_matched_claim_rate", "narrative_max_safe_phrase_token_coverage"]
    out_of_bounds = 0
    for col in rate_columns:
        values = pd.to_numeric(generations[col], errors="coerce").dropna()
        out_of_bounds += int(((values < -1e-12) | (values > 1+1e-12)).sum())
    add("rate_out_of_bounds_count", 0, out_of_bounds, out_of_bounds == 0)

    failed = sum(not x["passed"] for x in checks.values())
    return {
        "schema_version": "freddie_diagnostics_validation_v1",
        "diagnostic_version": str(claims["diagnostic_version"].iloc[0]) if len(claims) else None,
        "safe_phrase_analysis": lock["safe_phrase_readiness"],
        "checks": checks,
        "failed_check_count": failed,
        "passed": failed == 0,
        "exit_gate": "DIAGNOSTICS_READY" if failed == 0 else "DIAGNOSTICS_INVALID",
        "freddie_gate": "FREDDIE_DIAGNOSTICS_READY" if failed == 0 else "FREDDIE_DIAGNOSTICS_INVALID",
    }


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, float_format="%.12g", lineterminator="\n")


def directory_hashes(directory: Path) -> dict[str, str]:
    return {p.name: sha(p) for p in sorted(directory.iterdir()) if p.is_file()}


def build_once(root: Path, lock_path: Path, lock: dict[str, Any], protocol: dict[str, Any], out: Path, canonical_output_dir: Path) -> dict[str, Any]:
    paths = reverify_lock(root, lock)
    input_data = load_diagnostic_inputs({
        "data_mart_validation": paths["data_mart_validation"],
        "metric_validation": paths["metric_validation"],
        "statistical_validation": paths["statistical_validation"],
        "claims": paths["claims"],
        "generations": paths["generations"],
        "generation_metrics": paths["generation_metrics"],
        "cases": paths["cases"],
        "models": paths["models"],
        "evidence_levels": paths["evidence_levels"],
        "evidence_packages": paths["evidence_packages"],
        "evidence_items": paths["evidence_items"],
    })
    claim_type_columns = dynamic_claim_type_columns([str(x) for x in lock["expected"]["claim_types"]])
    outputs = build_diagnostic_outputs(
        input_data,
        claim_type_count_columns=claim_type_columns,
        diagnostic_version=str(protocol["diagnostic_version"]),
        safe_phrase_enabled=bool(lock["safe_phrase_readiness"]["enabled"]),
    )
    profiles = build_profiles(outputs, input_data)
    validation = validate_release(outputs, profiles, input_data, lock, claim_type_columns)
    if not validation["passed"]:
        failed = [k for k,v in validation["checks"].items() if not v["passed"]]
        raise SystemExit("M24 diagnostics validation failed: " + ", ".join(failed))

    out.mkdir(parents=True, exist_ok=False)
    write_diagnostic_outputs(outputs, out)
    for name, frame in profiles.items():
        write_csv(frame, out / f"{name}.csv")
    (out / "diagnostics_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    files: dict[str, Any] = {}
    all_frames = {**outputs, **profiles}
    for p in sorted(out.iterdir()):
        if p.is_file() and p.name not in {"diagnostics_manifest.json"}:
            rows = None
            if p.suffix == ".csv" and p.stem in all_frames:
                rows = len(all_frames[p.stem])
            files[p.name] = file_record(root, p, rows)
            files[p.name]["path"] = repo_path(root, canonical_output_dir / p.name)
    manifest = {
        "schema_version": "freddie_diagnostics_manifest_v1",
        "dataset_id": lock["dataset_id"],
        "experiment_id": lock["experiment_id"],
        "producer": "M24B_0027",
        "parent_diagnostics_input_lock": {"path": repo_path(root, lock_path), "sha256": sha(lock_path)},
        "diagnostic_version": protocol["diagnostic_version"],
        "counts": {
            "claims": int(len(outputs["claim_diagnostics"])),
            "generations": int(len(outputs["generation_diagnostics"])),
            "unusable_generations": int(len(outputs["pipeline_failures"])),
        },
        "safe_phrase_analysis": lock["safe_phrase_readiness"],
        "interpretation_limits": protocol["safe_phrase_analysis"]["forbidden_interpretations"],
        "files": files,
        "gate": "DIAGNOSTICS_READY",
        "freddie_gate": "FREDDIE_DIAGNOSTICS_READY",
    }
    (out / "diagnostics_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    return manifest


def reverify_existing(root: Path, lock_path: Path, output_dir: Path) -> dict[str, Any]:
    manifest = read_json(output_dir / "diagnostics_manifest.json")
    validation = read_json(output_dir / "diagnostics_validation.json")
    if manifest.get("gate") != "DIAGNOSTICS_READY" or manifest.get("freddie_gate") != "FREDDIE_DIAGNOSTICS_READY" or not validation.get("passed"):
        raise SystemExit("Existing M24 release is not certified.")
    if manifest.get("parent_diagnostics_input_lock", {}).get("sha256") != sha(lock_path):
        raise SystemExit("Existing M24 release parent lock drift.")
    for name, record in manifest.get("files", {}).items():
        path = output_dir / name
        if not path.is_file() or sha(path) != record["sha256"] or path.stat().st_size != int(record["byte_count"]):
            raise SystemExit(f"Existing M24 release artifact drift: {name}")
    return manifest


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--repo-root",required=True); ap.add_argument("--lock",required=True); ap.add_argument("--protocol",required=True); ap.add_argument("--output-dir",required=True); a=ap.parse_args()
    root=Path(a.repo_root).resolve(); lock_path=Path(a.lock).resolve(); protocol_path=Path(a.protocol).resolve(); output_dir=Path(a.output_dir).resolve()
    lock=read_json(lock_path); protocol=read_json(protocol_path)
    if lock.get("gate") != "FREDDIE_DIAGNOSTICS_INPUT_LOCK_READY": raise SystemExit("M24B requires FREDDIE_DIAGNOSTICS_INPUT_LOCK_READY.")
    reverify_lock(root, lock)
    if output_dir.exists():
        manifest=reverify_existing(root, lock_path, output_dir)
        print(f"FREDDIE_M24_DIAGNOSTICS=ALREADY_CERTIFIED generations={manifest['counts']['generations']} claims={manifest['counts']['claims']}")
        return 0
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    first=Path(tempfile.mkdtemp(prefix=".m24_diag_a_",dir=output_dir.parent)); shutil.rmtree(first)
    second=Path(tempfile.mkdtemp(prefix=".m24_diag_b_",dir=output_dir.parent)); shutil.rmtree(second)
    try:
        build_once(root,lock_path,lock,protocol,first,output_dir)
        build_once(root,lock_path,lock,protocol,second,output_dir)
        if directory_hashes(first) != directory_hashes(second): raise SystemExit("M24 deterministic replay mismatch between two clean builds.")
        os.replace(first,output_dir); first=Path("/__promoted__")
    finally:
        if first.exists(): shutil.rmtree(first,ignore_errors=True)
        if second.exists(): shutil.rmtree(second,ignore_errors=True)
    manifest=read_json(output_dir/"diagnostics_manifest.json")
    print("FREDDIE_M24_DIAGNOSTICS=PASS " + f"generations={manifest['counts']['generations']} claims={manifest['counts']['claims']} unusable={manifest['counts']['unusable_generations']} safe_phrase_enabled={str(manifest['safe_phrase_analysis']['enabled']).lower()}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
