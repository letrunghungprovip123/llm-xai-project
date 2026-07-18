from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import (
    ADAPTIVE_K_MAX_S3,
    ADAPTIVE_K_MAX_S4,
    ADAPTIVE_K_MIN,
    CLAIM_SCOPE_LOCAL_CASE,
    DEFAULT_LLM_AUDIENCE,
    DEFAULT_LLM_STYLE,
    DEFAULT_LLM_TARGET_LANGUAGE,
    DEFAULT_TOP_K_FOR_LLM,
    HIGH_ENTROPY_THRESHOLD,
    IR_SCHEMA_VERSION,
    LOW_ENTROPY_THRESHOLD,
    MODERATE_ABS_SHAP_THRESHOLD,
    NEUTRAL_SHAP_EPSILON,
    S3_COVERAGE_THRESHOLD,
    S4_COVERAGE_THRESHOLD,
    STRONG_ABS_SHAP_THRESHOLD,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_blank(value: Any) -> bool:
    if value is None:
        return True

    text = str(value).strip().lower()
    return text in {"", "none", "nan", "null"}


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if is_blank(value):
        return default

    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    if result != result:
        return default

    return result


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if is_blank(value):
        return default

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any, default: Optional[bool] = None) -> Optional[bool]:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()

    if text in {"true", "1", "yes", "y"}:
        return True

    if text in {"false", "0", "no", "n"}:
        return False

    return default


def round_float(value: Any, digits: int = 10) -> Optional[float]:
    number = safe_float(value)

    if number is None:
        return None

    return round(number, digits)


def format_probability(value: Any, digits: int = 4) -> Optional[str]:
    number = safe_float(value)

    if number is None:
        return None

    return f"{number:.{digits}f}"


def format_probability_percent(value: Any, digits: int = 2) -> Optional[str]:
    number = safe_float(value)

    if number is None:
        return None

    return f"{number * 100:.{digits}f}%"


def label_text_from_class(value: Any) -> str:
    label = safe_int(value)

    if label == 1:
        return "high_default_risk"

    if label == 0:
        return "low_default_risk"

    return "unknown_label"


def threshold_comparison_from_probability(probability: Any, threshold: Any) -> str:
    proba = safe_float(probability)
    th = safe_float(threshold)

    if proba is None or th is None:
        return "unknown_threshold_comparison"

    if proba >= th:
        return "above_or_equal_threshold"

    return "below_threshold"


def direction_from_shap(shap_value: Any) -> str:
    value = safe_float(shap_value, default=0.0) or 0.0

    if value > NEUTRAL_SHAP_EPSILON:
        return "increases_risk"

    if value < -NEUTRAL_SHAP_EPSILON:
        return "decreases_risk"

    return "neutral"


def strength_from_abs_shap(abs_shap_value: Any) -> str:
    value = safe_float(abs_shap_value, default=0.0) or 0.0

    if value >= STRONG_ABS_SHAP_THRESHOLD:
        return "strong"

    if value >= MODERATE_ABS_SHAP_THRESHOLD:
        return "moderate"

    return "weak"


def normalize_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback

    text = str(value).strip()
    return text if text else fallback


def make_safe_phrase_for_direction(name: str, direction: str) -> str:
    display_name = normalize_text(name, "Yếu tố này")

    if direction == "increases_risk":
        return f"{display_name} góp phần làm tăng rủi ro dự đoán của mô hình."

    if direction == "decreases_risk":
        return f"{display_name} góp phần làm giảm rủi ro dự đoán của mô hình."

    return f"{display_name} có đóng góp gần như trung tính đối với rủi ro dự đoán của mô hình."


def make_claim_policy() -> Dict[str, Any]:
    return {
        "allow_prediction_claim": True,
        "allow_feature_claim": True,
        "allow_concept_claim": True,
        "allow_direction_claim": True,
        "allow_magnitude_claim": True,
        "allow_uncertainty_claim": True,
        "allow_causal_claim": False,
        "allow_absolute_decision_claim": False,
        "allow_financial_advice": False,
        "required_uncertainty_note": True,
    }


def make_evidence_exposure_contract() -> Dict[str, Any]:
    return {
        "supported_levels": ["S0", "S1", "S2", "S3", "S4", "S5"],
        "default_level": "S3",
        "recommended_top_k": DEFAULT_TOP_K_FOR_LLM,
        "level_definitions": {
            "S0": "prediction_only",
            "S1": "raw_shap_fixed_topk",
            "S2": "semantic_shap_fixed_topk",
            "S3": "adaptive_coverage_with_constraints",
            "S4": "adaptive_coverage_entropy_concept_quality",
            "S5": "backend_overguided_baseline",
        },
        "level_inputs": {
            "S0": ["prediction_summary"],
            "S1": ["prediction_summary", "raw_topk_features", "shap_values"],
            "S2": ["prediction_summary", "semantic_topk_features"],
            "S3": ["prediction_summary", "adaptive_selected_features", "claim_policy", "forbidden_claims"],
            "S4": [
                "prediction_summary",
                "adaptive_selected_features",
                "concept_evidence",
                "xai_quality_metrics",
                "adaptive_selection_metadata",
                "claim_policy",
            ],
            "S5": [
                "prediction_summary",
                "evidence_views",
                "allowed_claims",
                "forbidden_claims",
                "claim_policy",
            ],
        },
    }


def make_adaptive_selection_contract() -> Dict[str, Any]:
    return {
        "enabled": True,
        "selector_stage": "after_ir_before_evidence_package",
        "do_not_modify_ir": True,
        "core_methods": [
            "shap_attribution_coverage",
            "shap_entropy_policy",
            "concept_aware_grouping",
        ],
        "coverage": {
            "enabled": True,
            "importance_signal": "abs_shap_value",
            "default_threshold_s3": S3_COVERAGE_THRESHOLD,
            "default_threshold_s4": S4_COVERAGE_THRESHOLD,
            "k_min": ADAPTIVE_K_MIN,
            "k_max_s3": ADAPTIVE_K_MAX_S3,
            "k_max_s4": ADAPTIVE_K_MAX_S4,
        },
        "entropy": {
            "enabled": True,
            "compute_on": "full_feature_factors",
            "low_threshold": LOW_ENTROPY_THRESHOLD,
            "high_threshold": HIGH_ENTROPY_THRESHOLD,
            "purpose": "narrative_policy_control_not_feature_ranking",
        },
        "concept_grouping": {
            "enabled": True,
            "method": "deterministic_grouping_by_concept_and_direction",
            "purpose": "reduce_repetition_without_embedding_dependency",
        },
        "cosine_redundancy": {
            "enabled": False,
            "status": "optional_future_extension",
            "reason": (
                "Cosine similarity may depend on embedding model and threshold. "
                "Core pipeline uses SHAP coverage, entropy policy and concept grouping."
            ),
        },
        "semantic_text_fields": [
            "display_name",
            "concept_display_name",
            "safe_phrase",
            "value_type",
            "unit",
            "description",
        ],
    }


def make_llm_input_contract(
    prediction: Dict[str, Any],
    top_increasing: List[Dict[str, Any]],
    top_decreasing: List[Dict[str, Any]],
    top_concepts: List[Dict[str, Any]],
    compact_view: Dict[str, Any],
    allowed_claim_ids: List[str],
    forbidden_rule_ids: List[str],
) -> Dict[str, Any]:
    return {
        "task": "generate_grounded_credit_risk_explanation",
        "language_target": DEFAULT_LLM_TARGET_LANGUAGE,
        "style": DEFAULT_LLM_STYLE,
        "audience": DEFAULT_LLM_AUDIENCE,
        "prediction": prediction,
        "main_risk_increasing_factors": top_increasing,
        "main_risk_decreasing_factors": top_decreasing,
        "main_concepts": top_concepts,
        "compact_llm_view": compact_view,
        "allowed_claim_ids": allowed_claim_ids,
        "forbidden_rule_ids": forbidden_rule_ids,
        "must_include": [
            "Nêu đây là dự đoán của mô hình, không phải kết luận tuyệt đối.",
            "Chỉ dùng evidence có trong IR hoặc Evidence Package.",
            "Nêu đúng chiều tăng/giảm rủi ro của từng yếu tố.",
        ],
        "must_not": [
            "Không khẳng định chắc chắn tuyệt đối.",
            "Không nói SHAP là nguyên nhân đời thực.",
            "Không thêm feature, concept hoặc số liệu ngoài evidence.",
            "Không đưa lời khuyên tài chính cá nhân.",
        ],
        "required_output_sections": [
            "summary",
            "prediction",
            "main_risk_increasing_factors",
            "main_risk_decreasing_factors",
            "uncertainty_note",
        ],
    }


def make_validation_contract(
    allowed_claim_ids: List[str],
    forbidden_rule_ids: List[str],
) -> Dict[str, Any]:
    return {
        "validator_batch": "Batch J - Claim-level Faithfulness Validator",
        "validation_scope": "claim_level",
        "allowed_claim_ids": allowed_claim_ids,
        "forbidden_rule_ids": forbidden_rule_ids,
        "checks": [
            "unsupported_feature",
            "unsupported_concept",
            "wrong_direction",
            "unsupported_magnitude",
            "causal_overclaim",
            "absolute_wording",
            "unsupported_advice",
            "missing_uncertainty",
        ],
    }


def make_ir_base(
    ir_id: str,
    source_evidence_id: str,
    trace_id: str,
    run_mode: str,
    has_ground_truth: bool,
) -> Dict[str, Any]:
    return {
        "ir_id": ir_id,
        "source_evidence_id": source_evidence_id,
        "trace_id": trace_id,
        "run_mode": run_mode,
        "has_ground_truth": has_ground_truth,
        "ir_schema_version": IR_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
    }