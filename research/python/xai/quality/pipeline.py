from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import (
    PROJECT_ROOT,
    XAI_EVIDENCE_MANIFEST_PATH,
    XAI_EVIDENCE_SUMMARY_CSV_PATH,
    XAI_LOCAL_EVIDENCE_JSONL_PATH,
    XAI_QUALITY_REPORT_JSON_PATH,
    validate_run_mode,
)
from ..loaders import load_xai_inputs


BATCH_NAME = "Batch G+ — XAI Evidence Quality Evaluation"
BATCH_SHORT_NAME = "batch_g_plus_xai_evidence_quality_evaluation"

XAI_QUALITY_OUTPUT_DIR = PROJECT_ROOT / "data/reports/xai_quality"
XAI_QUALITY_MANIFEST_PATH = PROJECT_ROOT / "data/manifests/xai_evidence_quality_manifest.json"

XAI_TOPK_COVERAGE_REPORT_PATH = XAI_QUALITY_OUTPUT_DIR / "xai_topk_coverage_report.csv"
XAI_CONCEPT_AGGREGATION_REPORT_PATH = XAI_QUALITY_OUTPUT_DIR / "xai_concept_aggregation_report.csv"
XAI_COMPREHENSIVENESS_REPORT_PATH = XAI_QUALITY_OUTPUT_DIR / "xai_comprehensiveness_report.csv"
XAI_SUFFICIENCY_REPORT_PATH = XAI_QUALITY_OUTPUT_DIR / "xai_sufficiency_report.csv"
XAI_STABILITY_REPORT_PATH = XAI_QUALITY_OUTPUT_DIR / "xai_stability_report.csv"
XAI_RUNTIME_REPORT_PATH = XAI_QUALITY_OUTPUT_DIR / "xai_runtime_report.csv"
XAI_EVIDENCE_QUALITY_SUMMARY_PATH = XAI_QUALITY_OUTPUT_DIR / "xai_evidence_quality_summary.csv"
XAI_EVIDENCE_QUALITY_MARKDOWN_PATH = XAI_QUALITY_OUTPUT_DIR / "xai_evidence_quality_report.md"

X_TRAIN_TREE_PATH = PROJECT_ROOT / "data/processed/model_ready/tree/X_train_tree.parquet"

TOPK_VALUES = [3, 5, 10, 20]
BASELINE_TOPK_VALUES = [5, 10]

MIN_MEAN_TOP10_COVERAGE = 0.50
MAX_ADDITIVITY_ERROR = 1e-2
MAX_CONCEPT_SUM_ERROR = 1e-8
MAX_UNKNOWN_ABS_SHARE = 0.05


def print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_safe(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass

    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    if isinstance(value, bool):
        return bool(value)

    if isinstance(value, int):
        return int(value)

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)

    if isinstance(value, str):
        return value

    return str(value)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain object: {path}")

    return data


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()

            if not text:
                continue

            item = json.loads(text)

            if not isinstance(item, dict):
                raise ValueError(
                    f"JSONL line must be object. path={path}, line={line_number}"
                )

            records.append(item)

    if not records:
        raise ValueError(f"JSONL file has no records: {path}")

    return records


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(json_safe(data), file, ensure_ascii=False, indent=2)


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        file.write(text)


def validate_required_files() -> None:
    required_paths = {
        "xai_local_evidence_jsonl": XAI_LOCAL_EVIDENCE_JSONL_PATH,
        "xai_evidence_summary_csv": XAI_EVIDENCE_SUMMARY_CSV_PATH,
        "xai_quality_report_json": XAI_QUALITY_REPORT_JSON_PATH,
        "xai_evidence_manifest_json": XAI_EVIDENCE_MANIFEST_PATH,
    }

    missing = {
        name: path
        for name, path in required_paths.items()
        if not path.exists()
    }

    if missing:
        lines = "\n".join(f"- {name}: {path}" for name, path in missing.items())
        raise FileNotFoundError(
            "Batch G+ cannot start because Batch G artifacts are missing:\n"
            f"{lines}"
        )


def run_pipeline(
    *,
    run_mode: str,
    skip_model_metrics: bool,
) -> int:
    started_at = time.perf_counter()
    run_mode = validate_run_mode(run_mode)

    XAI_QUALITY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    XAI_QUALITY_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    print_section(BATCH_NAME)
    print("Run mode:", run_mode)
    print("Skip model metrics:", skip_model_metrics)

    print_section("Step 1 - Validate Batch G artifacts")
    validate_required_files()
    print("Batch G artifacts exist.")

    print_section("Step 2 - Load Batch G evidence")
    evidence_records = read_jsonl(XAI_LOCAL_EVIDENCE_JSONL_PATH)
    evidence_summary = pd.read_csv(XAI_EVIDENCE_SUMMARY_CSV_PATH)
    batch_g_quality_report = read_json(XAI_QUALITY_REPORT_JSON_PATH)
    batch_g_manifest = read_json(XAI_EVIDENCE_MANIFEST_PATH)

    print("Evidence records:", len(evidence_records))
    print("Evidence summary shape:", list(evidence_summary.shape))

    if len(evidence_records) != len(evidence_summary):
        raise ValueError(
            "Evidence JSONL record count does not match evidence summary rows. "
            f"{len(evidence_records)} != {len(evidence_summary)}"
        )

    warnings = []
    failed_reasons = []

    topk_rows = []
    concept_rows = []
    accounting_rows = []

    print_section("Step 3 - Compute additivity, top-k coverage, direction balance, concept aggregation")

    for record in evidence_records:
        evidence_id = str(record.get("evidence_id"))
        customer = record.get("customer", {})
        prediction = record.get("prediction", {})
        shap = record.get("shap", {})
        quality = record.get("quality", {})
        local_features = record.get("local_features", [])

        if not isinstance(local_features, list) or not local_features:
            raise ValueError(f"Evidence record has no local_features: {evidence_id}")

        sk_id_curr = customer.get("sk_id_curr")
        case_type = customer.get("case_type")
        row_index = customer.get("row_index")
        y_true = prediction.get("y_true")
        y_proba = float(prediction.get("y_proba"))
        y_pred = prediction.get("y_pred")

        shap_values = [float(item.get("shap_value", 0.0)) for item in local_features]
        abs_values = [abs(value) for value in shap_values]
        total_abs_shap = float(sum(abs_values))
        feature_shap_sum = float(sum(shap_values))

        base_value = float(shap.get("base_value"))
        model_output = float(shap.get("model_output"))
        reconstructed_output = float(shap.get("reconstructed_output"))
        additivity_error = abs(float(shap.get("additivity_error")))
        additivity_pass = bool(
            quality.get("passed_additivity_check", additivity_error <= MAX_ADDITIVITY_ERROR)
        )

        sorted_features = sorted(
            local_features,
            key=lambda item: abs(float(item.get("shap_value", 0.0))),
            reverse=True,
        )

        topk_row = {
            "evidence_id": evidence_id,
            "SK_ID_CURR": sk_id_curr,
            "row_index": row_index,
            "case_type": case_type,
            "y_true": y_true,
            "y_proba": y_proba,
            "y_pred": y_pred,
            "feature_count_available": len(local_features),
            "feature_count_expected": record.get("model", {}).get("feature_count"),
            "base_value": base_value,
            "model_output": model_output,
            "reconstructed_output": reconstructed_output,
            "additivity_error": additivity_error,
            "additivity_error_abs": additivity_error,
            "additivity_pass": additivity_pass,
            "total_abs_shap": total_abs_shap,
        }

        for k in TOPK_VALUES:
            top_features = sorted_features[: min(k, len(sorted_features))]
            top_abs_sum = float(
                sum(abs(float(item.get("shap_value", 0.0))) for item in top_features)
            )
            coverage = None if total_abs_shap == 0 else top_abs_sum / total_abs_shap

            topk_row[f"top{k}_coverage"] = coverage
            topk_row[f"top{k}_abs_shap_sum"] = top_abs_sum
            topk_row[f"top{k}_features"] = "|".join(
                str(item.get("feature_name")) for item in top_features
            )

        positive_sum = float(sum(value for value in shap_values if value > 0))
        negative_sum = float(sum(value for value in shap_values if value < 0))
        positive_abs = float(sum(abs(value) for value in shap_values if value > 0))
        negative_abs = float(sum(abs(value) for value in shap_values if value < 0))
        neutral_count = int(sum(1 for value in shap_values if abs(value) <= 1e-12))

        top_positive_count = int(
            sum(1 for item in sorted_features[:10] if float(item.get("shap_value", 0.0)) > 0)
        )
        top_negative_count = int(
            sum(1 for item in sorted_features[:10] if float(item.get("shap_value", 0.0)) < 0)
        )

        topk_row["positive_shap_sum"] = positive_sum
        topk_row["negative_shap_sum"] = negative_sum
        topk_row["positive_abs_share"] = None if total_abs_shap == 0 else positive_abs / total_abs_shap
        topk_row["negative_abs_share"] = None if total_abs_shap == 0 else negative_abs / total_abs_shap
        topk_row["top_positive_feature_count"] = top_positive_count
        topk_row["top_negative_feature_count"] = top_negative_count
        topk_row["neutral_feature_count"] = neutral_count

        topk_rows.append(topk_row)

        concept_map = {}

        for item in local_features:
            concept = str(item.get("concept") or "unknown_feature_group")
            feature_name = str(item.get("feature_name"))
            shap_value = float(item.get("shap_value", 0.0))
            abs_shap_value = abs(shap_value)

            if concept not in concept_map:
                concept_map[concept] = {
                    "concept_group": concept,
                    "concept_shap_value": 0.0,
                    "concept_abs_shap": 0.0,
                    "feature_count_in_concept": 0,
                    "features": [],
                }

            concept_map[concept]["concept_shap_value"] += shap_value
            concept_map[concept]["concept_abs_shap"] += abs_shap_value
            concept_map[concept]["feature_count_in_concept"] += 1
            concept_map[concept]["features"].append((feature_name, abs_shap_value, shap_value))

        concept_items = list(concept_map.values())
        concept_items = sorted(
            concept_items,
            key=lambda item: float(item["concept_abs_shap"]),
            reverse=True,
        )

        concept_shap_sum = float(
            sum(float(item["concept_shap_value"]) for item in concept_items)
        )
        concept_abs_sum = float(
            sum(abs(float(item["concept_shap_value"])) for item in concept_items)
        )
        concept_feature_abs_sum = float(
            sum(float(item["concept_abs_shap"]) for item in concept_items)
        )
        concept_sum_error = float(feature_shap_sum - concept_shap_sum)
        concept_sum_error_abs = abs(concept_sum_error)
        concept_abs_accounting_gap = float(total_abs_shap - concept_abs_sum)

        unknown_feature_group_count = int(
            sum(
                int(item["feature_count_in_concept"])
                for item in concept_items
                if item["concept_group"] == "unknown_feature_group"
            )
        )

        unknown_feature_group_abs = float(
            sum(
                float(item["concept_abs_shap"])
                for item in concept_items
                if item["concept_group"] == "unknown_feature_group"
            )
        )

        top3_concept_abs = float(
            sum(float(item["concept_abs_shap"]) for item in concept_items[:3])
        )
        concept_coverage_top3 = None if total_abs_shap == 0 else top3_concept_abs / total_abs_shap

        for concept_rank, item in enumerate(concept_items, start=1):
            concept_value = float(item["concept_shap_value"])

            if concept_value > 1e-12:
                direction = "increases_risk"
            elif concept_value < -1e-12:
                direction = "decreases_risk"
            else:
                direction = "neutral"

            top_features = sorted(
                item["features"],
                key=lambda value: value[1],
                reverse=True,
            )[:5]

            concept_rows.append(
                {
                    "evidence_id": evidence_id,
                    "SK_ID_CURR": sk_id_curr,
                    "row_index": row_index,
                    "case_type": case_type,
                    "concept_group": item["concept_group"],
                    "concept_rank": concept_rank,
                    "concept_shap_value": concept_value,
                    "concept_abs_shap": float(item["concept_abs_shap"]),
                    "concept_direction": direction,
                    "feature_count_in_concept": int(item["feature_count_in_concept"]),
                    "top_features_in_concept": "|".join(feature[0] for feature in top_features),
                }
            )

        accounting_rows.append(
            {
                "evidence_id": evidence_id,
                "SK_ID_CURR": sk_id_curr,
                "row_index": row_index,
                "case_type": case_type,
                "feature_shap_sum": feature_shap_sum,
                "concept_shap_sum": concept_shap_sum,
                "concept_sum_error": concept_sum_error,
                "concept_sum_error_abs": concept_sum_error_abs,
                "feature_abs_shap_sum": total_abs_shap,
                "concept_abs_signed_sum": concept_abs_sum,
                "concept_feature_abs_sum": concept_feature_abs_sum,
                "concept_abs_accounting_gap": concept_abs_accounting_gap,
                "top1_concept": concept_items[0]["concept_group"] if concept_items else None,
                "top3_concepts": "|".join(item["concept_group"] for item in concept_items[:3]),
                "concept_coverage_top3": concept_coverage_top3,
                "unknown_feature_group_count": unknown_feature_group_count,
                "unknown_feature_group_abs_share": (
                    None if total_abs_shap == 0 else unknown_feature_group_abs / total_abs_shap
                ),
            }
        )

    topk_report = pd.DataFrame(topk_rows)
    concept_report = pd.DataFrame(concept_rows)
    accounting_report = pd.DataFrame(accounting_rows)

    topk_report.to_csv(XAI_TOPK_COVERAGE_REPORT_PATH, index=False)
    concept_report.to_csv(XAI_CONCEPT_AGGREGATION_REPORT_PATH, index=False)

    print("Top-k coverage report:", XAI_TOPK_COVERAGE_REPORT_PATH)
    print("Concept aggregation report:", XAI_CONCEPT_AGGREGATION_REPORT_PATH)

    print_section("Step 4 - Compute comprehensiveness and sufficiency")

    comprehensiveness_rows = []
    sufficiency_rows = []
    model_metrics_status = "completed"
    model_metrics_reason = None

    if skip_model_metrics:
        model_metrics_status = "skipped"
        model_metrics_reason = "User requested --skip-model-metrics."

    elif not X_TRAIN_TREE_PATH.exists():
        model_metrics_status = "skipped"
        model_metrics_reason = f"Training model-ready file does not exist: {X_TRAIN_TREE_PATH}"

    if model_metrics_status == "completed":
        inputs = load_xai_inputs(run_mode=run_mode)
        X_train = pd.read_parquet(X_TRAIN_TREE_PATH)
        X_train = X_train.loc[:, inputs.model_bundle.feature_columns]
        baseline = X_train.median(numeric_only=True)
        baseline = baseline.reindex(inputs.model_bundle.feature_columns).fillna(0.0)

        estimator = inputs.model_bundle.estimator
        feature_columns = inputs.model_bundle.feature_columns

        for record in evidence_records:
            evidence_id = str(record.get("evidence_id"))
            customer = record.get("customer", {})
            prediction = record.get("prediction", {})
            local_features = record.get("local_features", [])

            row_index = int(customer.get("row_index"))
            sk_id_curr = customer.get("sk_id_curr")
            case_type = customer.get("case_type")
            y_proba_original = float(prediction.get("y_proba"))

            sorted_features = sorted(
                local_features,
                key=lambda item: abs(float(item.get("shap_value", 0.0))),
                reverse=True,
            )

            x_original = inputs.X.iloc[[row_index]].loc[:, feature_columns].copy()

            comp_row = {
                "evidence_id": evidence_id,
                "SK_ID_CURR": sk_id_curr,
                "row_index": row_index,
                "case_type": case_type,
                "status": "completed",
                "y_proba_original": y_proba_original,
                "baseline_source": str(X_TRAIN_TREE_PATH),
                "replacement_strategy": "median_baseline_top_abs_shap_features",
            }

            suff_row = {
                "evidence_id": evidence_id,
                "SK_ID_CURR": sk_id_curr,
                "row_index": row_index,
                "case_type": case_type,
                "status": "completed",
                "y_proba_original": y_proba_original,
                "baseline_source": str(X_TRAIN_TREE_PATH),
                "retention_strategy": "median_baseline_keep_top_abs_shap_features",
            }

            for k in BASELINE_TOPK_VALUES:
                feature_names = [
                    str(item.get("feature_name"))
                    for item in sorted_features[: min(k, len(sorted_features))]
                ]

                x_removed = x_original.copy()

                for feature_name in feature_names:
                    if feature_name in x_removed.columns:
                        x_removed.loc[:, feature_name] = baseline[feature_name]

                removed_proba = float(estimator.predict_proba(x_removed)[:, 1][0])
                comp_row[f"y_proba_removed_top{k}"] = removed_proba
                comp_row[f"comprehensiveness_top{k}"] = y_proba_original - removed_proba
                comp_row[f"removed_features_top{k}"] = "|".join(feature_names)

                x_only = pd.DataFrame(
                    [baseline.to_dict()],
                    columns=feature_columns,
                )

                for feature_name in feature_names:
                    if feature_name in x_only.columns:
                        x_only.loc[:, feature_name] = x_original.iloc[0][feature_name]

                only_proba = float(estimator.predict_proba(x_only)[:, 1][0])
                suff_row[f"y_proba_only_top{k}"] = only_proba
                suff_row[f"sufficiency_drop_top{k}"] = y_proba_original - only_proba
                suff_row[f"kept_features_top{k}"] = "|".join(feature_names)

            comprehensiveness_rows.append(comp_row)
            sufficiency_rows.append(suff_row)

    else:
        comprehensiveness_rows.append(
            {
                "status": "skipped",
                "reason": model_metrics_reason,
                "next_step": "Provide X_train_tree.parquet and run without --skip-model-metrics.",
            }
        )
        sufficiency_rows.append(
            {
                "status": "skipped",
                "reason": model_metrics_reason,
                "next_step": "Provide X_train_tree.parquet and run without --skip-model-metrics.",
            }
        )

    comprehensiveness_report = pd.DataFrame(comprehensiveness_rows)
    sufficiency_report = pd.DataFrame(sufficiency_rows)

    comprehensiveness_report.to_csv(XAI_COMPREHENSIVENESS_REPORT_PATH, index=False)
    sufficiency_report.to_csv(XAI_SUFFICIENCY_REPORT_PATH, index=False)

    print("Comprehensiveness report:", XAI_COMPREHENSIVENESS_REPORT_PATH)
    print("Sufficiency report:", XAI_SUFFICIENCY_REPORT_PATH)

    print_section("Step 5 - Stability report")

    stability_report = pd.DataFrame(
        [
            {
                "status": "skipped",
                "reason": (
                    "Current Batch G artifact contains one SHAP run only. "
                    "Stability needs repeated SHAP runs with different background seeds."
                ),
                "next_step": (
                    "Add optional repeated SHAP generation with random_state 42, 43, 44 "
                    "and compare top-k Jaccard, rank correlation, and sign agreement."
                ),
            }
        ]
    )

    stability_report.to_csv(XAI_STABILITY_REPORT_PATH, index=False)
    print("Stability report:", XAI_STABILITY_REPORT_PATH)

    print_section("Step 6 - Build quality summary, runtime, markdown, manifest")

    quality_summary = topk_report.merge(
        accounting_report,
        on=["evidence_id", "SK_ID_CURR", "row_index", "case_type"],
        how="left",
    )

    if model_metrics_status == "completed":
        quality_summary = quality_summary.merge(
            comprehensiveness_report[
                [
                    "evidence_id",
                    "comprehensiveness_top5",
                    "comprehensiveness_top10",
                    "y_proba_removed_top5",
                    "y_proba_removed_top10",
                ]
            ],
            on="evidence_id",
            how="left",
        )

        quality_summary = quality_summary.merge(
            sufficiency_report[
                [
                    "evidence_id",
                    "sufficiency_drop_top5",
                    "sufficiency_drop_top10",
                    "y_proba_only_top5",
                    "y_proba_only_top10",
                ]
            ],
            on="evidence_id",
            how="left",
        )

    else:
        quality_summary["comprehensiveness_top5"] = np.nan
        quality_summary["comprehensiveness_top10"] = np.nan
        quality_summary["sufficiency_drop_top5"] = np.nan
        quality_summary["sufficiency_drop_top10"] = np.nan

    quality_summary["stability_score"] = np.nan
    quality_summary["stability_status"] = "skipped"

    quality_summary.to_csv(XAI_EVIDENCE_QUALITY_SUMMARY_PATH, index=False)

    runtime_seconds = time.perf_counter() - started_at
    case_count = int(len(evidence_records))
    feature_count = int(topk_report["feature_count_available"].max())

    runtime_report = pd.DataFrame(
        [
            {
                "batch_name": BATCH_NAME,
                "case_count": case_count,
                "feature_count": feature_count,
                "runtime_total_seconds": runtime_seconds,
                "runtime_per_case_ms": runtime_seconds / max(case_count, 1) * 1000.0,
                "runtime_per_feature_ms": runtime_seconds / max(case_count * feature_count, 1) * 1000.0,
                "model_metrics_status": model_metrics_status,
            }
        ]
    )

    runtime_report.to_csv(XAI_RUNTIME_REPORT_PATH, index=False)

    mean_additivity_error = float(topk_report["additivity_error_abs"].mean())
    max_additivity_error = float(topk_report["additivity_error_abs"].max())
    passed_additivity_count = int(topk_report["additivity_pass"].astype(bool).sum())
    failed_additivity_count = int((~topk_report["additivity_pass"].astype(bool)).sum())

    mean_top3 = float(topk_report["top3_coverage"].mean())
    median_top3 = float(topk_report["top3_coverage"].median())
    mean_top5 = float(topk_report["top5_coverage"].mean())
    median_top5 = float(topk_report["top5_coverage"].median())
    mean_top10 = float(topk_report["top10_coverage"].mean())
    median_top10 = float(topk_report["top10_coverage"].median())
    mean_top20 = float(topk_report["top20_coverage"].mean())
    median_top20 = float(topk_report["top20_coverage"].median())

    max_concept_sum_error = float(accounting_report["concept_sum_error_abs"].max())
    mean_concept_sum_error = float(accounting_report["concept_sum_error_abs"].mean())
    mean_unknown_abs_share = float(
        accounting_report["unknown_feature_group_abs_share"].fillna(0.0).mean()
    )

    top_concepts = (
        concept_report.groupby("concept_group", as_index=False)["concept_abs_shap"]
        .sum()
        .sort_values("concept_abs_shap", ascending=False)
        .head(10)
    )

    comp_top10_mean = None
    suff_top10_mean = None

    if model_metrics_status == "completed":
        comp_top10_mean = float(comprehensiveness_report["comprehensiveness_top10"].mean())
        suff_top10_mean = float(sufficiency_report["sufficiency_drop_top10"].mean())

    if failed_additivity_count > 0:
        status = "FAILED"
        failed_reasons.append("One or more evidence records failed additivity check.")
    else:
        status = "PASSED"

    if mean_top10 < MIN_MEAN_TOP10_COVERAGE:
        warnings.append(
            f"Mean top10 coverage is below threshold: {mean_top10:.4f} < {MIN_MEAN_TOP10_COVERAGE:.4f}"
        )

    if max_concept_sum_error > MAX_CONCEPT_SUM_ERROR:
        warnings.append(
            f"Concept accounting error is above threshold: {max_concept_sum_error:.12f}"
        )

    if mean_unknown_abs_share > MAX_UNKNOWN_ABS_SHARE:
        warnings.append(
            f"Unknown feature group abs share is above threshold: {mean_unknown_abs_share:.4f}"
        )

    if model_metrics_status == "skipped":
        warnings.append(
            f"Comprehensiveness and sufficiency were skipped: {model_metrics_reason}"
        )

    if status == "PASSED" and warnings:
        status = "PASSED_WITH_WARN"

    aggregate_summary = {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "status": status,
        "created_at": utc_now_iso(),
        "run_mode": run_mode,
        "case_count": case_count,
        "feature_count": feature_count,
        "input_scope": "pilot_selected_cases_from_batch_g",
        "additivity": {
            "mean_additivity_error": mean_additivity_error,
            "max_additivity_error": max_additivity_error,
            "passed_additivity_count": passed_additivity_count,
            "failed_additivity_count": failed_additivity_count,
        },
        "topk_coverage": {
            "mean_top3_coverage": mean_top3,
            "median_top3_coverage": median_top3,
            "mean_top5_coverage": mean_top5,
            "median_top5_coverage": median_top5,
            "mean_top10_coverage": mean_top10,
            "median_top10_coverage": median_top10,
            "mean_top20_coverage": mean_top20,
            "median_top20_coverage": median_top20,
        },
        "concept_accounting": {
            "mean_concept_sum_error": mean_concept_sum_error,
            "max_concept_sum_error": max_concept_sum_error,
            "mean_unknown_feature_group_abs_share": mean_unknown_abs_share,
        },
        "comprehensiveness": {
            "status": model_metrics_status,
            "reason": model_metrics_reason,
            "mean_comprehensiveness_top10": comp_top10_mean,
        },
        "sufficiency": {
            "status": model_metrics_status,
            "reason": model_metrics_reason,
            "mean_sufficiency_drop_top10": suff_top10_mean,
        },
        "stability": {
            "status": "skipped",
            "reason": "Repeated SHAP runs are not generated in this Batch G+ version.",
            "stability_score": None,
        },
        "runtime": {
            "runtime_total_seconds": runtime_seconds,
            "runtime_per_case_ms": runtime_seconds / max(case_count, 1) * 1000.0,
            "runtime_per_feature_ms": runtime_seconds / max(case_count * feature_count, 1) * 1000.0,
        },
        "warnings": warnings,
        "failed_reasons": failed_reasons,
    }

    topk_table_md = pd.DataFrame(
        [
            {"k": 3, "mean_coverage": mean_top3, "median_coverage": median_top3},
            {"k": 5, "mean_coverage": mean_top5, "median_coverage": median_top5},
            {"k": 10, "mean_coverage": mean_top10, "median_coverage": median_top10},
            {"k": 20, "mean_coverage": mean_top20, "median_coverage": median_top20},
        ]
    ).to_markdown(index=False)

    additivity_table_md = pd.DataFrame(
        [
            {
                "mean_error": mean_additivity_error,
                "max_error": max_additivity_error,
                "passed_count": passed_additivity_count,
                "failed_count": failed_additivity_count,
            }
        ]
    ).to_markdown(index=False)

    concept_table_md = top_concepts.to_markdown(index=False)
    runtime_table_md = runtime_report.to_markdown(index=False)

    limitations = [
        "Current scope uses Batch G selected pilot cases.",
        "Comprehensiveness and sufficiency use median baseline replacement on model-ready features.",
        "Top-k comprehensiveness currently uses absolute SHAP ranking, not actionability-aware feature filtering.",
        "Stability is skipped because Batch G currently stores one SHAP run only.",
    ]

    markdown_text = f"""# Batch G+ — XAI Evidence Quality Evaluation

## 1. Purpose

Đánh giá chất lượng SHAP evidence trước khi đưa vào Explanation IR v2 và LLM.

## 2. Inputs

- `{XAI_LOCAL_EVIDENCE_JSONL_PATH}`
- `{XAI_EVIDENCE_SUMMARY_CSV_PATH}`
- `{XAI_QUALITY_REPORT_JSON_PATH}`
- `{XAI_EVIDENCE_MANIFEST_PATH}`
- `{X_TRAIN_TREE_PATH}`

## 3. Evaluation Scope

- Scope: pilot/evaluation mode
- Run mode: `{run_mode}`
- Case count: `{case_count}`
- Feature count available in evidence: `{feature_count}`
- Batch G status: `{batch_g_quality_report.get("status")}`

## 4. Additivity Summary

{additivity_table_md}

## 5. Top-k Coverage

{topk_table_md}

## 6. Concept-level Aggregation

Top concept groups by total absolute SHAP contribution:

{concept_table_md}

Concept accounting:

- Mean concept sum error: `{mean_concept_sum_error}`
- Max concept sum error: `{max_concept_sum_error}`
- Mean unknown feature group abs share: `{mean_unknown_abs_share}`

## 7. Comprehensiveness

Status: `{model_metrics_status}`

Reason: `{model_metrics_reason}`

Mean comprehensiveness top10: `{comp_top10_mean}`

## 8. Sufficiency

Status: `{model_metrics_status}`

Reason: `{model_metrics_reason}`

Mean sufficiency drop top10: `{suff_top10_mean}`

## 9. Stability

Status: `skipped`

Reason: Current Batch G artifact contains one SHAP run only. Stability requires repeated SHAP runs with multiple random seeds/background samples.

## 10. Runtime

{runtime_table_md}

## 11. Limitations

{chr(10).join("- " + item for item in limitations)}

## 12. Next Step

Dùng kết quả Batch G+ để nâng cấp:

- Explanation IR v2
- Evidence Exposure Controller S0-S5
- Multi-LLM Explanation Runner
- Claim-level Faithfulness Evaluation

Final Status

{status}

Warnings:

{chr(10).join("- " + item for item in warnings) if warnings else "- None"}
"""

    write_markdown(XAI_EVIDENCE_QUALITY_MARKDOWN_PATH, markdown_text)

    manifest = {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "status": status,
        "created_at": utc_now_iso(),
        "run_mode": run_mode,
        "purpose": (
            "Evaluate SHAP evidence quality before Explanation IR v2 and LLM grounding."
        ),
        "inputs": {
            "xai_local_evidence_jsonl": str(XAI_LOCAL_EVIDENCE_JSONL_PATH),
            "xai_evidence_summary_csv": str(XAI_EVIDENCE_SUMMARY_CSV_PATH),
            "xai_quality_report_json": str(XAI_QUALITY_REPORT_JSON_PATH),
            "xai_evidence_manifest_json": str(XAI_EVIDENCE_MANIFEST_PATH),
            "x_train_tree_parquet": str(X_TRAIN_TREE_PATH),
        },
        "outputs": {
            "xai_topk_coverage_report_csv": str(XAI_TOPK_COVERAGE_REPORT_PATH),
            "xai_concept_aggregation_report_csv": str(XAI_CONCEPT_AGGREGATION_REPORT_PATH),
            "xai_comprehensiveness_report_csv": str(XAI_COMPREHENSIVENESS_REPORT_PATH),
            "xai_sufficiency_report_csv": str(XAI_SUFFICIENCY_REPORT_PATH),
            "xai_stability_report_csv": str(XAI_STABILITY_REPORT_PATH),
            "xai_runtime_report_csv": str(XAI_RUNTIME_REPORT_PATH),
            "xai_evidence_quality_summary_csv": str(XAI_EVIDENCE_QUALITY_SUMMARY_PATH),
            "xai_evidence_quality_report_md": str(XAI_EVIDENCE_QUALITY_MARKDOWN_PATH),
            "xai_evidence_quality_manifest_json": str(XAI_QUALITY_MANIFEST_PATH),
        },
        "batch_g_reference": {
            "status": batch_g_quality_report.get("status"),
            "manifest_status": batch_g_manifest.get("status"),
            "model": batch_g_quality_report.get("model"),
            "xai_method": batch_g_manifest.get("xai_method"),
        },
        "quality_gates": {
            "max_additivity_error_allowed": MAX_ADDITIVITY_ERROR,
            "min_mean_top10_coverage": MIN_MEAN_TOP10_COVERAGE,
            "max_concept_sum_error": MAX_CONCEPT_SUM_ERROR,
            "max_unknown_abs_share": MAX_UNKNOWN_ABS_SHARE,
        },
        "aggregate_summary": aggregate_summary,
    }

    write_json(XAI_QUALITY_MANIFEST_PATH, manifest)

    print("Quality summary:", XAI_EVIDENCE_QUALITY_SUMMARY_PATH)
    print("Runtime report:", XAI_RUNTIME_REPORT_PATH)
    print("Markdown report:", XAI_EVIDENCE_QUALITY_MARKDOWN_PATH)
    print("Manifest:", XAI_QUALITY_MANIFEST_PATH)

    print_section("Batch G+ completed")
    print("Status:", status)
    print("Case count:", case_count)
    print("Feature count:", feature_count)
    print("Mean top10 coverage:", round(mean_top10, 6))
    print("Max additivity error:", max_additivity_error)
    print("Max concept sum error:", max_concept_sum_error)
    print("Model metrics status:", model_metrics_status)
    print("Runtime seconds:", round(runtime_seconds, 2))
    print("Warnings:", warnings)

    if status == "FAILED":
        return 1

    return 0
