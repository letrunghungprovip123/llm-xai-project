from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.hashing import sha256_file
from ..datasets.profile import load_canonical_bundle, load_dataset_profile
from ..datasets.receipts import StageReceipt, load_receipt, write_json_atomic

EXPECTED_DATASET_ID = "freddie_sflld_2024"
EXPECTED_MODEL_PORTFOLIO = {"logistic_regression", "random_forest", "hist_gradient_boosting"}
EXPECTED_SELECTION = {
    "primary": "average_precision",
    "secondary": "roc_auc",
    "tiebreaker": "brier_score_lower_is_better",
}


@dataclass(frozen=True)
class FreddieM13Certification:
    receipt_path: Path
    receipt: StageReceipt
    summary: dict[str, Any]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _relative_hashes(workspace: Path, paths: list[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        path = _require(path)
        result[str(path.relative_to(workspace))] = sha256_file(path)
    return result


def certify_freddie_m13(
    *,
    workspace: Path,
    dataset_profile_path: Path,
    canonical_bundle_path: Path,
    m12_receipt_path: Path,
    write_receipt: bool = True,
    expected_rows: int = 1_036_383,
    expected_positives: int = 5_572,
    expected_raw_features: int = 19,
) -> FreddieM13Certification:
    workspace = workspace.expanduser().resolve()
    profile_path = dataset_profile_path.expanduser().resolve()
    bundle_path = canonical_bundle_path.expanduser().resolve()
    m12_receipt_path = m12_receipt_path.expanduser().resolve()

    profile = load_dataset_profile(profile_path)
    bundle = load_canonical_bundle(bundle_path)
    m12 = load_receipt(_require(m12_receipt_path))
    if profile.dataset_id != EXPECTED_DATASET_ID or bundle.dataset_id != EXPECTED_DATASET_ID:
        raise ValueError("M13 Freddie certification requires freddie_sflld_2024")
    if m12.dataset_id != EXPECTED_DATASET_ID or m12.status != "PASS":
        raise ValueError("M12 receipt is not a PASS Freddie receipt")
    if any(value != "PASS" for value in m12.invariants.values()):
        raise ValueError("M12 receipt contains a non-PASS invariant")

    manifest_dir = workspace / "data/manifests"
    registry_dir = workspace / "ml/registry"
    report_dir = workspace / "data/reports"
    model_dir = workspace / "artifacts/models"
    processed_dir = workspace / "data/processed"

    split_manifest_path = _require(manifest_dir / "common_ml_split_manifest.json")
    prep_manifest_path = _require(manifest_dir / "common_ml_preprocessing_manifest.json")
    model_manifest_path = _require(manifest_dir / "common_ml_model_training_manifest.json")
    model_registry_path = _require(registry_dir / "model_registry.json")
    metrics_path = _require(report_dir / "model_metrics_summary.csv")
    predictions_path = _require(report_dir / "model_predictions_test.csv")
    best_model_path = _require(model_dir / "best_model.joblib")
    mapping_tree_path = _require(registry_dir / "preprocessed_feature_mapping_tree.json")
    mapping_linear_path = _require(registry_dir / "preprocessed_feature_mapping_linear.json")

    split = _load_json(split_manifest_path)
    prep = _load_json(prep_manifest_path)
    model_manifest = _load_json(model_manifest_path)
    registry = _load_json(model_registry_path)
    metrics = pd.read_csv(metrics_path)
    predictions = pd.read_csv(predictions_path)
    tree_mapping = _load_json(mapping_tree_path)
    linear_mapping = _load_json(mapping_linear_path)

    invariants: dict[str, str] = {}
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str) -> None:
        invariants[name] = "PASS" if condition else "FAIL"
        if not condition:
            failures.append(f"{name}: {detail}")

    for name, payload in (("split", split), ("preprocessing", prep), ("modeling", model_manifest), ("registry", registry)):
        check(f"{name}_dataset_id", payload.get("dataset_id") == EXPECTED_DATASET_ID, str(payload.get("dataset_id")))
        check(
            f"{name}_dataset_fingerprint",
            payload.get("dataset_fingerprint") == bundle.dataset_fingerprint,
            str(payload.get("dataset_fingerprint")),
        )

    split_stats = split.get("split_stats", {})
    split_parts = split_stats.get("splits", {})
    full_rows = int(split_stats.get("full_rows", -1))
    rows_sum = sum(int(split_parts.get(name, {}).get("rows", 0)) for name in ("train", "valid", "test"))
    positives_sum = sum(int(split_parts.get(name, {}).get("positive_count", 0)) for name in ("train", "valid", "test"))
    overlaps = split_stats.get("case_id_overlap", {})
    check("split_full_rows", full_rows == expected_rows, f"actual={full_rows} expected={expected_rows}")
    check("split_rows_accounted", rows_sum == full_rows, f"sum={rows_sum} full={full_rows}")
    check("split_positive_count", positives_sum == expected_positives, f"actual={positives_sum} expected={expected_positives}")
    check("split_case_overlap_zero", all(int(value) == 0 for value in overlaps.values()), str(overlaps))
    check("raw_feature_count", int(split.get("model_feature_count", -1)) == expected_raw_features, str(split.get("model_feature_count")))

    validation = prep.get("validation", {})
    tree_count = int(validation.get("tree", {}).get("preprocessed_feature_count", -1))
    linear_count = int(validation.get("linear", {}).get("preprocessed_feature_count", -1))
    check("tree_model_ready_positive_width", tree_count >= expected_raw_features, f"actual={tree_count}")
    check("linear_model_ready_width_match", linear_count == tree_count and linear_count >= expected_raw_features, f"tree={tree_count} linear={linear_count}")

    for branch, mapping in (("tree", tree_mapping), ("linear", linear_mapping)):
        concepts = [item.get("concept") for item in mapping.values() if isinstance(item, dict)]
        check(f"{branch}_mapping_nonempty", len(mapping) == (tree_count if branch == "tree" else linear_count), f"mapping={len(mapping)}")
        check(f"{branch}_semantic_coverage", bool(concepts) and all(value not in (None, "", "unknown") for value in concepts), "unknown/missing concept")

    models = registry.get("models", [])
    model_names = {str(item.get("model_name")) for item in models}
    check("model_portfolio", model_names == EXPECTED_MODEL_PORTFOLIO, str(sorted(model_names)))
    check("selection_policy", registry.get("selection_policy") == EXPECTED_SELECTION, str(registry.get("selection_policy")))
    best = registry.get("best_model", {})
    best_name = str(best.get("model_name", ""))
    best_branch = str(best.get("dataset_branch", ""))
    check("best_model_member", best_name in EXPECTED_MODEL_PORTFOLIO, best_name)
    check("best_model_branch", best_branch in {"tree", "linear"}, best_branch)

    valid_metric_models = set(metrics.loc[metrics["split"] == "valid", "model_name"].astype(str))
    test_metric_models = set(metrics.loc[metrics["split"] == "test", "model_name"].astype(str))
    check("valid_metrics_all_models", valid_metric_models == EXPECTED_MODEL_PORTFOLIO, str(sorted(valid_metric_models)))
    check("test_metrics_best_only", test_metric_models == {best_name}, str(sorted(test_metric_models)))
    for column in ("average_precision", "roc_auc", "brier_score"):
        check(f"metric_{column}_finite", column in metrics.columns and metrics[column].notna().all(), column)

    y_test_path = processed_dir / "model_ready" / best_branch / "y_test.parquet"
    y_test = pd.read_parquet(_require(y_test_path))
    check("test_prediction_rows", len(predictions) == len(y_test), f"pred={len(predictions)} y={len(y_test)}")
    if len(predictions) == len(y_test):
        check(
            "test_prediction_case_alignment",
            predictions["case_id"].astype(str).tolist() == y_test["case_id"].astype(str).tolist(),
            "case_id order mismatch",
        )
        check(
            "test_prediction_truth_alignment",
            predictions["y_true"].astype(int).tolist() == y_test["target"].astype(int).tolist(),
            "y_true order mismatch",
        )
    check("threshold_frozen_0_5", predictions["threshold"].nunique() == 1 and float(predictions["threshold"].iloc[0]) == 0.5, str(predictions["threshold"].unique()[:5]))

    if failures:
        raise RuntimeError("Freddie M13 certification failed: " + "; ".join(failures))

    output_paths = [
        split_manifest_path,
        prep_manifest_path,
        model_manifest_path,
        model_registry_path,
        metrics_path,
        predictions_path,
        best_model_path,
        mapping_tree_path,
        mapping_linear_path,
    ]
    receipt = StageReceipt(
        stage="freddie_common_ml_m13",
        stage_version="v1",
        dataset_id=EXPECTED_DATASET_ID,
        patch_id="0008",
        input_fingerprints={
            "canonical_bundle": sha256_file(bundle_path),
            "m12_receipt": sha256_file(m12_receipt_path),
        },
        config_fingerprints={"dataset_profile": sha256_file(profile_path)},
        output_fingerprints=_relative_hashes(workspace, output_paths),
        invariants=invariants,
        status="PASS",
    )
    receipt_path = manifest_dir / "freddie_sflld_2024_m13_common_ml_receipt_v1.json"
    if write_receipt:
        write_json_atomic(receipt_path, receipt.to_dict())

    summary = {
        "rows": full_rows,
        "positives": positives_sum,
        "tree_features": tree_count,
        "linear_features": linear_count,
        "best_model": best_name,
        "best_branch": best_branch,
        "receipt_fingerprint": receipt.receipt_fingerprint,
    }
    return FreddieM13Certification(receipt_path=receipt_path, receipt=receipt, summary=summary)
