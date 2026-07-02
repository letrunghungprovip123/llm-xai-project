"""
Schema utilities for Batch H - Concept-aware Explanation IR Layer.

This module defines the internal schema used to transform Batch G XAI evidence
into Explanation IR.

The IR is designed for two downstream batches:
- Batch I: LLM Explanation Layer
- Batch J: Faithfulness Validator

Important:
- Natural-language strings in this layer are controlled templates.
- Every allowed claim should be traceable to evidence and truth conditions.
- This layer does not generate final user-facing explanation text.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ml.scripts.explanation_ir_layer.config import (
    BATCH_NAME,
    BATCH_SHORT_NAME,
    SOURCE_BATCH_NAME,
    IR_SCHEMA_VERSION,
    BUILDER_VERSION,
    CLAIM_SCOPE_LOCAL_CASE,
    STRONG_ABS_SHAP_THRESHOLD,
    MODERATE_ABS_SHAP_THRESHOLD,
    NEUTRAL_SHAP_EPSILON,
    RECORD_STATUS_FAILED,
    RECORD_STATUS_PASSED,
    RECORD_STATUS_WARNING,
)


# =============================================================================
# Basic helpers
# =============================================================================

def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Convert value to float safely.

    Returns default if conversion fails or value is None.
    """
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """
    Convert value to int safely.

    Returns default if conversion fails or value is None.
    """
    if value is None:
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def round_float(value: Any, digits: int = 10) -> Optional[float]:
    """
    Convert to float and round for stable JSON output.
    """
    converted = safe_float(value)

    if converted is None:
        return None

    return round(converted, digits)


def format_probability(value: Any, digits: int = 4) -> Optional[str]:
    """
    Format a probability as decimal string.

    Example:
        0.73123 -> "0.7312"
    """
    converted = safe_float(value)

    if converted is None:
        return None

    return f"{converted:.{digits}f}"


def format_probability_percent(value: Any, digits: int = 2) -> Optional[str]:
    """
    Format a probability as percent string.

    Example:
        0.73123 -> "73.12%"
    """
    converted = safe_float(value)

    if converted is None:
        return None

    return f"{converted * 100:.{digits}f}%"


def label_text_from_class(value: Any) -> str:
    """
    Convert class label to business label text.

    1 -> high_default_risk
    0 -> low_default_risk
    None/unknown -> unknown_label
    """
    label = safe_int(value)

    if label == 1:
        return "high_default_risk"

    if label == 0:
        return "low_default_risk"

    return "unknown_label"


def threshold_comparison_from_probability(
    probability: Any,
    threshold: Any,
) -> str:
    """
    Return above/below threshold comparison label.
    """
    proba = safe_float(probability)
    th = safe_float(threshold)

    if proba is None or th is None:
        return "unknown_threshold_comparison"

    if proba >= th:
        return "above_or_equal_threshold"

    return "below_threshold"


def is_probability_above_threshold(
    probability: Any,
    threshold: Any,
) -> Optional[bool]:
    """
    Return True/False if comparable, else None.
    """
    proba = safe_float(probability)
    th = safe_float(threshold)

    if proba is None or th is None:
        return None

    return proba >= th


def direction_from_shap(
    shap_value: Any,
    epsilon: float = NEUTRAL_SHAP_EPSILON,
) -> str:
    """
    Convert SHAP value into risk contribution direction.

    In this project SHAP output is in probability space.

    shap_value > 0:
        increases_risk

    shap_value < 0:
        decreases_risk

    near zero:
        neutral
    """
    value = safe_float(shap_value, default=0.0)

    if value is None:
        return "neutral"

    if value > epsilon:
        return "increases_risk"

    if value < -epsilon:
        return "decreases_risk"

    return "neutral"


def strength_from_abs_shap(
    abs_shap_value: Any,
    strong_threshold: float = STRONG_ABS_SHAP_THRESHOLD,
    moderate_threshold: float = MODERATE_ABS_SHAP_THRESHOLD,
) -> str:
    """
    Convert absolute SHAP value into strength label.

    Default v1 rule:
        abs_shap >= 0.10 -> strong
        abs_shap >= 0.03 -> moderate
        else              -> weak
    """
    value = safe_float(abs_shap_value, default=0.0)

    if value is None:
        return "weak"

    if value >= strong_threshold:
        return "strong"

    if value >= moderate_threshold:
        return "moderate"

    return "weak"


def normalize_display_name(value: Any, fallback: str = "Unknown factor") -> str:
    """
    Normalize display name for safe templates.
    """
    if value is None:
        return fallback

    text = str(value).strip()

    if not text:
        return fallback

    return text


def make_safe_phrase_for_direction(
    subject_display_name: str,
    direction: str,
) -> str:
    """
    Build a controlled Vietnamese phrase for a contribution direction.

    This is not final explanation text. It is a safe template for Batch I.
    """
    name = normalize_display_name(subject_display_name)

    if direction == "increases_risk":
        return (
            f"{name} góp phần làm tăng rủi ro dự đoán của mô hình."
        )

    if direction == "decreases_risk":
        return (
            f"{name} góp phần làm giảm rủi ro dự đoán của mô hình."
        )

    return (
        f"{name} có đóng góp gần như trung tính đối với rủi ro dự đoán của mô hình."
    )


def dataclass_to_dict(obj: Any) -> Any:
    """
    Convert dataclass or nested object into JSON-safe dictionaries/lists.

    This function is intentionally conservative and does not serialize unknown
    object types beyond their primitive values.
    """
    if is_dataclass(obj):
        return dataclass_to_dict(asdict(obj))

    if isinstance(obj, dict):
        return {str(k): dataclass_to_dict(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [dataclass_to_dict(v) for v in obj]

    if isinstance(obj, tuple):
        return [dataclass_to_dict(v) for v in obj]

    return obj


# =============================================================================
# IR schema dataclasses
# =============================================================================

@dataclass
class IRModelInfo:
    model_name: str
    model_version: str
    model_family: str
    dataset_branch: Optional[str] = None
    feature_count: Optional[int] = None


@dataclass
class IRCustomerInfo:
    SK_ID_CURR: Optional[int]
    row_index: Optional[int]
    case_type: Optional[str] = None
    selection_rank: Optional[int] = None


@dataclass
class IRPredictionSummary:
    predicted_class: Optional[int]
    predicted_label: str
    probability: Optional[float]
    probability_display: Optional[str]
    probability_percent_display: Optional[str]
    threshold: Optional[float]
    threshold_display: Optional[str]
    threshold_percent_display: Optional[str]
    threshold_comparison: str
    is_above_threshold: Optional[bool]
    true_label: Optional[int]
    true_label_text: str
    has_ground_truth: bool


@dataclass
class IRXAISummary:
    method: str = "SHAP"
    explainer_type: Optional[str] = None
    output_space: Optional[str] = None
    base_value: Optional[float] = None
    model_output: Optional[float] = None
    shap_sum: Optional[float] = None
    reconstructed_output: Optional[float] = None
    additivity_error: Optional[float] = None
    passed_additivity_check: Optional[bool] = None
    faithfulness_basis: str = (
        "For local SHAP explanations, base_value + sum(shap_values) should "
        "approximately equal the model output in the configured output space."
    )


@dataclass
class IRFeatureFactor:
    """
    One normalized local feature contribution.

    v1.1 additions:
        - feature_value_source_field
        - concept_display_name
        - value_type
        - unit
        - sensitive
        - allowed_in_user_explanation
        - direction_prior
        - formatting_rule
        - contribution_percent_of_top_k_abs

    These fields are read from Batch G feature metadata and are used to decide
    whether a feature is safe to expose directly to the LLM/user.
    """

    factor_id: str
    rank: int
    feature_name: str
    raw_feature_name: Optional[str]
    display_name: str
    concept: str
    value: Any
    shap_value: float
    abs_shap_value: float
    direction: str
    strength: str
    llm_visible: bool = True
    claimable: bool = True
    evidence_source: str = "local_features"
    source_direction: Optional[str] = None
    direction_consistent: bool = True
    safe_phrase: Optional[str] = None
    source_claim_ids: List[str] = field(default_factory=list)

    # Batch G metadata / registry information
    feature_value_source_field: Optional[str] = None
    concept_display_name: Optional[str] = None
    value_type: Optional[str] = None
    unit: Optional[str] = None
    sensitive: Optional[bool] = None
    allowed_in_user_explanation: Optional[str] = None
    direction_prior: Optional[str] = None
    formatting_rule: Optional[str] = None
    contribution_percent_of_top_k_abs: Optional[float] = None


@dataclass
class IRConceptSummary:
    concept_id: str
    display_name: str
    net_shap_value: float
    total_abs_shap_value: float
    direction: str
    strength: str
    feature_count: int
    positive_feature_count: int
    negative_feature_count: int
    neutral_feature_count: int
    has_mixed_directions: bool
    top_factor_ids: List[str]
    top_feature_display_names: List[str]
    llm_visible: bool = True
    claimable: bool = True
    safe_phrase: Optional[str] = None
    source_claim_ids: List[str] = field(default_factory=list)


@dataclass
class IREvidenceRef:
    ref_type: str
    ref_id: str
    field: Optional[str] = None
    value: Any = None


@dataclass
class IRTruthCondition:
    field: str
    operator: str
    value: Any


@dataclass
class IRAllowedClaim:
    claim_id: str
    claim_type: str
    subject_type: str
    subject_id: str
    predicate: str
    object: Any
    natural_language_template: str
    evidence_refs: List[IREvidenceRef]
    truth_condition: IRTruthCondition
    claim_scope: str = CLAIM_SCOPE_LOCAL_CASE
    verdict_from_ir: bool = True
    claim_status: str = "allowed"
    direction: Optional[str] = None
    strength: Optional[str] = None
    severity_if_contradicted: str = "medium"


@dataclass
class IRForbiddenClaim:
    forbidden_id: str
    rule_type: str
    severity: str
    natural_language_rule: str
    reason: str
    forbidden_patterns: List[str] = field(default_factory=list)


@dataclass
class IRLLMInputContract:
    task: str
    language_target: str
    style: str
    audience: str
    prediction: Dict[str, Any]
    main_risk_increasing_factors: List[Dict[str, Any]]
    main_risk_decreasing_factors: List[Dict[str, Any]]
    main_concepts: List[Dict[str, Any]]
    allowed_claim_ids: List[str]
    forbidden_rule_ids: List[str]
    must_include: List[str]
    must_not: List[str]
    required_output_sections: List[str]


@dataclass
class IRValidationRule:
    rule_id: str
    rule_type: str
    severity: str
    expected: Any
    description: str


@dataclass
class IRValidationContract:
    allowed_claim_ids: List[str]
    forbidden_rule_ids: List[str]
    claim_validation_rules: List[IRValidationRule]
    claimable_subjects: Dict[str, List[str]]
    disallowed_subjects: Dict[str, List[str]]
    allowed_directions_by_subject: Dict[str, str]
    allowed_strength_by_subject: Dict[str, str]


@dataclass
class IREvidenceTrace:
    source_file: str
    source_evidence_id: str
    source_batch: str
    source_local_feature_count: int
    source_top_positive_count: int
    source_top_negative_count: int
    source_additivity_passed: Optional[bool]
    source_mapping_missing_count: Optional[int]


@dataclass
class IRRecordQuality:
    status: str
    ir_validation_passed: bool
    warnings: List[str]
    errors: List[str]
    allowed_claim_count: int
    forbidden_claim_count: int
    feature_factor_count: int
    risk_increasing_factor_count: int
    risk_decreasing_factor_count: int
    concept_summary_count: int
    has_llm_input_contract: bool
    has_validation_contract: bool


@dataclass
class IRMetadata:
    batch_name: str = BATCH_NAME
    batch_short_name: str = BATCH_SHORT_NAME
    source_batch: str = SOURCE_BATCH_NAME
    ir_schema_version: str = IR_SCHEMA_VERSION
    builder_version: str = BUILDER_VERSION
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class ExplanationIRRecord:
    ir_id: str
    source_evidence_id: str
    trace_id: str
    run_mode: str
    has_ground_truth: bool
    ir_schema_version: str
    created_at: str
    source_batch: str
    model: IRModelInfo
    customer: IRCustomerInfo
    prediction_summary: IRPredictionSummary
    xai_summary: IRXAISummary
    feature_factors: List[IRFeatureFactor]
    risk_increasing_factors: List[IRFeatureFactor]
    risk_decreasing_factors: List[IRFeatureFactor]
    concept_summaries: List[IRConceptSummary]
    allowed_claims: List[IRAllowedClaim]
    forbidden_claims: List[IRForbiddenClaim]
    llm_input_contract: IRLLMInputContract
    validation_contract: IRValidationContract
    evidence_trace: IREvidenceTrace
    quality: IRRecordQuality
    metadata: IRMetadata


# =============================================================================
# Validation
# =============================================================================

@dataclass
class IRValidationResult:
    status: str
    passed: bool
    warnings: List[str]
    errors: List[str]


def validate_probability_fields(
    prediction_summary: IRPredictionSummary,
) -> List[str]:
    """Return errors for invalid probability fields."""
    errors: List[str] = []

    probability = prediction_summary.probability
    threshold = prediction_summary.threshold

    if probability is None:
        errors.append("prediction_summary.probability is missing.")
    elif probability < 0 or probability > 1:
        errors.append(
            f"prediction_summary.probability must be in [0, 1], got {probability}."
        )

    if threshold is None:
        errors.append("prediction_summary.threshold is missing.")
    elif threshold < 0 or threshold > 1:
        errors.append(
            f"prediction_summary.threshold must be in [0, 1], got {threshold}."
        )

    if prediction_summary.predicted_class not in (0, 1):
        errors.append(
            "prediction_summary.predicted_class must be 0 or 1, "
            f"got {prediction_summary.predicted_class!r}."
        )

    expected_label = label_text_from_class(prediction_summary.predicted_class)
    if prediction_summary.predicted_label != expected_label:
        errors.append(
            "prediction_summary.predicted_label does not match predicted_class: "
            f"expected {expected_label!r}, got {prediction_summary.predicted_label!r}."
        )

    if prediction_summary.true_label not in (0, 1, None):
        errors.append(
            "prediction_summary.true_label must be 0, 1, or None, "
            f"got {prediction_summary.true_label!r}."
        )

    return errors


def validate_feature_policy_fields(factor: IRFeatureFactor) -> List[str]:
    """
    Return warnings for unusual but non-fatal feature policy fields.

    These are warnings, not errors, because old evidence files may not have all
    registry metadata yet.
    """
    warnings: List[str] = []

    allowed_values = {None, "true", "false", "limited"}

    if factor.allowed_in_user_explanation not in allowed_values:
        warnings.append(
            f"factor_id={factor.factor_id}: unexpected "
            f"allowed_in_user_explanation={factor.allowed_in_user_explanation!r}."
        )

    if factor.sensitive is True and factor.llm_visible:
        warnings.append(
            f"factor_id={factor.factor_id}: sensitive=True but llm_visible=True."
        )

    if factor.allowed_in_user_explanation == "limited" and factor.llm_visible:
        warnings.append(
            f"factor_id={factor.factor_id}: allowed_in_user_explanation='limited' "
            "but llm_visible=True."
        )

    if factor.allowed_in_user_explanation == "false" and factor.llm_visible:
        warnings.append(
            f"factor_id={factor.factor_id}: allowed_in_user_explanation='false' "
            "but llm_visible=True."
        )

    return warnings


def validate_feature_factors(
    factors: List[IRFeatureFactor],
) -> tuple[List[str], List[str]]:
    """
    Validate feature factor list.

    Returns:
        (warnings, errors)
    """
    warnings: List[str] = []
    errors: List[str] = []

    if not factors:
        errors.append("feature_factors is empty.")

    factor_ids = set()

    for factor in factors:
        if factor.factor_id in factor_ids:
            errors.append(f"duplicate factor_id found: {factor.factor_id}")
        factor_ids.add(factor.factor_id)

        expected_direction = direction_from_shap(factor.shap_value)
        if factor.direction != expected_direction:
            errors.append(
                f"factor_id={factor.factor_id}: direction mismatch. "
                f"Expected {expected_direction}, got {factor.direction}."
            )

        expected_abs = abs(float(factor.shap_value))
        if abs(factor.abs_shap_value - expected_abs) > 1e-8:
            warnings.append(
                f"factor_id={factor.factor_id}: abs_shap_value does not exactly "
                f"match abs(shap_value). abs_shap_value={factor.abs_shap_value}, "
                f"abs(shap_value)={expected_abs}."
            )

        if factor.direction == "increases_risk" and factor.shap_value <= 0:
            errors.append(
                f"factor_id={factor.factor_id}: increases_risk requires shap_value > 0."
            )

        if factor.direction == "decreases_risk" and factor.shap_value >= 0:
            errors.append(
                f"factor_id={factor.factor_id}: decreases_risk requires shap_value < 0."
            )

        if factor.strength not in ("strong", "moderate", "weak"):
            errors.append(
                f"factor_id={factor.factor_id}: invalid strength={factor.strength!r}."
            )

        if factor.feature_value_source_field not in (None, "value", "feature_value"):
            warnings.append(
                f"factor_id={factor.factor_id}: unexpected "
                f"feature_value_source_field={factor.feature_value_source_field!r}."
            )

        warnings.extend(validate_feature_policy_fields(factor))

    return warnings, errors


def validate_concept_summaries(
    concepts: List[IRConceptSummary],
) -> tuple[List[str], List[str]]:
    """
    Validate concept summaries.

    Returns:
        (warnings, errors)
    """
    warnings: List[str] = []
    errors: List[str] = []

    concept_ids = set()

    for concept in concepts:
        if concept.concept_id in concept_ids:
            errors.append(f"duplicate concept_id found: {concept.concept_id}")
        concept_ids.add(concept.concept_id)

        if not concept.display_name:
            warnings.append(
                f"concept_id={concept.concept_id}: display_name is missing."
            )

        if concept.has_mixed_directions and concept.claimable:
            errors.append(
                f"concept_id={concept.concept_id}: mixed-direction concept "
                "must not be claimable."
            )

        if concept.direction == "neutral" and concept.claimable:
            errors.append(
                f"concept_id={concept.concept_id}: neutral concept must not be claimable."
            )

        if concept.strength not in ("strong", "moderate", "weak"):
            errors.append(
                f"concept_id={concept.concept_id}: invalid strength={concept.strength!r}."
            )

    return warnings, errors


def validate_allowed_claims(
    claims: List[IRAllowedClaim],
    factors: List[IRFeatureFactor],
    concepts: List[IRConceptSummary],
) -> tuple[List[str], List[str]]:
    """
    Validate allowed claims.

    Returns:
        (warnings, errors)
    """
    warnings: List[str] = []
    errors: List[str] = []

    if not claims:
        errors.append("allowed_claims is empty.")

    claim_ids = set()
    factor_ids = {factor.factor_id for factor in factors}
    feature_names = {factor.feature_name for factor in factors}
    concept_ids = {concept.concept_id for concept in concepts}

    for claim in claims:
        if claim.claim_id in claim_ids:
            errors.append(f"duplicate claim_id found: {claim.claim_id}")
        claim_ids.add(claim.claim_id)

        if not claim.claim_type:
            errors.append(f"claim_id={claim.claim_id}: missing claim_type.")

        if not claim.subject_type:
            errors.append(f"claim_id={claim.claim_id}: missing subject_type.")

        if not claim.subject_id:
            errors.append(f"claim_id={claim.claim_id}: missing subject_id.")

        if claim.subject_type == "feature":
            if claim.subject_id not in feature_names and claim.subject_id not in factor_ids:
                warnings.append(
                    f"claim_id={claim.claim_id}: feature subject_id={claim.subject_id!r} "
                    "does not match any known feature_name or factor_id."
                )

        if claim.subject_type == "concept":
            if claim.subject_id not in concept_ids:
                warnings.append(
                    f"claim_id={claim.claim_id}: concept subject_id={claim.subject_id!r} "
                    "does not match any known concept_id."
                )

        if not claim.evidence_refs:
            errors.append(f"claim_id={claim.claim_id}: missing evidence_refs.")

        if claim.truth_condition is None:
            errors.append(f"claim_id={claim.claim_id}: missing truth_condition.")

        if not claim.natural_language_template:
            errors.append(
                f"claim_id={claim.claim_id}: missing natural_language_template."
            )

        if claim.direction is not None and claim.direction not in (
            "increases_risk",
            "decreases_risk",
            "neutral",
        ):
            errors.append(
                f"claim_id={claim.claim_id}: invalid direction={claim.direction!r}."
            )

        if claim.strength is not None and claim.strength not in (
            "strong",
            "moderate",
            "weak",
        ):
            errors.append(
                f"claim_id={claim.claim_id}: invalid strength={claim.strength!r}."
            )

    return warnings, errors


def validate_forbidden_claims(
    forbidden_claims: List[IRForbiddenClaim],
) -> List[str]:
    """Return errors for invalid forbidden claims."""
    errors: List[str] = []

    if not forbidden_claims:
        errors.append("forbidden_claims is empty.")

    forbidden_ids = set()

    for item in forbidden_claims:
        if item.forbidden_id in forbidden_ids:
            errors.append(f"duplicate forbidden_id found: {item.forbidden_id}")
        forbidden_ids.add(item.forbidden_id)

        if not item.rule_type:
            errors.append(f"forbidden_id={item.forbidden_id}: missing rule_type.")

        if not item.natural_language_rule:
            errors.append(
                f"forbidden_id={item.forbidden_id}: missing natural_language_rule."
            )

        if item.severity not in ("low", "medium", "high"):
            errors.append(
                f"forbidden_id={item.forbidden_id}: invalid severity={item.severity!r}."
            )

    return errors


def validate_llm_input_contract(
    record: ExplanationIRRecord,
) -> tuple[List[str], List[str]]:
    """
    Validate LLM input contract consistency.

    Returns:
        (warnings, errors)
    """
    warnings: List[str] = []
    errors: List[str] = []

    contract = record.llm_input_contract

    if contract is None:
        errors.append("llm_input_contract is missing.")
        return warnings, errors

    if "claim_true_label_available" in contract.allowed_claim_ids:
        warnings.append(
            "llm_input_contract.allowed_claim_ids contains "
            "claim_true_label_available. This is evaluation-only and should "
            "not be exposed to default user-facing LLM output."
        )

    claimable_concepts = {
        concept.concept_id
        for concept in record.concept_summaries
        if concept.claimable and concept.llm_visible and not concept.has_mixed_directions
    }

    for concept_item in contract.main_concepts:
        concept_id = concept_item.get("concept_id")

        if concept_id not in claimable_concepts:
            errors.append(
                f"llm_input_contract.main_concepts contains non-claimable or "
                f"mixed concept: {concept_id!r}."
            )

    visible_factor_ids = {
        factor.factor_id
        for factor in record.feature_factors
        if factor.llm_visible and factor.claimable
    }

    for item in contract.main_risk_increasing_factors:
        factor_id = item.get("factor_id")
        if factor_id not in visible_factor_ids:
            errors.append(
                f"llm_input_contract.main_risk_increasing_factors contains "
                f"hidden/non-claimable factor: {factor_id!r}."
            )

    for item in contract.main_risk_decreasing_factors:
        factor_id = item.get("factor_id")
        if factor_id not in visible_factor_ids:
            errors.append(
                f"llm_input_contract.main_risk_decreasing_factors contains "
                f"hidden/non-claimable factor: {factor_id!r}."
            )

    return warnings, errors


def validate_validation_contract(
    record: ExplanationIRRecord,
) -> tuple[List[str], List[str]]:
    """
    Validate faithfulness validation contract consistency.

    Returns:
        (warnings, errors)
    """
    warnings: List[str] = []
    errors: List[str] = []

    contract = record.validation_contract

    if contract is None:
        errors.append("validation_contract is missing.")
        return warnings, errors

    if "claim_true_label_available" in contract.allowed_claim_ids:
        warnings.append(
            "validation_contract.allowed_claim_ids contains "
            "claim_true_label_available. This may allow evaluation-only claims "
            "in user-facing validation."
        )

    for concept_id in contract.claimable_subjects.get("concepts", []):
        matching = [
            concept for concept in record.concept_summaries
            if concept.concept_id == concept_id
        ]

        if not matching:
            errors.append(
                f"validation_contract claimable concept not found in summaries: {concept_id}"
            )
            continue

        concept = matching[0]
        if concept.has_mixed_directions or not concept.claimable:
            errors.append(
                f"validation_contract contains non-claimable/mixed concept: {concept_id}"
            )

    for feature_name in contract.claimable_subjects.get("features", []):
        matching = [
            factor for factor in record.feature_factors
            if factor.feature_name == feature_name
        ]

        if not matching:
            errors.append(
                f"validation_contract claimable feature not found in factors: {feature_name}"
            )
            continue

        factor = matching[0]
        if not factor.claimable or not factor.llm_visible:
            errors.append(
                f"validation_contract contains hidden/non-claimable feature: {feature_name}"
            )

    return warnings, errors


def validate_explanation_ir_record(
    record: ExplanationIRRecord,
) -> IRValidationResult:
    """
    Validate an ExplanationIRRecord.

    This checks internal consistency before saving IR to JSONL.
    """
    warnings: List[str] = []
    errors: List[str] = []

    if not record.ir_id:
        errors.append("ir_id is missing.")

    if not record.source_evidence_id:
        errors.append("source_evidence_id is missing.")

    if not record.trace_id:
        errors.append("trace_id is missing.")

    if record.run_mode not in ("evaluation", "inference"):
        errors.append(f"invalid run_mode={record.run_mode!r}.")

    if record.ir_schema_version != IR_SCHEMA_VERSION:
        warnings.append(
            f"IR schema version mismatch: expected {IR_SCHEMA_VERSION}, "
            f"got {record.ir_schema_version}."
        )

    errors.extend(validate_probability_fields(record.prediction_summary))

    factor_warnings, factor_errors = validate_feature_factors(record.feature_factors)
    warnings.extend(factor_warnings)
    errors.extend(factor_errors)

    concept_warnings, concept_errors = validate_concept_summaries(
        record.concept_summaries
    )
    warnings.extend(concept_warnings)
    errors.extend(concept_errors)

    claim_warnings, claim_errors = validate_allowed_claims(
        record.allowed_claims,
        record.feature_factors,
        record.concept_summaries,
    )
    warnings.extend(claim_warnings)
    errors.extend(claim_errors)

    errors.extend(validate_forbidden_claims(record.forbidden_claims))

    llm_warnings, llm_errors = validate_llm_input_contract(record)
    warnings.extend(llm_warnings)
    errors.extend(llm_errors)

    validator_warnings, validator_errors = validate_validation_contract(record)
    warnings.extend(validator_warnings)
    errors.extend(validator_errors)

    if record.evidence_trace is None:
        errors.append("evidence_trace is missing.")

    if record.xai_summary.passed_additivity_check is False:
        warnings.append("xai_summary.passed_additivity_check is false.")

    if record.xai_summary.passed_additivity_check is None:
        warnings.append("xai_summary.passed_additivity_check is missing/null.")

    if errors:
        status = RECORD_STATUS_FAILED
        passed = False
    elif warnings:
        status = RECORD_STATUS_WARNING
        passed = True
    else:
        status = RECORD_STATUS_PASSED
        passed = True

    return IRValidationResult(
        status=status,
        passed=passed,
        warnings=warnings,
        errors=errors,
    )


if __name__ == "__main__":
    print("direction +0.12:", direction_from_shap(0.12))
    print("direction -0.03:", direction_from_shap(-0.03))
    print("direction 0:", direction_from_shap(0.0))
    print("strength 0.12:", strength_from_abs_shap(0.12))
    print("strength 0.04:", strength_from_abs_shap(0.04))
    print("strength 0.001:", strength_from_abs_shap(0.001))
    print("label 1:", label_text_from_class(1))
    print("label 0:", label_text_from_class(0))
    print("label None:", label_text_from_class(None))
    print("probability:", format_probability(0.731234))
    print("percent:", format_probability_percent(0.731234))
    print(make_safe_phrase_for_direction("tín hiệu điểm ngoài", "increases_risk"))
    print(make_safe_phrase_for_direction("hành vi trả góp", "decreases_risk"))
    print("ir_schema.py smoke test: OK")