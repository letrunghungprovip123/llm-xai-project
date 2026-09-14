#!/usr/bin/env python3
"""Build and certify Freddie M22 generation metrics and 18-option summaries."""

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

from research.python.metric_engineering.build import build_metric_outputs, write_metric_outputs
from research.python.metric_engineering.load import load_metric_inputs
from research.python.metric_engineering.validate import (
    validate_metric_outputs,
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
            raise FileNotFoundError(f"Metric input missing: {name}: {path}")
        if sha(path) != entry["sha256"]:
            raise ValueError(f"Metric input drift: {name}: {path}")


def safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return float(numerator / denominator)


def build_option_performance(metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = metrics.groupby(
        ["model_order", "model_id", "evidence_order", "evidence_level"],
        sort=True,
        dropna=False,
    )
    for (model_order, model_id, evidence_order, evidence_level), frame in grouped:
        supported = int(frame["supported_count"].sum())
        unsupported = int(frame["unsupported_count"].sum())
        contradicted = int(frame["contradicted_count"].sum())
        not_verifiable = int(frame["not_verifiable_count"].sum())
        not_applicable = int(frame["not_applicable_count"].sum())
        resolved = int(frame["resolved_count"].sum())
        applicable = int(frame["applicable_count"].sum())
        planned = int(len(frame))
        usable = int(frame["usable"].astype(bool).sum())
        rows.append({
            "model_order": int(model_order),
            "model_id": str(model_id),
            "evidence_order": int(evidence_order),
            "evidence_level": str(evidence_level),
            "option_id": f"{model_id}::{evidence_level}",
            "planned_generation_count": planned,
            "usable_generation_count": usable,
            "unusable_generation_count": planned - usable,
            "usability_rate": safe_ratio(usable, planned),
            "mean_end_to_end_faithfulness_yield": float(frame["end_to_end_faithfulness_yield"].mean()),
            "median_end_to_end_faithfulness_yield": float(frame["end_to_end_faithfulness_yield"].median()),
            "std_end_to_end_faithfulness_yield": float(frame["end_to_end_faithfulness_yield"].std(ddof=1)) if planned > 1 else 0.0,
            "mean_resolved_faithfulness": float(frame["resolved_faithfulness"].mean()) if frame["resolved_faithfulness"].notna().any() else None,
            "resolved_faithfulness_n": int(frame["resolved_faithfulness"].notna().sum()),
            "mean_verifiability": float(frame["verifiability"].mean()) if frame["verifiability"].notna().any() else None,
            "verifiability_n": int(frame["verifiability"].notna().sum()),
            "mean_conservative_faithfulness": float(frame["conservative_faithfulness"].mean()) if frame["conservative_faithfulness"].notna().any() else None,
            "conservative_faithfulness_n": int(frame["conservative_faithfulness"].notna().sum()),
            "total_claim_count": int(frame["claim_count"].sum()),
            "supported_count": supported,
            "unsupported_count": unsupported,
            "contradicted_count": contradicted,
            "not_verifiable_count": not_verifiable,
            "not_applicable_count": not_applicable,
            "resolved_count": resolved,
            "applicable_count": applicable,
            "micro_resolved_faithfulness": safe_ratio(supported, resolved),
            "micro_verifiability": safe_ratio(resolved, applicable),
            "micro_conservative_faithfulness": safe_ratio(supported, applicable),
            "mean_latency_seconds": float(frame["latency_seconds"].mean()) if frame["latency_seconds"].notna().any() else None,
            "mean_total_token_count": float(frame["total_token_count"].mean()) if frame["total_token_count"].notna().any() else None,
            "mean_supported_claims_per_1000_total_tokens": float(frame["supported_claims_per_1000_total_tokens"].mean()) if frame["supported_claims_per_1000_total_tokens"].notna().any() else None,
        })
    return pd.DataFrame(rows).sort_values(
        ["model_order", "evidence_order"], kind="stable"
    ).reset_index(drop=True)


def validate_options(options: pd.DataFrame, expected: dict[str, int]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    def add(name: str, exp: Any, obs: Any, ok: bool) -> None:
        checks[name] = {"expected": exp, "observed": obs, "passed": bool(ok)}
    add("option_count", expected["model_evidence_cells"], len(options), len(options) == expected["model_evidence_cells"])
    add("duplicate_option_count", 0, int(options["option_id"].duplicated(keep=False).sum()), not options["option_id"].duplicated(keep=False).any())
    invalid_planned = int((options["planned_generation_count"] != expected["generations_per_model_evidence_cell"]).sum())
    add("invalid_planned_denominator_count", 0, invalid_planned, invalid_planned == 0)
    count_mismatch = int(((options["usable_generation_count"] + options["unusable_generation_count"]) != options["planned_generation_count"]).sum())
    add("option_usability_partition_mismatch_count", 0, count_mismatch, count_mismatch == 0)
    rate_columns = [
        "usability_rate", "mean_end_to_end_faithfulness_yield",
        "mean_resolved_faithfulness", "mean_verifiability",
        "mean_conservative_faithfulness", "micro_resolved_faithfulness",
        "micro_verifiability", "micro_conservative_faithfulness",
    ]
    out_of_bounds = 0
    for column in rate_columns:
        values = pd.to_numeric(options[column], errors="coerce").dropna()
        out_of_bounds += int(((values < 0) | (values > 1)).sum())
    add("option_rate_out_of_bounds_count", 0, out_of_bounds, out_of_bounds == 0)
    failed = sum(not item["passed"] for item in checks.values())
    return {"checks": checks, "failed_check_count": failed, "passed": failed == 0}


def files_manifest(directory: Path) -> dict[str, dict[str, Any]]:
    result = {}
    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if path.is_file() and path.name != "metric_manifest.json":
            result[path.name] = {"sha256": sha(path), "byte_count": path.stat().st_size}
    return result


def directory_hashes(directory: Path) -> dict[str, str]:
    return {path.name: sha(path) for path in directory.iterdir() if path.is_file()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--metric-lock", required=True)
    ap.add_argument("--output-dir", required=True)
    a = ap.parse_args()
    root = Path(a.repo_root).resolve()
    lock_path = Path(a.metric_lock).resolve()
    output_dir = Path(a.output_dir).resolve()
    lock = read_json(lock_path)
    if lock.get("gate") != "FREDDIE_METRIC_INPUT_LOCK_READY":
        raise SystemExit("M22B requires FREDDIE_METRIC_INPUT_LOCK_READY.")
    reverify_lock(root, lock)
    expected = {str(k): int(v) for k, v in lock["expected_counts"].items()}
    input_paths = {
        "data_mart_validation": resolve(root, lock["inputs"]["data_mart_validation"]["path"]),
        "generations": resolve(root, lock["inputs"]["generations"]["path"]),
        "claims": resolve(root, lock["inputs"]["claims"]["path"]),
    }
    inputs = load_metric_inputs(input_paths)
    outputs = build_metric_outputs(inputs)
    validation = validate_metric_outputs(outputs, inputs, expected_counts=expected)
    if not validation["passed"]:
        failed = [name for name, check in validation["checks"].items() if not check["passed"]]
        raise SystemExit("M22 metric validation failed: " + ", ".join(failed))
    options = build_option_performance(outputs["generation_metrics"])
    option_validation = validate_options(options, expected)
    if not option_validation["passed"]:
        failed = [name for name, check in option_validation["checks"].items() if not check["passed"]]
        raise SystemExit("M22 option validation failed: " + ", ".join(failed))

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".metric_v1_tmp_", dir=output_dir.parent))
    try:
        write_metric_outputs(
            outputs,
            generation_metrics_path=staging / "generation_metrics.csv",
            metric_dictionary_path=staging / "metric_dictionary.csv",
        )
        write_validation_report(validation, staging / "metric_validation.json")
        options.to_csv(staging / "option_performance.csv", index=False, float_format="%.12g", lineterminator="\n")
        formula_checks = {
            name: check
            for name, check in validation["checks"].items()
            if "formula" in name or "identity" in name or "partition" in name or "unusable_generation" in name
        }
        formula_audit = {
            "schema_version": "freddie_metric_formula_audit_v1",
            "primary_metric": lock["policies"]["primary_metric"],
            "checks": formula_checks,
            "failed_check_count": sum(not check["passed"] for check in formula_checks.values()),
            "passed": all(check["passed"] for check in formula_checks.values()),
        }
        (staging / "metric_formula_audit.json").write_text(
            json.dumps(formula_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (staging / "option_validation.json").write_text(
            json.dumps(option_validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest = {
            "schema_version": "freddie_metric_manifest_v1",
            "dataset_id": lock["dataset_id"],
            "experiment_id": lock["experiment_id"],
            "parent_metric_input_lock": {"path": repo_path(root, lock_path), "sha256": sha(lock_path)},
            "primary_metric": lock["policies"]["primary_metric"],
            "monetary_cost_comparison_ready": False,
            "generation_metric_count": int(len(outputs["generation_metrics"])),
            "option_count": int(len(options)),
            "gate": "ANALYTICAL_MART_READY",
            "freddie_gate": "FREDDIE_METRICS_READY",
            "files": files_manifest(staging),
        }
        (staging / "metric_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if output_dir.exists():
            if directory_hashes(output_dir) == directory_hashes(staging):
                print("FREDDIE_M22_METRICS=ALREADY_CERTIFIED")
                return 0
            raise SystemExit(f"Refusing to overwrite different M22 release: {output_dir}")
        os.replace(staging, output_dir)
        staging = Path("/__promoted__")
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    print(
        "FREDDIE_M22_METRICS=PASS "
        f"generations={len(outputs['generation_metrics'])} options={len(options)} "
        f"unusable={expected['unusable_generations']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
