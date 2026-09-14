#!/usr/bin/env python3
"""Freeze the M21 data mart and metric definitions before M22 execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def artifact(root: Path, path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        display = str(path.relative_to(root.resolve()))
    except ValueError:
        display = str(path)
    return {"path": display, "sha256": sha(path), "byte_count": path.stat().st_size}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--analysis-lock", required=True)
    ap.add_argument("--metric-protocol", required=True)
    ap.add_argument("--data-mart-dir", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    root = Path(a.repo_root).resolve()
    analysis_lock_path = Path(a.analysis_lock).resolve()
    protocol_path = Path(a.metric_protocol).resolve()
    mart = Path(a.data_mart_dir).resolve()
    output = Path(a.output).resolve()
    analysis_lock = read_json(analysis_lock_path)
    protocol = read_json(protocol_path)
    validation_path = mart / "data_mart_validation.json"
    manifest_path = mart / "data_mart_manifest.json"
    validation = read_json(validation_path)
    manifest = read_json(manifest_path)
    if not validation.get("passed") or validation.get("exit_gate") != "DATA_MART_READY":
        raise SystemExit("M22 requires DATA_MART_READY.")
    if manifest.get("gate") != "DATA_MART_READY":
        raise SystemExit("M22 requires DATA_MART_READY in the M21 manifest.")
    if manifest.get("freddie_gate") != "FREDDIE_M21_DATA_MART_READY":
        raise SystemExit("M22 requires FREDDIE_M21_DATA_MART_READY in the M21 manifest.")
    observed = analysis_lock["observed"]
    expected = {
        "generations": int(observed["planned_generations"]),
        "usable_generations": int(observed["usable_generations"]),
        "unusable_generations": int(observed["unusable_generations"]),
        "claims": int(observed["final_claims"]),
        "models": int(observed["models"]),
        "evidence_levels": int(observed["evidence_conditions"]),
        "model_evidence_cells": int(observed["models"]) * int(observed["evidence_conditions"]),
        "generations_per_model_evidence_cell": int(observed["canonical_cases"]),
    }
    if protocol["monetary_cost"]["comparison_ready"] is not False:
        raise SystemExit("Freddie monetary cost comparison must remain disabled in M22.")
    files = {
        "generations": mart / "generations.csv",
        "claims": mart / "claims.csv",
        "data_mart_validation": validation_path,
        "data_mart_manifest": manifest_path,
    }
    lock = {
        "schema_version": "freddie_metric_input_lock_v1",
        "dataset_id": analysis_lock["dataset_id"],
        "experiment_id": analysis_lock["experiment_id"],
        "parent_analysis_input_lock": artifact(root, analysis_lock_path),
        "metric_protocol": artifact(root, protocol_path),
        "inputs": {name: artifact(root, path) for name, path in files.items()},
        "expected_counts": expected,
        "policies": {
            "primary_metric": protocol["primary_metric"]["metric_id"],
            "unusable_primary_value": protocol["primary_metric"]["unusable_value"],
            "conditional_unusable_handling": protocol["conditional_metrics"]["unusable_handling"],
            "monetary_cost_comparison_ready": False,
        },
        "gate": "FREDDIE_METRIC_INPUT_LOCK_READY",
    }
    encoded = json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if output.read_text(encoding="utf-8") == encoded:
            print("FREDDIE_M22A_METRIC_INPUT_LOCK=ALREADY_CERTIFIED")
            return 0
        raise SystemExit(f"Refusing to overwrite different metric input lock: {output}")
    output.write_text(encoded, encoding="utf-8")
    print(
        "FREDDIE_M22A_METRIC_INPUT_LOCK=PASS "
        f"generations={expected['generations']} claims={expected['claims']} "
        f"options={expected['model_evidence_cells']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
