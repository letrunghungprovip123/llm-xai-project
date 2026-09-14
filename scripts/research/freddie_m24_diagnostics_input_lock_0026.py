#!/usr/bin/env python3
"""Freeze certified M21-M23 inputs and M24 diagnostic readiness."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from freddie_analysis_common_0021 import file_record, read_json, sha256, write_json
except ModuleNotFoundError:  # package import in tests
    from scripts.research.freddie_analysis_common_0021 import file_record, read_json, sha256, write_json


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def verify_manifest_files(root: Path, manifest: dict[str, Any], directory: Path) -> None:
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"Manifest has no file inventory: {directory}")
    for name, record in files.items():
        path = directory / str(name)
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256(path) != str(record["sha256"]):
            raise ValueError(f"Manifest SHA mismatch: {path}")
        if "byte_count" in record and path.stat().st_size != int(record["byte_count"]):
            raise ValueError(f"Manifest byte_count mismatch: {path}")


def safe_phrase_readiness(
    evidence_levels: pd.DataFrame,
    packages: pd.DataFrame,
    items: pd.DataFrame,
    requested: bool,
) -> dict[str, Any]:
    required = {"evidence_level", "safe_phrase_available"}
    if not required.issubset(evidence_levels.columns):
        return {
            "requested": requested,
            "exposure_contract_verified": False,
            "enabled": False,
            "disable_reason": "evidence_levels_missing_safe_phrase_contract",
        }
    if not {"package_id", "evidence_level", "safe_phrase_count"}.issubset(packages.columns):
        return {
            "requested": requested,
            "exposure_contract_verified": False,
            "enabled": False,
            "disable_reason": "evidence_packages_missing_safe_phrase_contract",
        }
    if not {"package_id", "safe_phrase"}.issubset(items.columns):
        return {
            "requested": requested,
            "exposure_contract_verified": False,
            "enabled": False,
            "disable_reason": "evidence_items_missing_safe_phrase_field",
        }

    phrase_mask = items["safe_phrase"].notna() & items["safe_phrase"].astype(str).str.strip().ne("")
    observed = items.loc[phrase_mask].groupby("package_id").size().to_dict()
    mismatched_packages: list[str] = []
    for row in packages.itertuples(index=False):
        if int(getattr(row, "safe_phrase_count")) != int(observed.get(str(row.package_id), 0)):
            mismatched_packages.append(str(row.package_id))

    by_level: dict[str, dict[str, Any]] = {}
    level_contract_mismatch: list[str] = []
    for row in evidence_levels.itertuples(index=False):
        level = str(row.evidence_level)
        level_packages = packages.loc[packages["evidence_level"].astype(str) == level]
        package_phrase_count = int(level_packages["safe_phrase_count"].sum())
        contract_available = bool(row.safe_phrase_available)
        observed_available = package_phrase_count > 0
        by_level[level] = {
            "safe_phrase_available_contract": contract_available,
            "observed_safe_phrase_count": package_phrase_count,
            "observed_available": observed_available,
        }
        if contract_available != observed_available:
            level_contract_mismatch.append(level)

    zero_control_violations = [
        level
        for level in ("S0", "S1")
        if by_level.get(level, {}).get("observed_safe_phrase_count", 0) != 0
    ]
    verified = not mismatched_packages and not level_contract_mismatch and not zero_control_violations
    return {
        "requested": bool(requested),
        "exposure_contract_verified": bool(verified),
        "enabled": bool(requested and verified),
        "disable_reason": None if (requested and verified) else (
            "not_requested" if not requested else "safe_phrase_exposure_contract_not_certified"
        ),
        "mismatched_package_count": len(mismatched_packages),
        "mismatched_package_examples": mismatched_packages[:10],
        "level_contract_mismatches": level_contract_mismatch,
        "control_level_violations": zero_control_violations,
        "by_evidence_level": by_level,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--analysis-lock", required=True)
    ap.add_argument("--data-mart-dir", required=True)
    ap.add_argument("--metric-dir", required=True)
    ap.add_argument("--stat-dir", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()

    root = Path(a.repo_root).resolve()
    protocol_path = Path(a.protocol).resolve()
    analysis_lock_path = Path(a.analysis_lock).resolve()
    mart = Path(a.data_mart_dir).resolve()
    metric = Path(a.metric_dir).resolve()
    stat = Path(a.stat_dir).resolve()
    output = Path(a.output).resolve()

    protocol = read_json(protocol_path)
    analysis_lock = read_json(analysis_lock_path)
    mart_manifest = read_json(mart / "data_mart_manifest.json")
    metric_manifest = read_json(metric / "metric_manifest.json")
    stat_manifest = read_json(stat / "statistical_manifest.json")
    mart_validation = read_json(mart / "data_mart_validation.json")
    metric_validation = read_json(metric / "metric_validation.json")
    stat_validation = read_json(stat / "statistical_validation.json")

    if analysis_lock.get("gate") != "FREDDIE_ANALYSIS_INPUT_LOCK_READY":
        raise SystemExit("M24 requires certified M21 analysis input lock.")
    if mart_manifest.get("gate") != "DATA_MART_READY" or mart_manifest.get("freddie_gate") != "FREDDIE_M21_DATA_MART_READY":
        raise SystemExit("M24 requires certified M21 data mart.")
    if metric_manifest.get("gate") != "ANALYTICAL_MART_READY" or metric_manifest.get("freddie_gate") != "FREDDIE_METRICS_READY":
        raise SystemExit("M24 requires certified M22 metrics.")
    if stat_manifest.get("gate") != "STATISTICAL_CORE_READY" or stat_manifest.get("freddie_gate") != "FREDDIE_STATISTICAL_CORE_READY":
        raise SystemExit("M24 requires certified M23 statistics.")
    for name, validation, gate in [
        ("data_mart", mart_validation, "DATA_MART_READY"),
        ("metric", metric_validation, "ANALYTICAL_MART_READY"),
        ("statistical", stat_validation, "STATISTICAL_CORE_READY"),
    ]:
        if not validation.get("passed") or validation.get("exit_gate") != gate:
            raise SystemExit(f"M24 upstream {name} validation is not certified.")

    verify_manifest_files(root, mart_manifest, mart)
    verify_manifest_files(root, metric_manifest, metric)
    verify_manifest_files(root, stat_manifest, stat)

    claims = pd.read_csv(mart / "claims.csv", low_memory=False)
    generations = pd.read_csv(mart / "generations.csv", low_memory=False)
    metrics = pd.read_csv(metric / "generation_metrics.csv", low_memory=False)
    evidence_levels = pd.read_csv(mart / "evidence_levels.csv", low_memory=False)
    packages = pd.read_csv(mart / "evidence_packages.csv", low_memory=False)
    items = pd.read_csv(mart / "evidence_items.csv", low_memory=False)

    observed = analysis_lock["observed"]
    expected_claims = int(observed["final_claims"])
    expected_generations = int(observed["planned_generations"])
    if len(claims) != expected_claims or len(generations) != expected_generations or len(metrics) != expected_generations:
        raise SystemExit("M24 upstream row counts disagree with M21 frozen counts.")
    locked_unusable = sorted(str(row["generation_id"]) for row in observed["unusable_generation_records"])
    actual_unusable = sorted(generations.loc[~generations["usable"].astype(bool), "generation_id"].astype(str))
    if actual_unusable != locked_unusable:
        raise SystemExit("M24 unusable generation identity set differs from M21 frozen topology.")

    claim_types = sorted(claims["claim_type"].astype(str).unique().tolist())
    registered = set(str(x) for x in mart_manifest.get("claim_types", []))
    unknown = sorted(set(claim_types) - registered)
    if unknown:
        raise SystemExit(f"M24 contains unregistered claim types: {unknown}")

    readiness = safe_phrase_readiness(
        evidence_levels,
        packages,
        items,
        bool(protocol["safe_phrase_analysis"]["requested"]),
    )

    status_counts = Counter(claims["validation_status"].astype(str))
    lock = {
        "schema_version": "freddie_diagnostics_input_lock_v1",
        "dataset_id": protocol["dataset_id"],
        "experiment_id": protocol["experiment_id"],
        "producer": "M24A_0026",
        "protocol": file_record(root, protocol_path),
        "parent_analysis_input_lock": file_record(root, analysis_lock_path),
        "parents": {
            "data_mart_manifest": file_record(root, mart / "data_mart_manifest.json"),
            "metric_manifest": file_record(root, metric / "metric_manifest.json"),
            "statistical_manifest": file_record(root, stat / "statistical_manifest.json"),
        },
        "inputs": {
            "data_mart_validation": file_record(root, mart / "data_mart_validation.json"),
            "metric_validation": file_record(root, metric / "metric_validation.json"),
            "statistical_validation": file_record(root, stat / "statistical_validation.json"),
            "claims": file_record(root, mart / "claims.csv", row_count=len(claims)),
            "generations": file_record(root, mart / "generations.csv", row_count=len(generations)),
            "generation_metrics": file_record(root, metric / "generation_metrics.csv", row_count=len(metrics)),
            "cases": file_record(root, mart / "cases.csv"),
            "models": file_record(root, mart / "models.csv"),
            "evidence_levels": file_record(root, mart / "evidence_levels.csv", row_count=len(evidence_levels)),
            "evidence_packages": file_record(root, mart / "evidence_packages.csv", row_count=len(packages)),
            "evidence_items": file_record(root, mart / "evidence_items.csv", row_count=len(items)),
        },
        "expected": {
            "claims": expected_claims,
            "generations": expected_generations,
            "usable_generations": int(observed["usable_generations"]),
            "unusable_generations": int(observed["unusable_generations"]),
            "cases": int(observed["canonical_cases"]),
            "models": int(observed["models"]),
            "evidence_levels": int(observed["evidence_conditions"]),
            "evidence_packages": int(observed["evidence_packages"]),
            "claim_types": claim_types,
            "validation_status_counts": dict(sorted(status_counts.items())),
            "unusable_generation_ids": locked_unusable,
        },
        "safe_phrase_readiness": readiness,
        "provider_execution_allowed": False,
        "gate": "FREDDIE_DIAGNOSTICS_INPUT_LOCK_READY",
    }

    encoded = json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if output.read_text(encoding="utf-8") == encoded:
            print(
                "FREDDIE_M24A_DIAGNOSTICS_INPUT_LOCK=ALREADY_CERTIFIED "
                f"safe_phrase_enabled={str(readiness['enabled']).lower()}"
            )
            return 0
        raise SystemExit(f"Refusing to overwrite different M24 diagnostics input lock: {output}")
    output.write_text(encoded, encoding="utf-8")
    print(
        "FREDDIE_M24A_DIAGNOSTICS_INPUT_LOCK=PASS "
        f"generations={expected_generations} claims={expected_claims} "
        f"unusable={len(locked_unusable)} safe_phrase_enabled={str(readiness['enabled']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
