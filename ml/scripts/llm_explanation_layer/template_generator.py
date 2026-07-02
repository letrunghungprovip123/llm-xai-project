"""
Template-based explanation generator for Batch I v0.1.

This generator does NOT call an external LLM/API.

It converts Batch H Explanation IR records into structured Vietnamese
natural-language explanations using deterministic templates.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ml.scripts.llm_explanation_layer.config import (
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_CONCEPTS_TO_MENTION,
    DEFAULT_MAX_FEATURES_TO_MENTION,
    GENERATOR_NAME_TEMPLATE,
    GENERATOR_TYPE_TEMPLATE,
    GENERATOR_VERSION,
    RECORD_STATUS_FAILED,
    RECORD_STATUS_GENERATED,
    RECORD_STATUS_WARNING,
    SOURCE_BATCH_NAME,
    USES_EXTERNAL_AI_API,
)
from ml.scripts.llm_explanation_layer.explanation_schema import (
    LLMExplanationBuildResult,
    LLMExplanationMetadata,
    LLMExplanationPayload,
    LLMExplanationQuality,
    LLMExplanationRecord,
    LLMExplanationSections,
    LLMGeneratorInfo,
    LLMPredictionInfo,
    LLMSourceContract,
    LLMSourceInfo,
    dataclass_to_dict,
    utc_now_iso,
)


# =============================================================================
# Generic helpers
# =============================================================================

def get_nested_value(
    data: Dict[str, Any],
    path: str,
    default: Any = None,
) -> Any:
    """Safely read nested dictionary values with dot notation."""
    current: Any = data

    for part in path.split("."):
        if not isinstance(current, dict):
            return default

        if part not in current:
            return default

        current = current[part]

    return current


def clean_text(value: Any, fallback: str = "") -> str:
    """Convert value to clean text."""
    if value is None:
        return fallback

    text = str(value).strip()

    if not text:
        return fallback

    return text


def business_label_vietnamese(label: Optional[str]) -> str:
    """
    Convert internal prediction label to Vietnamese explanation label.
    """
    if label == "high_default_risk":
        return "rủi ro cao"

    if label == "low_default_risk":
        return "rủi ro thấp"

    return clean_text(label, fallback="không xác định")


def comparison_vietnamese(threshold_comparison: Optional[str]) -> str:
    """Convert threshold comparison to Vietnamese phrase."""
    if threshold_comparison == "above_or_equal_threshold":
        return "cao hơn hoặc bằng ngưỡng"

    if threshold_comparison == "below_threshold":
        return "thấp hơn ngưỡng"

    return "không xác định so với ngưỡng"


def strength_vietnamese(strength: Optional[str]) -> str:
    """Convert strength label to Vietnamese phrase."""
    if strength == "strong":
        return "mức đóng góp mạnh"

    if strength == "moderate":
        return "mức đóng góp vừa phải"

    if strength == "weak":
        return "mức đóng góp yếu"

    return "mức đóng góp không xác định"


def join_vietnamese_items(items: List[str]) -> str:
    """
    Join Vietnamese items naturally.

    Examples:
        ["A"] -> "A"
        ["A", "B"] -> "A và B"
        ["A", "B", "C"] -> "A, B và C"
    """
    cleaned = [clean_text(item) for item in items if clean_text(item)]

    if not cleaned:
        return ""

    if len(cleaned) == 1:
        return cleaned[0]

    if len(cleaned) == 2:
        return f"{cleaned[0]} và {cleaned[1]}"

    return f"{', '.join(cleaned[:-1])} và {cleaned[-1]}"


def make_explanation_id(ir_id: str) -> str:
    """Create explanation id from IR id."""
    if ir_id.startswith("ir_"):
        return "llm_" + ir_id

    return f"llm_{ir_id}"


# =============================================================================
# Section builders
# =============================================================================

def build_prediction_section(contract: Dict[str, Any]) -> str:
    """Build prediction section from LLM input contract."""
    prediction = contract.get("prediction") or {}

    predicted_label = clean_text(prediction.get("predicted_label"), "unknown_label")
    predicted_label_vi = business_label_vietnamese(predicted_label)

    probability_percent = clean_text(
        prediction.get("probability_percent_display"),
        "không xác định",
    )

    threshold_percent = clean_text(
        prediction.get("threshold_percent_display"),
        "không xác định",
    )

    threshold_comparison = clean_text(
        prediction.get("threshold_comparison"),
        "unknown_threshold_comparison",
    )

    comparison_vi = comparison_vietnamese(threshold_comparison)

    return (
        f"Mô hình dự đoán khách hàng thuộc nhóm {predicted_label_vi} "
        f"với xác suất {probability_percent}, {comparison_vi} "
        f"{threshold_percent}."
    )


def concept_phrase(concept: Dict[str, Any]) -> str:
    """Create compact concept phrase."""
    display_name = clean_text(
        concept.get("display_name"),
        fallback=clean_text(concept.get("concept_id"), "nhóm yếu tố không xác định"),
    )

    strength = strength_vietnamese(concept.get("strength"))

    return f"{display_name} ({strength})"


def factor_phrase(factor: Dict[str, Any]) -> str:
    """Create compact feature/factor phrase."""
    display_name = clean_text(
        factor.get("display_name"),
        fallback=clean_text(factor.get("feature_name"), "yếu tố không xác định"),
    )

    strength = strength_vietnamese(factor.get("strength"))

    return f"{display_name} ({strength})"


def build_main_risk_drivers_section(
    contract: Dict[str, Any],
    max_concepts: int = DEFAULT_MAX_CONCEPTS_TO_MENTION,
    max_features: int = DEFAULT_MAX_FEATURES_TO_MENTION,
) -> str:
    """Build main risk drivers section."""
    concepts = contract.get("main_concepts") or []
    increasing_factors = contract.get("main_risk_increasing_factors") or []

    concept_items = [
        concept_phrase(item)
        for item in concepts[:max_concepts]
        if isinstance(item, dict)
    ]

    factor_items = [
        factor_phrase(item)
        for item in increasing_factors[:max_features]
        if isinstance(item, dict)
    ]

    sentences: List[str] = []

    if concept_items:
        sentences.append(
            "Các nhóm yếu tố chính góp phần làm tăng rủi ro dự đoán gồm "
            f"{join_vietnamese_items(concept_items)}."
        )

    if factor_items:
        sentences.append(
            "Một số yếu tố cụ thể được phép hiển thị gồm "
            f"{join_vietnamese_items(factor_items)}."
        )

    if not sentences:
        sentences.append(
            "Không có nhóm yếu tố hoặc yếu tố cụ thể nào đủ điều kiện hiển thị "
            "để mô tả phần làm tăng rủi ro dự đoán."
        )

    return " ".join(sentences)


def build_risk_reducing_factors_section(
    contract: Dict[str, Any],
    max_features: int = DEFAULT_MAX_FEATURES_TO_MENTION,
) -> str:
    """Build risk reducing factors section."""
    decreasing_factors = contract.get("main_risk_decreasing_factors") or []

    factor_items = [
        factor_phrase(item)
        for item in decreasing_factors[:max_features]
        if isinstance(item, dict)
    ]

    if not factor_items:
        return (
            "Không có yếu tố làm giảm rủi ro nào đủ điều kiện hiển thị trực tiếp "
            "trong phần bằng chứng được phép."
        )

    return (
        "Một số yếu tố góp phần làm giảm rủi ro dự đoán gồm "
        f"{join_vietnamese_items(factor_items)}."
    )


def build_limitations_section(contract: Dict[str, Any]) -> str:
    """Build limitations section."""
    return (
        "Các yếu tố trên chỉ mô tả đóng góp vào dự đoán của mô hình, "
        "không chứng minh quan hệ nhân quả ngoài thực tế. "
        "Dự đoán này là kết quả xác suất của mô hình, không phải khẳng định "
        "chắc chắn về hành vi trả nợ trong tương lai."
    )


def build_full_text(sections: LLMExplanationSections) -> str:
    """Combine explanation sections into full text."""
    return "\n\n".join(
        [
            sections.prediction,
            sections.main_risk_drivers,
            sections.risk_reducing_factors,
            sections.limitations,
        ]
    )


# =============================================================================
# Record builder
# =============================================================================

def build_prediction_info(ir_record: Dict[str, Any]) -> LLMPredictionInfo:
    """Build prediction info from IR record/contract."""
    contract_prediction = get_nested_value(
        ir_record,
        "llm_input_contract.prediction",
        {},
    )

    return LLMPredictionInfo(
        predicted_label=contract_prediction.get("predicted_label"),
        predicted_class=contract_prediction.get("predicted_class"),
        probability=contract_prediction.get("probability"),
        probability_display=contract_prediction.get("probability_display"),
        probability_percent_display=contract_prediction.get("probability_percent_display"),
        threshold=contract_prediction.get("threshold"),
        threshold_display=contract_prediction.get("threshold_display"),
        threshold_percent_display=contract_prediction.get("threshold_percent_display"),
        threshold_comparison=contract_prediction.get("threshold_comparison"),
    )


def build_source_contract(ir_record: Dict[str, Any]) -> LLMSourceContract:
    """Build source contract block from IR record."""
    contract = ir_record.get("llm_input_contract") or {}

    return LLMSourceContract(
        allowed_claim_ids=list(contract.get("allowed_claim_ids") or []),
        forbidden_rule_ids=list(contract.get("forbidden_rule_ids") or []),
        must_include=list(contract.get("must_include") or []),
        must_not=list(contract.get("must_not") or []),
        required_output_sections=list(contract.get("required_output_sections") or []),
    )


def build_quality(
    sections: LLMExplanationSections,
    warnings: List[str],
    errors: List[str],
) -> LLMExplanationQuality:
    """Build quality block."""
    section_values = [
        sections.prediction,
        sections.main_risk_drivers,
        sections.risk_reducing_factors,
        sections.limitations,
    ]

    full_text = "\n\n".join(section_values)

    if errors:
        status = RECORD_STATUS_FAILED
    elif warnings:
        status = RECORD_STATUS_WARNING
    else:
        status = RECORD_STATUS_GENERATED

    return LLMExplanationQuality(
        status=status,
        warnings=warnings,
        errors=errors,
        section_count=sum(1 for item in section_values if clean_text(item)),
        character_count=len(full_text),
        has_prediction_section=bool(clean_text(sections.prediction)),
        has_main_risk_drivers_section=bool(clean_text(sections.main_risk_drivers)),
        has_risk_reducing_factors_section=bool(clean_text(sections.risk_reducing_factors)),
        has_limitations_section=bool(clean_text(sections.limitations)),
    )


def build_single_template_explanation(
    ir_record: Dict[str, Any],
) -> tuple[LLMExplanationRecord, List[str], List[str]]:
    """
    Build one template-based explanation record from one IR record.

    Returns:
        (explanation_record, warnings, errors)
    """
    warnings: List[str] = []
    errors: List[str] = []

    ir_id = clean_text(ir_record.get("ir_id"))
    source_evidence_id = clean_text(ir_record.get("source_evidence_id"))
    trace_id = clean_text(ir_record.get("trace_id"))

    if not ir_id:
        errors.append("missing ir_id.")

    if not source_evidence_id:
        errors.append("missing source_evidence_id.")

    if not trace_id:
        errors.append("missing trace_id.")

    contract = ir_record.get("llm_input_contract") or {}

    if not isinstance(contract, dict):
        errors.append("llm_input_contract is missing or invalid.")
        contract = {}

    if "claim_true_label_available" in contract.get("allowed_claim_ids", []):
        warnings.append(
            "llm_input_contract.allowed_claim_ids contains claim_true_label_available."
        )

    main_concepts = contract.get("main_concepts") or []
    increasing_factors = contract.get("main_risk_increasing_factors") or []
    decreasing_factors = contract.get("main_risk_decreasing_factors") or []

    if not main_concepts and not increasing_factors:
        warnings.append(
            "No main concepts or increasing factors available for explanation."
        )

    if not decreasing_factors:
        warnings.append(
            "No risk-decreasing factors available for user-facing explanation."
        )

    prediction_section = build_prediction_section(contract)
    main_risk_drivers_section = build_main_risk_drivers_section(contract)
    risk_reducing_factors_section = build_risk_reducing_factors_section(contract)
    limitations_section = build_limitations_section(contract)

    sections = LLMExplanationSections(
        prediction=prediction_section,
        main_risk_drivers=main_risk_drivers_section,
        risk_reducing_factors=risk_reducing_factors_section,
        limitations=limitations_section,
    )

    full_text = build_full_text(sections)

    quality = build_quality(
        sections=sections,
        warnings=warnings,
        errors=errors,
    )

    created_at = utc_now_iso()

    explanation_record = LLMExplanationRecord(
        explanation_id=make_explanation_id(ir_id),
        source_ir_id=ir_id,
        source_evidence_id=source_evidence_id,
        trace_id=trace_id,
        run_mode=clean_text(ir_record.get("run_mode"), "evaluation"),
        has_ground_truth=bool(ir_record.get("has_ground_truth", False)),
        created_at=created_at,
        generator=LLMGeneratorInfo(
            generator_type=GENERATOR_TYPE_TEMPLATE,
            generator_name=GENERATOR_NAME_TEMPLATE,
            generator_version=GENERATOR_VERSION,
            uses_external_ai_api=USES_EXTERNAL_AI_API,
            provider=None,
            model_name=None,
        ),
        source=LLMSourceInfo(
            source_ir_id=ir_id,
            source_evidence_id=source_evidence_id,
            trace_id=trace_id,
            source_batch=SOURCE_BATCH_NAME,
            source_ir_schema_version=ir_record.get("ir_schema_version"),
        ),
        customer=dict(ir_record.get("customer") or {}),
        model=dict(ir_record.get("model") or {}),
        prediction=build_prediction_info(ir_record),
        source_contract=build_source_contract(ir_record),
        explanation=LLMExplanationPayload(
            language=DEFAULT_LANGUAGE,
            sections=sections,
            full_text=full_text,
        ),
        quality=quality,
        metadata=LLMExplanationMetadata(),
    )

    return explanation_record, warnings, errors


def build_summary_row(record: LLMExplanationRecord) -> Dict[str, Any]:
    """Build one flat summary row."""
    return {
        "explanation_id": record.explanation_id,
        "source_ir_id": record.source_ir_id,
        "source_evidence_id": record.source_evidence_id,
        "trace_id": record.trace_id,
        "run_mode": record.run_mode,
        "has_ground_truth": record.has_ground_truth,
        "SK_ID_CURR": record.customer.get("SK_ID_CURR"),
        "case_type": record.customer.get("case_type"),
        "selection_rank": record.customer.get("selection_rank"),
        "model_name": record.model.get("model_name"),
        "model_version": record.model.get("model_version"),
        "generator_type": record.generator.generator_type,
        "generator_name": record.generator.generator_name,
        "generator_version": record.generator.generator_version,
        "uses_external_ai_api": record.generator.uses_external_ai_api,
        "predicted_label": record.prediction.predicted_label,
        "probability_percent_display": record.prediction.probability_percent_display,
        "threshold_percent_display": record.prediction.threshold_percent_display,
        "allowed_claim_count": len(record.source_contract.allowed_claim_ids),
        "forbidden_rule_count": len(record.source_contract.forbidden_rule_ids),
        "section_count": record.quality.section_count,
        "character_count": record.quality.character_count,
        "quality_status": record.quality.status,
        "warning_count": len(record.quality.warnings),
        "error_count": len(record.quality.errors),
    }


def build_template_explanations(
    ir_records: List[Dict[str, Any]],
) -> LLMExplanationBuildResult:
    """
    Build template explanations for a list of IR records.
    """
    explanation_records: List[LLMExplanationRecord] = []
    explanation_record_dicts: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []

    warnings: List[str] = []
    errors: List[str] = []

    for idx, ir_record in enumerate(ir_records):
        try:
            explanation_record, record_warnings, record_errors = (
                build_single_template_explanation(ir_record)
            )

            explanation_records.append(explanation_record)
            explanation_record_dicts.append(dataclass_to_dict(explanation_record))
            summary_rows.append(build_summary_row(explanation_record))

            for warning in record_warnings:
                warnings.append(f"{explanation_record.explanation_id}: {warning}")

            for error in record_errors:
                errors.append(f"{explanation_record.explanation_id}: {error}")

        except Exception as exc:
            errors.append(
                f"record_index={idx}: failed to build template explanation. "
                f"Error: {exc}"
            )

    return LLMExplanationBuildResult(
        explanation_records=explanation_records,
        explanation_record_dicts=explanation_record_dicts,
        summary_rows=summary_rows,
        warnings=warnings,
        errors=errors,
    )