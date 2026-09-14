from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import (
    NEGATIVE_CLASS,
    NEGATIVE_LABEL_TEXT,
    POSITIVE_CLASS,
    POSITIVE_LABEL_TEXT,
    UNKNOWN_LABEL_TEXT,
)


@dataclass(frozen=True)
class ModelEvidence:
    model_name: str
    model_version: str
    model_family: str
    dataset_branch: str
    feature_count: int


@dataclass(frozen=True)
class CustomerEvidence:
    sk_id_curr: int
    row_index: int
    case_type: str
    selection_rank: int


@dataclass(frozen=True)
class PredictionEvidence:
    y_true: int | None
    y_proba: float
    y_pred: int
    threshold: float
    predicted_label_text: str
    true_label_text: str


@dataclass(frozen=True)
class ShapEvidence:
    base_value: float
    model_output: float
    shap_sum: float
    reconstructed_output: float
    additivity_error: float
    output_space: str
    positive_class: int
    xai_method: str
    explainer_type: str


@dataclass(frozen=True)
class LocalFeatureEvidence:
    rank: int
    feature_name: str
    raw_feature_name: str
    display_name: str
    concept: str
    feature_value: float | int | str | None
    shap_value: float
    abs_shap_value: float
    direction: str
    contribution_percent_of_top_k_abs: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceQuality:
    top_k: int
    feature_count: int
    local_feature_count: int
    positive_feature_count: int
    negative_feature_count: int
    neutral_feature_count: int
    mapping_missing_count: int
    passed_additivity_check: bool
    additivity_tolerance: float


@dataclass(frozen=True)
class LocalEvidenceRecord:
    evidence_id: str
    created_at: str
    model: ModelEvidence
    customer: CustomerEvidence
    prediction: PredictionEvidence
    shap: ShapEvidence
    local_features: list[LocalFeatureEvidence]
    top_positive_features: list[LocalFeatureEvidence]
    top_negative_features: list[LocalFeatureEvidence]
    quality: EvidenceQuality
    metadata: dict[str, Any] = field(default_factory=dict)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True

    try:
        if hasattr(value, "item"):
            value = value.item()
    except Exception:
        pass

    if isinstance(value, float):
        return math.isnan(value)

    try:
        import pandas as pd

        return bool(pd.isna(value))
    except Exception:
        return False


def to_optional_int(value: Any) -> int | None:
    if is_missing_value(value):
        return None

    return int(value)


def to_json_safe(value: Any) -> Any:
    if is_missing_value(value):
        return None

    if hasattr(value, "item"):
        try:
            return to_json_safe(value.item())
        except Exception:
            pass

    if isinstance(value, dict):
        return {
            str(key): to_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [to_json_safe(item) for item in value]

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


def dataclass_to_json_safe_dict(instance: Any) -> dict[str, Any]:
    return to_json_safe(asdict(instance))


def label_text_from_class(label: int | None) -> str:
    if label is None:
        return UNKNOWN_LABEL_TEXT

    if int(label) == POSITIVE_CLASS:
        return POSITIVE_LABEL_TEXT

    if int(label) == NEGATIVE_CLASS:
        return NEGATIVE_LABEL_TEXT

    return UNKNOWN_LABEL_TEXT


def direction_from_shap_value(
    shap_value: float,
    epsilon: float = 1e-12,
) -> str:
    if shap_value > epsilon:
        return "increases_risk"

    if shap_value < -epsilon:
        return "decreases_risk"

    return "neutral"


def build_prediction_evidence(
    *,
    y_true: int | None,
    y_proba: float,
    y_pred: int,
    threshold: float,
) -> PredictionEvidence:
    y_true_value = to_optional_int(y_true)

    return PredictionEvidence(
        y_true=y_true_value,
        y_proba=float(y_proba),
        y_pred=int(y_pred),
        threshold=float(threshold),
        predicted_label_text=label_text_from_class(int(y_pred)),
        true_label_text=label_text_from_class(y_true_value),
    )


def build_shap_evidence(
    *,
    base_value: float,
    model_output: float,
    shap_values_for_case: list[float],
    additivity_error: float,
    output_space: str,
    xai_method: str,
    explainer_type: str,
) -> ShapEvidence:
    shap_sum = float(sum(float(value) for value in shap_values_for_case))
    reconstructed_output = float(base_value) + shap_sum

    return ShapEvidence(
        base_value=float(base_value),
        model_output=float(model_output),
        shap_sum=shap_sum,
        reconstructed_output=float(reconstructed_output),
        additivity_error=float(additivity_error),
        output_space=str(output_space),
        positive_class=int(POSITIVE_CLASS),
        xai_method=str(xai_method),
        explainer_type=str(explainer_type),
    )


def build_local_feature_evidence(
    *,
    rank: int,
    feature_name: str,
    raw_feature_name: str,
    display_name: str,
    concept: str,
    feature_value: Any,
    shap_value: float,
    contribution_percent_of_top_k_abs: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> LocalFeatureEvidence:
    shap_value_float = float(shap_value)

    return LocalFeatureEvidence(
        rank=int(rank),
        feature_name=str(feature_name),
        raw_feature_name=str(raw_feature_name),
        display_name=str(display_name),
        concept=str(concept),
        feature_value=to_json_safe(feature_value),
        shap_value=shap_value_float,
        abs_shap_value=abs(shap_value_float),
        direction=direction_from_shap_value(shap_value_float),
        contribution_percent_of_top_k_abs=(
            None
            if contribution_percent_of_top_k_abs is None
            else float(contribution_percent_of_top_k_abs)
        ),
        metadata={} if metadata is None else to_json_safe(metadata),
    )


def split_features_by_direction(
    local_features: list[LocalFeatureEvidence],
) -> tuple[
    list[LocalFeatureEvidence],
    list[LocalFeatureEvidence],
    list[LocalFeatureEvidence],
]:
    positive_features = [
        feature
        for feature in local_features
        if feature.direction == "increases_risk"
    ]

    negative_features = [
        feature
        for feature in local_features
        if feature.direction == "decreases_risk"
    ]

    neutral_features = [
        feature
        for feature in local_features
        if feature.direction == "neutral"
    ]

    return positive_features, negative_features, neutral_features


def build_evidence_quality(
    *,
    local_features: list[LocalFeatureEvidence],
    top_k: int,
    feature_count: int,
    mapping_missing_count: int,
    passed_additivity_check: bool,
    additivity_tolerance: float,
) -> EvidenceQuality:
    positive_features, negative_features, neutral_features = split_features_by_direction(
        local_features
    )

    return EvidenceQuality(
        top_k=int(top_k),
        feature_count=int(feature_count),
        local_feature_count=int(len(local_features)),
        positive_feature_count=int(len(positive_features)),
        negative_feature_count=int(len(negative_features)),
        neutral_feature_count=int(len(neutral_features)),
        mapping_missing_count=int(mapping_missing_count),
        passed_additivity_check=bool(passed_additivity_check),
        additivity_tolerance=float(additivity_tolerance),
    )


def build_local_evidence_record(
    *,
    evidence_id: str,
    model: ModelEvidence,
    customer: CustomerEvidence,
    prediction: PredictionEvidence,
    shap: ShapEvidence,
    local_features: list[LocalFeatureEvidence],
    quality: EvidenceQuality,
    metadata: dict[str, Any] | None = None,
) -> LocalEvidenceRecord:
    positive_features, negative_features, _ = split_features_by_direction(
        local_features
    )

    return LocalEvidenceRecord(
        evidence_id=str(evidence_id),
        created_at=utc_now_iso(),
        model=model,
        customer=customer,
        prediction=prediction,
        shap=shap,
        local_features=local_features,
        top_positive_features=positive_features,
        top_negative_features=negative_features,
        quality=quality,
        metadata={} if metadata is None else to_json_safe(metadata),
    )


def validate_local_evidence_record(record: LocalEvidenceRecord) -> None:
    if not record.evidence_id:
        raise ValueError("Evidence record has empty evidence_id.")

    if record.customer.row_index < 0:
        raise ValueError("Evidence record has negative row_index.")

    if not 0 <= record.prediction.y_proba <= 1:
        raise ValueError("Evidence record y_proba must be in [0, 1].")

    if record.prediction.y_pred not in {NEGATIVE_CLASS, POSITIVE_CLASS}:
        raise ValueError("Evidence record y_pred must be 0 or 1.")

    if record.prediction.y_true is not None:
        if record.prediction.y_true not in {NEGATIVE_CLASS, POSITIVE_CLASS}:
            raise ValueError("Evidence record y_true must be 0, 1, or None.")

    if not record.local_features:
        raise ValueError("Evidence record has no local_features.")

    ranks = [feature.rank for feature in record.local_features]

    if ranks != sorted(ranks):
        raise ValueError("Local feature ranks must be sorted ascending.")

    if len(set(ranks)) != len(ranks):
        raise ValueError("Local feature ranks must be unique.")

    abs_values = [
        feature.abs_shap_value
        for feature in record.local_features
    ]

    if abs_values != sorted(abs_values, reverse=True):
        raise ValueError("Local features must be sorted by abs_shap_value descending.")

    for feature in record.top_positive_features:
        if feature.direction != "increases_risk":
            raise ValueError("top_positive_features contains non-positive feature.")

    for feature in record.top_negative_features:
        if feature.direction != "decreases_risk":
            raise ValueError("top_negative_features contains non-negative feature.")


def local_evidence_record_to_dict(record: LocalEvidenceRecord) -> dict[str, Any]:
    validate_local_evidence_record(record)
    return dataclass_to_json_safe_dict(record)


__all__ = [
    "ModelEvidence",
    "CustomerEvidence",
    "PredictionEvidence",
    "ShapEvidence",
    "LocalFeatureEvidence",
    "EvidenceQuality",
    "LocalEvidenceRecord",
    "utc_now_iso",
    "is_missing_value",
    "to_optional_int",
    "to_json_safe",
    "dataclass_to_json_safe_dict",
    "label_text_from_class",
    "direction_from_shap_value",
    "build_prediction_evidence",
    "build_shap_evidence",
    "build_local_feature_evidence",
    "split_features_by_direction",
    "build_evidence_quality",
    "build_local_evidence_record",
    "validate_local_evidence_record",
    "local_evidence_record_to_dict",
]