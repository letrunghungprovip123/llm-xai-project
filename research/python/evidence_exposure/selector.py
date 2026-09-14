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

    display_name = feature.get("display_name") or feature.get("feature_display_name")
    display_name_source = feature.get("display_name_source")

    if not display_name:
        display_name = feature.get("feature_name") or feature_id
        display_name_source = "fallback"
    elif not display_name_source:
        simple_fallback = str(feature_id).replace("_", " ") if feature_id is not None else None
        if display_name in (feature_id, simple_fallback):
            display_name_source = "fallback"
        else:
            display_name_source = "registry"

    item = {
        "feature_id": feature_id,
        "feature_name": feature.get("feature_name") or feature_id,
        "display_name": display_name,
        "display_name_source": display_name_source,
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

    return selected


# Chọn adaptive top-k sao cho đạt coverage theo tổng abs SHAP.
def select_by_coverage(features, threshold, k_min, k_max):
    ordered = sort_features_by_abs_shap(features)
    total_mass = sum(get_abs_shap(feature) for feature in ordered)

    if not ordered:
        return {
            "selected": [],
            "adaptive_k": 0,
            "coverage": 0.0,
            "coverage_threshold": threshold,
            "coverage_status": "NO_FEATURES",
            "selected_feature_ids": [],
            "total_abs_shap_mass": 0.0,
        }

    if total_mass <= 0:
        limit = min(k_min, len(ordered))
        selected = []

        for i, feature in enumerate(ordered[:limit], start=1):
            selected.append(normalize_feature(feature, rank=i))

        return {
            "selected": selected,
            "adaptive_k": len(selected),
            "coverage": 0.0,
            "coverage_threshold": threshold,
            "coverage_status": "ZERO_TOTAL_MASS",
            "selected_feature_ids": [x.get("feature_id") for x in selected],
            "total_abs_shap_mass": 0.0,
        }

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

    return {
        "selected": selected,
        "adaptive_k": len(selected),
        "coverage": coverage,
        "coverage_threshold": threshold,
        "coverage_status": "PASSED" if coverage >= threshold else "BELOW_TARGET",
        "selected_feature_ids": [x.get("feature_id") for x in selected],
        "total_abs_shap_mass": total_mass,
    }


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
        return {
            "normalized_entropy": 0.0,
            "entropy_level": "low",
        }

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

    return {
        "normalized_entropy": normalized,
        "entropy_level": level,
    }


# Gom feature theo đúng concept + direction.
def build_concept_grouping(selected_evidence):
    groups = {}

    for item in selected_evidence:
        concept = item.get("concept") or "unknown"
        direction = item.get("direction") or "unknown"
        key = (concept, direction)

        if key not in groups:
            groups[key] = []

        groups[key].append(item)

    concept_groups = []
    representative_features = []
    grouped_supporting_features = []
    directions_by_concept = {}

    for (concept, direction), features in groups.items():
        features = sorted(
            features,
            key=lambda x: safe_float(x.get("abs_shap_value")),
            reverse=True,
        )

        representative = features[0]
        supporting = features[1:]
        representative_features.append(representative)

        for feature in supporting:
            grouped_supporting_features.append({
                "concept": concept,
                "concept_display_name": representative.get("concept_display_name"),
                "direction": direction,
                "feature_id": feature.get("feature_id"),
                "display_name": feature.get("display_name"),
                "rank": feature.get("rank"),
                "abs_shap_value": feature.get("abs_shap_value"),
            })

        concept_groups.append({
            "concept": concept,
            "concept_display_name": representative.get("concept_display_name"),
            "direction": direction,
            "representative_feature": representative,
            "supporting_features": supporting,
            "selected_feature_ids": [x.get("feature_id") for x in features],
            "feature_count": len(features),
            "selected_abs_shap_sum": sum(
                safe_float(x.get("abs_shap_value")) for x in features
            ),
        })

        if concept not in directions_by_concept:
            directions_by_concept[concept] = set()

        if direction not in ("neutral", "unknown"):
            directions_by_concept[concept].add(direction)

    mixed_concept_groups = []

    for concept, directions in directions_by_concept.items():
        if len(directions) <= 1:
            continue

        feature_count = 0
        for group in concept_groups:
            if group.get("concept") == concept:
                feature_count += group.get("feature_count", 0)

        mixed_concept_groups.append({
            "concept": concept,
            "directions": sorted(directions),
            "feature_count": feature_count,
        })

    concept_groups = sorted(
        concept_groups,
        key=lambda x: safe_float(x.get("selected_abs_shap_sum")),
        reverse=True,
    )

    return {
        "concept_groups": concept_groups,
        "representative_features": representative_features,
        "grouped_supporting_features": grouped_supporting_features,
        "mixed_concept_groups": mixed_concept_groups,
        "concept_group_count": len(concept_groups),
        "unique_concept_count": len(directions_by_concept),
    }
