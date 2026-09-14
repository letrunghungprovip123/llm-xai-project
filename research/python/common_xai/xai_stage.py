from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..common_ml.split import CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN
from ..xai.evidence_builder import (
    build_feature_registry_lookup,
    build_local_features_for_case,
)
from ..xai.evidence_schema import (
    build_evidence_quality,
    build_prediction_evidence,
    build_shap_evidence,
    dataclass_to_json_safe_dict,
)
from ..xai.loaders import XAIInputs, XAIModelBundle, load_model_bundle
from ..xai.model_capabilities import resolve_xai_explainer_plan
from ..xai.shap_explainer import compute_local_shap_values
from .context import CommonXAIRunContext

CASE_GROUPS = (
    "top_high_risk",
    "low_risk",
    "true_positive",
    "false_positive",
    "false_negative",
    "near_threshold",
)
DEFAULT_CASES_PER_GROUP = 20


@dataclass(frozen=True)
class CommonXAIResult:
    manifest_path: Path
    evidence_path: Path
    quality_path: Path
    selected_cases_path: Path
    case_count: int
    feature_count: int
    explainer_type: str
    failed_additivity_count: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _read_yaml(path: Path) -> dict[str, Any]:
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"YAML registry must contain an object: {path}")
    return payload


def _branch_paths(ctx: CommonXAIRunContext, branch: str) -> tuple[Path, Path, Path, Path]:
    if branch not in {"tree", "linear"}:
        raise ValueError(f"Unsupported selected-model branch: {branch!r}")
    suffix = branch
    directory = ctx.source_paths.processed_dir / "model_ready" / branch
    return (
        directory / f"X_train_{suffix}.parquet",
        directory / f"X_test_{suffix}.parquet",
        directory / "y_test.parquet",
        ctx.source_paths.registry_dir / f"preprocessed_feature_mapping_{branch}.json",
    )


def _load_inputs(ctx: CommonXAIRunContext) -> tuple[XAIInputs, pd.DataFrame, pd.DataFrame]:
    model_path = ctx.source_paths.artifact_dir / "models" / "best_model.joblib"
    model_bundle = load_model_bundle(model_path, enforce_legacy_expectations=False)
    X_train_path, X_test_path, y_test_path, mapping_path = _branch_paths(ctx, model_bundle.dataset_branch)
    required = [X_train_path, X_test_path, y_test_path, mapping_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Selected-model XAI inputs are missing: " + ", ".join(missing))

    X_train = pd.read_parquet(X_train_path)
    X_test = pd.read_parquet(X_test_path)
    y_test = pd.read_parquet(y_test_path)
    predictions = pd.read_csv(ctx.source_paths.report_dir / "model_predictions_test.csv")
    feature_mapping = _read_json(mapping_path)
    feature_registry = pd.read_csv(ctx.source_paths.registry_dir / "feature_registry.csv")
    concept_registry = _read_yaml(ctx.source_paths.registry_dir / "concept_registry.yaml")
    model_registry = _read_json(ctx.source_paths.registry_dir / "model_registry.json")

    if list(X_test.columns) != model_bundle.feature_columns:
        raise ValueError("Selected-model X_test columns do not match model bundle feature order")
    if list(X_train.columns) != model_bundle.feature_columns:
        raise ValueError("Selected-model X_train columns do not match model bundle feature order")
    if len(X_test) != len(y_test) or len(X_test) != len(predictions):
        raise ValueError("X_test/y_test/predictions row counts differ")
    for column in (CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN):
        if column not in y_test.columns or column not in predictions.columns:
            raise ValueError(f"Dataset-neutral XAI identity column missing: {column}")
    if y_test[CASE_ID_COLUMN].astype(str).tolist() != predictions[CASE_ID_COLUMN].astype(str).tolist():
        raise ValueError("Predictions are not aligned with y_test canonical case IDs")
    target_column = model_bundle.bundle.get("target_column")
    if not target_column or target_column not in y_test.columns:
        raise ValueError("Selected model bundle target_column is missing from y_test")
    if y_test[target_column].astype(int).tolist() != predictions["y_true"].astype(int).tolist():
        raise ValueError("Predictions y_true values are not aligned with y_test")

    inputs = XAIInputs(
        run_mode="evaluation",
        has_ground_truth=True,
        model_bundle=model_bundle,
        model_registry=model_registry,
        X=X_test,
        y=None,
        predictions=predictions,
        tree_feature_columns=list(model_bundle.feature_columns),
        feature_mapping=feature_mapping,
        feature_registry=feature_registry,
        concept_registry=concept_registry,
    )
    return inputs, X_train, y_test


def _with_identity_sort_key(predictions: pd.DataFrame) -> pd.DataFrame:
    frame = predictions.copy()
    numeric = pd.to_numeric(frame[SOURCE_ENTITY_ID_COLUMN], errors="coerce")
    if numeric.notna().all():
        frame["_identity_sort_kind"] = 0
        frame["_identity_sort_numeric"] = numeric.astype(float)
        frame["_identity_sort_text"] = ""
    else:
        frame["_identity_sort_kind"] = 1
        frame["_identity_sort_numeric"] = 0.0
        frame["_identity_sort_text"] = frame[SOURCE_ENTITY_ID_COLUMN].astype(str)
    return frame


def _case_candidates(predictions: pd.DataFrame, case_type: str) -> pd.DataFrame:
    frame = _with_identity_sort_key(predictions)
    tie = ["_identity_sort_kind", "_identity_sort_numeric", "_identity_sort_text"]
    if case_type == "top_high_risk":
        return frame.sort_values(["y_proba", *tie], ascending=[False, True, True, True])
    if case_type == "low_risk":
        return frame.sort_values(["y_proba", *tie], ascending=[True, True, True, True])
    if case_type == "near_threshold":
        return frame.sort_values(["abs_distance_to_threshold", *tie], ascending=[True, True, True, True])
    if case_type == "true_positive":
        frame = frame[(frame.y_true == 1) & (frame.y_pred == 1)]
        return frame.sort_values(["y_proba", *tie], ascending=[False, True, True, True])
    if case_type == "false_positive":
        frame = frame[(frame.y_true == 0) & (frame.y_pred == 1)]
        return frame.sort_values(["y_proba", *tie], ascending=[False, True, True, True])
    if case_type == "false_negative":
        frame = frame[(frame.y_true == 1) & (frame.y_pred == 0)]
        return frame.sort_values(["y_proba", *tie], ascending=[False, True, True, True])
    raise ValueError(f"Unsupported case type: {case_type}")


def select_common_cases(
    *,
    ctx: CommonXAIRunContext,
    model_bundle: XAIModelBundle,
    predictions: pd.DataFrame,
    cases_per_group: int,
) -> tuple[pd.DataFrame, dict[str, int], list[str]]:
    frame = predictions.copy()
    label_column = "y_pred_default_threshold_0_5" if "y_pred_default_threshold_0_5" in frame.columns else "y_pred"
    required = [CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN, "row_index", "y_true", "y_proba", label_column]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Common XAI predictions missing required columns: {missing}")
    frame[CASE_ID_COLUMN] = frame[CASE_ID_COLUMN].astype(str)
    frame[SOURCE_ENTITY_ID_COLUMN] = frame[SOURCE_ENTITY_ID_COLUMN].astype(str)
    frame["row_index"] = frame["row_index"].astype(int)
    frame["y_true"] = frame["y_true"].astype(int)
    frame["y_proba"] = frame["y_proba"].astype(float)
    frame["y_pred"] = frame[label_column].astype(int)
    threshold = float(frame["threshold"].dropna().iloc[0]) if "threshold" in frame.columns else float(model_bundle.default_threshold)
    frame["threshold"] = threshold
    frame["abs_distance_to_threshold"] = (frame["y_proba"] - threshold).abs()

    selected_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    warnings: list[str] = []
    for case_type in CASE_GROUPS:
        count = 0
        for _, row in _case_candidates(frame, case_type).iterrows():
            case_id = str(row[CASE_ID_COLUMN])
            if case_id in selected_ids:
                continue
            selected_ids.add(case_id)
            item = row.to_dict()
            count += 1
            item["case_type"] = case_type
            item["selection_rank"] = count
            rows.append(item)
            if count >= cases_per_group:
                break
        counts[case_type] = count
        if count < cases_per_group:
            warnings.append(f"Case group {case_type!r} selected {count}/{cases_per_group} cases")

    selected = pd.DataFrame(rows)
    if selected.empty:
        raise ValueError("No common XAI cases could be selected")
    selected["model_name"] = model_bundle.model_name
    selected["model_version"] = model_bundle.model_version
    selected["model_family"] = model_bundle.model_family
    selected["dataset_branch"] = model_bundle.dataset_branch
    selected["feature_count"] = model_bundle.feature_count
    selected["run_mode"] = "evaluation"
    selected["has_ground_truth"] = True
    selected["evidence_id"] = selected.apply(
        lambda row: (
            f"xai::{ctx.profile.dataset_id}::{ctx.experiment_id}::"
            f"{model_bundle.model_name}::{model_bundle.model_version}::"
            f"{row[CASE_ID_COLUMN]}::{row['case_type']}"
        ),
        axis=1,
    )
    if selected["evidence_id"].duplicated().any() or selected[CASE_ID_COLUMN].duplicated().any():
        raise ValueError("Common XAI case/evidence identity collision detected")
    return selected.reset_index(drop=True), counts, warnings


def _build_evidence_records(
    *,
    ctx: CommonXAIRunContext,
    inputs: XAIInputs,
    shap_result: Any,
) -> list[dict[str, Any]]:
    lookup = build_feature_registry_lookup(inputs.feature_registry)
    records: list[dict[str, Any]] = []
    top_k = inputs.model_bundle.feature_count
    for position in range(len(shap_result.selected_cases)):
        case = shap_result.selected_cases.iloc[position]
        X_case = shap_result.X_cases.iloc[position]
        shap_values = shap_result.shap_values[position]
        local_features, mapping_missing = build_local_features_for_case(
            X_case=X_case,
            shap_values_for_case=shap_values,
            feature_names=shap_result.feature_names,
            feature_mapping=inputs.feature_mapping,
            feature_registry_lookup=lookup,
            top_k=top_k,
        )
        prediction = build_prediction_evidence(
            y_true=int(case["y_true"]),
            y_proba=float(case["y_proba"]),
            y_pred=int(case["y_pred"]),
            threshold=float(case["threshold"]),
        )
        shap = build_shap_evidence(
            base_value=float(shap_result.base_values[position]),
            model_output=float(shap_result.model_outputs[position]),
            shap_values_for_case=shap_values.tolist(),
            additivity_error=float(shap_result.additivity_errors[position]),
            output_space=shap_result.output_space,
            xai_method="SHAP",
            explainer_type=shap_result.explainer_type,
        )
        quality = build_evidence_quality(
            local_features=local_features,
            top_k=top_k,
            feature_count=inputs.model_bundle.feature_count,
            mapping_missing_count=mapping_missing,
            passed_additivity_check=bool(shap_result.passed_additivity_check[position]),
            additivity_tolerance=1e-2,
        )
        records.append(
            {
                "evidence_id": str(case["evidence_id"]),
                "created_at": _utc_now(),
                "model": {
                    "model_name": inputs.model_bundle.model_name,
                    "model_version": inputs.model_bundle.model_version,
                    "model_family": inputs.model_bundle.model_family,
                    "dataset_branch": inputs.model_bundle.dataset_branch,
                    "feature_count": inputs.model_bundle.feature_count,
                },
                "case": {
                    "case_id": str(case[CASE_ID_COLUMN]),
                    "source_entity_id": str(case[SOURCE_ENTITY_ID_COLUMN]),
                    "entity_type": ctx.profile.entity.entity_type,
                    "row_index": int(case["row_index"]),
                    "case_type": str(case["case_type"]),
                    "selection_rank": int(case["selection_rank"]),
                },
                "prediction": dataclass_to_json_safe_dict(prediction),
                "shap": dataclass_to_json_safe_dict(shap),
                "local_features": [dataclass_to_json_safe_dict(item) for item in local_features],
                "quality": dataclass_to_json_safe_dict(quality),
                "metadata": {
                    **ctx.provenance(),
                    "case_id": str(case[CASE_ID_COLUMN]),
                    "source_entity_id": str(case[SOURCE_ENTITY_ID_COLUMN]),
                    "entity_type": ctx.profile.entity.entity_type,
                    "row_index": int(case["row_index"]),
                    "case_type": str(case["case_type"]),
                    "selection_rank": int(case["selection_rank"]),
                    "source": "common_xai_v1",
                },
            }
        )
    return records


def _quality_for_records(
    *,
    inputs: XAIInputs,
    X_train: pd.DataFrame,
    records: list[dict[str, Any]],
    selected_cases: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    estimator = inputs.model_bundle.estimator
    feature_columns = inputs.model_bundle.feature_columns
    baseline = X_train.loc[:, feature_columns].median(numeric_only=True).reindex(feature_columns).fillna(0.0)
    quality_rows: list[dict[str, Any]] = []
    concept_rows: list[dict[str, Any]] = []
    for record, (_, case) in zip(records, selected_cases.iterrows()):
        features = sorted(record["local_features"], key=lambda item: abs(float(item["shap_value"])), reverse=True)
        shap_values = np.asarray([float(item["shap_value"]) for item in features], dtype=float)
        abs_values = np.abs(shap_values)
        total_abs = float(abs_values.sum())
        row: dict[str, Any] = {
            "evidence_id": record["evidence_id"],
            "case_id": record["case"]["case_id"],
            "row_index": record["case"]["row_index"],
            "case_type": record["case"]["case_type"],
            "additivity_error": float(record["shap"]["additivity_error"]),
            "additivity_error_abs": abs(float(record["shap"]["additivity_error"])),
            "additivity_pass": bool(record["quality"]["passed_additivity_check"]),
            "total_abs_shap": total_abs,
        }
        for k in (3, 5, 10, 20):
            top_abs = float(abs_values[: min(k, len(abs_values))].sum())
            row[f"top{k}_coverage"] = None if total_abs <= 0 else top_abs / total_abs
        positive = shap_values[shap_values > 0]
        negative = shap_values[shap_values < 0]
        row["positive_shap_sum"] = float(positive.sum()) if positive.size else 0.0
        row["negative_shap_sum"] = float(negative.sum()) if negative.size else 0.0
        row["positive_abs_share"] = None if total_abs <= 0 else float(np.abs(positive).sum()) / total_abs
        row["negative_abs_share"] = None if total_abs <= 0 else float(np.abs(negative).sum()) / total_abs
        row["top_positive_feature_count"] = sum(1 for item in features[:10] if float(item["shap_value"]) > 0)
        row["top_negative_feature_count"] = sum(1 for item in features[:10] if float(item["shap_value"]) < 0)
        row["neutral_feature_count"] = sum(1 for item in features if abs(float(item["shap_value"])) <= 1e-12)

        concept_map: dict[str, dict[str, Any]] = {}
        for item in features:
            concept = str(item.get("concept") or "unknown_feature_group")
            bucket = concept_map.setdefault(concept, {"sum": 0.0, "abs": 0.0, "features": []})
            value = float(item["shap_value"])
            bucket["sum"] += value
            bucket["abs"] += abs(value)
            bucket["features"].append(str(item.get("display_name") or item.get("feature_name")))
        ranked = sorted(concept_map.items(), key=lambda pair: pair[1]["abs"], reverse=True)
        for rank, (concept, values) in enumerate(ranked, start=1):
            concept_rows.append(
                {
                    "evidence_id": record["evidence_id"],
                    "concept_group": concept,
                    "concept_rank": rank,
                    "concept_shap_value": values["sum"],
                    "concept_abs_shap": values["abs"],
                    "concept_direction": "increases_risk" if values["sum"] > 1e-12 else "decreases_risk" if values["sum"] < -1e-12 else "neutral",
                    "feature_count_in_concept": len(values["features"]),
                    "top_features_in_concept": "|".join(values["features"][:5]),
                }
            )
        concept_sum = float(sum(values["sum"] for values in concept_map.values()))
        feature_sum = float(shap_values.sum())
        row["concept_sum_error"] = feature_sum - concept_sum
        row["concept_sum_error_abs"] = abs(feature_sum - concept_sum)
        unknown = concept_map.get("unknown_feature_group", {"abs": 0.0, "features": []})
        row["unknown_feature_group_count"] = len(unknown["features"])
        row["unknown_feature_group_abs_share"] = 0.0 if total_abs <= 0 else float(unknown["abs"]) / total_abs
        row["concept_coverage_top3"] = 0.0 if total_abs <= 0 else sum(values["abs"] for _, values in ranked[:3]) / total_abs
        row["top1_concept"] = ranked[0][0] if ranked else None
        row["top3_concepts"] = "|".join(name for name, _ in ranked[:3])

        x_original = inputs.X.iloc[[int(case["row_index"])]].loc[:, feature_columns].copy()
        original_proba = float(case["y_proba"])
        for k in (5, 10):
            names = [str(item["feature_name"]) for item in features[: min(k, len(features))]]
            removed = x_original.copy()
            for name in names:
                removed.loc[:, name] = baseline[name]
            removed_proba = float(estimator.predict_proba(removed)[:, 1][0])
            only = pd.DataFrame([baseline.to_dict()], columns=feature_columns)
            for name in names:
                only.loc[:, name] = x_original.iloc[0][name]
            only_proba = float(estimator.predict_proba(only)[:, 1][0])
            row[f"comprehensiveness_top{k}"] = original_proba - removed_proba
            row[f"sufficiency_drop_top{k}"] = original_proba - only_proba
        row["stability_status"] = "skipped"
        row["stability_score"] = None
        quality_rows.append(row)
    return pd.DataFrame(quality_rows), concept_rows


def run_common_xai(ctx: CommonXAIRunContext, *, cases_per_group: int = DEFAULT_CASES_PER_GROUP) -> CommonXAIResult:
    if not ctx.profile.capabilities.supports_feature_level_xai:
        raise ValueError("DatasetProfile declares supports_feature_level_xai=false")
    if not ctx.profile.capabilities.supports_case_strata:
        raise ValueError("DatasetProfile declares supports_case_strata=false")
    if not ctx.profile.capabilities.supports_semantic_registry:
        raise ValueError("DatasetProfile declares supports_semantic_registry=false")
    ctx.create_workspace()
    inputs, X_train, _ = _load_inputs(ctx)
    selected, group_counts, selection_warnings = select_common_cases(
        ctx=ctx,
        model_bundle=inputs.model_bundle,
        predictions=inputs.predictions,
        cases_per_group=cases_per_group,
    )
    plan = resolve_xai_explainer_plan(
        estimator=inputs.model_bundle.estimator,
        model_family=inputs.model_bundle.model_family,
    )
    shap_result = compute_local_shap_values(
        inputs=inputs,
        selected_cases=selected,
        background_sample_size=200,
        prefer_tree_explainer=plan.prefer_tree_explainer,
    )
    evidence_records = _build_evidence_records(ctx=ctx, inputs=inputs, shap_result=shap_result)
    quality_df, concept_rows = _quality_for_records(
        inputs=inputs,
        X_train=X_train,
        records=evidence_records,
        selected_cases=selected,
    )

    xai_dir = ctx.paths.report_dir / "xai"
    quality_dir = ctx.paths.report_dir / "xai_quality"
    selected_path = xai_dir / "xai_selected_cases.csv"
    evidence_path = xai_dir / "xai_local_evidence.jsonl"
    summary_path = xai_dir / "xai_evidence_summary.csv"
    quality_path = quality_dir / "xai_evidence_quality_summary.csv"
    concept_path = quality_dir / "xai_concept_aggregation_report.csv"
    selected.to_csv(selected_path, index=False)
    _write_jsonl(evidence_path, evidence_records)
    pd.DataFrame(
        [
            {
                "evidence_id": item["evidence_id"],
                "case_id": item["case"]["case_id"],
                "source_entity_id": item["case"]["source_entity_id"],
                "case_type": item["case"]["case_type"],
                "selection_rank": item["case"]["selection_rank"],
                "y_true": item["prediction"]["y_true"],
                "y_proba": item["prediction"]["y_proba"],
                "y_pred": item["prediction"]["y_pred"],
                "model_name": item["model"]["model_name"],
                "feature_count": item["model"]["feature_count"],
            }
            for item in evidence_records
        ]
    ).to_csv(summary_path, index=False)
    quality_df.to_csv(quality_path, index=False)
    pd.DataFrame(concept_rows).to_csv(concept_path, index=False)

    failed = int((~quality_df["additivity_pass"].astype(bool)).sum())
    manifest = {
        "schema_version": "common_xai_manifest_v1",
        "created_at_utc": _utc_now(),
        **ctx.provenance(),
        "selected_model": {
            "model_name": inputs.model_bundle.model_name,
            "model_version": inputs.model_bundle.model_version,
            "model_family": inputs.model_bundle.model_family,
            "dataset_branch": inputs.model_bundle.dataset_branch,
        },
        "explainer_plan": {
            "strategy": plan.strategy,
            "preferred_explainer": plan.preferred_explainer,
            "fallback_explainer": plan.fallback_explainer,
            "reason": plan.reason,
        },
        "explainer_type": shap_result.explainer_type,
        "case_selection": {
            "cases_per_group": cases_per_group,
            "case_groups": list(CASE_GROUPS),
            "group_counts": group_counts,
            "warnings": selection_warnings,
        },
        "case_count": len(evidence_records),
        "feature_count": inputs.model_bundle.feature_count,
        "additivity": {
            "failed_count": failed,
            "passed_count": len(evidence_records) - failed,
            "max_error": float(quality_df["additivity_error_abs"].max()),
        },
        "quality": {
            "mean_top10_coverage": float(quality_df["top10_coverage"].mean()),
            "mean_comprehensiveness_top10": float(quality_df["comprehensiveness_top10"].mean()),
            "mean_sufficiency_drop_top10": float(quality_df["sufficiency_drop_top10"].mean()),
            "unknown_feature_group_abs_share_mean": float(quality_df["unknown_feature_group_abs_share"].mean()),
        },
        "outputs": {
            "selected_cases": str(selected_path),
            "local_evidence": str(evidence_path),
            "evidence_summary": str(summary_path),
            "quality_summary": str(quality_path),
            "concept_aggregation": str(concept_path),
        },
        "status": "passed" if failed == 0 else "failed",
    }
    manifest_path = ctx.paths.manifest_dir / "common_xai_manifest.json"
    _write_json(manifest_path, manifest)
    if failed:
        raise RuntimeError(f"Common XAI additivity gate failed for {failed} cases")
    return CommonXAIResult(
        manifest_path=manifest_path,
        evidence_path=evidence_path,
        quality_path=quality_path,
        selected_cases_path=selected_path,
        case_count=len(evidence_records),
        feature_count=inputs.model_bundle.feature_count,
        explainer_type=shap_result.explainer_type,
        failed_additivity_count=failed,
    )
