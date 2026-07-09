from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ml.scripts.explanation_ir_layer.config import (
    DEFAULT_AUDIT_TOP_K,
    DEFAULT_MAX_CONCEPTS_FOR_LLM,
    DEFAULT_MAX_RISK_FACTORS_PER_DIRECTION,
    DEFAULT_TOP_K_FOR_LLM,
    MAX_ADDITIVITY_ERROR_FOR_READY,
    MAX_CONCEPT_SUM_ERROR_FOR_READY,
    MAX_UNKNOWN_CONCEPT_SHARE_FOR_READY,
    MIN_TOP10_COVERAGE_FOR_READY,
    RECORD_STATUS_FAILED,
    RECORD_STATUS_PASSED,
    RECORD_STATUS_WARNING,
    SOURCE_BATCH_NAME,
    SOURCE_QUALITY_BATCH_NAME,
)
from ml.scripts.explanation_ir_layer.ir_schema import (
    direction_from_shap,
    format_probability,
    format_probability_percent,
    label_text_from_class,
    make_adaptive_selection_contract,
    make_claim_policy,
    make_evidence_exposure_contract,
    make_ir_base,
    make_llm_input_contract,
    make_safe_phrase_for_direction,
    make_validation_contract,
    normalize_text,
    round_float,
    safe_bool,
    safe_float,
    safe_int,
    strength_from_abs_shap,
    threshold_comparison_from_probability,
    utc_now_iso,
)


@dataclass
class ExplanationIRBuildResult:
    ir_records: List[Dict[str, Any]]
    summary_rows: List[Dict[str, Any]]
    warnings: List[str]
    errors: List[str]
    joined_gplus_count: int
    missing_gplus_count: int


def get_nested_value(data: Dict[str, Any], path: str) -> Any:
    cur: Any = data

    for part in path.split("."):
        if not isinstance(cur, dict):
            return None

        if part not in cur:
            return None

        cur = cur[part]

    return cur


def first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        return value

    return None


def normalize_policy(value: Any) -> str:
    if value is None:
        return "true"

    text = str(value).strip().lower()

    if text in {"true", "1", "yes", "y"}:
        return "true"

    if text in {"false", "0", "no", "n"}:
        return "false"

    if text == "limited":
        return "limited"

    return text


def feature_visible(sensitive: Optional[bool], policy: str) -> bool:
    if policy in {"false", "limited"}:
        return False

    if sensitive is True:
        return False

    return True


def concept_name(concept_id: Any) -> str:
    text = str(concept_id or "unknown_feature_group").replace("_", " ").strip()

    if not text:
        return "Unknown feature group"

    return text[:1].upper() + text[1:]


def get_evidence_id(record: Dict[str, Any], idx: int) -> str:
    value = (
        record.get("evidence_id")
        or record.get("source_evidence_id")
        or get_nested_value(record, "metadata.evidence_id")
    )

    if value is None or not str(value).strip():
        return f"xai_missing_evidence_id_{idx:06d}"

    return str(value)


def make_ir_id(evidence_id: str) -> str:
    return f"ir_{evidence_id}"


def make_trace_id(evidence_id: str) -> str:
    return f"trace_{evidence_id}"


def build_model_info(record: Dict[str, Any]) -> Dict[str, Any]:
    model = record.get("model") or {}

    return {
        "model_name": str(model.get("model_name") or "unknown_model"),
        "model_version": str(model.get("model_version") or "unknown_version"),
        "model_family": str(model.get("model_family") or "unknown_family"),
        "dataset_branch": model.get("dataset_branch"),
        "feature_count": safe_int(model.get("feature_count")),
    }


def build_customer_info(record: Dict[str, Any]) -> Dict[str, Any]:
    customer = record.get("customer") or {}
    prediction = record.get("prediction") or {}
    metadata = record.get("metadata") or {}

    return {
        "SK_ID_CURR": safe_int(
            first_present(
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
        ),
        "row_index": safe_int(
            first_present(
                customer.get("row_index"),
                prediction.get("row_index"),
                metadata.get("row_index"),
                record.get("row_index"),
            )
        ),
        "case_type": first_present(
            customer.get("case_type"),
            prediction.get("case_type"),
            metadata.get("case_type"),
            record.get("case_type"),
        ),
        "selection_rank": safe_int(
            first_present(
                customer.get("selection_rank"),
                prediction.get("selection_rank"),
                metadata.get("selection_rank"),
                record.get("selection_rank"),
            )
        ),
    }


def build_prediction_summary(
    record: Dict[str, Any],
    has_ground_truth: bool,
) -> Dict[str, Any]:
    prediction = record.get("prediction") or {}

    y_pred = safe_int(
        first_present(
            prediction.get("y_pred"),
            prediction.get("predicted_class"),
        )
    )
    y_true = safe_int(prediction.get("y_true"))

    probability = safe_float(
        first_present(
            prediction.get("y_proba"),
            prediction.get("probability"),
        )
    )
    threshold = safe_float(prediction.get("threshold"), default=0.5)

    predicted_label = first_present(
        prediction.get("predicted_label_text"),
        prediction.get("predicted_label"),
        label_text_from_class(y_pred),
    )

    true_label_text = first_present(
        prediction.get("true_label_text"),
        label_text_from_class(y_true),
    )

    if probability is not None and threshold is not None:
        above_threshold = probability >= threshold
    else:
        above_threshold = None

    return {
        "predicted_class": y_pred,
        "predicted_label": str(predicted_label),
        "probability": round_float(probability),
        "probability_display": format_probability(probability),
        "probability_percent_display": format_probability_percent(probability),
        "threshold": round_float(threshold),
        "threshold_display": format_probability(threshold),
        "threshold_percent_display": format_probability_percent(threshold),
        "threshold_comparison": threshold_comparison_from_probability(probability, threshold),
        "is_above_threshold": above_threshold,
        "true_label": y_true if has_ground_truth else None,
        "true_label_text": true_label_text if has_ground_truth else "unknown_label",
        "has_ground_truth": has_ground_truth,
    }


def build_xai_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    shap = record.get("shap") or {}
    quality = record.get("quality") or {}

    additivity_error = safe_float(shap.get("additivity_error"))
    passed = first_present(
        shap.get("passed_additivity_check"),
        quality.get("passed_additivity_check"),
    )

    if passed is None and additivity_error is not None:
        tolerance = safe_float(quality.get("additivity_tolerance"), default=0.01)
        passed = additivity_error <= tolerance

    return {
        "method": str(first_present(shap.get("xai_method"), shap.get("method"), "SHAP")),
        "explainer_type": shap.get("explainer_type"),
        "output_space": shap.get("output_space"),
        "base_value": round_float(shap.get("base_value")),
        "model_output": round_float(shap.get("model_output")),
        "shap_sum": round_float(shap.get("shap_sum")),
        "reconstructed_output": round_float(shap.get("reconstructed_output")),
        "additivity_error": round_float(additivity_error),
        "passed_additivity_check": safe_bool(passed, passed),
        "faithfulness_basis": (
            "base_value + sum(shap_values) should approximately equal "
            "model_output in the configured SHAP output space."
        ),
    }


def normalize_feature(feature: Dict[str, Any], idx: int) -> Dict[str, Any]:
    metadata = feature.get("metadata") or {}
    registry = metadata.get("feature_registry") or {}

    rank = safe_int(feature.get("rank"), default=idx + 1) or (idx + 1)

    feature_name = str(
        first_present(
            feature.get("feature_name"),
            feature.get("preprocessed_feature_name"),
            f"unknown_feature_{rank}",
        )
    )

    raw_feature_name = first_present(
        feature.get("raw_feature_name"),
        registry.get("raw_feature_name"),
    )

    display_name = str(
        first_present(
            feature.get("display_name"),
            registry.get("display_name"),
            feature_name,
        )
    )

    concept = str(
        first_present(
            feature.get("concept"),
            feature.get("concept_id"),
            registry.get("concept"),
            registry.get("concept_id"),
            "unknown_feature_group",
        )
    )

    concept_display_name = str(
        first_present(
            metadata.get("concept_display_name"),
            registry.get("concept_display_name"),
            concept_name(concept),
        )
    )

    sensitive = safe_bool(
        first_present(
            metadata.get("sensitive"),
            registry.get("sensitive"),
        )
    )

    policy = normalize_policy(
        first_present(
            metadata.get("allowed_in_user_explanation"),
            registry.get("allowed_in_user_explanation"),
            "true",
        )
    )

    shap_value = safe_float(feature.get("shap_value"), default=0.0) or 0.0
    abs_shap = safe_float(feature.get("abs_shap_value"))

    if abs_shap is None:
        abs_shap = abs(shap_value)

    direction = direction_from_shap(shap_value)
    source_direction = feature.get("direction")

    if source_direction is None:
        direction_consistent = True
    else:
        direction_consistent = str(source_direction) == direction

    value_type = first_present(
        metadata.get("value_type"),
        registry.get("value_type"),
    )
    unit = first_present(
        metadata.get("unit"),
        registry.get("unit"),
    )
    description = first_present(
        metadata.get("description"),
        registry.get("description"),
        registry.get("business_description"),
        "",
    )

    safe_phrase = make_safe_phrase_for_direction(display_name, direction)

    semantic_parts = [
        display_name,
        concept_display_name,
        safe_phrase,
        value_type or "",
        unit or "",
        description or "",
    ]
    semantic_text = " ".join(str(x).strip() for x in semantic_parts if str(x).strip())

    visible = feature_visible(sensitive, policy)

    return {
        "factor_id": f"factor_{rank:03d}",
        "rank": rank,
        "feature_name": feature_name,
        "raw_feature_name": raw_feature_name,
        "display_name": display_name,
        "concept": concept,
        "concept_display_name": concept_display_name,
        "value": first_present(feature.get("value"), feature.get("feature_value")),
        "value_type": value_type,
        "unit": unit,
        "description": description,
        "semantic_text": semantic_text,
        "shap_value": round_float(shap_value) or 0.0,
        "abs_shap_value": round_float(abs_shap) or 0.0,
        "direction": direction,
        "strength": strength_from_abs_shap(abs_shap),
        "llm_visible": visible,
        "claimable": visible,
        "evidence_source": "local_features",
        "source_direction": str(source_direction) if source_direction is not None else None,
        "direction_consistent": direction_consistent,
        "safe_phrase": safe_phrase,
        "sensitive": sensitive,
        "allowed_in_user_explanation": policy,
        "direction_prior": first_present(
            metadata.get("direction_prior"),
            registry.get("direction_prior"),
        ),
        "formatting_rule": first_present(
            metadata.get("formatting_rule"),
            registry.get("formatting_rule"),
        ),
        "contribution_percent_of_top_k_abs": round_float(
            feature.get("contribution_percent_of_top_k_abs")
        ),
    }


def build_feature_factors(record: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    local_features = record.get("local_features") or []
    warnings: List[str] = []
    factors: List[Dict[str, Any]] = []

    if not isinstance(local_features, list):
        return [], ["local_features is not a list"]

    for idx, feature in enumerate(local_features):
        if not isinstance(feature, dict):
            warnings.append(f"local_features[{idx}] is not an object")
            continue

        factor = normalize_feature(feature, idx)
        factors.append(factor)

        if not factor["direction_consistent"]:
            warnings.append(
                f"{factor['factor_id']}: source_direction={factor['source_direction']} "
                f"differs from shap_direction={factor['direction']}"
            )

    factors.sort(key=lambda x: (x["rank"], -x["abs_shap_value"]))
    return factors, warnings


def compact_feature(factor: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "factor_id": factor["factor_id"],
        "rank": factor["rank"],
        "feature_name": factor["feature_name"],
        "display_name": factor["display_name"],
        "concept": factor["concept"],
        "concept_display_name": factor.get("concept_display_name"),
        "value": factor.get("value"),
        "shap_value": factor["shap_value"],
        "abs_shap_value": factor["abs_shap_value"],
        "direction": factor["direction"],
        "strength": factor["strength"],
        "safe_phrase": factor.get("safe_phrase"),
        "semantic_text": factor.get("semantic_text"),
    }


def top_abs_features(
    factors: List[Dict[str, Any]],
    k: int,
    visible_only: bool = True,
) -> List[Dict[str, Any]]:
    rows = []

    for factor in factors:
        if visible_only and not factor.get("llm_visible"):
            continue
        rows.append(factor)

    rows.sort(key=lambda x: (-x["abs_shap_value"], x["rank"]))
    return rows[:k]


def build_concept_summaries_from_factors(
    factors: List[Dict[str, Any]],
    limit: int = DEFAULT_MAX_CONCEPTS_FOR_LLM,
) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for factor in factors:
        if factor.get("allowed_in_user_explanation") == "false":
            continue

        concept = factor.get("concept") or "unknown_feature_group"
        groups.setdefault(concept, []).append(factor)

    summaries: List[Dict[str, Any]] = []

    for concept, rows in groups.items():
        net = 0.0
        abs_sum = 0.0
        pos = 0
        neg = 0
        neu = 0

        for row in rows:
            shap = safe_float(row.get("shap_value"), default=0.0) or 0.0
            abs_value = safe_float(row.get("abs_shap_value"), default=0.0) or 0.0
            net += shap
            abs_sum += abs_value

            if row.get("direction") == "increases_risk":
                pos += 1
            elif row.get("direction") == "decreases_risk":
                neg += 1
            else:
                neu += 1

        rows.sort(key=lambda x: (-x["abs_shap_value"], x["rank"]))
        direction = direction_from_shap(net)
        display = first_present(rows[0].get("concept_display_name"), concept_name(concept))

        summaries.append(
            {
                "concept_id": concept,
                "display_name": str(display),
                "net_shap_value": round_float(net) or 0.0,
                "total_abs_shap_value": round_float(abs_sum) or 0.0,
                "direction": direction,
                "strength": strength_from_abs_shap(abs_sum),
                "feature_count": len(rows),
                "positive_feature_count": pos,
                "negative_feature_count": neg,
                "neutral_feature_count": neu,
                "has_mixed_directions": pos > 0 and neg > 0,
                "top_factor_ids": [x["factor_id"] for x in rows[:3]],
                "top_feature_display_names": [x["display_name"] for x in rows[:3]],
                "llm_visible": True,
                "claimable": direction != "neutral",
                "safe_phrase": make_safe_phrase_for_direction(str(display), direction),
            }
        )

    summaries.sort(key=lambda x: (-x["total_abs_shap_value"], x["concept_id"]))
    return summaries[:limit]


def parse_top_features(value: Any) -> List[str]:
    if value is None:
        return []

    text = str(value).strip()

    if not text:
        return []

    if "|" in text:
        return [x.strip() for x in text.split("|") if x.strip()]

    if ";" in text:
        return [x.strip() for x in text.split(";") if x.strip()]

    if "," in text:
        return [x.strip() for x in text.split(",") if x.strip()]

    return [text]


def build_concept_evidence(
    evidence_id: str,
    factors: List[Dict[str, Any]],
    concept_rows: List[Dict[str, Any]],
    quality_row: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    all_concepts: List[Dict[str, Any]] = []

    if concept_rows:
        for row in concept_rows:
            concept = str(row.get("concept_group") or row.get("concept_id") or "unknown_feature_group")

            all_concepts.append(
                {
                    "concept_group": concept,
                    "display_name": concept_name(concept),
                    "rank": safe_int(row.get("concept_rank")),
                    "shap_value": round_float(row.get("concept_shap_value")) or 0.0,
                    "abs_shap": round_float(row.get("concept_abs_shap")) or 0.0,
                    "direction": row.get("concept_direction"),
                    "feature_count": safe_int(row.get("feature_count_in_concept")),
                    "top_features": parse_top_features(row.get("top_features_in_concept")),
                }
            )
    else:
        summaries = build_concept_summaries_from_factors(factors, limit=9999)

        for idx, row in enumerate(summaries, start=1):
            all_concepts.append(
                {
                    "concept_group": row["concept_id"],
                    "display_name": row["display_name"],
                    "rank": idx,
                    "shap_value": row["net_shap_value"],
                    "abs_shap": row["total_abs_shap_value"],
                    "direction": row["direction"],
                    "feature_count": row["feature_count"],
                    "top_features": row["top_feature_display_names"],
                }
            )

    all_concepts.sort(key=lambda x: safe_int(x.get("rank"), default=999999) or 999999)

    feature_sum = sum(safe_float(x.get("shap_value"), default=0.0) or 0.0 for x in factors)
    concept_sum = sum(safe_float(x.get("shap_value"), default=0.0) or 0.0 for x in all_concepts)
    feature_abs_sum = sum(safe_float(x.get("abs_shap_value"), default=0.0) or 0.0 for x in factors)

    unknown_abs = 0.0
    unknown_count = 0

    for factor in factors:
        if factor.get("concept") == "unknown_feature_group":
            unknown_count += 1
            unknown_abs += safe_float(factor.get("abs_shap_value"), default=0.0) or 0.0

    if quality_row:
        concept_sum_error = safe_float(quality_row.get("concept_sum_error"))
        concept_sum_error_abs = safe_float(quality_row.get("concept_sum_error_abs"))
        unknown_share = safe_float(quality_row.get("unknown_feature_group_abs_share"))
        unknown_count_from_quality = safe_int(quality_row.get("unknown_feature_group_count"))
    else:
        concept_sum_error = feature_sum - concept_sum
        concept_sum_error_abs = abs(concept_sum_error)
        unknown_share = unknown_abs / feature_abs_sum if feature_abs_sum else 0.0
        unknown_count_from_quality = unknown_count

    return {
        "top_concepts": all_concepts[:DEFAULT_MAX_CONCEPTS_FOR_LLM],
        "all_concepts": all_concepts,
        "accounting": {
            "feature_shap_sum": round_float(feature_sum),
            "concept_shap_sum": round_float(concept_sum),
            "concept_sum_error": round_float(concept_sum_error),
            "concept_sum_error_abs": round_float(concept_sum_error_abs),
            "feature_abs_shap_sum": round_float(feature_abs_sum),
            "unknown_feature_group_count": unknown_count_from_quality,
            "unknown_feature_group_abs_share": round_float(unknown_share),
        },
        "source": "xai_concept_aggregation_report" if concept_rows else "computed_from_feature_factors",
        "source_evidence_id": evidence_id,
    }


def build_xai_quality_metrics(
    quality_row: Optional[Dict[str, Any]],
    xai_summary: Dict[str, Any],
) -> Dict[str, Any]:
    if quality_row is None:
        return {
            "status": "missing",
            "additivity": {
                "error": xai_summary.get("additivity_error"),
                "abs_error": xai_summary.get("additivity_error"),
                "passed": xai_summary.get("passed_additivity_check"),
            },
            "topk_coverage": {},
            "direction_balance": {},
            "concept_accounting": {},
            "comprehensiveness": {"status": "missing"},
            "sufficiency": {"status": "missing"},
            "stability": {"status": "missing", "score": None},
        }

    stability_status = quality_row.get("stability_status")

    if stability_status is None or not str(stability_status).strip():
        stability_status = "skipped"

    return {
        "status": "available",
        "additivity": {
            "error": round_float(quality_row.get("additivity_error")),
            "abs_error": round_float(quality_row.get("additivity_error_abs")),
            "passed": safe_bool(quality_row.get("additivity_pass"), default=True),
        },
        "topk_coverage": {
            "top3": round_float(quality_row.get("top3_coverage")),
            "top5": round_float(quality_row.get("top5_coverage")),
            "top10": round_float(quality_row.get("top10_coverage")),
            "top20": round_float(quality_row.get("top20_coverage")),
            "recommended_top_k_s3": 10,
            "recommended_top_k_s4": 20,
        },
        "direction_balance": {
            "positive_shap_sum": round_float(quality_row.get("positive_shap_sum")),
            "negative_shap_sum": round_float(quality_row.get("negative_shap_sum")),
            "positive_abs_share": round_float(quality_row.get("positive_abs_share")),
            "negative_abs_share": round_float(quality_row.get("negative_abs_share")),
            "top_positive_feature_count": safe_int(quality_row.get("top_positive_feature_count")),
            "top_negative_feature_count": safe_int(quality_row.get("top_negative_feature_count")),
            "neutral_feature_count": safe_int(quality_row.get("neutral_feature_count")),
        },
        "concept_accounting": {
            "concept_sum_error": round_float(quality_row.get("concept_sum_error")),
            "concept_sum_error_abs": round_float(quality_row.get("concept_sum_error_abs")),
            "concept_coverage_top3": round_float(quality_row.get("concept_coverage_top3")),
            "unknown_feature_group_count": safe_int(quality_row.get("unknown_feature_group_count")),
            "unknown_feature_group_abs_share": round_float(
                quality_row.get("unknown_feature_group_abs_share")
            ),
            "top1_concept": quality_row.get("top1_concept"),
            "top3_concepts": quality_row.get("top3_concepts"),
        },
        "comprehensiveness": {
            "status": "completed"
            if safe_float(quality_row.get("comprehensiveness_top10")) is not None
            else "missing",
            "top5_probability_drop": round_float(quality_row.get("comprehensiveness_top5")),
            "top10_probability_drop": round_float(quality_row.get("comprehensiveness_top10")),
            "method": "median_baseline_replacement_top_abs_shap_features",
            "note": "Perturbation sanity check, not causal intervention.",
        },
        "sufficiency": {
            "status": "completed"
            if safe_float(quality_row.get("sufficiency_drop_top10")) is not None
            else "missing",
            "top5_drop": round_float(quality_row.get("sufficiency_drop_top5")),
            "top10_drop": round_float(quality_row.get("sufficiency_drop_top10")),
            "method": "median_baseline_keep_top_abs_shap_features",
            "note": "Perturbation sanity check, not causal intervention.",
        },
        "stability": {
            "status": str(stability_status),
            "score": round_float(quality_row.get("stability_score")),
            "reason": "Repeated SHAP runs are not available."
            if str(stability_status) == "skipped"
            else None,
        },
    }


def build_evidence_readiness(
    metrics: Dict[str, Any],
    has_gplus: bool,
) -> Dict[str, Any]:
    if not has_gplus:
        return {
            "status": "NOT_READY",
            "suitable_for_llm_grounding": False,
            "recommended_default_exposure_level": "S2",
            "recommended_top_k": DEFAULT_TOP_K_FOR_LLM,
            "quality_notes": [],
            "warnings": ["missing_batch_g_plus_metrics"],
        }

    notes: List[str] = []
    warnings: List[str] = []

    additivity = metrics.get("additivity") or {}
    topk = metrics.get("topk_coverage") or {}
    concept = metrics.get("concept_accounting") or {}
    stability = metrics.get("stability") or {}

    add_error = safe_float(additivity.get("abs_error"))
    if add_error is None:
        add_error = 999.0

    top10 = safe_float(topk.get("top10"))
    if top10 is None:
        top10 = 0.0

    concept_error = safe_float(concept.get("concept_sum_error_abs"))
    if concept_error is None:
        concept_error = 999.0

    unknown_share = safe_float(concept.get("unknown_feature_group_abs_share"))
    if unknown_share is None:
        unknown_share = 1.0

    if additivity.get("passed") is True and add_error <= MAX_ADDITIVITY_ERROR_FOR_READY:
        notes.append("additivity_passed")
    else:
        warnings.append("additivity_not_passed")

    if top10 >= MIN_TOP10_COVERAGE_FOR_READY:
        notes.append("top10_coverage_acceptable")
    else:
        warnings.append("low_top10_coverage")

    if concept_error <= MAX_CONCEPT_SUM_ERROR_FOR_READY:
        notes.append("concept_accounting_passed")
    else:
        warnings.append("concept_accounting_warning")

    if unknown_share <= MAX_UNKNOWN_CONCEPT_SHARE_FOR_READY:
        notes.append("unknown_concept_share_acceptable")
    else:
        warnings.append("high_unknown_concept_share")

    if stability.get("status") == "skipped":
        warnings.append("stability_not_available")
    elif stability.get("status") == "completed":
        notes.append("stability_completed")

    if "additivity_not_passed" in warnings or "concept_accounting_warning" in warnings:
        status = "NOT_READY"
        suitable = False
    elif warnings:
        status = "READY_WITH_WARNINGS"
        suitable = True
    else:
        status = "READY"
        suitable = True

    return {
        "status": status,
        "suitable_for_llm_grounding": suitable,
        "recommended_default_exposure_level": "S3",
        "recommended_top_k": DEFAULT_TOP_K_FOR_LLM,
        "quality_notes": notes,
        "warnings": warnings,
    }


def build_evidence_views(
    prediction: Dict[str, Any],
    factors: List[Dict[str, Any]],
    concept_evidence: Dict[str, Any],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    top3 = [compact_feature(x) for x in top_abs_features(factors, 3)]
    top5 = [compact_feature(x) for x in top_abs_features(factors, 5)]
    top10 = [compact_feature(x) for x in top_abs_features(factors, 10)]
    top20 = [compact_feature(x) for x in top_abs_features(factors, 20)]

    increasing = []
    decreasing = []

    for factor in factors:
        if not factor.get("llm_visible"):
            continue

        if factor.get("direction") == "increases_risk":
            increasing.append(factor)

        if factor.get("direction") == "decreases_risk":
            decreasing.append(factor)

    increasing.sort(key=lambda x: (-x["abs_shap_value"], x["rank"]))
    decreasing.sort(key=lambda x: (-x["abs_shap_value"], x["rank"]))

    top_concepts = concept_evidence.get("top_concepts") or []

    return {
        "top3_abs_features": top3,
        "top5_abs_features": top5,
        "top10_abs_features": top10,
        "top20_abs_features": top20,
        "top_risk_increasing_features": [
            compact_feature(x) for x in increasing[:DEFAULT_MAX_RISK_FACTORS_PER_DIRECTION]
        ],
        "top_risk_decreasing_features": [
            compact_feature(x) for x in decreasing[:DEFAULT_MAX_RISK_FACTORS_PER_DIRECTION]
        ],
        "top_concepts": top_concepts,
        "compact_llm_view": {
            "prediction": prediction,
            "top_features_default_s3": top10,
            "top_features_audit_s4": top20,
            "top_concepts": top_concepts,
            "quality_notes": {
                "top10_coverage": (metrics.get("topk_coverage") or {}).get("top10"),
                "top20_coverage": (metrics.get("topk_coverage") or {}).get("top20"),
                "stability_status": (metrics.get("stability") or {}).get("status"),
                "comprehensiveness_top10": (
                    metrics.get("comprehensiveness") or {}
                ).get("top10_probability_drop"),
                "sufficiency_drop_top10": (
                    metrics.get("sufficiency") or {}
                ).get("top10_drop"),
            },
        },
    }


def build_contribution_accounting(
    factors: List[Dict[str, Any]],
    xai_summary: Dict[str, Any],
) -> Dict[str, Any]:
    total_sum = 0.0
    total_abs = 0.0
    visible_count = 0

    for factor in factors:
        total_sum += safe_float(factor.get("shap_value"), default=0.0) or 0.0
        total_abs += safe_float(factor.get("abs_shap_value"), default=0.0) or 0.0

        if factor.get("llm_visible"):
            visible_count += 1

    top10 = top_abs_features(factors, 10)
    top20 = top_abs_features(factors, 20)

    top10_abs = sum(safe_float(x.get("abs_shap_value"), default=0.0) or 0.0 for x in top10)
    top20_abs = sum(safe_float(x.get("abs_shap_value"), default=0.0) or 0.0 for x in top20)

    return {
        "output_space": xai_summary.get("output_space"),
        "total_feature_count": len(factors),
        "visible_feature_count": visible_count,
        "hidden_or_nonclaimable_feature_count": len(factors) - visible_count,
        "base_value": xai_summary.get("base_value"),
        "model_output": xai_summary.get("model_output"),
        "shap_sum": xai_summary.get("shap_sum"),
        "reconstructed_output": xai_summary.get("reconstructed_output"),
        "all_feature_sum": round_float(total_sum),
        "all_feature_abs_sum": round_float(total_abs),
        "top10_abs_sum": round_float(top10_abs),
        "top20_abs_sum": round_float(top20_abs),
        "top10_abs_coverage": round_float(top10_abs / total_abs if total_abs else None),
        "top20_abs_coverage": round_float(top20_abs / total_abs if total_abs else None),
        "accounting_note": (
            "IR keeps full local SHAP evidence. LLM-facing packages should be "
            "created later by Adaptive Evidence Selection."
        ),
    }


def build_feature_tiers(factors: List[Dict[str, Any]]) -> Dict[str, Any]:
    top20 = [compact_feature(x) for x in top_abs_features(factors, 20)]

    return {
        "primary_features": top20[:8],
        "supporting_features": top20[8:],
        "remaining_features_summary": {
            "remaining_count": max(len(factors) - len(top20), 0),
        },
        "hidden_or_nonclaimable_summary": {
            "hidden_count": sum(1 for x in factors if not x.get("llm_visible")),
        },
        "tiering_rules": {
            "primary_features": "top visible absolute SHAP features",
            "supporting_features": "next visible absolute SHAP features",
        },
    }


def make_evidence_ref(
    ref_type: str,
    ref_id: str,
    field: str,
    value: Any,
) -> Dict[str, Any]:
    return {
        "ref_type": ref_type,
        "ref_id": ref_id,
        "field": field,
        "value": value,
    }


def make_truth_condition(field: str, operator: str, value: Any) -> Dict[str, Any]:
    return {
        "field": field,
        "operator": operator,
        "value": value,
    }


def build_allowed_claims(
    prediction: Dict[str, Any],
    factors: List[Dict[str, Any]],
    concept_evidence: Dict[str, Any],
) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []

    claims.append(
        {
            "claim_id": "claim_prediction_label",
            "claim_type": "prediction_label",
            "subject_type": "prediction",
            "subject_id": "prediction",
            "predicate": "equals",
            "object": prediction.get("predicted_label"),
            "direction": None,
            "strength": None,
            "natural_language_template": (
                f"Mô hình dự đoán khách hàng thuộc nhóm "
                f"{prediction.get('predicted_label')}."
            ),
            "evidence_refs": [
                make_evidence_ref(
                    "prediction_summary",
                    "prediction",
                    "predicted_label",
                    prediction.get("predicted_label"),
                )
            ],
            "truth_condition": make_truth_condition(
                "prediction_summary.predicted_label",
                "equals",
                prediction.get("predicted_label"),
            ),
            "claim_scope": "local_case",
            "verdict_from_ir": True,
            "claim_status": "allowed",
            "severity_if_contradicted": "high",
        }
    )

    claims.append(
        {
            "claim_id": "claim_probability_threshold_comparison",
            "claim_type": "probability_threshold_comparison",
            "subject_type": "prediction",
            "subject_id": "prediction",
            "predicate": prediction.get("threshold_comparison"),
            "object": prediction.get("threshold"),
            "direction": None,
            "strength": None,
            "natural_language_template": (
                f"Xác suất dự đoán là {prediction.get('probability_percent_display')}, "
                f"so với ngưỡng {prediction.get('threshold_percent_display')}."
            ),
            "evidence_refs": [
                make_evidence_ref(
                    "prediction_summary",
                    "prediction",
                    "probability",
                    prediction.get("probability"),
                ),
                make_evidence_ref(
                    "prediction_summary",
                    "prediction",
                    "threshold",
                    prediction.get("threshold"),
                ),
            ],
            "truth_condition": make_truth_condition(
                "prediction_summary.threshold_comparison",
                "equals",
                prediction.get("threshold_comparison"),
            ),
            "claim_scope": "local_case",
            "verdict_from_ir": True,
            "claim_status": "allowed",
            "severity_if_contradicted": "high",
        }
    )

    if prediction.get("has_ground_truth"):
        claims.append(
            {
                "claim_id": "claim_true_label_available",
                "claim_type": "true_label_available",
                "subject_type": "ground_truth",
                "subject_id": "true_label",
                "predicate": "equals",
                "object": prediction.get("true_label_text"),
                "direction": None,
                "strength": None,
                "natural_language_template": (
                    f"Nhãn thật của mẫu đánh giá này là "
                    f"{prediction.get('true_label_text')}."
                ),
                "evidence_refs": [
                    make_evidence_ref(
                        "prediction_summary",
                        "prediction",
                        "true_label_text",
                        prediction.get("true_label_text"),
                    )
                ],
                "truth_condition": make_truth_condition(
                    "prediction_summary.true_label_text",
                    "equals",
                    prediction.get("true_label_text"),
                ),
                "claim_scope": "local_case",
                "verdict_from_ir": True,
                "claim_status": "allowed",
                "severity_if_contradicted": "medium",
            }
        )

    claimable_features = []

    for factor in factors:
        if not factor.get("claimable"):
            continue

        if not factor.get("llm_visible"):
            continue

        if factor.get("direction") == "neutral":
            continue

        claimable_features.append(factor)

    claimable_features.sort(key=lambda x: (-x["abs_shap_value"], x["rank"]))

    for idx, factor in enumerate(claimable_features[:DEFAULT_AUDIT_TOP_K], start=1):
        claims.append(
            {
                "claim_id": f"claim_feature_{idx:03d}",
                "claim_type": "feature_contribution",
                "subject_type": "feature",
                "subject_id": factor.get("feature_name"),
                "predicate": "contributed_to",
                "object": f"{factor.get('direction')}_model_predicted_risk",
                "direction": factor.get("direction"),
                "strength": factor.get("strength"),
                "natural_language_template": factor.get("safe_phrase"),
                "evidence_refs": [
                    make_evidence_ref(
                        "feature_factor",
                        factor.get("factor_id"),
                        "shap_value",
                        factor.get("shap_value"),
                    ),
                    make_evidence_ref(
                        "feature_factor",
                        factor.get("factor_id"),
                        "direction",
                        factor.get("direction"),
                    ),
                ],
                "truth_condition": make_truth_condition(
                    f"feature_factors.{factor.get('factor_id')}.direction",
                    "equals",
                    factor.get("direction"),
                ),
                "claim_scope": "local_case",
                "verdict_from_ir": True,
                "claim_status": "allowed",
                "severity_if_contradicted": "high",
            }
        )

    for idx, concept in enumerate((concept_evidence.get("top_concepts") or [])[:5], start=1):
        direction = concept.get("direction")

        if direction == "neutral" or direction is None:
            continue

        concept_id = concept.get("concept_group")
        display_name = concept.get("display_name") or concept_name(concept_id)

        claims.append(
            {
                "claim_id": f"claim_concept_{idx:03d}",
                "claim_type": "concept_contribution",
                "subject_type": "concept",
                "subject_id": concept_id,
                "predicate": "contributed_to",
                "object": f"{direction}_model_predicted_risk",
                "direction": direction,
                "strength": strength_from_abs_shap(concept.get("abs_shap")),
                "natural_language_template": make_safe_phrase_for_direction(display_name, direction),
                "evidence_refs": [
                    make_evidence_ref(
                        "concept_evidence",
                        str(concept_id),
                        "direction",
                        direction,
                    ),
                    make_evidence_ref(
                        "concept_evidence",
                        str(concept_id),
                        "shap_value",
                        concept.get("shap_value"),
                    ),
                ],
                "truth_condition": make_truth_condition(
                    f"concept_evidence.{concept_id}.direction",
                    "equals",
                    direction,
                ),
                "claim_scope": "local_case",
                "verdict_from_ir": True,
                "claim_status": "allowed",
                "severity_if_contradicted": "medium",
            }
        )

    claims.append(
        {
            "claim_id": "claim_model_prediction_not_absolute",
            "claim_type": "uncertainty_note",
            "subject_type": "model_prediction",
            "subject_id": "prediction_uncertainty",
            "predicate": "must_be_described_as",
            "object": "model_prediction_not_absolute_conclusion",
            "direction": None,
            "strength": None,
            "natural_language_template": (
                "Đây là dự đoán thống kê của mô hình, không phải kết luận tuyệt đối."
            ),
            "evidence_refs": [
                make_evidence_ref(
                    "claim_policy",
                    "claim_policy",
                    "required_uncertainty_note",
                    True,
                )
            ],
            "truth_condition": make_truth_condition(
                "claim_policy.required_uncertainty_note",
                "equals",
                True,
            ),
            "claim_scope": "local_case",
            "verdict_from_ir": True,
            "claim_status": "allowed",
            "severity_if_contradicted": "high",
        }
    )

    return claims


def build_forbidden_claims() -> List[Dict[str, Any]]:
    return [
        {
            "forbidden_id": "forbid_certainty_wording",
            "rule_type": "no_certainty",
            "severity": "high",
            "natural_language_rule": "Không mô tả dự đoán như kết luận chắc chắn.",
            "reason": "Model output là xác suất dự đoán, không phải kết luận tuyệt đối.",
            "forbidden_patterns": ["chắc chắn", "luôn luôn", "khẳng định tuyệt đối"],
        },
        {
            "forbidden_id": "forbid_real_world_causality",
            "rule_type": "no_real_world_causality",
            "severity": "high",
            "natural_language_rule": "Không nói feature là nguyên nhân đời thực.",
            "reason": "SHAP phản ánh đóng góp vào prediction của mô hình, không phải nhân quả đời thực.",
            "forbidden_patterns": ["gây ra", "là nguyên nhân trực tiếp", "dẫn đến chắc chắn"],
        },
        {
            "forbidden_id": "forbid_unsupported_feature",
            "rule_type": "no_unsupported_feature_or_concept",
            "severity": "high",
            "natural_language_rule": "Không nhắc feature hoặc concept không có trong evidence.",
            "reason": "LLM chỉ được dùng evidence trong IR hoặc Evidence Package.",
            "forbidden_patterns": [],
        },
        {
            "forbidden_id": "forbid_direction_reversal",
            "rule_type": "no_direction_reversal",
            "severity": "high",
            "natural_language_rule": "Không đảo chiều tăng/giảm rủi ro của SHAP.",
            "reason": "Chiều tác động phải bám vào dấu SHAP.",
            "forbidden_patterns": [],
        },
        {
            "forbidden_id": "forbid_financial_advice",
            "rule_type": "no_financial_advice",
            "severity": "medium",
            "natural_language_rule": "Không đưa lời khuyên tài chính cá nhân.",
            "reason": "Hệ thống chỉ giải thích dự đoán, không tư vấn quyết định tài chính.",
            "forbidden_patterns": ["nên vay", "không nên vay", "phải trả", "phải làm"],
        },
    ]


def build_one_ir_record(
    record: Dict[str, Any],
    idx: int,
    run_mode: str,
    has_ground_truth: bool,
    source_file: str | Path,
    quality_by_evidence_id: Dict[str, Dict[str, Any]],
    concepts_by_evidence_id: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Dict[str, Any], bool, List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []

    evidence_id = get_evidence_id(record, idx)

    model = build_model_info(record)
    customer = build_customer_info(record)
    prediction = build_prediction_summary(record, has_ground_truth)
    xai_summary = build_xai_summary(record)

    factors, factor_warnings = build_feature_factors(record)
    warnings.extend(factor_warnings)

    if not factors:
        errors.append("no feature_factors created")

    quality_row = quality_by_evidence_id.get(evidence_id)
    concept_rows = concepts_by_evidence_id.get(evidence_id, [])
    has_gplus = quality_row is not None

    if quality_row is None:
        warnings.append("missing Batch G+ quality metrics")

    if not concept_rows:
        warnings.append("missing Batch G+ concept aggregation rows; fallback to feature aggregation")

    xai_quality_metrics = build_xai_quality_metrics(quality_row, xai_summary)
    concept_evidence = build_concept_evidence(evidence_id, factors, concept_rows, quality_row)
    evidence_readiness = build_evidence_readiness(xai_quality_metrics, has_gplus)
    evidence_views = build_evidence_views(prediction, factors, concept_evidence, xai_quality_metrics)

    claim_policy = make_claim_policy()
    allowed_claims = build_allowed_claims(prediction, factors, concept_evidence)
    forbidden_claims = build_forbidden_claims()

    allowed_claim_ids = []

    for claim in allowed_claims:
        if claim.get("claim_type") == "true_label_available":
            continue

        allowed_claim_ids.append(claim.get("claim_id"))

    forbidden_rule_ids = [item.get("forbidden_id") for item in forbidden_claims]

    ir_record = {
        **make_ir_base(
            ir_id=make_ir_id(evidence_id),
            source_evidence_id=evidence_id,
            trace_id=make_trace_id(evidence_id),
            run_mode=run_mode,
            has_ground_truth=has_ground_truth,
        ),
        "model": model,
        "customer": customer,
        "prediction_summary": prediction,
        "xai_summary": xai_summary,
        "xai_quality_metrics": xai_quality_metrics,
        "evidence_readiness": evidence_readiness,
        "feature_factors": factors,
        "risk_increasing_factors": evidence_views["top_risk_increasing_features"],
        "risk_decreasing_factors": evidence_views["top_risk_decreasing_features"],
        "concept_summaries": build_concept_summaries_from_factors(factors),
        "concept_evidence": concept_evidence,
        "contribution_accounting": build_contribution_accounting(factors, xai_summary),
        "feature_tiers": build_feature_tiers(factors),
        "evidence_views": evidence_views,
        "allowed_claims": allowed_claims,
        "forbidden_claims": forbidden_claims,
        "claim_policy": claim_policy,
        "llm_input_contract": make_llm_input_contract(
            prediction=prediction,
            top_increasing=evidence_views["top_risk_increasing_features"],
            top_decreasing=evidence_views["top_risk_decreasing_features"],
            top_concepts=evidence_views["top_concepts"],
            compact_view=evidence_views["compact_llm_view"],
            allowed_claim_ids=allowed_claim_ids,
            forbidden_rule_ids=forbidden_rule_ids,
        ),
        "validation_contract": make_validation_contract(
            allowed_claim_ids=allowed_claim_ids,
            forbidden_rule_ids=forbidden_rule_ids,
        ),
        "evidence_exposure_contract": make_evidence_exposure_contract(),
        "adaptive_selection_contract": make_adaptive_selection_contract(),
        "evidence_trace": {
            "source_batch": SOURCE_BATCH_NAME,
            "source_quality_batch": SOURCE_QUALITY_BATCH_NAME,
            "source_evidence_id": evidence_id,
            "source_file": str(source_file),
            "quality_metrics_available": quality_row is not None,
            "quality_join_key": "evidence_id",
        },
        "metadata": {
            "builder_version": "v2",
            "record_index": idx,
            "source_created_at": record.get("created_at"),
            "built_at": utc_now_iso(),
        },
    }

    if evidence_readiness.get("status") == "NOT_READY":
        warnings.append("evidence_readiness is NOT_READY")

    stability = xai_quality_metrics.get("stability") or {}
    if stability.get("status") == "skipped":
        warnings.append("stability metric skipped")

    if errors:
        record_status = RECORD_STATUS_FAILED
    elif warnings:
        record_status = RECORD_STATUS_WARNING
    else:
        record_status = RECORD_STATUS_PASSED

    ir_record["quality"] = {
        "status": record_status,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "warnings": warnings,
        "errors": errors,
    }

    return ir_record, has_gplus, warnings, errors


def build_summary_rows(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for record in records:
        prediction = record.get("prediction_summary") or {}
        customer = record.get("customer") or {}
        quality = record.get("quality") or {}
        readiness = record.get("evidence_readiness") or {}
        metrics = record.get("xai_quality_metrics") or {}
        topk = metrics.get("topk_coverage") or {}
        comp = metrics.get("comprehensiveness") or {}
        suff = metrics.get("sufficiency") or {}
        concept_acc = (record.get("concept_evidence") or {}).get("accounting") or {}

        rows.append(
            {
                "ir_id": record.get("ir_id"),
                "source_evidence_id": record.get("source_evidence_id"),
                "SK_ID_CURR": customer.get("SK_ID_CURR"),
                "case_type": customer.get("case_type"),
                "predicted_label": prediction.get("predicted_label"),
                "probability": prediction.get("probability"),
                "true_label": prediction.get("true_label"),
                "record_quality_status": quality.get("status"),
                "evidence_readiness_status": readiness.get("status"),
                "suitable_for_llm_grounding": readiness.get("suitable_for_llm_grounding"),
                "top3_coverage": topk.get("top3"),
                "top5_coverage": topk.get("top5"),
                "top10_coverage": topk.get("top10"),
                "top20_coverage": topk.get("top20"),
                "comprehensiveness_top10": comp.get("top10_probability_drop"),
                "sufficiency_drop_top10": suff.get("top10_drop"),
                "concept_sum_error_abs": concept_acc.get("concept_sum_error_abs"),
                "unknown_feature_group_abs_share": concept_acc.get("unknown_feature_group_abs_share"),
                "stability_status": (metrics.get("stability") or {}).get("status"),
                "feature_factor_count": len(record.get("feature_factors") or []),
                "allowed_claim_count": len(record.get("allowed_claims") or []),
                "forbidden_claim_count": len(record.get("forbidden_claims") or []),
            }
        )

    return rows


def build_explanation_ir_records(
    evidence_records: List[Dict[str, Any]],
    run_mode: str,
    has_ground_truth: bool,
    source_file: str | Path,
    quality_by_evidence_id: Optional[Dict[str, Dict[str, Any]]] = None,
    concepts_by_evidence_id: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> ExplanationIRBuildResult:
    quality_by_evidence_id = quality_by_evidence_id or {}
    concepts_by_evidence_id = concepts_by_evidence_id or {}

    ir_records: List[Dict[str, Any]] = []
    warnings: List[str] = []
    errors: List[str] = []

    joined = 0
    missing = 0

    for idx, record in enumerate(evidence_records):
        try:
            ir_record, has_gplus, record_warnings, record_errors = build_one_ir_record(
                record=record,
                idx=idx,
                run_mode=run_mode,
                has_ground_truth=has_ground_truth,
                source_file=source_file,
                quality_by_evidence_id=quality_by_evidence_id,
                concepts_by_evidence_id=concepts_by_evidence_id,
            )
        except Exception as exc:
            evidence_id = get_evidence_id(record, idx)
            errors.append(f"record_index={idx}, evidence_id={evidence_id}: {exc}")
            continue

        ir_records.append(ir_record)

        for warning in record_warnings:
            warnings.append(f"{ir_record['source_evidence_id']}: {warning}")

        for error in record_errors:
            errors.append(f"{ir_record['source_evidence_id']}: {error}")

        if has_gplus:
            joined += 1
        else:
            missing += 1

    return ExplanationIRBuildResult(
        ir_records=ir_records,
        summary_rows=build_summary_rows(ir_records),
        warnings=warnings,
        errors=errors,
        joined_gplus_count=joined,
        missing_gplus_count=missing,
    )