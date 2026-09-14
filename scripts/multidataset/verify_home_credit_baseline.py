#!/usr/bin/env python3
"""Read-only regression guard for the certified Home Credit baseline.

The script never rewrites scientific artifacts. Missing optional late-stage
artifacts are reported as SKIPPED so it can also run in source-only worktrees.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from research.python.datasets.root import find_repository_root


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object: {path}")
    return payload


def nested(payload: dict[str, Any] | None, *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def main() -> None:
    root = find_repository_root(Path(__file__))
    baseline = json.loads(
        (root / "config/research/baselines/home_credit_baseline_v1.json").read_text(
            encoding="utf-8"
        )
    )["scientific_truths"]

    raw = load_json(root / "data/manifests/raw_file_manifest.json")
    matrix = load_json(root / "data/manifests/batch_c_feature_matrix_registry_summary.json")
    split = load_json(root / "data/manifests/split_manifest.json")
    preprocessing = load_json(root / "data/manifests/preprocessing_manifest.json")
    modeling = load_json(root / "data/manifests/model_training_manifest.json")
    xai = load_json(root / "data/manifests/xai_evidence_manifest.json")
    ir = load_json(root / "data/manifests/explanation_ir_v2_manifest_evaluation.json")
    evidence = load_json(root / "data/manifests/evidence_exposure_manifest_evaluation.json")
    selection = load_json(
        root / "data/reports/evidence_exposure/evaluation_36/selection_manifest.json"
    )

    checks: list[tuple[str, Any, Any]] = [
        (
            "application_rows",
            nested(raw, "raw_files", "application_train.csv", "rows"),
            baseline["application_rows"],
        ),
        (
            "engineered_feature_count",
            nested(matrix, "final_matrix_stats", "feature_count"),
            baseline["engineered_feature_count"],
        ),
        (
            "model_ready_feature_count",
            nested(preprocessing, "validation", "tree_validation", "preprocessed_feature_count"),
            baseline["model_ready_feature_count"],
        ),
        (
            "split_train_rows",
            nested(split, "split_stats", "splits", "train", "rows"),
            baseline["split_rows"]["train"],
        ),
        (
            "split_valid_rows",
            nested(split, "split_stats", "splits", "valid", "rows"),
            baseline["split_rows"]["valid"],
        ),
        (
            "split_test_rows",
            nested(split, "split_stats", "splits", "test", "rows"),
            baseline["split_rows"]["test"],
        ),
        (
            "selected_model",
            nested(modeling, "model_selection", "best_model_name")
            or nested(modeling, "best_model", "model_name")
            or modeling.get("best_model_name") if modeling else None,
            baseline["selected_model"],
        ),
        (
            "xai_case_count",
            nested(xai, "xai_method", "case_count")
            or nested(xai, "quality_report", "case_selection", "selected_case_count")
            or nested(xai, "record_counts", "output_record_count")
            or xai.get("case_count") if xai else None,
            baseline["xai_case_count"],
        ),
        (
            "ir_case_count",
            nested(ir, "build_summary", "ir_record_count")
            or nested(ir, "quality_report", "record_counts", "output_ir_record_count")
            or nested(ir, "record_counts", "output_ir_record_count"),
            baseline["xai_case_count"],
        ),
        (
            "full_evidence_package_count",
            evidence.get("output_package_count") if evidence else None,
            baseline["full_evidence_package_count"],
        ),
        (
            "evaluation_case_count",
            selection.get("selected_case_count") if selection else None,
            baseline["evaluation_case_count"],
        ),
        (
            "selected_evidence_package_count",
            selection.get("selected_package_count") if selection else None,
            baseline["selected_evidence_package_count"],
        ),
    ]

    failed = []
    for name, actual, expected in checks:
        if actual is None:
            print(f"SKIP {name}: artifact/field unavailable in this worktree")
            continue
        if actual != expected:
            print(f"FAIL {name}: actual={actual!r} expected={expected!r}")
            failed.append(name)
        else:
            print(f"PASS {name}: {actual!r}")

    if failed:
        raise SystemExit(f"HOME_CREDIT_BASELINE_REGRESSION=FAIL checks={failed}")
    print("HOME_CREDIT_BASELINE_REGRESSION=PASS")


if __name__ == "__main__":
    main()
