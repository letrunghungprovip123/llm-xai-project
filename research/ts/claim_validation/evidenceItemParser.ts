import type {
  ClaimValidationConceptEvidence,
  ClaimValidationFeatureEvidence,
} from "./runtimeTypes";
import {
  optionalFiniteNumber,
  requireDirection,
  requireFiniteNumber,
  requireObject,
  requirePositiveInteger,
  requireString,
  requireStringArray,
} from "./parseHelpers";

/** Parses an exposed feature item without retaining unchecked source fields. */
export function parseFeatureEvidence(
  value: unknown,
  context: string,
): ClaimValidationFeatureEvidence {
  const item = requireObject(value, context);
  const strength = parseStrength(item.strength, `${context}.strength`);
  const featureValue = optionalFiniteNumber(item.value, `${context}.value`);
  return {
    feature_id: requireString(item.feature_id, `${context}.feature_id`),
    shap_value: requireFiniteNumber(item.shap_value, `${context}.shap_value`),
    abs_shap_value: requireFiniteNumber(
      item.abs_shap_value,
      `${context}.abs_shap_value`,
    ),
    direction: requireDirection(item.direction, `${context}.direction`),
    rank: requirePositiveInteger(item.rank, `${context}.rank`),
    ...(strength === undefined ? {} : { strength }),
    ...(featureValue === undefined ? {} : { value: featureValue }),
  };
}

/** Parses an exposed concept and the nested feature facts validators consume. */
export function parseConceptEvidence(
  value: unknown,
  context: string,
): ClaimValidationConceptEvidence {
  const item = requireObject(value, context);
  if (!Array.isArray(item.supporting_features)) {
    throw new Error(`${context}.supporting_features must be an array.`);
  }
  return {
    concept: requireString(item.concept, `${context}.concept`),
    direction: requireDirection(item.direction, `${context}.direction`),
    representative_feature: parseFeatureEvidence(
      item.representative_feature,
      `${context}.representative_feature`,
    ),
    supporting_features: item.supporting_features.map((feature, index) =>
      parseFeatureEvidence(feature, `${context}.supporting_features[${index}]`),
    ),
    selected_feature_ids: requireStringArray(
      item.selected_feature_ids,
      `${context}.selected_feature_ids`,
    ),
    feature_count: requirePositiveInteger(
      item.feature_count,
      `${context}.feature_count`,
    ),
    selected_abs_shap_sum: requireFiniteNumber(
      item.selected_abs_shap_sum,
      `${context}.selected_abs_shap_sum`,
    ),
  };
}

function parseStrength(
  value: unknown,
  context: string,
): ClaimValidationFeatureEvidence["strength"] {
  if (value === undefined) return undefined;
  if (value === "weak" || value === "moderate" || value === "strong") {
    return value;
  }
  throw new Error(`${context} must be weak, moderate, or strong.`);
}
