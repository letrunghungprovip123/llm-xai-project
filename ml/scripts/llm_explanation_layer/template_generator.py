"""
Template-based explanation generator for Batch I v1.1.

This generator does NOT call an external LLM/API.

It converts Batch H Explanation IR records into structured Vietnamese
natural-language explanations using deterministic templates.

The goal of v1.1 is to match the target LLM output schema before introducing
an external API generator.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ml.scripts.llm_explanation_layer.config import (
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_PRIMARY_FEATURES_TO_MENTION,
    DEFAULT_MAX_RISK_REDUCING_FEATURES_TO_MENTION,
    DEFAULT_MAX_SUPPORTING_GROUPS_TO_MENTION,
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
    LLMEvidenceGroupUsed,
    LLMEvidenceItemUsed,
    LLMExplanationBuildResult,
    LLMExplanationMetadata,
    LLMExplanationPayload,
    LLMExplanationQuality,
    LLMExplanationRecord,
    LLMExplanationSections,
    LLMGeneratorInfo,
    LLMPredictionInfo,
    LLMReferencedTerm,
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

    Avoid the stronger wording "vỡ nợ" in user-facing explanations.
    """
    if label == "high_default_risk":
        return "rủi ro gặp khó khăn trong thanh toán cao"

    if label == "low_default_risk":
        return "rủi ro gặp khó khăn trong thanh toán thấp"

    return clean_text(label, fallback="rủi ro không xác định")


def comparison_vietnamese(threshold_comparison: Optional[str]) -> str:
    """Convert threshold comparison to Vietnamese phrase."""
    if threshold_comparison == "above_or_equal_threshold":
        return "cao hơn hoặc bằng"

    if threshold_comparison == "below_threshold":
        return "thấp hơn"

    return "không xác định so với"


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


def is_raw_technical_text(text: Any) -> bool:
    """
    Detect raw/technical feature names that should not be copied into explanation.
    """
    value = clean_text(text)

    if not value:
        return False

    lowered = value.lower()

    technical_tokens = [
        "_",
        "bureau ",
        "installment ",
        "pos cash ",
        "credit card ",
        " avg ",
        " max ",
        " min ",
        " sum ",
        " std",
        " dpd",
        " def ",
        " xna",
        " cnt",
        " amt",
    ]

    if any(token in lowered for token in technical_tokens):
        return True

    if value.isupper() and len(value) > 3:
        return True

    return False


def safe_feature_mention(item: Dict[str, Any]) -> str:
    """
    Return a safe Vietnamese mention for a feature item.

    If display_name is technical/raw English, fall back to concept-level wording.
    """
    display_name = clean_text(item.get("display_name"))
    concept_display_name = clean_text(item.get("concept_display_name"))
    concept = clean_text(item.get("concept"))

    if display_name and not is_raw_technical_text(display_name):
        return display_name

    if concept_display_name:
        return f"một tín hiệu thuộc nhóm {concept_display_name}"

    if concept:
        return f"một tín hiệu thuộc nhóm {concept.replace('_', ' ')}"

    return "một tín hiệu được phép hiển thị"


def contribution_display(item: Dict[str, Any]) -> str:
    """
    Get contribution display from Batch H contract.
    """
    value = clean_text(item.get("contribution_points_display"))

    if value:
        return value

    value = clean_text(item.get("net_contribution_points_display"))

    if value:
        return value

    return "không xác định"


def direction_phrase(direction: Optional[str]) -> str:
    """Convert contribution direction to Vietnamese phrase."""
    if direction == "increases_risk":
        return "làm tăng rủi ro dự đoán"

    if direction == "decreases_risk":
        return "làm giảm rủi ro dự đoán"

    return "có đóng góp hỗn hợp hoặc gần trung tính"


def has_forbidden_default_wording(text: str) -> bool:
    """
    Lightweight forbidden wording check.

    Batch J will perform stricter faithfulness and policy validation.
    """
    forbidden = [
        "vỡ nợ",
        "chắc chắn không trả",
        "chắc chắn sẽ trả",
        "TARGET",
        "true_label",
        "true positive",
        "false positive",
        "false negative",
    ]

    lowered = text.lower()
    return any(item.lower() in lowered for item in forbidden)


def has_raw_technical_feature_name(text: str) -> bool:
    """
    Lightweight output check. Batch J will perform stricter validation later.
    """
    lowered = text.lower()

    suspicious = [
        "bureau credit",
        "bureau balance",
        "installment_",
        "pos_cash",
        "credit_card",
        "ext_source",
        "name_income_type",
        "occupation_type",
        "__",
    ]

    return any(item in lowered for item in suspicious)


def make_explanation_id(ir_id: str) -> str:
    """Create explanation id from IR id."""
    if ir_id.startswith("ir_"):
        return "llm_" + ir_id

    return f"llm_{ir_id}"


def format_coverage(value: Any) -> str:
    """Format coverage percentage from accounting."""
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "không xác định"


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
        f"Mô hình dự đoán khách hàng thuộc nhóm {predicted_label_vi}, "
        f"với xác suất {probability_percent}, {comparison_vi} "
        f"ngưỡng quyết định {threshold_percent}. "
        "Đây là dự đoán xác suất của mô hình, không phải kết luận chắc chắn "
        "về hành vi thanh toán thực tế."
    )


def build_contribution_overview_section(contract: Dict[str, Any]) -> str:
    """Build contribution accounting overview section."""
    accounting = contract.get("contribution_accounting") or {}

    total_feature_count = accounting.get("total_feature_count")
    base_value_display = clean_text(accounting.get("base_value_display"))
    model_output_display = clean_text(accounting.get("model_output_display"))
    all_feature_sum_display = clean_text(accounting.get("all_feature_sum_display"))

    primary_count = accounting.get("primary_feature_count")
    supporting_count = accounting.get("supporting_feature_count")
    remaining_count = accounting.get("remaining_feature_count")
    hidden_count = accounting.get("hidden_or_nonclaimable_feature_count")
    coverage = accounting.get("explained_abs_coverage_percent")

    parts: List[str] = []

    if total_feature_count:
        parts.append(
            f"Giải thích này dựa trên SHAP ở không gian xác suất, với "
            f"{total_feature_count} đặc trưng được tính trong tổng đóng góp cục bộ."
        )
    else:
        parts.append(
            "Giải thích này dựa trên SHAP ở không gian xác suất."
        )

    if base_value_display and model_output_display:
        if all_feature_sum_display:
            parts.append(
                f"Mức nền của mô hình là {base_value_display}; tổng đóng góp "
                f"của các đặc trưng là {all_feature_sum_display}, đưa xác suất "
                f"dự đoán đến {model_output_display}."
            )
        else:
            parts.append(
                f"Mức nền của mô hình là {base_value_display}, và xác suất "
                f"dự đoán sau khi cộng các đóng góp cục bộ là {model_output_display}."
            )

    tier_texts: List[str] = []

    if primary_count is not None:
        tier_texts.append(f"{primary_count} yếu tố chính")

    if supporting_count is not None:
        tier_texts.append(f"{supporting_count} yếu tố hỗ trợ")

    if remaining_count is not None:
        tier_texts.append(f"{remaining_count} yếu tố còn lại")

    if hidden_count is not None:
        tier_texts.append(
            f"{hidden_count} yếu tố bị ẩn hoặc chỉ được phép hiển thị giới hạn"
        )

    if tier_texts:
        parts.append(
            "Phần giải thích bên dưới chỉ trình bày phần evidence được chọn gồm "
            f"{join_vietnamese_items(tier_texts)}; các yếu tố còn lại vẫn được "
            "tính trong tổng đóng góp của mô hình."
        )

    if coverage is not None:
        parts.append(
            f"Các yếu tố được trình bày chi tiết bao phủ khoảng "
            f"{format_coverage(coverage)} tổng độ lớn đóng góp tuyệt đối của mô hình."
        )

    return " ".join(parts)


def factor_phrase(factor: Dict[str, Any]) -> str:
    """Create compact feature/factor phrase with contribution points."""
    mention = safe_feature_mention(factor)
    strength = strength_vietnamese(factor.get("strength"))
    contribution = contribution_display(factor)
    direction = direction_phrase(factor.get("direction"))

    if contribution != "không xác định":
        return f"{mention}, {direction} khoảng {contribution} ({strength})"

    return f"{mention}, {direction} ({strength})"


def build_main_risk_drivers_section(
    contract: Dict[str, Any],
    max_features: int = DEFAULT_MAX_PRIMARY_FEATURES_TO_MENTION,
) -> str:
    """Build main risk drivers section from primary_features."""
    primary_features = contract.get("primary_features") or []

    increasing_items = [
        item
        for item in primary_features
        if isinstance(item, dict)
        and item.get("direction") == "increases_risk"
    ]

    factor_items = [
        factor_phrase(item)
        for item in increasing_items[:max_features]
    ]

    if not factor_items:
        fallback_factors = contract.get("main_risk_increasing_factors") or []

        factor_items = [
            factor_phrase(item)
            for item in fallback_factors[:max_features]
            if isinstance(item, dict)
        ]

    if factor_items:
        return (
            "Các yếu tố chính làm tăng rủi ro dự đoán gồm "
            f"{join_vietnamese_items(factor_items)}."
        )

    return (
        "Không có yếu tố chính làm tăng rủi ro nào đủ điều kiện hiển thị trực tiếp. "
        "Nếu có tín hiệu nhạy cảm hoặc tên feature còn kỹ thuật, phần giải thích "
        "ưu tiên trình bày ở cấp nhóm evidence."
    )


def supporting_group_phrase(group: Dict[str, Any]) -> str:
    """Create phrase for one supporting evidence group."""
    display_name = clean_text(
        group.get("display_name"),
        fallback=clean_text(group.get("concept_id"), "nhóm evidence hỗ trợ"),
    )

    feature_count = group.get("feature_count")
    direction = direction_phrase(group.get("direction"))
    contribution = clean_text(group.get("net_contribution_points_display"))

    if feature_count is not None and contribution:
        return (
            f"nhóm {display_name} gồm {feature_count} đặc trưng hỗ trợ, "
            f"{direction} khoảng {contribution}"
        )

    if contribution:
        return f"nhóm {display_name}, {direction} khoảng {contribution}"

    return f"nhóm {display_name}, {direction}"


def build_supporting_evidence_groups_section(
    contract: Dict[str, Any],
    max_groups: int = DEFAULT_MAX_SUPPORTING_GROUPS_TO_MENTION,
) -> str:
    """Build supporting evidence group section."""
    groups = contract.get("supporting_feature_groups") or []

    group_items = [
        supporting_group_phrase(item)
        for item in groups[:max_groups]
        if isinstance(item, dict)
    ]

    if not group_items:
        return (
            "Không có nhóm evidence hỗ trợ đủ lớn để trình bày riêng. "
            "Các đặc trưng còn lại vẫn được tính trong tổng đóng góp của mô hình."
        )

    return (
        "Ngoài các yếu tố chính, các nhóm evidence hỗ trợ gồm "
        f"{join_vietnamese_items(group_items)}. "
        "Các nhóm này là cụm tín hiệu mà mô hình dùng để điều chỉnh xác suất "
        "dự đoán, không phải quan hệ nhân quả ngoài thực tế."
    )


def build_risk_reducing_factors_section(
    contract: Dict[str, Any],
    max_features: int = DEFAULT_MAX_RISK_REDUCING_FEATURES_TO_MENTION,
) -> str:
    """Build risk reducing factors section."""
    primary_features = contract.get("primary_features") or []

    decreasing_items = [
        item
        for item in primary_features
        if isinstance(item, dict)
        and item.get("direction") == "decreases_risk"
    ]

    if not decreasing_items:
        decreasing_items = [
            item
            for item in (contract.get("main_risk_decreasing_factors") or [])
            if isinstance(item, dict)
        ]

    factor_items = [
        factor_phrase(item)
        for item in decreasing_items[:max_features]
    ]

    if not factor_items:
        return (
            "Trong phần evidence được phép hiển thị, không có yếu tố giảm rủi ro "
            "nổi bật. Điều này không có nghĩa là mô hình không tính yếu tố giảm rủi ro; "
            "các yếu tố nhỏ hơn hoặc bị giới hạn hiển thị vẫn có thể nằm trong tổng đóng góp."
        )

    return (
        "Một số yếu tố góp phần làm giảm rủi ro dự đoán gồm "
        f"{join_vietnamese_items(factor_items)}. "
        "Các yếu tố này làm giảm xác suất dự đoán, nhưng cần được so sánh với "
        "tổng các đóng góp làm tăng rủi ro."
    )


def build_limitations_section(contract: Dict[str, Any]) -> str:
    """Build limitations section."""
    return (
        "Giải thích này chỉ mô tả đóng góp của các đặc trưng vào dự đoán cục bộ "
        "của mô hình cho riêng khách hàng này. SHAP không chứng minh quan hệ "
        "nhân quả ngoài thực tế giữa các yếu tố và hành vi thanh toán. "
        "Một số đặc trưng là chỉ số tổng hợp từ nhiều bảng dữ liệu, nên phần "
        "giải thích ưu tiên diễn giải theo nhóm tín hiệu thay vì nêu tên kỹ thuật. "
        "Các đặc trưng nhạy cảm hoặc chỉ được phép hiển thị giới hạn vẫn được "
        "tính trong mô hình nhưng không được diễn giải trực tiếp ở cấp feature. "
        "Kết quả này không phải quyết định tín dụng cuối cùng và không nên được "
        "khái quát hóa cho mọi khách hàng."
    )


def build_full_text(sections: LLMExplanationSections) -> str:
    """Combine explanation sections into server-built full text."""
    return "\n\n".join(
        [
            sections.prediction,
            sections.contribution_overview,
            sections.main_risk_drivers,
            sections.supporting_evidence_groups,
            sections.risk_reducing_factors,
            sections.limitations,
        ]
    )


# =============================================================================
# Record builder helpers
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
        contribution_accounting=dict(contract.get("contribution_accounting") or {}),
        primary_features=list(contract.get("primary_features") or []),
        supporting_feature_groups=list(contract.get("supporting_feature_groups") or []),
        remaining_features_summary=dict(contract.get("remaining_features_summary") or {}),
        allowed_terms=list(contract.get("allowed_terms") or []),
        writing_rules=dict(contract.get("writing_rules") or {}),
        forbidden_content=list(contract.get("forbidden_content") or []),
    )


def build_referenced_terms(contract: Dict[str, Any]) -> List[LLMReferencedTerm]:
    """Build referenced terms from allowed_terms."""
    terms: Dict[tuple[str, str], LLMReferencedTerm] = {}

    for item in contract.get("allowed_terms") or []:
        if not isinstance(item, dict):
            continue

        term_id = clean_text(item.get("term_id"))
        term_type = clean_text(item.get("term_type"))
        mention = clean_text(item.get("display_name") or item.get("mention"))

        if term_id and term_type and mention:
            terms[(term_type, term_id)] = LLMReferencedTerm(
                term_id=term_id,
                term_type=term_type,
                mention=mention,
            )

    return list(terms.values())


def build_evidence_items_used(contract: Dict[str, Any]) -> List[LLMEvidenceItemUsed]:
    """Build self-reported evidence item usage for Batch J debugging."""
    items: List[LLMEvidenceItemUsed] = []

    for item in contract.get("primary_features") or []:
        if not isinstance(item, dict):
            continue

        feature_name = clean_text(item.get("feature_name") or item.get("factor_id"))

        if not feature_name:
            continue

        direction = clean_text(item.get("direction"), "neutral_or_mixed")
        usage = clean_text(item.get("usage"), "primary")

        items.append(
            LLMEvidenceItemUsed(
                evidence_id=feature_name,
                evidence_type="feature",
                direction=direction,
                usage=usage,
            )
        )

    for item in contract.get("supporting_feature_groups") or []:
        if not isinstance(item, dict):
            continue

        concept_id = clean_text(item.get("concept_id"))

        if not concept_id:
            continue

        direction = clean_text(item.get("direction"), "neutral_or_mixed")

        items.append(
            LLMEvidenceItemUsed(
                evidence_id=concept_id,
                evidence_type="concept",
                direction=direction,
                usage="supporting",
            )
        )

    return items


def build_evidence_groups_used(contract: Dict[str, Any]) -> List[LLMEvidenceGroupUsed]:
    """Build group usage metadata."""
    groups: List[LLMEvidenceGroupUsed] = []

    for item in contract.get("supporting_feature_groups") or []:
        if not isinstance(item, dict):
            continue

        group_id = clean_text(item.get("group_id"))
        concept_id = clean_text(item.get("concept_id"))

        if not group_id:
            continue

        groups.append(
            LLMEvidenceGroupUsed(
                group_id=group_id,
                concept_id=concept_id or None,
                usage="supporting_group",
            )
        )

    remaining = contract.get("remaining_features_summary") or {}

    if isinstance(remaining, dict) and remaining.get("count", 0):
        groups.append(
            LLMEvidenceGroupUsed(
                group_id="remaining_features",
                concept_id=None,
                usage="remaining_summary",
            )
        )

    return groups


def build_quality(
    sections: LLMExplanationSections,
    full_text: str,
    referenced_terms: List[LLMReferencedTerm],
    evidence_items_used: List[LLMEvidenceItemUsed],
    evidence_groups_used: List[LLMEvidenceGroupUsed],
    warnings: List[str],
    errors: List[str],
) -> LLMExplanationQuality:
    """Build quality block."""
    section_values = [
        sections.prediction,
        sections.contribution_overview,
        sections.main_risk_drivers,
        sections.supporting_evidence_groups,
        sections.risk_reducing_factors,
        sections.limitations,
    ]

    contains_forbidden = has_forbidden_default_wording(full_text)
    contains_raw_technical = has_raw_technical_feature_name(full_text)

    record_warnings = list(warnings)

    if contains_forbidden:
        record_warnings.append("Output contains forbidden/default wording.")

    if contains_raw_technical:
        record_warnings.append("Output may contain raw technical feature name.")

    if errors:
        status = RECORD_STATUS_FAILED
    elif record_warnings:
        status = RECORD_STATUS_WARNING
    else:
        status = RECORD_STATUS_GENERATED

    return LLMExplanationQuality(
        status=status,
        warnings=record_warnings,
        errors=errors,
        section_count=sum(1 for item in section_values if clean_text(item)),
        character_count=len(full_text),
        has_prediction_section=bool(clean_text(sections.prediction)),
        has_contribution_overview_section=bool(clean_text(sections.contribution_overview)),
        has_main_risk_drivers_section=bool(clean_text(sections.main_risk_drivers)),
        has_supporting_evidence_groups_section=bool(clean_text(sections.supporting_evidence_groups)),
        has_risk_reducing_factors_section=bool(clean_text(sections.risk_reducing_factors)),
        has_limitations_section=bool(clean_text(sections.limitations)),
        has_referenced_terms=bool(referenced_terms),
        has_evidence_items_used=bool(evidence_items_used),
        has_evidence_groups_used=bool(evidence_groups_used),
        contains_forbidden_default_wording=contains_forbidden,
        contains_raw_technical_feature_name=contains_raw_technical,
    )


# =============================================================================
# Main single-record builder
# =============================================================================

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

    if not main_concepts and not increasing_factors and not contract.get("primary_features"):
        warnings.append(
            "No main concepts, primary features, or increasing factors available for explanation."
        )

    prediction_section = build_prediction_section(contract)
    contribution_overview_section = build_contribution_overview_section(contract)
    main_risk_drivers_section = build_main_risk_drivers_section(contract)
    supporting_evidence_groups_section = build_supporting_evidence_groups_section(contract)
    risk_reducing_factors_section = build_risk_reducing_factors_section(contract)
    limitations_section = build_limitations_section(contract)

    sections = LLMExplanationSections(
        prediction=prediction_section,
        contribution_overview=contribution_overview_section,
        main_risk_drivers=main_risk_drivers_section,
        supporting_evidence_groups=supporting_evidence_groups_section,
        risk_reducing_factors=risk_reducing_factors_section,
        limitations=limitations_section,
    )

    full_text = build_full_text(sections)

    referenced_terms = build_referenced_terms(contract)
    evidence_items_used = build_evidence_items_used(contract)
    evidence_groups_used = build_evidence_groups_used(contract)

    quality = build_quality(
        sections=sections,
        full_text=full_text,
        referenced_terms=referenced_terms,
        evidence_items_used=evidence_items_used,
        evidence_groups_used=evidence_groups_used,
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
            referenced_terms=referenced_terms,
            evidence_items_used=evidence_items_used,
            evidence_groups_used=evidence_groups_used,
        ),
        quality=quality,
        metadata=LLMExplanationMetadata(),
    )

    return explanation_record, quality.warnings, errors


# =============================================================================
# Summary DataFrame
# =============================================================================

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
        "has_prediction_section": record.quality.has_prediction_section,
        "has_contribution_overview_section": record.quality.has_contribution_overview_section,
        "has_main_risk_drivers_section": record.quality.has_main_risk_drivers_section,
        "has_supporting_evidence_groups_section": record.quality.has_supporting_evidence_groups_section,
        "has_risk_reducing_factors_section": record.quality.has_risk_reducing_factors_section,
        "has_limitations_section": record.quality.has_limitations_section,
        "has_referenced_terms": record.quality.has_referenced_terms,
        "has_evidence_items_used": record.quality.has_evidence_items_used,
        "has_evidence_groups_used": record.quality.has_evidence_groups_used,
        "contains_forbidden_default_wording": record.quality.contains_forbidden_default_wording,
        "contains_raw_technical_feature_name": record.quality.contains_raw_technical_feature_name,
        "referenced_term_count": len(record.explanation.referenced_terms),
        "evidence_item_used_count": len(record.explanation.evidence_items_used),
        "evidence_group_used_count": len(record.explanation.evidence_groups_used),
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