from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ml.scripts.xai_layer.config import (
    ID_COLUMN,
    XAI_CONFIG,
)
from ml.scripts.xai_layer.evidence_schema import (
    CustomerEvidence,
    LocalEvidenceRecord,
    ModelEvidence,
    build_evidence_quality,
    build_local_evidence_record,
    build_local_feature_evidence,
    build_prediction_evidence,
    build_shap_evidence,
    local_evidence_record_to_dict,
    to_optional_int,
)
from ml.scripts.xai_layer.loaders import XAIInputs
from ml.scripts.xai_layer.shap_explainer import LocalShapResult


@dataclass(frozen=True)
class EvidenceBuildResult:
    records: list[LocalEvidenceRecord]
    record_dicts: list[dict[str, Any]]
    summary: pd.DataFrame
    warnings: list[str]


def normalize_mapping_entry(
    *,
    feature_name: str,
    feature_mapping: dict[str, Any],
) -> dict[str, Any]:
    entry = feature_mapping.get(feature_name)

    if entry is None:
        return {
            "raw_feature_name": feature_name,
            "display_name": feature_name,
            "concept": "unknown_feature_group",
            "mapping_found": False,
            "metadata": {},
        }

    if isinstance(entry, str):
        return {
            "raw_feature_name": entry,
            "display_name": entry,
            "concept": "unknown_feature_group",
            "mapping_found": True,
            "metadata": {"raw_mapping_entry": entry},
        }

    if not isinstance(entry, dict):
        return {
            "raw_feature_name": feature_name,
            "display_name": feature_name,
            "concept": "unknown_feature_group",
            "mapping_found": False,
            "metadata": {"unsupported_mapping_type": type(entry).__name__},
        }

    raw_feature_name = (
        entry.get("raw_feature_name")
        or entry.get("original_feature")
        or entry.get("source_feature")
        or entry.get("input_feature")
        or entry.get("base_feature")
        or feature_name
    )

    display_name = (
        entry.get("display_name")
        or entry.get("human_name")
        or entry.get("description")
        or raw_feature_name
        or feature_name
    )

    concept = (
        entry.get("concept")
        or entry.get("concept_id")
        or entry.get("feature_group")
        or entry.get("group")
        or "unknown_feature_group"
    )

    metadata = {
        key: value
        for key, value in entry.items()
        if key not in {
            "raw_feature_name",
            "original_feature",
            "source_feature",
            "input_feature",
            "base_feature",
            "display_name",
            "human_name",
            "description",
            "concept",
            "concept_id",
            "feature_group",
            "group",
        }
    }

    return {
        "raw_feature_name": str(raw_feature_name),
        "display_name": str(display_name),
        "concept": str(concept),
        "mapping_found": True,
        "metadata": metadata,
    }


def build_feature_registry_lookup(
    feature_registry: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}

    possible_key_columns = [
        "feature_name",
        "raw_feature_name",
        "feature_id",
        "name",
    ]

    key_columns = [
        column
        for column in possible_key_columns
        if column in feature_registry.columns
    ]

    if not key_columns:
        return lookup

    for _, row in feature_registry.iterrows():
        row_dict = row.to_dict()

        for key_column in key_columns:
            key_value = row_dict.get(key_column)

            if pd.isna(key_value):
                continue

            key = str(key_value)

            if key and key not in lookup:
                lookup[key] = row_dict

    return lookup


def enrich_mapping_with_feature_registry(
    *,
    mapping_info: dict[str, Any],
    feature_name: str,
    feature_registry_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    raw_feature_name = str(mapping_info["raw_feature_name"])

    registry_row = (
        feature_registry_lookup.get(feature_name)
        or feature_registry_lookup.get(raw_feature_name)
    )

    if registry_row is None:
        return mapping_info

    display_name = mapping_info["display_name"]
    concept = mapping_info["concept"]

    for display_column in [
        "display_name",
        "human_name",
        "description",
        "feature_description",
    ]:
        value = registry_row.get(display_column)

        if value is not None and not pd.isna(value):
            display_name = str(value)
            break

    for concept_column in [
        "concept",
        "concept_id",
        "feature_group",
        "group",
    ]:
        value = registry_row.get(concept_column)

        if value is not None and not pd.isna(value):
            concept = str(value)
            break

    metadata = dict(mapping_info.get("metadata", {}))

    metadata["feature_registry"] = {
        key: value
        for key, value in registry_row.items()
        if value is not None and not pd.isna(value)
    }

    return {
        **mapping_info,
        "display_name": display_name,
        "concept": concept,
        "metadata": metadata,
    }


def get_top_feature_indices(
    *,
    shap_values_for_case: np.ndarray,
    top_k: int,
) -> np.ndarray:
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")

    feature_count = len(shap_values_for_case)
    effective_top_k = min(top_k, feature_count)

    sorted_indices = np.argsort(np.abs(shap_values_for_case))[::-1]

    return sorted_indices[:effective_top_k]


def build_local_features_for_case(
    *,
    X_case: pd.Series,
    shap_values_for_case: np.ndarray,
    feature_names: list[str],
    feature_mapping: dict[str, Any],
    feature_registry_lookup: dict[str, dict[str, Any]],
    top_k: int,
) -> tuple[list[Any], int]:
    top_indices = get_top_feature_indices(
        shap_values_for_case=shap_values_for_case,
        top_k=top_k,
    )

    top_abs_sum = float(
        np.abs(shap_values_for_case[top_indices]).sum()
    )

    local_features = []
    mapping_missing_count = 0

    for rank, feature_index in enumerate(top_indices, start=1):
        feature_name = feature_names[int(feature_index)]
        feature_value = X_case[feature_name]
        shap_value = float(shap_values_for_case[int(feature_index)])

        mapping_info = normalize_mapping_entry(
            feature_name=feature_name,
            feature_mapping=feature_mapping,
        )

        mapping_info = enrich_mapping_with_feature_registry(
            mapping_info=mapping_info,
            feature_name=feature_name,
            feature_registry_lookup=feature_registry_lookup,
        )

        if not bool(mapping_info.get("mapping_found", False)):
            mapping_missing_count += 1

        abs_shap_value = abs(shap_value)

        if top_abs_sum > 0:
            contribution_percent = abs_shap_value / top_abs_sum * 100.0
        else:
            contribution_percent = None

        metadata = dict(mapping_info.get("metadata", {}))
        metadata["mapping_found"] = bool(mapping_info.get("mapping_found", False))
        metadata["feature_index"] = int(feature_index)

        local_feature = build_local_feature_evidence(
            rank=rank,
            feature_name=feature_name,
            raw_feature_name=str(mapping_info["raw_feature_name"]),
            display_name=str(mapping_info["display_name"]),
            concept=str(mapping_info["concept"]),
            feature_value=feature_value,
            shap_value=shap_value,
            contribution_percent_of_top_k_abs=contribution_percent,
            metadata=metadata,
        )

        local_features.append(local_feature)

    return local_features, mapping_missing_count


def build_model_evidence(inputs: XAIInputs) -> ModelEvidence:
    return ModelEvidence(
        model_name=inputs.model_bundle.model_name,
        model_version=inputs.model_bundle.model_version,
        model_family=inputs.model_bundle.model_family,
        dataset_branch=inputs.model_bundle.dataset_branch,
        feature_count=inputs.model_bundle.feature_count,
    )


def build_customer_evidence(case_row: pd.Series) -> CustomerEvidence:
    return CustomerEvidence(
        sk_id_curr=int(case_row[ID_COLUMN]),
        row_index=int(case_row["row_index"]),
        case_type=str(case_row["case_type"]),
        selection_rank=int(case_row["selection_rank"]),
    )


def get_optional_y_true(case_row: pd.Series) -> int | None:
    if "y_true" not in case_row.index:
        return None

    return to_optional_int(case_row["y_true"])


def build_single_evidence_record(
    *,
    inputs: XAIInputs,
    shap_result: LocalShapResult,
    case_position: int,
    feature_registry_lookup: dict[str, dict[str, Any]],
    top_k: int,
) -> LocalEvidenceRecord:
    selected_case = shap_result.selected_cases.iloc[case_position]
    X_case = shap_result.X_cases.iloc[case_position]

    shap_values_for_case = shap_result.shap_values[case_position]
    base_value = float(shap_result.base_values[case_position])
    model_output = float(shap_result.model_outputs[case_position])
    additivity_error = float(shap_result.additivity_errors[case_position])
    passed_additivity_check = bool(shap_result.passed_additivity_check[case_position])

    model = build_model_evidence(inputs)
    customer = build_customer_evidence(selected_case)

    prediction = build_prediction_evidence(
        y_true=get_optional_y_true(selected_case),
        y_proba=float(selected_case["y_proba"]),
        y_pred=int(selected_case["y_pred"]),
        threshold=float(selected_case["threshold"]),
    )

    shap = build_shap_evidence(
        base_value=base_value,
        model_output=model_output,
        shap_values_for_case=shap_values_for_case.tolist(),
        additivity_error=additivity_error,
        output_space=shap_result.output_space,
        xai_method=XAI_CONFIG.xai_method,
        explainer_type=shap_result.explainer_type,
    )

    local_features, mapping_missing_count = build_local_features_for_case(
        X_case=X_case,
        shap_values_for_case=shap_values_for_case,
        feature_names=shap_result.feature_names,
        feature_mapping=inputs.feature_mapping,
        feature_registry_lookup=feature_registry_lookup,
        top_k=top_k,
    )

    quality = build_evidence_quality(
        local_features=local_features,
        top_k=top_k,
        feature_count=inputs.model_bundle.feature_count,
        mapping_missing_count=mapping_missing_count,
        passed_additivity_check=passed_additivity_check,
        additivity_tolerance=XAI_CONFIG.additivity_tolerance,
    )

    metadata = {
        "source": "Batch G - XAI Evidence Layer",
        "run_mode": inputs.run_mode,
        "has_ground_truth": inputs.has_ground_truth,
        "case_position": int(case_position),
        "selected_cases_source": (
            "model_predictions_test.csv"
            if inputs.has_ground_truth
            else "model_predictions_inference.csv"
        ),
    }

    return build_local_evidence_record(
        evidence_id=str(selected_case["evidence_id"]),
        model=model,
        customer=customer,
        prediction=prediction,
        shap=shap,
        local_features=local_features,
        quality=quality,
        metadata=metadata,
    )


def validate_evidence_records(records: list[LocalEvidenceRecord]) -> None:
    if not records:
        raise ValueError("No evidence records were built.")

    evidence_ids = [record.evidence_id for record in records]

    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("Duplicate evidence_id found in evidence records.")

    for record in records:
        local_evidence_record_to_dict(record)


def build_evidence_summary(records: list[LocalEvidenceRecord]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for record in records:
        row: dict[str, Any] = {
            "evidence_id": record.evidence_id,
            "SK_ID_CURR": record.customer.sk_id_curr,
            "row_index": record.customer.row_index,
            "case_type": record.customer.case_type,
            "selection_rank": record.customer.selection_rank,
            "run_mode": record.metadata.get("run_mode"),
            "has_ground_truth": record.metadata.get("has_ground_truth"),
            "y_true": record.prediction.y_true,
            "y_proba": record.prediction.y_proba,
            "y_pred": record.prediction.y_pred,
            "threshold": record.prediction.threshold,
            "predicted_label_text": record.prediction.predicted_label_text,
            "true_label_text": record.prediction.true_label_text,
            "model_name": record.model.model_name,
            "model_version": record.model.model_version,
            "model_family": record.model.model_family,
            "dataset_branch": record.model.dataset_branch,
            "feature_count": record.model.feature_count,
            "base_value": record.shap.base_value,
            "model_output": record.shap.model_output,
            "shap_sum": record.shap.shap_sum,
            "reconstructed_output": record.shap.reconstructed_output,
            "additivity_error": record.shap.additivity_error,
            "passed_additivity_check": record.quality.passed_additivity_check,
            "top_k": record.quality.top_k,
            "local_feature_count": record.quality.local_feature_count,
            "positive_feature_count": record.quality.positive_feature_count,
            "negative_feature_count": record.quality.negative_feature_count,
            "neutral_feature_count": record.quality.neutral_feature_count,
            "mapping_missing_count": record.quality.mapping_missing_count,
        }

        for index in range(3):
            rank = index + 1

            if index < len(record.local_features):
                feature = record.local_features[index]
                row[f"top_{rank}_feature"] = feature.feature_name
                row[f"top_{rank}_display_name"] = feature.display_name
                row[f"top_{rank}_concept"] = feature.concept
                row[f"top_{rank}_value"] = feature.feature_value
                row[f"top_{rank}_shap"] = feature.shap_value
                row[f"top_{rank}_direction"] = feature.direction
            else:
                row[f"top_{rank}_feature"] = None
                row[f"top_{rank}_display_name"] = None
                row[f"top_{rank}_concept"] = None
                row[f"top_{rank}_value"] = None
                row[f"top_{rank}_shap"] = None
                row[f"top_{rank}_direction"] = None

        rows.append(row)

    return pd.DataFrame(rows)


def build_local_evidence_records(
    *,
    inputs: XAIInputs,
    shap_result: LocalShapResult,
    top_k: int | None = None,
) -> EvidenceBuildResult:
    if top_k is None:
        top_k = XAI_CONFIG.top_k_features

    if len(shap_result.selected_cases) != shap_result.shap_values.shape[0]:
        raise ValueError(
            "Selected case count does not match SHAP row count. "
            f"{len(shap_result.selected_cases)} != {shap_result.shap_values.shape[0]}"
        )

    if shap_result.shap_values.shape[1] != len(shap_result.feature_names):
        raise ValueError(
            "SHAP feature count does not match feature_names length. "
            f"{shap_result.shap_values.shape[1]} != {len(shap_result.feature_names)}"
        )

    feature_registry_lookup = build_feature_registry_lookup(
        inputs.feature_registry
    )

    records = [
        build_single_evidence_record(
            inputs=inputs,
            shap_result=shap_result,
            case_position=case_position,
            feature_registry_lookup=feature_registry_lookup,
            top_k=top_k,
        )
        for case_position in range(len(shap_result.selected_cases))
    ]

    validate_evidence_records(records)

    record_dicts = [
        local_evidence_record_to_dict(record)
        for record in records
    ]

    summary = build_evidence_summary(records)

    warnings: list[str] = []

    total_mapping_missing = int(summary["mapping_missing_count"].sum())

    if total_mapping_missing > 0:
        warnings.append(
            f"Missing feature mapping count across all records: {total_mapping_missing}"
        )

    failed_additivity_count = int(
        (~summary["passed_additivity_check"].astype(bool)).sum()
    )

    if failed_additivity_count > 0:
        warnings.append(
            f"Additivity check failed for {failed_additivity_count} evidence records."
        )

    return EvidenceBuildResult(
        records=records,
        record_dicts=record_dicts,
        summary=summary,
        warnings=warnings,
    )


def summarize_evidence_build_result(
    result: EvidenceBuildResult,
) -> dict[str, Any]:
    summary = result.summary

    return {
        "record_count": int(len(result.records)),
        "summary_shape": list(summary.shape),
        "run_mode_counts": summary["run_mode"].value_counts(dropna=False).to_dict(),
        "has_ground_truth_counts": summary["has_ground_truth"].value_counts(dropna=False).to_dict(),
        "case_type_counts": summary["case_type"].value_counts().to_dict(),
        "mapping_missing_total": int(summary["mapping_missing_count"].sum()),
        "failed_additivity_count": int(
            (~summary["passed_additivity_check"].astype(bool)).sum()
        ),
        "mean_y_proba": float(summary["y_proba"].mean()),
        "min_y_proba": float(summary["y_proba"].min()),
        "max_y_proba": float(summary["y_proba"].max()),
        "first_5_evidence_ids": summary["evidence_id"].head(5).tolist(),
        "warnings": result.warnings,
    }


__all__ = [
    "EvidenceBuildResult",
    "normalize_mapping_entry",
    "build_feature_registry_lookup",
    "enrich_mapping_with_feature_registry",
    "get_top_feature_indices",
    "build_local_features_for_case",
    "build_model_evidence",
    "build_customer_evidence",
    "get_optional_y_true",
    "build_single_evidence_record",
    "validate_evidence_records",
    "build_evidence_summary",
    "build_local_evidence_records",
    "summarize_evidence_build_result",
]