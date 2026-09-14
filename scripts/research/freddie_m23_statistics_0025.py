#!/usr/bin/env python3
"""Execute, validate, bootstrap and certify the Freddie M23 statistical core."""

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

from research.python.statistical_analysis.bootstrap import build_case_bootstrap
from research.python.statistical_analysis.build import build_statistical_outputs
from research.python.statistical_analysis.load import load_statistical_inputs
from research.python.statistical_analysis.validate import (
    validate_statistical_outputs,
    write_validation_report,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root.resolve()))
    except ValueError:
        return str(resolved)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def reverify_lock(root: Path, lock: dict[str, Any]) -> None:
    for name, entry in lock["inputs"].items():
        path = resolve(root, entry["path"])
        if not path.is_file():
            raise FileNotFoundError(f"Statistical input missing: {name}: {path}")
        if sha(path) != entry["sha256"]:
            raise ValueError(f"Statistical input drift: {name}: {path}")


def contrast_id_from_row(row: pd.Series) -> str:
    family = str(row["contrast_family"])
    if family == "model_within_evidence":
        return (
            f"model_within_evidence::{row['condition_a_evidence_level']}::"
            f"{row['condition_a_model_id']}::{row['condition_b_model_id']}"
        )
    if family == "evidence_vs_s0":
        return (
            f"evidence_vs_s0::{row['condition_a_model_id']}::"
            f"{row['condition_a_evidence_level']}"
        )
    raise ValueError(f"Unknown contrast family: {family}")


def add_contrast_ids(paired: pd.DataFrame) -> pd.DataFrame:
    result = paired.copy()
    result.insert(0, "contrast_id", result.apply(contrast_id_from_row, axis=1))
    return result


def write_frame(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, lineterminator="\n")


def file_manifest(directory: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "statistical_manifest.json":
            result[path.name] = {
                "sha256": sha(path),
                "byte_count": path.stat().st_size,
            }
    return result


def directory_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: sha(path)
        for path in sorted(directory.iterdir(), key=lambda item: item.name)
        if path.is_file()
    }


def reverify_existing_release(root: Path, output_dir: Path, lock_path: Path) -> dict[str, Any]:
    """Fail closed if an existing certified release has drifted."""
    manifest_path = output_dir / "statistical_manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Existing M23 directory lacks statistical_manifest.json: {output_dir}")
    manifest = read_json(manifest_path)
    if manifest.get("gate") != "STATISTICAL_CORE_READY":
        raise SystemExit("Existing M23 manifest is not STATISTICAL_CORE_READY.")
    if manifest.get("freddie_gate") != "FREDDIE_STATISTICAL_CORE_READY":
        raise SystemExit("Existing M23 manifest is not FREDDIE_STATISTICAL_CORE_READY.")
    parent = manifest.get("parent_statistical_input_lock")
    if not isinstance(parent, dict) or parent.get("sha256") != sha(lock_path):
        raise SystemExit("Existing M23 release points to a different statistical input lock.")
    declared_files = manifest.get("files")
    if not isinstance(declared_files, dict):
        raise SystemExit("Existing M23 manifest lacks a file inventory.")
    expected_names = {str(name) for name in declared_files}
    observed_names = {p.name for p in output_dir.iterdir() if p.is_file() and p.name != "statistical_manifest.json"}
    if expected_names != observed_names:
        raise SystemExit("Existing M23 file inventory differs from its manifest.")
    for name, record in declared_files.items():
        path = output_dir / str(name)
        if not path.is_file():
            raise SystemExit(f"Existing M23 artifact missing: {name}")
        if not isinstance(record, dict) or record.get("sha256") != sha(path):
            raise SystemExit(f"Existing M23 artifact hash drift: {name}")
        if int(record.get("byte_count", -1)) != path.stat().st_size:
            raise SystemExit(f"Existing M23 artifact byte-count drift: {name}")
    validation = read_json(output_dir / "statistical_validation.json")
    contrast = read_json(output_dir / "contrast_registry_validation.json")
    bootstrap = read_json(output_dir / "bootstrap_validation.json")
    if not validation.get("passed") or validation.get("exit_gate") != "STATISTICAL_CORE_READY":
        raise SystemExit("Existing M23 statistical validation is not ready.")
    if not contrast.get("passed"):
        raise SystemExit("Existing M23 contrast registry validation is not ready.")
    if not bootstrap.get("passed"):
        raise SystemExit("Existing M23 bootstrap validation is not ready.")
    return manifest


def validate_protocol_contrasts(
    paired: pd.DataFrame,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    expected = [str(item["contrast_id"]) for item in protocol["paired_tests"]["contrasts"]]
    observed = add_contrast_ids(paired)["contrast_id"].astype(str).tolist()
    return {
        "expected_count": len(expected),
        "observed_count": len(observed),
        "expected_unique_count": len(set(expected)),
        "observed_unique_count": len(set(observed)),
        "exact_set_match": set(expected) == set(observed),
        "passed": len(expected) == 33 and len(observed) == 33 and set(expected) == set(observed),
    }


def validate_bootstrap(
    option_bootstrap: pd.DataFrame,
    contrast_bootstrap: pd.DataFrame,
    option_performance: pd.DataFrame,
    paired_with_ids: pd.DataFrame,
    bootstrap: dict[str, Any],
) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    def add(name: str, expected: Any, observed: Any, passed: bool) -> None:
        checks[name] = {"expected": expected, "observed": observed, "passed": bool(passed)}
    add("option_interval_count", 18, len(option_bootstrap), len(option_bootstrap) == 18)
    add("contrast_interval_count", 33, len(contrast_bootstrap), len(contrast_bootstrap) == 33)
    add("option_id_unique", 18, option_bootstrap["option_id"].nunique(), option_bootstrap["option_id"].nunique() == 18)
    add("contrast_id_unique", 33, contrast_bootstrap["contrast_id"].nunique(), contrast_bootstrap["contrast_id"].nunique() == 33)
    add("bootstrap_iterations", int(bootstrap["iterations"]), sorted(option_bootstrap["iterations"].unique().tolist()), sorted(option_bootstrap["iterations"].unique().tolist()) == [int(bootstrap["iterations"])])
    add("bootstrap_seed", int(bootstrap["seed"]), sorted(option_bootstrap["seed"].unique().tolist()), sorted(option_bootstrap["seed"].unique().tolist()) == [int(bootstrap["seed"])])

    option_expected = option_performance.set_index("option_id")["mean_end_to_end_faithfulness_yield"]
    option_observed = option_bootstrap.set_index("option_id")["observed_mean"].reindex(option_expected.index)
    option_diff = np.abs(option_expected.to_numpy(dtype=float) - option_observed.to_numpy(dtype=float))
    add("option_observed_mean_max_abs_diff", 0.0, float(option_diff.max(initial=0.0)), bool((option_diff <= 1e-12).all()))

    paired_expected = paired_with_ids.set_index("contrast_id")["mean_difference"]
    contrast_observed = contrast_bootstrap.set_index("contrast_id")["observed_mean_difference"].reindex(paired_expected.index)
    contrast_diff = np.abs(paired_expected.to_numpy(dtype=float) - contrast_observed.to_numpy(dtype=float))
    add("contrast_observed_mean_max_abs_diff", 0.0, float(contrast_diff.max(initial=0.0)), bool((contrast_diff <= 1e-12).all()))

    invalid_bounds = int((option_bootstrap["ci_lower"] > option_bootstrap["ci_upper"]).sum())
    invalid_bounds += int((contrast_bootstrap["ci_lower"] > contrast_bootstrap["ci_upper"]).sum())
    add("invalid_ci_order_count", 0, invalid_bounds, invalid_bounds == 0)
    failed = sum(not item["passed"] for item in checks.values())
    return {"checks": checks, "failed_check_count": failed, "passed": failed == 0}


def build_release(
    root: Path,
    lock_path: Path,
    lock: dict[str, Any],
    protocol: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    input_paths = {
        "metric_validation": resolve(root, lock["inputs"]["metric_validation"]["path"]),
        "generation_metrics": resolve(root, lock["inputs"]["generation_metrics"]["path"]),
        "cases": resolve(root, lock["inputs"]["cases"]["path"]),
        "models": resolve(root, lock["inputs"]["models"]["path"]),
        "evidence_levels": resolve(root, lock["inputs"]["evidence_levels"]["path"]),
    }
    inputs = load_statistical_inputs(input_paths)
    outputs = build_statistical_outputs(inputs)
    expected_counts = {str(k): int(v) for k, v in lock["expected_counts"].items()}
    validation = validate_statistical_outputs(
        outputs,
        inputs,
        expected_counts=expected_counts,
        expected_unusable_generation_ids=[str(x) for x in lock["expected_unusable_generation_ids"]],
    )
    if not validation["passed"]:
        failed = [name for name, check in validation["checks"].items() if not check["passed"]]
        raise SystemExit("M23 statistical validation failed: " + ", ".join(failed))

    analysis_frame = outputs["analysis_frame"]
    complete_ids = sorted(
        analysis_frame.loc[analysis_frame["is_complete_case"].astype(bool), "case_id"]
        .astype(str).unique().tolist()
    )
    if complete_ids != sorted(str(x) for x in lock["expected_complete_case_ids"]):
        raise SystemExit("M23 complete-case identity set differs from M21 frozen topology.")

    contrast_check = validate_protocol_contrasts(outputs["paired_tests"], protocol)
    if not contrast_check["passed"]:
        raise SystemExit("M23 primary contrasts do not match the frozen 33-contrast registry.")
    paired_with_ids = add_contrast_ids(outputs["paired_tests"])
    conditional_with_ids = add_contrast_ids(outputs["conditional_paired_tests"])

    boot = protocol["bootstrap"]
    option_bootstrap, contrast_bootstrap = build_case_bootstrap(
        analysis_frame,
        protocol["paired_tests"]["contrasts"],
        protocol["primary_metric"],
        iterations=int(boot["iterations"]),
        confidence=float(boot["confidence"]),
        seed=int(boot["seed"]),
    )
    option_performance = pd.read_csv(resolve(root, lock["inputs"]["option_performance"]["path"]), low_memory=False)
    bootstrap_validation = validate_bootstrap(
        option_bootstrap, contrast_bootstrap, option_performance, paired_with_ids, boot
    )
    if not bootstrap_validation["passed"]:
        failed = [name for name, check in bootstrap_validation["checks"].items() if not check["passed"]]
        raise SystemExit("M23 bootstrap validation failed: " + ", ".join(failed))

    output_dir.mkdir(parents=True, exist_ok=False)
    write_frame(outputs["analysis_frame"], output_dir / "analysis_frame.csv")
    write_frame(outputs["descriptive_statistics"], output_dir / "descriptive_statistics.csv")
    write_frame(outputs["omnibus_tests"], output_dir / "omnibus_tests.csv")
    write_frame(paired_with_ids, output_dir / "paired_tests.csv")
    write_frame(conditional_with_ids, output_dir / "conditional_paired_tests.csv")
    write_frame(outputs["complete_case_omnibus_tests"], output_dir / "complete_case_omnibus_tests.csv")
    write_frame(outputs["unusable_generations"], output_dir / "unusable_generations.csv")
    write_frame(outputs["sensitivity_summary"], output_dir / "sensitivity_summary.csv")
    write_frame(option_bootstrap, output_dir / "bootstrap_option_intervals.csv")
    write_frame(contrast_bootstrap, output_dir / "bootstrap_contrast_intervals.csv")
    write_validation_report(validation, output_dir / "statistical_validation.json")
    (output_dir / "contrast_registry_validation.json").write_text(
        json.dumps(contrast_check, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "bootstrap_validation.json").write_text(
        json.dumps(bootstrap_validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": "freddie_statistical_manifest_v1",
        "dataset_id": lock["dataset_id"],
        "experiment_id": lock["experiment_id"],
        "parent_statistical_input_lock": {"path": repo_path(root, lock_path), "sha256": sha(lock_path)},
        "primary_metric": protocol["primary_metric"],
        "primary_subject_count": int(expected_counts["cases"]),
        "complete_case_subject_count": int(expected_counts["complete_case_count"]),
        "omnibus_test_count": int(len(outputs["omnibus_tests"])),
        "primary_contrast_count": int(len(paired_with_ids)),
        "conditional_contrast_count": int(len(conditional_with_ids)),
        "bootstrap_option_interval_count": int(len(option_bootstrap)),
        "bootstrap_contrast_interval_count": int(len(contrast_bootstrap)),
        "gate": "STATISTICAL_CORE_READY",
        "freddie_gate": "FREDDIE_STATISTICAL_CORE_READY",
        "files": file_manifest(output_dir),
    }
    (output_dir / "statistical_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--repo-root',required=True); ap.add_argument('--stat-lock',required=True); ap.add_argument('--protocol',required=True); ap.add_argument('--output-dir',required=True); a=ap.parse_args()
    root=Path(a.repo_root).resolve(); lock_path=Path(a.stat_lock).resolve(); protocol_path=Path(a.protocol).resolve(); output_dir=Path(a.output_dir).resolve()
    lock=read_json(lock_path); protocol=read_json(protocol_path)
    if lock.get('gate')!='FREDDIE_STATISTICAL_INPUT_LOCK_READY': raise SystemExit('M23B requires FREDDIE_STATISTICAL_INPUT_LOCK_READY.')
    reverify_lock(root,lock)
    if output_dir.exists():
        reverify_existing_release(root, output_dir, lock_path)
        print('FREDDIE_M23_STATISTICS=ALREADY_CERTIFIED')
        return 0
    output_dir.parent.mkdir(parents=True,exist_ok=True)
    first=Path(tempfile.mkdtemp(prefix='.stat_v1_a_',dir=output_dir.parent)); shutil.rmtree(first)
    second=Path(tempfile.mkdtemp(prefix='.stat_v1_b_',dir=output_dir.parent)); shutil.rmtree(second)
    try:
        build_release(root,lock_path,lock,protocol,first)
        build_release(root,lock_path,lock,protocol,second)
        if directory_hashes(first)!=directory_hashes(second):
            raise SystemExit('M23 deterministic replay mismatch between two clean builds.')
        if output_dir.exists():
            raise SystemExit(f'Refusing to overwrite concurrently-created M23 release: {output_dir}')
        os.replace(first,output_dir); first=Path('/__promoted__')
    finally:
        if first.exists(): shutil.rmtree(first,ignore_errors=True)
        if second.exists(): shutil.rmtree(second,ignore_errors=True)
    manifest=read_json(output_dir/'statistical_manifest.json')
    print('FREDDIE_M23_STATISTICS=PASS ' + f"subjects={manifest['primary_subject_count']} complete_cases={manifest['complete_case_subject_count']} omnibus={manifest['omnibus_test_count']} paired={manifest['primary_contrast_count']} conditional={manifest['conditional_contrast_count']} bootstrap_options={manifest['bootstrap_option_interval_count']} bootstrap_contrasts={manifest['bootstrap_contrast_interval_count']}")
    return 0
if __name__=='__main__': raise SystemExit(main())
