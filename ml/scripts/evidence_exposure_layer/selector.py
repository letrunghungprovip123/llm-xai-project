import math


# Ép giá trị về float an toàn.
def safe_float(value, default=0.0):
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# Lấy trị tuyệt đối SHAP từ nhiều dạng field khác nhau.
def get_abs_shap(feature):
    for key in ("abs_shap_value", "abs_shap", "absolute_shap_value", "abs_contribution"):
        if key in feature:
            return abs(safe_float(feature.get(key)))

    for key in ("shap_value", "contribution", "contribution_value", "phi"):
        if key in feature:
            return abs(safe_float(feature.get(key)))

    return 0.0


# Lấy SHAP gốc có dấu âm/dương.
def get_shap_value(feature):
    for key in ("shap_value", "contribution", "contribution_value", "phi"):
        if key in feature:
            return safe_float(feature.get(key))

    return 0.0


# Suy luận chiều tác động nếu feature chưa có direction.
def infer_direction(feature):
    current = feature.get("direction") or feature.get("risk_direction") or feature.get("effect_direction")
    if current:
        return str(current)

    shap_value = get_shap_value(feature)

    if shap_value > 1e-12:
        return "increase_risk"
    if shap_value < -1e-12:
        return "decrease_risk"

    return "neutral"


# Chuẩn hóa feature về một schema thống nhất.
def normalize_feature(feature, rank=None):
    feature_id = feature.get("feature_id") or feature.get("feature_name") or feature.get("name")
    shap_value = get_shap_value(feature)
    abs_shap = get_abs_shap(feature)

    item = {
        "feature_id": feature_id,
        "feature_name": feature.get("feature_name") or feature_id,
        "display_name": feature.get("display_name") or feature.get("feature_display_name") or feature_id,
        "concept": feature.get("concept") or feature.get("feature_group") or feature.get("concept_id") or "unknown",
        "concept_display_name": feature.get("concept_display_name") or feature.get("concept_name"),
        "shap_value": shap_value,
        "abs_shap_value": abs_shap,
        "direction": infer_direction(feature),
        "rank": rank if rank is not None else feature.get("rank"),
    }

    for key in ("strength", "safe_phrase", "raw_value", "value"):
        if key in feature:
            item[key] = feature.get(key)

    return item


# Lọc dict hợp lệ và sắp xếp theo abs SHAP giảm dần.
def sort_features_by_abs_shap(features):
    clean = []

    for feature in features:
        if isinstance(feature, dict):
            clean.append(feature)

    return sorted(clean, key=get_abs_shap, reverse=True)


# Chọn fixed top-k feature theo abs SHAP.
def fixed_top_features(features, top_k):
    selected = []
    ordered = sort_features_by_abs_shap(features)

    for i, feature in enumerate(ordered[:top_k], start=1):
        selected.append(normalize_feature(feature, rank=i))

    print("fixed_top_features:")
    print("  selected_count:", len(selected))
    print("  selected_feature_ids:", [x.get("feature_id") for x in selected])

    return selected


# Chọn adaptive top-k sao cho đạt coverage theo tổng abs SHAP.
def select_by_coverage(features, threshold, k_min, k_max):
    ordered = sort_features_by_abs_shap(features)
    total_mass = sum(get_abs_shap(feature) for feature in ordered)

    if not ordered:
        result = {
            "selected": [],
            "adaptive_k": 0,
            "coverage": 0.0,
            "coverage_threshold": threshold,
            "coverage_status": "NO_FEATURES",
            "selected_feature_ids": [],
            "total_abs_shap_mass": 0.0,
        }

        print("select_by_coverage:")
        print("  status:", result["coverage_status"])
        print("  adaptive_k:", result["adaptive_k"])
        print("  coverage:", result["coverage"])

        return result

    if total_mass <= 0:
        limit = min(k_min, len(ordered))
        selected = []

        for i, feature in enumerate(ordered[:limit], start=1):
            selected.append(normalize_feature(feature, rank=i))

        result = {
            "selected": selected,
            "adaptive_k": len(selected),
            "coverage": 0.0,
            "coverage_threshold": threshold,
            "coverage_status": "ZERO_TOTAL_MASS",
            "selected_feature_ids": [x.get("feature_id") for x in selected],
            "total_abs_shap_mass": 0.0,
        }

        print("select_by_coverage:")
        print("  status:", result["coverage_status"])
        print("  adaptive_k:", result["adaptive_k"])
        print("  coverage:", result["coverage"])
        print("  selected_feature_ids:", result["selected_feature_ids"])

        return result

    selected = []
    cumulative = 0.0
    max_take = min(k_max, len(ordered))

    for i, feature in enumerate(ordered[:max_take], start=1):
        selected.append(normalize_feature(feature, rank=i))
        cumulative += get_abs_shap(feature)

        coverage = cumulative / total_mass
        if i >= k_min and coverage >= threshold:
            break

    coverage = cumulative / total_mass

    result = {
        "selected": selected,
        "adaptive_k": len(selected),
        "coverage": coverage,
        "coverage_threshold": threshold,
        "coverage_status": "PASSED" if coverage >= threshold else "BELOW_TARGET",
        "selected_feature_ids": [x.get("feature_id") for x in selected],
        "total_abs_shap_mass": total_mass,
    }

    print("select_by_coverage:")
    print("  status:", result["coverage_status"])
    print("  adaptive_k:", result["adaptive_k"])
    print("  coverage:", result["coverage"])
    print("  threshold:", result["coverage_threshold"])
    print("  selected_feature_ids:", result["selected_feature_ids"])

    return result


# Tính normalized entropy để biết SHAP tập trung hay phân tán.
def compute_entropy(features):
    ordered = sort_features_by_abs_shap(features)
    values = []

    for feature in ordered:
        value = get_abs_shap(feature)
        if value > 0:
            values.append(value)

    total = sum(values)

    if total <= 0 or len(values) <= 1:
        result = {
            "normalized_entropy": 0.0,
            "entropy_level": "low",
        }

        print("compute_entropy:")
        print("  normalized_entropy:", result["normalized_entropy"])
        print("  entropy_level:", result["entropy_level"])

        return result

    entropy = 0.0

    for value in values:
        p = value / total
        entropy -= p * math.log(p)

    normalized = entropy / math.log(len(values))

    if normalized < 0.40:
        level = "low"
    elif normalized < 0.70:
        level = "medium"
    else:
        level = "high"

    result = {
        "normalized_entropy": normalized,
        "entropy_level": level,
    }

    print("compute_entropy:")
    print("  normalized_entropy:", result["normalized_entropy"])
    print("  entropy_level:", result["entropy_level"])

    return result


# Gom feature theo concept và direction.
def build_concept_grouping(selected_evidence):
    by_concept = {}

    for item in selected_evidence:
        concept = item.get("concept") or "unknown"
        direction = item.get("direction") or "unknown"

        if concept not in by_concept:
            by_concept[concept] = {}

        if direction not in by_concept[concept]:
            by_concept[concept][direction] = []

        by_concept[concept][direction].append(item)

    representative_features = []
    grouped_supporting_features = []
    mixed_concept_groups = []

    for concept, direction_groups in by_concept.items():
        directions = []

        for direction in direction_groups.keys():
            if direction != "neutral":
                directions.append(direction)

        if len(set(directions)) > 1:
            mixed_concept_groups.append({
                "concept": concept,
                "directions": sorted(set(directions)),
                "feature_count": sum(len(value) for value in direction_groups.values()),
            })

        for direction, features in direction_groups.items():
            features = sorted(features, key=lambda x: safe_float(x.get("abs_shap_value")), reverse=True)

            for feature in features[:2]:
                representative_features.append(feature)

            for feature in features[2:]:
                grouped_supporting_features.append({
                    "concept": concept,
                    "direction": direction,
                    "feature_id": feature.get("feature_id"),
                    "display_name": feature.get("display_name"),
                    "rank": feature.get("rank"),
                    "abs_shap_value": feature.get("abs_shap_value"),
                })

    result = {
        "representative_features": representative_features,
        "grouped_supporting_features": grouped_supporting_features,
        "mixed_concept_groups": mixed_concept_groups,
        "concept_group_count": len(by_concept),
    }


    return result