from selector import fixed_top_features, select_by_coverage, compute_entropy, build_concept_grouping


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


# Lấy thông tin prediction từ IR.
def get_prediction(ir):
    prediction = ir.get("prediction_summary") or ir.get("prediction")
    if isinstance(prediction, dict):
        return prediction
    return {}


# Lấy claim_policy nếu IR có cung cấp.
def get_claim_policy(ir):
    policy = ir.get("claim_policy")
    if isinstance(policy, dict):
        return policy
    return {}


# Lấy danh sách claim được phép sinh.
def get_allowed_claim_ids(ir):
    policy = get_claim_policy(ir)
    value = policy.get("allowed_claim_ids") or policy.get("allowed_claims") or ir.get("allowed_claims")

    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                result.append(item.get("claim_id") or item.get("id"))
            else:
                result.append(item)
        return [x for x in result if x is not None]

    return []


# Lấy danh sách claim bị cấm.
def get_forbidden_claims(ir):
    policy = get_claim_policy(ir)
    value = policy.get("forbidden_claims") or ir.get("forbidden_claims")

    if isinstance(value, list):
        return value

    return []


# Lấy concept evidence từ IR.
def get_concept_evidence(ir):
    value = ir.get("concept_evidence")
    if isinstance(value, list):
        return value

    views = ir.get("evidence_views")
    if isinstance(views, dict):
        for key in ("concept_evidence", "top_concepts", "concepts", "concept_level_evidence"):
            if isinstance(views.get(key), list):
                return views.get(key)

    metrics = ir.get("xai_quality_metrics")
    if isinstance(metrics, dict):
        for key in ("concept_evidence", "concept_aggregation", "concepts", "top_concepts"):
            if isinstance(metrics.get(key), list):
                return metrics.get(key)

    adaptive_contract = ir.get("adaptive_selection_contract")
    if isinstance(adaptive_contract, dict):
        for key in ("concept_evidence", "concepts", "top_concepts"):
            if isinstance(adaptive_contract.get(key), list):
                return adaptive_contract.get(key)

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

    return result


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
        "evidence_level": evidence_level,
        "customer": customer,
        "prediction": get_prediction(ir),
        "selected_evidence": [],
        "concept_evidence": [],
        "selection_metrics": {},
        "narrative_policy": {},
        "constraints": {
            "allowed_claim_ids": get_allowed_claim_ids(ir),
            "forbidden_rule_ids": get_forbidden_rule_ids(ir),
            "claim_policy": get_claim_policy(ir),
        },
        "audit_trace": {
            "source_ir_id": source_ir_id,
            "source_evidence_id": source_evidence_id,
            "selection_method": None,
            "selected_feature_ids": [],
            "not_selected_feature_count": len(get_feature_factors(ir)),
        },
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
        "forbidden_claims": get_forbidden_claims(ir),
    }

    package["audit_trace"]["selection_method"] = "prediction_only"

    return package


# Tạo S1 package với raw SHAP top 10.
def build_s1_package(ir):
    features = get_feature_factors(ir)
    selected = fixed_top_features(features, 10)
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
        "fixed_top_k": 10,
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
        "avoid_single_cause_wording": False,
        "allow_main_reason_wording": True,
        "must_include_distributed_evidence_note": False,
        "forbidden_claims": get_forbidden_claims(ir),
    }

    package["audit_trace"].update({
        "selection_method": "fixed_raw_shap_top10",
        "selected_feature_ids": [x.get("feature_id") for x in package["selected_evidence"]],
        "not_selected_feature_count": max(len(features) - len(package["selected_evidence"]), 0),
    })

    return package


# Tạo S2 package với semantic top 10 nếu có evidence view.
def build_s2_package(ir):
    features = get_top10_from_view(ir)
    if not features:
        features = get_feature_factors(ir)

    selected = fixed_top_features(features, 10)
    package = base_package(ir, "S2")

    package["selected_evidence"] = []
    for item in selected:
        package["selected_evidence"].append({
            "feature_id": item.get("feature_id"),
            "display_name": item.get("display_name"),
            "concept": item.get("concept"),
            "concept_display_name": item.get("concept_display_name"),
            "direction": item.get("direction"),
            "strength": item.get("strength"),
            "safe_phrase": item.get("safe_phrase"),
            "rank": item.get("rank"),
            "shap_value": item.get("shap_value"),
            "abs_shap_value": item.get("abs_shap_value"),
        })

    package["selection_metrics"] = {
        "selected_evidence_count": len(package["selected_evidence"]),
        "fixed_top_k": 10,
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
        "avoid_single_cause_wording": False,
        "allow_main_reason_wording": True,
        "must_include_distributed_evidence_note": False,
        "forbidden_claims": get_forbidden_claims(ir),
    }

    package["audit_trace"].update({
        "selection_method": "fixed_semantic_shap_top10",
        "selected_feature_ids": [x.get("feature_id") for x in package["selected_evidence"]],
        "not_selected_feature_count": max(len(get_feature_factors(ir)) - len(package["selected_evidence"]), 0),
    })

    return package


# Tạo S3 package bằng adaptive SHAP coverage ngưỡng 0.60.
def build_s3_package(ir):
    features = get_feature_factors(ir)
    result = select_by_coverage(features, 0.60, 3, 10)
    package = base_package(ir, "S3")

    package["selected_evidence"] = result["selected"]

    package["selection_metrics"] = {
        "adaptive_k": result["adaptive_k"],
        "selected_evidence_count": len(result["selected"]),
        "coverage": result["coverage"],
        "coverage_threshold": result["coverage_threshold"],
        "coverage_status": result["coverage_status"],
        "normalized_entropy": None,
        "entropy_level": None,
        "total_abs_shap_mass": result["total_abs_shap_mass"],
        "top10_coverage_from_gplus": get_topk_coverage(ir, "top10"),
        "top20_coverage_from_gplus": get_topk_coverage(ir, "top20"),
    }

    package["narrative_policy"] = {
        "must_include_uncertainty": True,
        "avoid_single_cause_wording": False,
        "allow_main_reason_wording": True,
        "must_include_distributed_evidence_note": False,
        "forbidden_claims": get_forbidden_claims(ir),
    }

    package["audit_trace"].update({
        "selection_method": "adaptive_shap_coverage_0.60_k3_10",
        "selected_feature_ids": result["selected_feature_ids"],
        "not_selected_feature_count": max(len(features) - len(result["selected"]), 0),
    })

    return package


# Tạo S4 package bằng adaptive coverage, entropy và concept grouping.
def build_s4_package(ir):
    features = get_feature_factors(ir)
    result = select_by_coverage(features, 0.70, 5, 20)
    entropy = compute_entropy(features)
    grouping = build_concept_grouping(result["selected"])

    package = base_package(ir, "S4")

    package["selected_evidence"] = result["selected"]
    package["concept_evidence"] = get_concept_evidence(ir)
    package["concept_grouping"] = grouping
    package["xai_quality_metrics"] = ir.get("xai_quality_metrics") if isinstance(ir.get("xai_quality_metrics"), dict) else {}

    package["selection_metrics"] = {
        "adaptive_k": result["adaptive_k"],
        "selected_evidence_count": len(result["selected"]),
        "coverage": result["coverage"],
        "coverage_threshold": result["coverage_threshold"],
        "coverage_status": result["coverage_status"],
        "normalized_entropy": entropy["normalized_entropy"],
        "entropy_level": entropy["entropy_level"],
        "total_abs_shap_mass": result["total_abs_shap_mass"],
        "concept_group_count": grouping["concept_group_count"],
        "mixed_concept_group_count": len(grouping["mixed_concept_groups"]),
        "grouped_supporting_feature_count": len(grouping["grouped_supporting_features"]),
        "top10_coverage_from_gplus": get_topk_coverage(ir, "top10"),
        "top20_coverage_from_gplus": get_topk_coverage(ir, "top20"),
    }

    high_entropy = entropy["entropy_level"] == "high"

    package["narrative_policy"] = {
        "must_include_uncertainty": True,
        "avoid_single_cause_wording": high_entropy,
        "allow_main_reason_wording": not high_entropy,
        "must_include_distributed_evidence_note": high_entropy,
        "mention_mixed_signals": len(grouping["mixed_concept_groups"]) > 0,
        "forbidden_claims": get_forbidden_claims(ir),
    }

    package["audit_trace"].update({
        "selection_method": "adaptive_shap_coverage_0.70_entropy_concept_grouping_k5_20",
        "selected_feature_ids": result["selected_feature_ids"],
        "not_selected_feature_count": max(len(features) - len(result["selected"]), 0),
    })

    return package


# Tạo S5 package theo baseline backend-overguided skeleton.
def build_s5_package(ir):
    features = get_top10_from_view(ir)
    if not features:
        features = get_feature_factors(ir)

    selected = fixed_top_features(features, 10)
    package = base_package(ir, "S5")

    package["selected_evidence"] = selected

    package["backend_explanation_skeleton"] = {
        "prediction_statement": get_prediction(ir),
        "main_factor_slots": [
            {
                "feature_id": item.get("feature_id"),
                "display_name": item.get("display_name"),
                "concept": item.get("concept"),
                "direction": item.get("direction"),
                "rank": item.get("rank"),
                "safe_phrase": item.get("safe_phrase"),
            }
            for item in selected[:5]
        ],
        "required_uncertainty_note": True,
        "forbidden_wording": [
            "direct cause",
            "guarantee",
            "certainly default",
            "only reason",
        ],
    }

    package["selection_metrics"] = {
        "selected_evidence_count": len(selected),
        "fixed_top_k": 10,
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
        "forbidden_claims": get_forbidden_claims(ir),
    }

    package["audit_trace"].update({
        "selection_method": "backend_overguided_skeleton_top10",
        "selected_feature_ids": [x.get("feature_id") for x in selected],
        "not_selected_feature_count": max(len(get_feature_factors(ir)) - len(selected), 0),
    })

    return package


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
    return [
        build_s0_package(ir),
        build_s1_package(ir),
        build_s2_package(ir),
        build_s3_package(ir),
        build_s4_package(ir),
        build_s5_package(ir),
    ]