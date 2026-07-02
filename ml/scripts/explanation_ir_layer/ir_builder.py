"""
Builder for Batch H - Concept-aware Explanation IR Layer.

This module converts Batch G structured XAI evidence records into
concept-aware Explanation IR records.

Main transformation:
    xai_local_evidence.jsonl
        -> ExplanationIRRecord
        -> allowed claims
        -> forbidden claims
        -> LLM input contract
        -> validation contract

Important:
- This module does NOT call an LLM.
- This module does NOT generate final explanation text.
- This module does NOT compute SHAP again.
- This module only transforms structured evidence into a controlled IR contract.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ml.scripts.explanation_ir_layer.config import (
    SOURCE_BATCH_NAME,
    IR_SCHEMA_VERSION,
    DEFAULT_LLM_AUDIENCE,
    DEFAULT_LLM_STYLE,
    DEFAULT_LLM_TARGET_LANGUAGE,
    DEFAULT_MAX_CONCEPT_SUMMARIES,
    DEFAULT_MAX_FEATURE_FACTORS_PER_DIRECTION,
    RECORD_STATUS_PASSED,
)
from ml.scripts.explanation_ir_layer.ir_schema import (
    ExplanationIRRecord,
    IRAllowedClaim,
    IRConceptSummary,
    IRCustomerInfo,
    IREvidenceRef,
    IREvidenceTrace,
    IRFeatureFactor,
    IRForbiddenClaim,
    IRLLMInputContract,
    IRMetadata,
    IRModelInfo,
    IRPredictionSummary,
    IRRecordQuality,
    IRTruthCondition,
    IRValidationContract,
    IRValidationRule,
    IRXAISummary,
    dataclass_to_dict,
    direction_from_shap,
    format_probability,
    format_probability_percent,
    is_probability_above_threshold,
    label_text_from_class,
    make_safe_phrase_for_direction,
    normalize_display_name,
    round_float,
    safe_float,
    safe_int,
    strength_from_abs_shap,
    threshold_comparison_from_probability,
    utc_now_iso,
    validate_explanation_ir_record,
)


# =============================================================================
# Result dataclass
# =============================================================================

@dataclass(frozen=True)
class ExplanationIRBuildResult:
    """
    Result returned by the IR builder.

    Attributes:
        ir_records:
            List of ExplanationIRRecord dataclass instances.

        ir_record_dicts:
            JSON-safe dictionaries for saving as JSONL.

        summary_df:
            Flat DataFrame for CSV debugging/reporting.

        warnings:
            Batch-level and record-level non-fatal warnings.

        errors:
            Fatal or record-level errors that caused failed records.
    """

    ir_records: List[ExplanationIRRecord]
    ir_record_dicts: List[Dict[str, Any]]
    summary_df: pd.DataFrame
    warnings: List[str]
    errors: List[str]


# =============================================================================
# Generic helpers
# =============================================================================

def get_nested_value(
    data: Dict[str, Any],
    path: str,
    default: Any = None,
) -> Any:
    """
    Safely read nested dictionary values with dot notation.

    Example:
        get_nested_value(record, "metadata.run_mode")
    """
    current: Any = data

    for part in path.split("."):
        if not isinstance(current, dict):
            return default

        if part not in current:
            return default

        current = current[part]

    return current


def first_present_value(*values: Any) -> Any:
    """
    Return the first value that is not None and not an empty string.

    Important:
        0, 0.0, and False are valid values and should not be skipped.
    """
    for value in values:
        if value is None:
            continue

        if isinstance(value, str) and value.strip() == "":
            continue

        return value

    return None


def normalize_bool_flag(value: Any) -> Optional[bool]:
    """
    Normalize bool-like values.

    Supports:
        True / False
        "True" / "False"
        "true" / "false"
        1 / 0
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False

    text = str(value).strip().lower()

    if text in {"true", "yes", "y", "1"}:
        return True

    if text in {"false", "no", "n", "0"}:
        return False

    return None


def normalize_user_explanation_policy(value: Any) -> str:
    """
    Normalize allowed_in_user_explanation policy from Batch G metadata.

    Expected values from feature registry/evidence:
        "True"
        "False"
        "limited"

    Returns:
        "true", "false", or "limited"
    """
    if value is None:
        return "true"

    text = str(value).strip().lower()

    if text in {"true", "yes", "y", "1"}:
        return "true"

    if text in {"false", "no", "n", "0"}:
        return "false"

    if text == "limited":
        return "limited"

    return text


def compute_feature_llm_visibility(
    sensitive: Optional[bool],
    allowed_policy: str,
) -> bool:
    """
    Decide whether an exact feature is visible to the LLM/user-facing explanation.

    v1.1 policy:
        allowed_policy == "false"   -> hidden
        allowed_policy == "limited" -> hidden at exact feature level
        sensitive == True           -> hidden at exact feature level
        otherwise                   -> visible

    Important:
        Hidden feature-level evidence can still contribute to concept-level
        summaries if policy is not false.
    """
    policy = normalize_user_explanation_policy(allowed_policy)

    if policy == "false":
        return False

    if policy == "limited":
        return False

    if sensitive is True:
        return False

    return True


def compute_feature_claimable(
    sensitive: Optional[bool],
    allowed_policy: str,
) -> bool:
    """
    Decide whether exact feature-level claims should be created.

    Same as feature-level LLM visibility in v1.1.
    """
    return compute_feature_llm_visibility(
        sensitive=sensitive,
        allowed_policy=allowed_policy,
    )


def is_factor_allowed_at_concept_level(factor: IRFeatureFactor) -> bool:
    """
    Decide whether a factor may contribute to concept-level explanation.

    v1.1 policy:
        - exact sensitive/limited features may be hidden from feature-level LLM
        - but their concept may still be explained if allowed_policy != false

    Example:
        ext_source_mean may be sensitive/limited as an exact feature,
        but the concept "tín hiệu điểm ngoài" can still appear.
    """
    policy = normalize_user_explanation_policy(
        getattr(factor, "allowed_in_user_explanation", None)
    )

    return policy != "false"


def is_claim_visible_to_llm(claim: IRAllowedClaim) -> bool:
    """
    Decide whether an allowed claim should be exposed to Batch I.

    Keep evaluation-only claims in the IR, but do not expose them to the default
    user-facing LLM contract.
    """
    if claim.claim_type == "true_label_available":
        return False

    return True


def get_evidence_id(record: Dict[str, Any], fallback_index: int) -> str:
    """
    Get evidence id from a Batch G record.

    Falls back to a deterministic id if missing.
    """
    value = (
        record.get("evidence_id")
        or record.get("source_evidence_id")
        or get_nested_value(record, "metadata.evidence_id")
    )

    if value is None or str(value).strip() == "":
        return f"xai_missing_evidence_id_{fallback_index:06d}"

    return str(value)


def make_ir_id(source_evidence_id: str) -> str:
    """Create IR id from source evidence id."""
    if source_evidence_id.startswith("xai_"):
        return "ir_" + source_evidence_id

    return f"ir_{source_evidence_id}"


def make_trace_id(source_evidence_id: str) -> str:
    """Create trace id from source evidence id."""
    if source_evidence_id.startswith("xai_"):
        return "trace_" + source_evidence_id

    return f"trace_{source_evidence_id}"


def get_run_mode_from_record(record: Dict[str, Any], default: str) -> str:
    """Read run_mode from evidence record."""
    value = (
        record.get("run_mode")
        or get_nested_value(record, "metadata.run_mode")
        or default
    )
    return str(value).strip().lower()


def get_has_ground_truth_from_record(
    record: Dict[str, Any],
    default: bool,
) -> bool:
    """Read has_ground_truth from evidence record."""
    value = record.get("has_ground_truth")

    if isinstance(value, bool):
        return value

    value = get_nested_value(record, "metadata.has_ground_truth")

    if isinstance(value, bool):
        return value

    return default


def concept_display_name(concept_id: str) -> str:
    """
    Convert concept_id into a human-readable fallback display name.

    Example:
        external_score_signal -> External score signal
    """
    if concept_id is None:
        return "Unknown concept"

    text = str(concept_id).replace("_", " ").strip()

    if not text:
        return "Unknown concept"

    return text[:1].upper() + text[1:]


# =============================================================================
# Model/customer/prediction/XAI summary builders
# =============================================================================

def build_model_info(record: Dict[str, Any]) -> IRModelInfo:
    """Build model info from evidence record."""
    model = record.get("model") or {}

    return IRModelInfo(
        model_name=str(model.get("model_name") or "unknown_model"),
        model_version=str(model.get("model_version") or "unknown_version"),
        model_family=str(model.get("model_family") or "unknown_family"),
        dataset_branch=model.get("dataset_branch"),
        feature_count=safe_int(model.get("feature_count")),
    )


def build_customer_info(record: Dict[str, Any]) -> IRCustomerInfo:
    """
    Build customer info from evidence record.

    Batch G evidence currently stores the customer id as:
        customer.sk_id_curr

    Batch H keeps the output field name as:
        customer.SK_ID_CURR

    This keeps downstream IR consistent while supporting the actual Batch G schema.
    """
    customer = record.get("customer") or {}
    prediction = record.get("prediction") or {}
    metadata = record.get("metadata") or {}

    sk_id_curr = first_present_value(
        customer.get("SK_ID_CURR"),
        customer.get("sk_id_curr"),
        customer.get("customer_id"),
        prediction.get("SK_ID_CURR"),
        prediction.get("sk_id_curr"),
        metadata.get("SK_ID_CURR"),
        metadata.get("sk_id_curr"),
        record.get("SK_ID_CURR"),
        record.get("sk_id_curr"),
    )

    row_index = first_present_value(
        customer.get("row_index"),
        prediction.get("row_index"),
        metadata.get("row_index"),
        record.get("row_index"),
    )

    case_type = first_present_value(
        customer.get("case_type"),
        prediction.get("case_type"),
        metadata.get("case_type"),
        record.get("case_type"),
    )

    selection_rank = first_present_value(
        customer.get("selection_rank"),
        prediction.get("selection_rank"),
        metadata.get("selection_rank"),
        record.get("selection_rank"),
    )

    return IRCustomerInfo(
        SK_ID_CURR=safe_int(sk_id_curr),
        row_index=safe_int(row_index),
        case_type=str(case_type) if case_type is not None else None,
        selection_rank=safe_int(selection_rank),
    )


def build_prediction_summary(
    record: Dict[str, Any],
    has_ground_truth: bool,
) -> IRPredictionSummary:
    """
    Build prediction summary.

    This intentionally standardizes probabilities and label text so Batch I
    does not format numbers by itself.
    """
    prediction = record.get("prediction") or {}

    y_pred = safe_int(
        prediction.get("y_pred")
        if prediction.get("y_pred") is not None
        else prediction.get("predicted_class")
    )

    probability = safe_float(
        prediction.get("y_proba")
        if prediction.get("y_proba") is not None
        else prediction.get("probability")
    )

    threshold = safe_float(prediction.get("threshold"), default=0.5)

    y_true = safe_int(prediction.get("y_true"))

    predicted_label = (
        prediction.get("predicted_label_text")
        or prediction.get("predicted_label")
        or label_text_from_class(y_pred)
    )

    true_label_text = (
        prediction.get("true_label_text")
        or label_text_from_class(y_true)
    )

    return IRPredictionSummary(
        predicted_class=y_pred,
        predicted_label=str(predicted_label),
        probability=round_float(probability),
        probability_display=format_probability(probability),
        probability_percent_display=format_probability_percent(probability),
        threshold=round_float(threshold),
        threshold_display=format_probability(threshold),
        threshold_percent_display=format_probability_percent(threshold),
        threshold_comparison=threshold_comparison_from_probability(
            probability,
            threshold,
        ),
        is_above_threshold=is_probability_above_threshold(probability, threshold),
        true_label=y_true if has_ground_truth else None,
        true_label_text=true_label_text if has_ground_truth else "unknown_label",
        has_ground_truth=has_ground_truth,
    )


def build_xai_summary(record: Dict[str, Any]) -> IRXAISummary:
    """
    Build XAI summary from SHAP evidence.

    Batch G stores additivity_error in shap and passed_additivity_check in quality.
    This function supports both locations and can infer pass/fail from tolerance.
    """
    shap = record.get("shap") or {}
    quality = record.get("quality") or {}

    passed_additivity_check = first_present_value(
        shap.get("passed_additivity_check"),
        quality.get("passed_additivity_check"),
    )

    if passed_additivity_check is None:
        additivity_error = safe_float(shap.get("additivity_error"))
        tolerance = safe_float(quality.get("additivity_tolerance"), default=1e-6)

        if additivity_error is not None and tolerance is not None:
            passed_additivity_check = additivity_error <= tolerance

    return IRXAISummary(
        method=str(
            first_present_value(
                shap.get("xai_method"),
                shap.get("method"),
                "SHAP",
            )
        ),
        explainer_type=shap.get("explainer_type"),
        output_space=shap.get("output_space"),
        base_value=round_float(shap.get("base_value")),
        model_output=round_float(shap.get("model_output")),
        shap_sum=round_float(shap.get("shap_sum")),
        reconstructed_output=round_float(shap.get("reconstructed_output")),
        additivity_error=round_float(shap.get("additivity_error")),
        passed_additivity_check=passed_additivity_check,
    )


# =============================================================================
# Feature factor builders
# =============================================================================

def normalize_local_feature(
    feature: Dict[str, Any],
    index: int,
) -> IRFeatureFactor:
    """
    Convert one Batch G local feature into an IRFeatureFactor.

    Source of truth for direction:
        sign(shap_value)

    Supports actual Batch G schema:
        feature.feature_value
        feature.metadata.concept_display_name
        feature.metadata.sensitive
        feature.metadata.allowed_in_user_explanation
        feature.metadata.value_type
        feature.metadata.unit
        feature.metadata.direction_prior
        feature.metadata.formatting_rule
    """
    rank = safe_int(feature.get("rank"), default=index + 1)
    if rank is None:
        rank = index + 1

    feature_name = str(
        feature.get("feature_name")
        or feature.get("preprocessed_feature_name")
        or f"unknown_feature_{rank}"
    )

    raw_feature_name = feature.get("raw_feature_name")

    display_name = normalize_display_name(
        feature.get("display_name"),
        fallback=feature_name,
    )

    concept = str(
        feature.get("concept")
        or feature.get("concept_id")
        or "unknown_feature_group"
    )

    feature_metadata = feature.get("metadata") or {}

    concept_display = first_present_value(
        feature_metadata.get("concept_display_name"),
        get_nested_value(feature_metadata, "feature_registry.concept_display_name"),
    )

    value_type = first_present_value(
        feature_metadata.get("value_type"),
        get_nested_value(feature_metadata, "feature_registry.value_type"),
    )

    unit = first_present_value(
        feature_metadata.get("unit"),
        get_nested_value(feature_metadata, "feature_registry.unit"),
    )

    sensitive = normalize_bool_flag(
        first_present_value(
            feature_metadata.get("sensitive"),
            get_nested_value(feature_metadata, "feature_registry.sensitive"),
        )
    )

    allowed_in_user_explanation = first_present_value(
        feature_metadata.get("allowed_in_user_explanation"),
        get_nested_value(feature_metadata, "feature_registry.allowed_in_user_explanation"),
        "True",
    )

    normalized_policy = normalize_user_explanation_policy(
        allowed_in_user_explanation
    )

    direction_prior = first_present_value(
        feature_metadata.get("direction_prior"),
        get_nested_value(feature_metadata, "feature_registry.direction_prior"),
    )

    formatting_rule = first_present_value(
        feature_metadata.get("formatting_rule"),
        get_nested_value(feature_metadata, "feature_registry.formatting_rule"),
    )

    feature_value = first_present_value(
        feature.get("value"),
        feature.get("feature_value"),
    )

    shap_value = safe_float(feature.get("shap_value"), default=0.0)
    if shap_value is None:
        shap_value = 0.0

    abs_shap_value = safe_float(feature.get("abs_shap_value"))
    if abs_shap_value is None:
        abs_shap_value = abs(shap_value)

    derived_direction = direction_from_shap(shap_value)
    source_direction = feature.get("direction")
    direction_consistent = True

    if source_direction is not None:
        direction_consistent = str(source_direction) == derived_direction

    strength = strength_from_abs_shap(abs_shap_value)

    llm_visible = compute_feature_llm_visibility(
        sensitive=sensitive,
        allowed_policy=normalized_policy,
    )

    claimable = compute_feature_claimable(
        sensitive=sensitive,
        allowed_policy=normalized_policy,
    )

    factor = IRFeatureFactor(
        factor_id=f"factor_{rank:03d}",
        rank=rank,
        feature_name=feature_name,
        raw_feature_name=raw_feature_name,
        display_name=display_name,
        concept=concept,
        value=feature_value,
        shap_value=round_float(shap_value) or 0.0,
        abs_shap_value=round_float(abs_shap_value) or abs(shap_value),
        direction=derived_direction,
        strength=strength,
        llm_visible=llm_visible,
        claimable=claimable,
        evidence_source="local_features",
        source_direction=str(source_direction) if source_direction is not None else None,
        direction_consistent=direction_consistent,
        safe_phrase=make_safe_phrase_for_direction(display_name, derived_direction),
        source_claim_ids=[],
        feature_value_source_field="feature_value"
        if "feature_value" in feature
        else "value",
        concept_display_name=str(concept_display) if concept_display is not None else None,
        value_type=str(value_type) if value_type is not None else None,
        unit=str(unit) if unit is not None else None,
        sensitive=sensitive,
        allowed_in_user_explanation=normalized_policy,
        direction_prior=str(direction_prior) if direction_prior is not None else None,
        formatting_rule=str(formatting_rule) if formatting_rule is not None else None,
        contribution_percent_of_top_k_abs=round_float(
            feature.get("contribution_percent_of_top_k_abs")
        ),
    )

    return factor


def build_feature_factors(record: Dict[str, Any]) -> Tuple[List[IRFeatureFactor], List[str]]:
    """
    Build feature factors from local_features.

    Returns:
        (factors, warnings)
    """
    local_features = record.get("local_features") or []
    warnings: List[str] = []

    if not isinstance(local_features, list):
        return [], ["local_features is not a list."]

    factors = [
        normalize_local_feature(feature, idx)
        for idx, feature in enumerate(local_features)
        if isinstance(feature, dict)
    ]

    factors.sort(key=lambda item: (item.rank, -item.abs_shap_value))

    for factor in factors:
        if not factor.direction_consistent:
            warnings.append(
                f"{factor.factor_id}: source direction {factor.source_direction!r} "
                f"does not match SHAP-derived direction {factor.direction!r}. "
                "Using SHAP-derived direction."
            )

    return factors, warnings


def split_risk_factors(
    factors: List[IRFeatureFactor],
) -> Tuple[List[IRFeatureFactor], List[IRFeatureFactor]]:
    """
    Split visible feature factors into increasing/decreasing risk factors.

    Only factors with llm_visible=True are included here because these lists are
    used by the LLM input contract.
    """
    increasing = [
        factor for factor in factors
        if factor.direction == "increases_risk" and factor.llm_visible
    ]

    decreasing = [
        factor for factor in factors
        if factor.direction == "decreases_risk" and factor.llm_visible
    ]

    increasing.sort(key=lambda item: (-item.abs_shap_value, item.rank))
    decreasing.sort(key=lambda item: (-item.abs_shap_value, item.rank))

    return increasing, decreasing


# =============================================================================
# Concept summary builders
# =============================================================================

def build_concept_summaries(
    factors: List[IRFeatureFactor],
    max_concepts: int = DEFAULT_MAX_CONCEPT_SUMMARIES,
) -> List[IRConceptSummary]:
    """
    Group feature factors by concept.

    Concept direction is based on net SHAP value.
    Mixed direction flag is true when a concept contains both positive and
    negative contributing features.

    v1.1 policy:
        - feature-level sensitive/limited factors may be hidden from LLM
        - but they can still contribute to concept-level summaries
          if allowed_in_user_explanation != false
    """
    groups: Dict[str, List[IRFeatureFactor]] = defaultdict(list)

    for factor in factors:
        if is_factor_allowed_at_concept_level(factor):
            groups[factor.concept].append(factor)

    summaries: List[IRConceptSummary] = []

    for concept_id, concept_factors in groups.items():
        if not concept_factors:
            continue

        net_shap = sum(f.shap_value for f in concept_factors)
        total_abs = sum(f.abs_shap_value for f in concept_factors)

        positive_count = sum(
            1 for f in concept_factors if f.direction == "increases_risk"
        )
        negative_count = sum(
            1 for f in concept_factors if f.direction == "decreases_risk"
        )
        neutral_count = sum(
            1 for f in concept_factors if f.direction == "neutral"
        )

        direction = direction_from_shap(net_shap)
        strength = strength_from_abs_shap(total_abs)

        has_mixed_directions = positive_count > 0 and negative_count > 0

        concept_factors_sorted = sorted(
            concept_factors,
            key=lambda item: (-item.abs_shap_value, item.rank),
        )

        display_name = first_present_value(
            concept_factors_sorted[0].concept_display_name
            if concept_factors_sorted
            else None,
            concept_display_name(concept_id),
        )

        claimable = not has_mixed_directions and direction != "neutral"

        summary = IRConceptSummary(
            concept_id=concept_id,
            display_name=str(display_name),
            net_shap_value=round_float(net_shap) or 0.0,
            total_abs_shap_value=round_float(total_abs) or 0.0,
            direction=direction,
            strength=strength,
            feature_count=len(concept_factors),
            positive_feature_count=positive_count,
            negative_feature_count=negative_count,
            neutral_feature_count=neutral_count,
            has_mixed_directions=has_mixed_directions,
            top_factor_ids=[f.factor_id for f in concept_factors_sorted[:3]],
            top_feature_display_names=[
                f.display_name for f in concept_factors_sorted[:3]
            ],
            llm_visible=True,
            claimable=claimable,
            safe_phrase=make_safe_phrase_for_direction(str(display_name), direction),
            source_claim_ids=[],
        )

        summaries.append(summary)

    summaries.sort(
        key=lambda item: (-item.total_abs_shap_value, item.concept_id)
    )

    return summaries[:max_concepts]


# =============================================================================
# Allowed claim builders
# =============================================================================

def make_evidence_ref(
    ref_type: str,
    ref_id: str,
    field: Optional[str] = None,
    value: Any = None,
) -> IREvidenceRef:
    return IREvidenceRef(
        ref_type=ref_type,
        ref_id=ref_id,
        field=field,
        value=value,
    )


def make_truth_condition(
    field: str,
    operator: str,
    value: Any,
) -> IRTruthCondition:
    return IRTruthCondition(
        field=field,
        operator=operator,
        value=value,
    )


def build_prediction_allowed_claims(
    prediction: IRPredictionSummary,
) -> List[IRAllowedClaim]:
    """Build allowed claims about model prediction."""
    claims: List[IRAllowedClaim] = []

    claims.append(
        IRAllowedClaim(
            claim_id="claim_prediction_label",
            claim_type="prediction_label",
            subject_type="prediction",
            subject_id="prediction",
            predicate="equals",
            object=prediction.predicted_label,
            direction=None,
            strength=None,
            natural_language_template=(
                f"Mô hình dự đoán khách hàng thuộc nhóm {prediction.predicted_label}."
            ),
            evidence_refs=[
                make_evidence_ref(
                    ref_type="prediction_summary",
                    ref_id="prediction",
                    field="predicted_label",
                    value=prediction.predicted_label,
                )
            ],
            truth_condition=make_truth_condition(
                field="prediction_summary.predicted_label",
                operator="equals",
                value=prediction.predicted_label,
            ),
            severity_if_contradicted="high",
        )
    )

    claims.append(
        IRAllowedClaim(
            claim_id="claim_probability_threshold_comparison",
            claim_type="probability_threshold_comparison",
            subject_type="prediction",
            subject_id="prediction",
            predicate=prediction.threshold_comparison,
            object=prediction.threshold,
            direction=None,
            strength=None,
            natural_language_template=(
                f"Xác suất dự đoán là {prediction.probability_percent_display}, "
                f"so với ngưỡng {prediction.threshold_percent_display}."
            ),
            evidence_refs=[
                make_evidence_ref(
                    ref_type="prediction_summary",
                    ref_id="prediction",
                    field="probability",
                    value=prediction.probability,
                ),
                make_evidence_ref(
                    ref_type="prediction_summary",
                    ref_id="prediction",
                    field="threshold",
                    value=prediction.threshold,
                ),
            ],
            truth_condition=make_truth_condition(
                field="prediction_summary.threshold_comparison",
                operator="equals",
                value=prediction.threshold_comparison,
            ),
            severity_if_contradicted="high",
        )
    )

    if prediction.has_ground_truth:
        claims.append(
            IRAllowedClaim(
                claim_id="claim_true_label_available",
                claim_type="true_label_available",
                subject_type="ground_truth",
                subject_id="true_label",
                predicate="equals",
                object=prediction.true_label_text,
                direction=None,
                strength=None,
                natural_language_template=(
                    f"Nhãn thật của mẫu đánh giá này là {prediction.true_label_text}."
                ),
                evidence_refs=[
                    make_evidence_ref(
                        ref_type="prediction_summary",
                        ref_id="prediction",
                        field="true_label_text",
                        value=prediction.true_label_text,
                    )
                ],
                truth_condition=make_truth_condition(
                    field="prediction_summary.true_label_text",
                    operator="equals",
                    value=prediction.true_label_text,
                ),
                severity_if_contradicted="medium",
            )
        )

    return claims


def build_feature_allowed_claims(
    factors: List[IRFeatureFactor],
) -> List[IRAllowedClaim]:
    """Build feature-level contribution claims."""
    claims: List[IRAllowedClaim] = []

    visible_claimable_factors = [
        factor
        for factor in factors
        if factor.claimable and factor.llm_visible and factor.direction != "neutral"
    ]

    for idx, factor in enumerate(visible_claimable_factors, start=1):
        claim_id = f"claim_feature_{idx:03d}"

        claim = IRAllowedClaim(
            claim_id=claim_id,
            claim_type="feature_contribution",
            subject_type="feature",
            subject_id=factor.feature_name,
            predicate="contributed_to",
            object=f"{factor.direction}_model_predicted_risk",
            direction=factor.direction,
            strength=factor.strength,
            natural_language_template=factor.safe_phrase
            or make_safe_phrase_for_direction(factor.display_name, factor.direction),
            evidence_refs=[
                make_evidence_ref(
                    ref_type="factor",
                    ref_id=factor.factor_id,
                    field="shap_value",
                    value=factor.shap_value,
                )
            ],
            truth_condition=make_truth_condition(
                field=f"feature_factors.{factor.factor_id}.direction",
                operator="equals",
                value=factor.direction,
            ),
            severity_if_contradicted="high",
        )

        claims.append(claim)
        factor.source_claim_ids.append(claim_id)

    return claims


def build_concept_allowed_claims(
    concepts: List[IRConceptSummary],
) -> List[IRAllowedClaim]:
    """Build concept-level contribution claims."""
    claims: List[IRAllowedClaim] = []

    visible_claimable_concepts = [
        concept
        for concept in concepts
        if concept.claimable and concept.llm_visible and concept.direction != "neutral"
    ]

    for idx, concept in enumerate(visible_claimable_concepts, start=1):
        claim_id = f"claim_concept_{idx:03d}"

        claim = IRAllowedClaim(
            claim_id=claim_id,
            claim_type="concept_contribution",
            subject_type="concept",
            subject_id=concept.concept_id,
            predicate="contributed_to",
            object=f"{concept.direction}_model_predicted_risk",
            direction=concept.direction,
            strength=concept.strength,
            natural_language_template=concept.safe_phrase
            or make_safe_phrase_for_direction(concept.display_name, concept.direction),
            evidence_refs=[
                make_evidence_ref(
                    ref_type="concept_summary",
                    ref_id=concept.concept_id,
                    field="direction",
                    value=concept.direction,
                )
            ],
            truth_condition=make_truth_condition(
                field=f"concept_summaries.{concept.concept_id}.direction",
                operator="equals",
                value=concept.direction,
            ),
            severity_if_contradicted="high",
        )

        claims.append(claim)
        concept.source_claim_ids.append(claim_id)

    return claims


def build_method_allowed_claims() -> List[IRAllowedClaim]:
    """Build method/boundary claims that LLM is allowed and encouraged to say."""
    return [
        IRAllowedClaim(
            claim_id="claim_evidence_basis_shap",
            claim_type="evidence_basis",
            subject_type="xai_method",
            subject_id="SHAP",
            predicate="is_based_on",
            object="local_shap_contributions",
            direction=None,
            strength=None,
            natural_language_template=(
                "Giải thích này dựa trên đóng góp SHAP cục bộ cho riêng dự đoán này."
            ),
            evidence_refs=[
                make_evidence_ref(
                    ref_type="xai_summary",
                    ref_id="xai_summary",
                    field="method",
                    value="SHAP",
                )
            ],
            truth_condition=make_truth_condition(
                field="xai_summary.method",
                operator="equals",
                value="SHAP",
            ),
            severity_if_contradicted="medium",
        ),
        IRAllowedClaim(
            claim_id="claim_non_causality_limitation",
            claim_type="non_causality_limitation",
            subject_type="xai_method",
            subject_id="SHAP",
            predicate="does_not_prove",
            object="real_world_causality",
            direction=None,
            strength=None,
            natural_language_template=(
                "Các yếu tố này mô tả đóng góp vào dự đoán của mô hình, "
                "không chứng minh quan hệ nhân quả ngoài thực tế."
            ),
            evidence_refs=[
                make_evidence_ref(
                    ref_type="xai_summary",
                    ref_id="xai_summary",
                    field="method",
                    value="SHAP",
                )
            ],
            truth_condition=make_truth_condition(
                field="xai_summary.method",
                operator="equals",
                value="SHAP",
            ),
            severity_if_contradicted="high",
        ),
    ]


def build_allowed_claims(
    prediction: IRPredictionSummary,
    feature_factors: List[IRFeatureFactor],
    concept_summaries: List[IRConceptSummary],
) -> List[IRAllowedClaim]:
    """Build all allowed claims for one IR record."""
    claims: List[IRAllowedClaim] = []
    claims.extend(build_prediction_allowed_claims(prediction))
    claims.extend(build_feature_allowed_claims(feature_factors))
    claims.extend(build_concept_allowed_claims(concept_summaries))
    claims.extend(build_method_allowed_claims())
    return claims


# =============================================================================
# Forbidden claim builders
# =============================================================================

def build_forbidden_claims() -> List[IRForbiddenClaim]:
    """
    Build standard forbidden claims for all IR records.

    These rules prevent LLM hallucination, overclaiming, direction reversal, and
    unsafe conversion of local explanation into global explanation.
    """
    return [
        IRForbiddenClaim(
            forbidden_id="forbidden_no_certainty",
            rule_type="no_certainty",
            severity="high",
            natural_language_rule=(
                "Không được khẳng định khách hàng chắc chắn sẽ vỡ nợ hoặc "
                "chắc chắn sẽ trả nợ."
            ),
            reason=(
                "Mô hình chỉ tạo xác suất dự đoán và nhãn theo ngưỡng, "
                "không tạo kết luận chắc chắn về tương lai."
            ),
            forbidden_patterns=[
                "chắc chắn sẽ vỡ nợ",
                "chắc chắn không trả được nợ",
                "đảm bảo sẽ vỡ nợ",
                "đảm bảo sẽ trả nợ",
                "definitely default",
                "guaranteed to default",
            ],
        ),
        IRForbiddenClaim(
            forbidden_id="forbidden_no_real_world_causality",
            rule_type="no_real_world_causality",
            severity="high",
            natural_language_rule=(
                "Không được nói rằng một feature gây ra vỡ nợ hoặc gây ra hành vi "
                "trả nợ ngoài thực tế."
            ),
            reason=(
                "SHAP mô tả đóng góp vào dự đoán của mô hình, không chứng minh "
                "quan hệ nhân quả ngoài thực tế."
            ),
            forbidden_patterns=[
                "gây ra vỡ nợ",
                "nguyên nhân thực tế khiến khách hàng vỡ nợ",
                "caused the default",
                "causes default",
            ],
        ),
        IRForbiddenClaim(
            forbidden_id="forbidden_no_unsupported_feature_or_concept",
            rule_type="no_unsupported_feature_or_concept",
            severity="high",
            natural_language_rule=(
                "Không được nhắc feature hoặc concept không có trong Explanation IR "
                "của trường hợp này."
            ),
            reason=(
                "Giải thích phải bám vào evidence của dự đoán cục bộ."
            ),
            forbidden_patterns=[],
        ),
        IRForbiddenClaim(
            forbidden_id="forbidden_no_direction_reversal",
            rule_type="no_direction_reversal",
            severity="high",
            natural_language_rule=(
                "Không được nói một yếu tố làm tăng rủi ro nếu IR nói nó làm giảm "
                "rủi ro, hoặc ngược lại."
            ),
            reason=(
                "Đảo chiều đóng góp phá vỡ faithfulness với SHAP evidence."
            ),
            forbidden_patterns=[],
        ),
        IRForbiddenClaim(
            forbidden_id="forbidden_no_unsupported_magnitude",
            rule_type="no_unsupported_magnitude",
            severity="medium",
            natural_language_rule=(
                "Không được mô tả yếu tố yếu hoặc trung bình là quyết định, "
                "áp đảo, hoặc là lý do duy nhất nếu IR không hỗ trợ mức độ đó."
            ),
            reason=(
                "Cách diễn đạt về độ mạnh phải khớp với strength từ SHAP."
            ),
            forbidden_patterns=[
                "yếu tố quyết định",
                "yếu tố áp đảo",
                "lý do duy nhất",
                "dominant factor",
                "decisive factor",
                "only reason",
            ],
        ),
        IRForbiddenClaim(
            forbidden_id="forbidden_no_sensitive_or_hidden_feature_exposure",
            rule_type="no_sensitive_or_hidden_feature_exposure",
            severity="medium",
            natural_language_rule=(
                "Không được nhắc trực tiếp feature nhạy cảm, feature bị ẩn, "
                "hoặc feature chỉ được phép hiển thị giới hạn."
            ),
            reason=(
                "Feature registry có thể đánh dấu một số feature là sensitive "
                "hoặc limited cho user-facing explanation."
            ),
            forbidden_patterns=[],
        ),
        IRForbiddenClaim(
            forbidden_id="forbidden_no_raw_data_overclaim",
            rule_type="no_raw_data_overclaim",
            severity="medium",
            natural_language_rule=(
                "Không được nói mô hình trực tiếp dùng raw table khi mô hình dùng "
                "feature đã tiền xử lý."
            ),
            reason=(
                "Mô hình hoạt động trên model-ready features được sinh từ raw data, "
                "không đọc raw table trực tiếp."
            ),
            forbidden_patterns=[
                "mô hình trực tiếp đọc raw data",
                "raw table gây ra dự đoán",
                "the model directly read the raw data",
            ],
        ),
        IRForbiddenClaim(
            forbidden_id="forbidden_no_global_generalization_from_local_explanation",
            rule_type="no_global_generalization_from_local_explanation",
            severity="high",
            natural_language_rule=(
                "Không được khái quát hóa giải thích cục bộ này thành nhận định "
                "toàn cục cho mọi khách hàng."
            ),
            reason=(
                "IR này được tạo từ SHAP cục bộ cho một khách hàng/một dự đoán."
            ),
            forbidden_patterns=[
                "mô hình luôn dựa vào",
                "đối với mọi khách hàng",
                "trong mọi trường hợp",
                "the model always relies on",
                "for all customers",
            ],
        ),
    ]


# =============================================================================
# LLM input contract and validation contract
# =============================================================================

def factor_to_llm_item(factor: IRFeatureFactor) -> Dict[str, Any]:
    """Convert factor to compact LLM input item."""
    return {
        "factor_id": factor.factor_id,
        "feature_name": factor.feature_name,
        "display_name": factor.display_name,
        "concept": factor.concept,
        "concept_display_name": getattr(factor, "concept_display_name", None),
        "direction": factor.direction,
        "strength": factor.strength,
        "safe_phrase": factor.safe_phrase,
        "source_claim_ids": factor.source_claim_ids,
        "value_type": getattr(factor, "value_type", None),
        "unit": getattr(factor, "unit", None),
    }


def concept_to_llm_item(concept: IRConceptSummary) -> Dict[str, Any]:
    """Convert concept summary to compact LLM input item."""
    return {
        "concept_id": concept.concept_id,
        "display_name": concept.display_name,
        "direction": concept.direction,
        "strength": concept.strength,
        "has_mixed_directions": concept.has_mixed_directions,
        "safe_phrase": concept.safe_phrase,
        "source_claim_ids": concept.source_claim_ids,
    }


def build_llm_input_contract(
    prediction: IRPredictionSummary,
    increasing_factors: List[IRFeatureFactor],
    decreasing_factors: List[IRFeatureFactor],
    concept_summaries: List[IRConceptSummary],
    allowed_claims: List[IRAllowedClaim],
    forbidden_claims: List[IRForbiddenClaim],
    max_factors_per_direction: int = DEFAULT_MAX_FEATURE_FACTORS_PER_DIRECTION,
    max_concepts: int = DEFAULT_MAX_CONCEPT_SUMMARIES,
) -> IRLLMInputContract:
    """
    Build compact contract for Batch I.

    Batch I should use this contract instead of reading the entire IR record
    blindly.

    v1.1:
        - expose only feature-level factors that are llm_visible
        - expose only concepts that are claimable and not mixed
        - do not expose evaluation-only true_label claims
    """
    visible_allowed_claim_ids = [
        claim.claim_id
        for claim in allowed_claims
        if is_claim_visible_to_llm(claim)
    ]

    visible_main_concepts = [
        concept_to_llm_item(c)
        for c in concept_summaries
        if c.llm_visible and c.claimable and not c.has_mixed_directions
    ][:max_concepts]

    return IRLLMInputContract(
        task=(
            "Sinh giải thích cục bộ trung thực bằng tiếng Việt, chỉ sử dụng "
            "các claim được phép và tuân thủ toàn bộ luật cấm."
        ),
        language_target=DEFAULT_LLM_TARGET_LANGUAGE,
        style=DEFAULT_LLM_STYLE,
        audience=DEFAULT_LLM_AUDIENCE,
        prediction={
            "predicted_label": prediction.predicted_label,
            "predicted_class": prediction.predicted_class,
            "probability": prediction.probability,
            "probability_display": prediction.probability_display,
            "probability_percent_display": prediction.probability_percent_display,
            "threshold": prediction.threshold,
            "threshold_display": prediction.threshold_display,
            "threshold_percent_display": prediction.threshold_percent_display,
            "threshold_comparison": prediction.threshold_comparison,
        },
        main_risk_increasing_factors=[
            factor_to_llm_item(f)
            for f in increasing_factors[:max_factors_per_direction]
        ],
        main_risk_decreasing_factors=[
            factor_to_llm_item(f)
            for f in decreasing_factors[:max_factors_per_direction]
        ],
        main_concepts=visible_main_concepts,
        allowed_claim_ids=visible_allowed_claim_ids,
        forbidden_rule_ids=[item.forbidden_id for item in forbidden_claims],
        must_include=[
            "prediction_label",
            "main_risk_increasing_factors_or_concepts",
            "main_risk_decreasing_factors_if_available",
            "non_causality_limitation",
        ],
        must_not=[
            "Không khẳng định chắc chắn khách hàng sẽ vỡ nợ hoặc chắc chắn sẽ trả nợ.",
            "Không khẳng định quan hệ nhân quả ngoài thực tế.",
            "Không nhắc feature hoặc concept không có trong IR.",
            "Không đảo chiều đóng góp rủi ro.",
            "Không khái quát hóa giải thích cục bộ này cho toàn bộ khách hàng.",
            "Không nhắc trực tiếp feature nhạy cảm hoặc chỉ được phép hiển thị giới hạn.",
        ],
        required_output_sections=[
            "prediction",
            "main_risk_drivers",
            "risk_reducing_factors",
            "limitations",
        ],
    )


def build_validation_contract(
    allowed_claims: List[IRAllowedClaim],
    forbidden_claims: List[IRForbiddenClaim],
    feature_factors: List[IRFeatureFactor],
    concept_summaries: List[IRConceptSummary],
    prediction: IRPredictionSummary,
) -> IRValidationContract:
    """
    Build validation contract for Batch J.

    This lets the Faithfulness Validator compare extracted LLM claims against
    allowed subjects, directions, and forbidden rules without re-deriving all
    logic from scratch.
    """
    claimable_features = [
        factor.feature_name
        for factor in feature_factors
        if factor.claimable and factor.llm_visible
    ]

    claimable_concepts = [
        concept.concept_id
        for concept in concept_summaries
        if concept.claimable and concept.llm_visible
    ]

    disallowed_features = [
        factor.feature_name
        for factor in feature_factors
        if not factor.claimable or not factor.llm_visible
    ]

    disallowed_concepts = [
        concept.concept_id
        for concept in concept_summaries
        if not concept.claimable or not concept.llm_visible
    ]

    allowed_directions_by_subject: Dict[str, str] = {}
    allowed_strength_by_subject: Dict[str, str] = {}

    for factor in feature_factors:
        if factor.claimable and factor.llm_visible and factor.direction != "neutral":
            allowed_directions_by_subject[factor.feature_name] = factor.direction
            allowed_strength_by_subject[factor.feature_name] = factor.strength

    for concept in concept_summaries:
        if concept.claimable and concept.llm_visible and concept.direction != "neutral":
            allowed_directions_by_subject[concept.concept_id] = concept.direction
            allowed_strength_by_subject[concept.concept_id] = concept.strength

    rules = [
        IRValidationRule(
            rule_id="val_prediction_label_must_match",
            rule_type="prediction_label_must_match",
            severity="high",
            expected=prediction.predicted_label,
            description=(
                "Any extracted prediction-label claim must match the predicted "
                "label in prediction_summary."
            ),
        ),
        IRValidationRule(
            rule_id="val_direction_must_match",
            rule_type="direction_must_match",
            severity="high",
            expected=allowed_directions_by_subject,
            description=(
                "Any extracted feature/concept direction claim must match the "
                "direction allowed by this IR."
            ),
        ),
        IRValidationRule(
            rule_id="val_strength_must_not_overclaim",
            rule_type="strength_must_not_overclaim",
            severity="medium",
            expected=allowed_strength_by_subject,
            description=(
                "Any extracted magnitude or strength claim must not exceed the "
                "strength assigned by this IR."
            ),
        ),
        IRValidationRule(
            rule_id="val_subject_must_be_claimable",
            rule_type="subject_must_be_claimable",
            severity="high",
            expected={
                "features": claimable_features,
                "concepts": claimable_concepts,
            },
            description=(
                "Any extracted feature or concept must be present and claimable "
                "in this IR."
            ),
        ),
    ]

    return IRValidationContract(
        allowed_claim_ids=[
            claim.claim_id
            for claim in allowed_claims
            if is_claim_visible_to_llm(claim)
        ],
        forbidden_rule_ids=[item.forbidden_id for item in forbidden_claims],
        claim_validation_rules=rules,
        claimable_subjects={
            "features": claimable_features,
            "concepts": claimable_concepts,
        },
        disallowed_subjects={
            "features": disallowed_features,
            "concepts": disallowed_concepts,
        },
        allowed_directions_by_subject=allowed_directions_by_subject,
        allowed_strength_by_subject=allowed_strength_by_subject,
    )


# =============================================================================
# Evidence trace and quality
# =============================================================================

def build_evidence_trace(
    record: Dict[str, Any],
    source_file: str | Path,
    source_evidence_id: str,
) -> IREvidenceTrace:
    """
    Build evidence trace block.

    Batch G stores:
        quality.passed_additivity_check
        quality.mapping_missing_count
    """
    local_features = record.get("local_features") or []
    top_positive = record.get("top_positive_features") or []
    top_negative = record.get("top_negative_features") or []
    shap = record.get("shap") or {}
    quality = record.get("quality") or {}

    passed_additivity_check = first_present_value(
        shap.get("passed_additivity_check"),
        quality.get("passed_additivity_check"),
    )

    if passed_additivity_check is None:
        additivity_error = safe_float(shap.get("additivity_error"))
        tolerance = safe_float(quality.get("additivity_tolerance"), default=1e-6)

        if additivity_error is not None and tolerance is not None:
            passed_additivity_check = additivity_error <= tolerance

    return IREvidenceTrace(
        source_file=str(source_file),
        source_evidence_id=source_evidence_id,
        source_batch=SOURCE_BATCH_NAME,
        source_local_feature_count=len(local_features)
        if isinstance(local_features, list)
        else 0,
        source_top_positive_count=len(top_positive)
        if isinstance(top_positive, list)
        else 0,
        source_top_negative_count=len(top_negative)
        if isinstance(top_negative, list)
        else 0,
        source_additivity_passed=passed_additivity_check,
        source_mapping_missing_count=safe_int(
            quality.get("mapping_missing_count")
            if isinstance(quality, dict)
            else None
        ),
    )


def build_quality(
    validation_status: str,
    validation_passed: bool,
    warnings: List[str],
    errors: List[str],
    allowed_claims: List[IRAllowedClaim],
    forbidden_claims: List[IRForbiddenClaim],
    feature_factors: List[IRFeatureFactor],
    increasing_factors: List[IRFeatureFactor],
    decreasing_factors: List[IRFeatureFactor],
    concept_summaries: List[IRConceptSummary],
    has_llm_input_contract: bool,
    has_validation_contract: bool,
) -> IRRecordQuality:
    """Build record quality block."""
    return IRRecordQuality(
        status=validation_status,
        ir_validation_passed=validation_passed,
        warnings=warnings,
        errors=errors,
        allowed_claim_count=len(allowed_claims),
        forbidden_claim_count=len(forbidden_claims),
        feature_factor_count=len(feature_factors),
        risk_increasing_factor_count=len(increasing_factors),
        risk_decreasing_factor_count=len(decreasing_factors),
        concept_summary_count=len(concept_summaries),
        has_llm_input_contract=has_llm_input_contract,
        has_validation_contract=has_validation_contract,
    )


# =============================================================================
# Main single-record builder
# =============================================================================

def build_single_ir_record(
    record: Dict[str, Any],
    record_index: int,
    run_mode: str,
    has_ground_truth: bool,
    source_file: str | Path,
) -> Tuple[ExplanationIRRecord, List[str], List[str]]:
    """
    Build one ExplanationIRRecord from one XAI evidence record.

    Returns:
        (ir_record, warnings, errors)
    """
    warnings: List[str] = []
    errors: List[str] = []

    source_evidence_id = get_evidence_id(record, record_index)
    ir_id = make_ir_id(source_evidence_id)
    trace_id = make_trace_id(source_evidence_id)

    record_run_mode = get_run_mode_from_record(record, run_mode)
    record_has_ground_truth = get_has_ground_truth_from_record(
        record,
        has_ground_truth,
    )

    if record_run_mode != run_mode:
        warnings.append(
            f"record run_mode={record_run_mode!r} differs from builder "
            f"run_mode={run_mode!r}."
        )

    if record_has_ground_truth != has_ground_truth:
        warnings.append(
            f"record has_ground_truth={record_has_ground_truth!r} differs from "
            f"builder has_ground_truth={has_ground_truth!r}."
        )

    model = build_model_info(record)
    customer = build_customer_info(record)
    prediction = build_prediction_summary(record, has_ground_truth)
    xai_summary = build_xai_summary(record)

    feature_factors, factor_warnings = build_feature_factors(record)
    warnings.extend(factor_warnings)

    increasing_factors, decreasing_factors = split_risk_factors(feature_factors)
    concept_summaries = build_concept_summaries(feature_factors)

    allowed_claims = build_allowed_claims(
        prediction=prediction,
        feature_factors=feature_factors,
        concept_summaries=concept_summaries,
    )

    forbidden_claims = build_forbidden_claims()

    llm_input_contract = build_llm_input_contract(
        prediction=prediction,
        increasing_factors=increasing_factors,
        decreasing_factors=decreasing_factors,
        concept_summaries=concept_summaries,
        allowed_claims=allowed_claims,
        forbidden_claims=forbidden_claims,
    )

    validation_contract = build_validation_contract(
        allowed_claims=allowed_claims,
        forbidden_claims=forbidden_claims,
        feature_factors=feature_factors,
        concept_summaries=concept_summaries,
        prediction=prediction,
    )

    evidence_trace = build_evidence_trace(
        record=record,
        source_file=source_file,
        source_evidence_id=source_evidence_id,
    )

    metadata = IRMetadata()

    quality = build_quality(
        validation_status=RECORD_STATUS_PASSED,
        validation_passed=True,
        warnings=warnings,
        errors=errors,
        allowed_claims=allowed_claims,
        forbidden_claims=forbidden_claims,
        feature_factors=feature_factors,
        increasing_factors=increasing_factors,
        decreasing_factors=decreasing_factors,
        concept_summaries=concept_summaries,
        has_llm_input_contract=True,
        has_validation_contract=True,
    )

    created_at = utc_now_iso()

    ir_record = ExplanationIRRecord(
        ir_id=ir_id,
        source_evidence_id=source_evidence_id,
        trace_id=trace_id,
        run_mode=run_mode,
        has_ground_truth=has_ground_truth,
        ir_schema_version=IR_SCHEMA_VERSION,
        created_at=created_at,
        source_batch=SOURCE_BATCH_NAME,
        model=model,
        customer=customer,
        prediction_summary=prediction,
        xai_summary=xai_summary,
        feature_factors=feature_factors,
        risk_increasing_factors=increasing_factors,
        risk_decreasing_factors=decreasing_factors,
        concept_summaries=concept_summaries,
        allowed_claims=allowed_claims,
        forbidden_claims=forbidden_claims,
        llm_input_contract=llm_input_contract,
        validation_contract=validation_contract,
        evidence_trace=evidence_trace,
        quality=quality,
        metadata=metadata,
    )

    validation = validate_explanation_ir_record(ir_record)
    warnings.extend(validation.warnings)
    errors.extend(validation.errors)

    final_quality = build_quality(
        validation_status=validation.status,
        validation_passed=validation.passed,
        warnings=warnings,
        errors=errors,
        allowed_claims=allowed_claims,
        forbidden_claims=forbidden_claims,
        feature_factors=feature_factors,
        increasing_factors=increasing_factors,
        decreasing_factors=decreasing_factors,
        concept_summaries=concept_summaries,
        has_llm_input_contract=True,
        has_validation_contract=True,
    )

    ir_record.quality = final_quality

    return ir_record, warnings, errors


# =============================================================================
# Summary DataFrame
# =============================================================================

def top_factor_name(factors: List[IRFeatureFactor]) -> Optional[str]:
    if not factors:
        return None
    return factors[0].display_name


def top_factor_concept(factors: List[IRFeatureFactor]) -> Optional[str]:
    if not factors:
        return None
    return factors[0].concept


def top_factor_strength(factors: List[IRFeatureFactor]) -> Optional[str]:
    if not factors:
        return None
    return factors[0].strength


def build_ir_summary_dataframe(
    ir_records: List[ExplanationIRRecord],
) -> pd.DataFrame:
    """
    Build flat summary DataFrame for debug and reporting.
    """
    rows: List[Dict[str, Any]] = []

    for record in ir_records:
        rows.append(
            {
                "ir_id": record.ir_id,
                "source_evidence_id": record.source_evidence_id,
                "trace_id": record.trace_id,
                "SK_ID_CURR": record.customer.SK_ID_CURR,
                "row_index": record.customer.row_index,
                "case_type": record.customer.case_type,
                "selection_rank": record.customer.selection_rank,
                "run_mode": record.run_mode,
                "has_ground_truth": record.has_ground_truth,
                "model_name": record.model.model_name,
                "model_version": record.model.model_version,
                "model_family": record.model.model_family,
                "dataset_branch": record.model.dataset_branch,
                "feature_count": record.model.feature_count,
                "predicted_label": record.prediction_summary.predicted_label,
                "predicted_class": record.prediction_summary.predicted_class,
                "probability": record.prediction_summary.probability,
                "probability_display": record.prediction_summary.probability_display,
                "probability_percent_display": record.prediction_summary.probability_percent_display,
                "threshold": record.prediction_summary.threshold,
                "threshold_comparison": record.prediction_summary.threshold_comparison,
                "true_label": record.prediction_summary.true_label,
                "true_label_text": record.prediction_summary.true_label_text,
                "xai_method": record.xai_summary.method,
                "explainer_type": record.xai_summary.explainer_type,
                "output_space": record.xai_summary.output_space,
                "passed_additivity_check": record.xai_summary.passed_additivity_check,
                "additivity_error": record.xai_summary.additivity_error,
                "feature_factor_count": len(record.feature_factors),
                "feature_llm_visible_count": sum(
                    1 for f in record.feature_factors if f.llm_visible
                ),
                "feature_claimable_count": sum(
                    1 for f in record.feature_factors if f.claimable
                ),
                "hidden_feature_count": sum(
                    1 for f in record.feature_factors if not f.llm_visible
                ),
                "sensitive_feature_count": sum(
                    1
                    for f in record.feature_factors
                    if getattr(f, "sensitive", None) is True
                ),
                "limited_feature_count": sum(
                    1
                    for f in record.feature_factors
                    if getattr(f, "allowed_in_user_explanation", None) == "limited"
                ),
                "risk_increasing_factor_count": len(record.risk_increasing_factors),
                "risk_decreasing_factor_count": len(record.risk_decreasing_factors),
                "concept_summary_count": len(record.concept_summaries),
                "allowed_claim_count": len(record.allowed_claims),
                "forbidden_claim_count": len(record.forbidden_claims),
                "top_increasing_factor": top_factor_name(record.risk_increasing_factors),
                "top_increasing_concept": top_factor_concept(record.risk_increasing_factors),
                "top_increasing_strength": top_factor_strength(record.risk_increasing_factors),
                "top_decreasing_factor": top_factor_name(record.risk_decreasing_factors),
                "top_decreasing_concept": top_factor_concept(record.risk_decreasing_factors),
                "top_decreasing_strength": top_factor_strength(record.risk_decreasing_factors),
                "validation_status": record.quality.status,
                "ir_validation_passed": record.quality.ir_validation_passed,
                "warning_count": len(record.quality.warnings),
                "error_count": len(record.quality.errors),
            }
        )

    return pd.DataFrame(rows)


# =============================================================================
# Public batch builder
# =============================================================================

def build_explanation_ir_records(
    evidence_records: List[Dict[str, Any]],
    run_mode: str,
    has_ground_truth: bool,
    source_file: str | Path,
) -> ExplanationIRBuildResult:
    """
    Build Explanation IR records from Batch G evidence records.
    """
    ir_records: List[ExplanationIRRecord] = []
    ir_record_dicts: List[Dict[str, Any]] = []
    warnings: List[str] = []
    errors: List[str] = []

    for idx, evidence_record in enumerate(evidence_records):
        try:
            ir_record, record_warnings, record_errors = build_single_ir_record(
                record=evidence_record,
                record_index=idx,
                run_mode=run_mode,
                has_ground_truth=has_ground_truth,
                source_file=source_file,
            )

            ir_records.append(ir_record)
            ir_record_dicts.append(dataclass_to_dict(ir_record))

            for warning in record_warnings:
                warnings.append(f"{ir_record.ir_id}: {warning}")

            for error in record_errors:
                errors.append(f"{ir_record.ir_id}: {error}")

        except Exception as exc:
            error_message = (
                f"record_index={idx}: failed to build Explanation IR record. "
                f"Error: {exc}"
            )
            errors.append(error_message)

    summary_df = build_ir_summary_dataframe(ir_records)

    return ExplanationIRBuildResult(
        ir_records=ir_records,
        ir_record_dicts=ir_record_dicts,
        summary_df=summary_df,
        warnings=warnings,
        errors=errors,
    )