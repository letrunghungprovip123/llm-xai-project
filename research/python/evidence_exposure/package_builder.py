import copy

from .config import (
    EVIDENCE_PACKAGE_SCHEMA_VERSION,
    S1_TOP_K,
    S2_TOP_K,
    S3_COVERAGE_THRESHOLD,
    S3_K_MIN,
    S3_K_MAX,
    S4_COVERAGE_THRESHOLD,
    S4_K_MIN,
    S4_K_MAX,
)
from .selector import (
    fixed_top_features,
    select_by_coverage,
    compute_entropy,
    build_concept_grouping,
    get_abs_shap,
    normalize_feature,
)


# Lấy danh sách feature factors từ IR hoặc từ evidence.
def get_feature_factors(ir):
    value = ir.get("feature_factors")
    if isinstance(value, list):
        return value

    evidence = ir.get("evidence")
    if isinstance(evidence, dict) and isinstance(evidence.get("feature_factors"), list):
        return evidence.get("feature_factors")

    return []


# Lấy top 10 feature đã được chuẩn bị sẵn trong evidence_views nếu có.
def get_top10_from_view(ir):
    views = ir.get("evidence_views")
    if not isinstance(views, dict):
        return []

    for key in ("top10_abs_features", "top_10_abs_features", "top10_features", "top_features"):
        if isinstance(views.get(key), list):
            return views.get(key)

    return []


# Lấy thông tin prediction đầy đủ từ IR.
def get_prediction(ir):
    prediction = ir.get("prediction_summary") or ir.get("prediction")
    if isinstance(prediction, dict):
        return prediction
    return {}


# Chỉ lấy các field prediction an toàn để đưa vào prompt.
def get_prompt_prediction(ir):
    prediction = get_prediction(ir)
    allowed_keys = (
        "predicted_class",
        "predicted_label",
        "probability",
        "probability_display",
        "probability_percent_display",
        "threshold",
        "threshold_display",
        "threshold_percent_display",
        "threshold_comparison",
        "is_above_threshold",
    )

    result = {}
    for key in allowed_keys:
        if key in prediction:
            result[key] = prediction.get(key)

    return result


# Lấy metadata ground truth nhưng không đưa vào prompt_payload.
def get_ground_truth_metadata(ir):
    prediction = get_prediction(ir)

    return {
        "has_ground_truth": bool(prediction.get("has_ground_truth", ir.get("has_ground_truth", False))),
        "true_label": prediction.get("true_label"),
        "true_label_text": prediction.get("true_label_text"),
    }


# Lấy claim_policy nếu IR có cung cấp.
def get_claim_policy(ir):
    policy = ir.get("claim_policy")
    if isinstance(policy, dict):
        return policy
    return {}


# Lấy danh sách claim bị cấm.
def get_forbidden_claims(ir):
    policy = get_claim_policy(ir)
    value = policy.get("forbidden_claims") or ir.get("forbidden_claims")

    if isinstance(value, list):
        return value

    return []


# Lấy danh sách rule id bị cấm.
def get_forbidden_rule_ids(ir):
    result = []

    for item in get_forbidden_claims(ir):
        if isinstance(item, dict):
            value = (
                item.get("forbidden_id")
                or item.get("rule_id")
                or item.get("claim_id")
                or item.get("id")
                or item.get("name")
            )
        else:
            value = item

        if value is not None:
            result.append(value)

    if result:
        return result

    return [
        "forbid_certainty_wording",
        "forbid_real_world_causality",
        "forbid_unsupported_feature",
        "forbid_direction_reversal",
        "forbid_financial_advice",
    ]


# Tạo semantic lookup từ feature factors và evidence view.
def build_semantic_lookup(ir):
    result = {}
    sources = []
    sources.extend(get_feature_factors(ir))
    sources.extend(get_top10_from_view(ir))

    for item in sources:
        if not isinstance(item, dict):
            continue

        feature_id = item.get("feature_id") or item.get("feature_name") or item.get("name")
        if feature_id is None:
            continue

        current = result.get(feature_id, {})
        merged = dict(current)

        for key in (
            "feature_name",
            "display_name",
            "feature_display_name",
            "display_name_source",
            "concept",
            "feature_group",
            "concept_id",
            "concept_display_name",
            "concept_name",
            "strength",
            "safe_phrase",
            "raw_value",
            "value",
        ):
            value = item.get(key)
            if value is not None:
                merged[key] = value

        result[feature_id] = merged

    return result


# Semantic hóa feature nhưng giữ nguyên identity, rank và SHAP từ raw selection.
def build_semantic_evidence(raw_selected, ir):
    semantic_lookup = build_semantic_lookup(ir)
    result = []

    for raw_item in raw_selected:
        feature_id = raw_item.get("feature_id")
        merged = dict(raw_item)
        semantic = semantic_lookup.get(feature_id) or {}

        for key in (
            "feature_name",
            "display_name",
            "feature_display_name",
            "display_name_source",
            "concept",
            "feature_group",
            "concept_id",
            "concept_display_name",
            "concept_name",
            "strength",
            "safe_phrase",
            "raw_value",
            "value",
        ):
            value = semantic.get(key)
            if value is not None:
                merged[key] = value

        normalized = normalize_feature(merged, rank=raw_item.get("rank"))
        normalized["shap_value"] = raw_item.get("shap_value")
        normalized["abs_shap_value"] = raw_item.get("abs_shap_value")
        normalized["direction"] = raw_item.get("direction")
        result.append(normalized)

    return result


# Tính coverage thật của selected evidence trên toàn bộ SHAP mass.
def compute_selected_coverage(features, selected_evidence):
    total_mass = sum(get_abs_shap(item) for item in features if isinstance(item, dict))
    selected_mass = sum(get_abs_shap(item) for item in selected_evidence if isinstance(item, dict))

    if total_mass <= 0:
        return 0.0, 0.0

    return selected_mass / total_mass, total_mass


# Tạo claim policy riêng cho từng evidence level.
def build_level_claim_policy(evidence_level):
    policy = {
        "allow_prediction_claim": True,
        "allow_uncertainty_claim": True,
        "allow_feature_claim": evidence_level != "S0",
        "allow_concept_claim": evidence_level in ("S2", "S3", "S4", "S5"),
        "allow_direction_claim": evidence_level != "S0",
        "allow_magnitude_claim": evidence_level in ("S2", "S3", "S4", "S5"),
        "allow_causal_claim": False,
        "allow_financial_advice": False,
        "allow_absolute_decision_claim": False,
        "allow_true_label_claim": False,
    }

    if evidence_level == "S1":
        policy["allow_concept_claim"] = False
        policy["allow_magnitude_claim"] = False

    return policy


# Tạo allowed claim IDs theo đúng evidence được expose.
def build_allowed_claim_ids(evidence_level, feature_ids, concept_ids):
    result = [
        "claim_prediction_label",
        "claim_probability_threshold_comparison",
        "claim_model_prediction_not_absolute",
    ]

    if evidence_level == "S0":
        return result

    for index, _ in enumerate(feature_ids, start=1):
        result.append(f"claim_feature_{index:03d}")

    if evidence_level in ("S2", "S3", "S4", "S5"):
        for index, _ in enumerate(concept_ids, start=1):
            result.append(f"claim_concept_{index:03d}")

    return result


# Tạo constraints từ đúng selected evidence của từng level.
def build_constraints(ir, evidence_level, selected_evidence, concept_evidence=None, allowed_feature_ids=None):
    selected_feature_ids = [
        item.get("feature_id")
        for item in selected_evidence
        if isinstance(item, dict) and item.get("feature_id") is not None
    ]

    if allowed_feature_ids is None:
        allowed_feature_ids = selected_feature_ids

    concept_ids = []

    for item in concept_evidence or []:
        if not isinstance(item, dict):
            continue

        concept = item.get("concept") or item.get("concept_id")
        if concept is not None and concept not in concept_ids:
            concept_ids.append(concept)

    return {
        "allowed_claim_ids": build_allowed_claim_ids(
            evidence_level,
            allowed_feature_ids,
            concept_ids,
        ),
        "allowed_feature_ids": allowed_feature_ids,
        "allowed_concept_ids": concept_ids,
        "forbidden_rule_ids": get_forbidden_rule_ids(ir),
        "claim_policy": build_level_claim_policy(evidence_level),
    }


# Chỉ đưa selection context cần thiết của từng level vào prompt.
def build_prompt_selection_context(package):
    level = package.get("evidence_level")
    metrics = package.get("selection_metrics") or {}

    result = {
        "selected_evidence_count": metrics.get("selected_evidence_count"),
    }

    if level in ("S3", "S4", "S5"):
        result.update({
            "adaptive_k": metrics.get("adaptive_k"),
            "coverage": metrics.get("coverage"),
            "coverage_threshold": metrics.get("coverage_threshold"),
            "coverage_status": metrics.get("coverage_status"),
        })

    if level in ("S4", "S5"):
        result.update({
            "normalized_entropy": metrics.get("normalized_entropy"),
            "entropy_level": metrics.get("entropy_level"),
            "concept_group_count": metrics.get("concept_group_count"),
            "mixed_concept_group_count": metrics.get("mixed_concept_group_count"),
        })

    return result


# Tạo prompt_payload an toàn, không chứa ground truth hay metadata đánh giá.
def finalize_prompt_payload(package):
    payload = {
        "evidence_level": package.get("evidence_level"),
        "prediction": copy.deepcopy(package.get("prediction") or {}),
        "selected_evidence": copy.deepcopy(package.get("selected_evidence") or []),
        "concept_evidence": copy.deepcopy(package.get("concept_evidence") or []),
        "selection_context": build_prompt_selection_context(package),
        "narrative_policy": copy.deepcopy(package.get("narrative_policy") or {}),
        "constraints": copy.deepcopy(package.get("constraints") or {}),
    }

    if package.get("backend_explanation_skeleton"):
        payload["backend_explanation_skeleton"] = copy.deepcopy(
            package.get("backend_explanation_skeleton")
        )

    package["prompt_payload"] = payload
    return package


# Tạo khung package chung cho mọi evidence level.
def base_package(ir, evidence_level):
    source_ir_id = ir.get("ir_id") or ir.get("source_ir_id")
    source_evidence_id = ir.get("source_evidence_id") or ir.get("evidence_id")

    customer = ir.get("customer") or ir.get("customer_context")
    if not isinstance(customer, dict):
        value = ir.get("sk_id_curr") or ir.get("customer_id")
        if value is not None:
            customer = {"customer_id": value}
        else:
            customer = {}

    return {
        "package_id": f"pkg_{evidence_level}_{source_ir_id}",
        "source_ir_id": source_ir_id,
        "source_evidence_id": source_evidence_id,
        "trace_id": ir.get("trace_id"),
        "run_mode": ir.get("run_mode", "evaluation"),
        "ir_schema_version": ir.get("ir_schema_version"),
        "evidence_package_schema_version": EVIDENCE_PACKAGE_SCHEMA_VERSION,
        "evidence_level": evidence_level,
        "internal_metadata": {
            "customer": customer,
            "ground_truth": get_ground_truth_metadata(ir),
        },
        "prediction": get_prompt_prediction(ir),
        "selected_evidence": [],
        "concept_evidence": [],
        "selection_metrics": {},
        "narrative_policy": {},
        "constraints": {},
        "audit_trace": {
            "source_ir_id": source_ir_id,
            "source_evidence_id": source_evidence_id,
            "selection_method": None,
            "selected_feature_ids": [],
            "not_selected_feature_count": len(get_feature_factors(ir)),
        },
        "prompt_payload": {},
    }


# Tạo S0 package chỉ có prediction, không đưa feature evidence cho LLM.
def build_s0_package(ir):
    package = base_package(ir, "S0")

    package["selection_metrics"] = {
        "selected_evidence_count": 0,
        "coverage": None,
        "coverage_threshold": None,
        "coverage_status": "NOT_APPLICABLE",
        "normalized_entropy": None,
        "entropy_level": None,
        "top10_coverage_from_gplus": get_topk_coverage(ir, "top10"),
        "top20_coverage_from_gplus": get_topk_coverage(ir, "top20"),
    }

    package["narrative_policy"] = {
        "must_include_uncertainty": True,
        "avoid_single_cause_wording": True,
        "allow_main_reason_wording": False,
        "must_include_distributed_evidence_note": False,
        "must_not_give_specific_feature_reason": True,
    }

    package["constraints"] = build_constraints(ir, "S0", [])
    package["audit_trace"]["selection_method"] = "prediction_only"

    return finalize_prompt_payload(package)


# Tạo S1 package với raw SHAP top 10.
def build_s1_package(ir):
    features = get_feature_factors(ir)
    selected = fixed_top_features(features, S1_TOP_K)
    coverage, total_mass = compute_selected_coverage(features, selected)
    package = base_package(ir, "S1")

    package["selected_evidence"] = []
    for item in selected:
        package["selected_evidence"].append({
            "feature_id": item.get("feature_id"),
            "feature_name": item.get("feature_name"),
            "shap_value": item.get("shap_value"),
            "abs_shap_value": item.get("abs_shap_value"),
            "direction": item.get("direction"),
            "rank": item.get("rank"),
        })

    package["selection_metrics"] = {
        "selected_evidence_count": len(package["selected_evidence"]),
        "fixed_top_k": S1_TOP_K,
        "coverage": coverage,
        "coverage_threshold": None,
        "coverage_status": "MEASURED_NOT_TARGETED",
        "normalized_entropy": None,
        "entropy_level": None,
        "total_abs_shap_mass": total_mass,
        "top10_coverage_from_gplus": get_topk_coverage(ir, "top10"),
        "top20_coverage_from_gplus": get_topk_coverage(ir, "top20"),
    }

    package["narrative_policy"] = {
        "must_include_uncertainty": True,
        "avoid_single_cause_wording": False,
        "allow_main_reason_wording": True,
        "must_include_distributed_evidence_note": False,
    }

    package["constraints"] = build_constraints(
        ir,
        "S1",
        package["selected_evidence"],
    )

    package["audit_trace"].update({
        "selection_method": "fixed_raw_shap_top10",
        "selected_feature_ids": [x.get("feature_id") for x in package["selected_evidence"]],
        "not_selected_feature_count": max(len(features) - len(package["selected_evidence"]), 0),
    })

    return finalize_prompt_payload(package)


# Tạo S2 bằng đúng feature set của S1, chỉ bổ sung semantic metadata.
def build_s2_package(ir, s1_package=None):
    features = get_feature_factors(ir)

    if s1_package is None:
        raw_selected = fixed_top_features(features, S2_TOP_K)
    else:
        raw_selected = copy.deepcopy(s1_package.get("selected_evidence") or [])

    selected = build_semantic_evidence(raw_selected, ir)
    coverage, total_mass = compute_selected_coverage(features, selected)
    package = base_package(ir, "S2")
    package["selected_evidence"] = selected

    package["selection_metrics"] = {
        "selected_evidence_count": len(selected),
        "fixed_top_k": S2_TOP_K,
        "coverage": coverage,
        "coverage_threshold": None,
        "coverage_status": "MEASURED_NOT_TARGETED",
        "normalized_entropy": None,
        "entropy_level": None,
        "total_abs_shap_mass": total_mass,
        "top10_coverage_from_gplus": get_topk_coverage(ir, "top10"),
        "top20_coverage_from_gplus": get_topk_coverage(ir, "top20"),
    }

    package["narrative_policy"] = {
        "must_include_uncertainty": True,
        "avoid_single_cause_wording": False,
        "allow_main_reason_wording": True,
        "must_include_distributed_evidence_note": False,
    }

    package["constraints"] = build_constraints(ir, "S2", selected)

    package["audit_trace"].update({
        "selection_method": "fixed_semantic_enrichment_of_raw_shap_top10",
        "selected_feature_ids": [x.get("feature_id") for x in selected],
        "not_selected_feature_count": max(len(features) - len(selected), 0),
        "source_feature_set": "S1_exact_ordered_top10",
    })

    return finalize_prompt_payload(package)


# Tạo S3 package bằng adaptive SHAP coverage ngưỡng 0.60.
def build_s3_package(ir):
    features = get_feature_factors(ir)
    result = select_by_coverage(
        features,
        S3_COVERAGE_THRESHOLD,
        S3_K_MIN,
        S3_K_MAX,
    )
    package = base_package(ir, "S3")

    package["selected_evidence"] = result["selected"]

    package["selection_metrics"] = {
        "adaptive_k": result["adaptive_k"],
        "selected_evidence_count": len(result["selected"]),
        "coverage": result["coverage"],
        "coverage_threshold": result["coverage_threshold"],
        "coverage_status": result["coverage_status"],
        "coverage_gap": max(result["coverage_threshold"] - result["coverage"], 0.0),
        "is_compacted": result["adaptive_k"] < S3_K_MAX,
        "reached_k_max": result["adaptive_k"] >= min(S3_K_MAX, len(features)),
        "normalized_entropy": None,
        "entropy_level": None,
        "total_abs_shap_mass": result["total_abs_shap_mass"],
        "top10_coverage_from_gplus": get_topk_coverage(ir, "top10"),
        "top20_coverage_from_gplus": get_topk_coverage(ir, "top20"),
    }

    below_target = result["coverage_status"] != "PASSED"

    package["narrative_policy"] = {
        "must_include_uncertainty": True,
        "avoid_single_cause_wording": below_target,
        "allow_main_reason_wording": not below_target,
        "must_include_distributed_evidence_note": False,
        "must_include_partial_evidence_note": below_target,
        "must_not_claim_evidence_is_complete": below_target,
    }

    package["constraints"] = build_constraints(ir, "S3", result["selected"])

    package["audit_trace"].update({
        "selection_method": "adaptive_shap_coverage_0.60_k3_10",
        "selected_feature_ids": result["selected_feature_ids"],
        "not_selected_feature_count": max(len(features) - len(result["selected"]), 0),
    })

    return finalize_prompt_payload(package)


# Tạo S4 package bằng adaptive coverage, entropy và concept grouping.
def build_s4_package(ir):
    features = get_feature_factors(ir)
    result = select_by_coverage(
        features,
        S4_COVERAGE_THRESHOLD,
        S4_K_MIN,
        S4_K_MAX,
    )
    entropy = compute_entropy(features)
    grouping = build_concept_grouping(result["selected"])

    package = base_package(ir, "S4")

    package["selected_evidence"] = result["selected"]
    package["concept_evidence"] = grouping["concept_groups"]
    package["concept_grouping"] = grouping
    package["xai_quality_metrics"] = (
        ir.get("xai_quality_metrics")
        if isinstance(ir.get("xai_quality_metrics"), dict)
        else {}
    )

    package["selection_metrics"] = {
        "adaptive_k": result["adaptive_k"],
        "selected_evidence_count": len(result["selected"]),
        "coverage": result["coverage"],
        "coverage_threshold": result["coverage_threshold"],
        "coverage_status": result["coverage_status"],
        "coverage_gap": max(result["coverage_threshold"] - result["coverage"], 0.0),
        "reached_k_max": result["adaptive_k"] >= min(S4_K_MAX, len(features)),
        "normalized_entropy": entropy["normalized_entropy"],
        "entropy_level": entropy["entropy_level"],
        "total_abs_shap_mass": result["total_abs_shap_mass"],
        "concept_group_count": grouping["concept_group_count"],
        "unique_concept_count": grouping["unique_concept_count"],
        "mixed_concept_group_count": len(grouping["mixed_concept_groups"]),
        "grouped_supporting_feature_count": len(grouping["grouped_supporting_features"]),
        "top10_coverage_from_gplus": get_topk_coverage(ir, "top10"),
        "top20_coverage_from_gplus": get_topk_coverage(ir, "top20"),
    }

    high_entropy = entropy["entropy_level"] == "high"
    below_target = result["coverage_status"] != "PASSED"

    package["narrative_policy"] = {
        "must_include_uncertainty": True,
        "avoid_single_cause_wording": high_entropy or below_target,
        "allow_main_reason_wording": not high_entropy and not below_target,
        "must_include_distributed_evidence_note": high_entropy,
        "must_include_partial_evidence_note": below_target,
        "must_not_claim_evidence_is_complete": below_target,
        "mention_mixed_signals": len(grouping["mixed_concept_groups"]) > 0,
    }

    package["constraints"] = build_constraints(
        ir,
        "S4",
        result["selected"],
        grouping["concept_groups"],
    )

    package["audit_trace"].update({
        "selection_method": "adaptive_shap_coverage_0.70_entropy_concept_direction_grouping_k5_20",
        "selected_feature_ids": result["selected_feature_ids"],
        "not_selected_feature_count": max(len(features) - len(result["selected"]), 0),
        "concept_evidence_source": "selected_evidence_only",
    })

    return finalize_prompt_payload(package)


# Tạo S5 từ đúng evidence của S4 và chỉ bổ sung backend guidance.
def build_s5_package(ir, s4_package=None):
    if s4_package is None:
        s4_package = build_s4_package(ir)

    package = copy.deepcopy(s4_package)
    package["package_id"] = f"pkg_S5_{package.get('source_ir_id')}"
    package["evidence_level"] = "S5"

    representatives = (
        package.get("concept_grouping", {}).get("representative_features") or []
    )
    representatives = sorted(
        representatives,
        key=lambda x: x.get("rank") if x.get("rank") is not None else 10**9,
    )
    main_factor_slots = representatives[:5]

    if not main_factor_slots:
        main_factor_slots = (package.get("selected_evidence") or [])[:5]

    package["backend_explanation_skeleton"] = {
        "prediction_statement": copy.deepcopy(package.get("prediction") or {}),
        "required_section_order": [
            "prediction_summary",
            "main_factors",
            "supporting_factors",
            "uncertainty_note",
            "safe_summary",
        ],
        "main_factor_slots": [
            {
                "feature_id": item.get("feature_id"),
                "display_name": item.get("display_name"),
                "concept": item.get("concept"),
                "concept_display_name": item.get("concept_display_name"),
                "direction": item.get("direction"),
                "rank": item.get("rank"),
                "safe_phrase": item.get("safe_phrase"),
            }
            for item in main_factor_slots
        ],
        "required_uncertainty_note": True,
        "must_follow_factor_order": True,
        "must_not_add_factor_outside_skeleton": True,
        "forbidden_wording": [
            "direct cause",
            "guarantee",
            "certainly default",
            "only reason",
        ],
    }

    package["narrative_policy"] = copy.deepcopy(s4_package.get("narrative_policy") or {})
    package["narrative_policy"].update({
        "backend_controls_factor_order": True,
        "must_follow_backend_skeleton": True,
        "must_not_add_factor_outside_skeleton": True,
    })

    allowed_feature_ids = [
        item.get("feature_id")
        for item in main_factor_slots
        if item.get("feature_id") is not None
    ]

    package["constraints"] = build_constraints(
        ir,
        "S5",
        package.get("selected_evidence") or [],
        package.get("concept_evidence") or [],
        allowed_feature_ids=allowed_feature_ids,
    )

    allowed_concept_ids = []
    for item in main_factor_slots:
        concept = item.get("concept")
        if concept is not None and concept not in allowed_concept_ids:
            allowed_concept_ids.append(concept)
    package["constraints"]["allowed_concept_ids"] = allowed_concept_ids
    package["constraints"]["allowed_claim_ids"] = build_allowed_claim_ids(
        "S5",
        allowed_feature_ids,
        allowed_concept_ids,
    )

    package["audit_trace"] = copy.deepcopy(s4_package.get("audit_trace") or {})
    package["audit_trace"].update({
        "selection_method": "backend_overguided_from_s4_same_evidence",
        "source_evidence_level": "S4",
        "backend_skeleton_feature_ids": allowed_feature_ids,
    })

    return finalize_prompt_payload(package)


# Lấy coverage top-k từ xai_quality_metrics nếu có.
def get_topk_coverage(ir, key):
    metrics = ir.get("xai_quality_metrics")
    if not isinstance(metrics, dict):
        return None

    topk = metrics.get("topk_coverage")
    if isinstance(topk, dict):
        if key == "top10":
            for name in ("top10", "top_10", "coverage_top10"):
                if name in topk:
                    return topk.get(name)
        if key == "top20":
            for name in ("top20", "top_20", "coverage_top20"):
                if name in topk:
                    return topk.get(name)

    if key == "top10":
        for name in ("top10_coverage", "top_10_coverage", "coverage_top10", "mean_top10_coverage"):
            if name in metrics:
                return metrics.get(name)

    if key == "top20":
        for name in ("top20_coverage", "top_20_coverage", "coverage_top20", "mean_top20_coverage"):
            if name in metrics:
                return metrics.get(name)

    return None


# Build đầy đủ các package S0 đến S5 cho một IR.
def build_all_packages_for_ir(ir):
    s0 = build_s0_package(ir)
    s1 = build_s1_package(ir)
    s2 = build_s2_package(ir, s1_package=s1)
    s3 = build_s3_package(ir)
    s4 = build_s4_package(ir)
    s5 = build_s5_package(ir, s4_package=s4)

    return [s0, s1, s2, s3, s4, s5]
