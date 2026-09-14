import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../../contracts/validation-claims";
import type {
  ClaimValidationConceptEvidence,
  ClaimValidationEvidencePackage,
  ClaimValidationFeatureEvidence,
} from "../runtimeTypes";
import { normalizeNumericUnit } from "../numericPolicy";
import { CLAIM_VALIDATION_POLICY, normalizeDirection } from "../policy";
import { REASON_CODE, type ReasonCode } from "../constants";
import { emptyClaimValidationFactValues, type ClaimValidationFactValues } from "../types";

export type SemanticDecision = {
  reasonCode: ReasonCode;
  reasonCodes: ReasonCode[];
  expected: ClaimValidationFactValues;
  observed: ClaimValidationFactValues;
  message: string;
  normalizationsApplied: string[];
  sourceRecordKeys: string[];
  policyStatus: "COMPLIANT" | "VIOLATION" | "NOT_APPLICABLE";
  validationCoverage:
    | "DETERMINISTIC"
    | "SEMANTIC_REQUIRED"
    | "HUMAN_ADJUDICATED";
  unresolvedFacts: string[];
  numericComparison: {
    difference: number;
    tolerance: number;
    tolerancePolicyId: string;
  } | null;
};

export type SemanticDecisionMetadata = Partial<
  Pick<
    SemanticDecision,
    | "policyStatus"
    | "validationCoverage"
    | "unresolvedFacts"
    | "numericComparison"
  >
> & {
  additionalReasonCodes?: ReasonCode[];
};

export const EVIDENCE_EXPOSURE_STATES = [
  "NOT_EXPOSED",
  "EXPOSED_FORBIDDEN",
  "EXPOSED_ALLOWED",
  "SOURCE_MISSING",
  "NOT_APPLICABLE",
] as const;

export type EvidenceExposureState =
  (typeof EVIDENCE_EXPOSURE_STATES)[number];

export type EvidenceView = {
  package: ClaimValidationEvidencePackage;
  exposed_features: readonly ClaimValidationFeatureEvidence[];
  allowed_feature_ids: readonly string[];
  exposed_concept_instances: readonly ClaimValidationConceptEvidence[];
  aggregated_concepts: ReadonlyMap<string, ConceptAggregate>;
  allowed_concept_ids: readonly string[];
};

export type ConceptAggregate = {
  package_id: string;
  concept_id: string;
  direction: ClaimValidationFactValues["direction"];
  instance_count: number;
  supporting_feature_ids: readonly string[];
  source_record_keys: readonly string[];
  exposure_state: EvidenceExposureState;
  feature_count: number;
  selected_abs_shap_sum: number;
  representative_feature: ClaimValidationFeatureEvidence | null;
  normalizations_applied: readonly string[];
};

export function buildEvidenceView(
  packageItem: ClaimValidationEvidencePackage,
): EvidenceView {
  const payload = packageItem.prompt_payload;
  const exposedConceptInstances = payload.concept_evidence.slice();
  const allowedConceptIds = payload.constraints.allowed_concept_ids.slice();
  return {
    package: packageItem,
    exposed_features: payload.selected_evidence.slice(),
    allowed_feature_ids: payload.constraints.allowed_feature_ids.slice(),
    exposed_concept_instances: exposedConceptInstances,
    aggregated_concepts: aggregateConceptInstances(
      packageItem.package_id,
      exposedConceptInstances,
      allowedConceptIds,
    ),
    allowed_concept_ids: allowedConceptIds,
  };
}

export function aggregateConceptInstances(
  packageId: string,
  instances: readonly ClaimValidationConceptEvidence[],
  allowedConceptIds: readonly string[],
): ReadonlyMap<string, ConceptAggregate> {
  const grouped = new Map<string, ClaimValidationConceptEvidence[]>();
  for (const instance of instances) {
    const group = grouped.get(instance.concept);
    if (group) {
      group.push(instance);
    } else {
      grouped.set(instance.concept, [instance]);
    }
  }

  const aggregates = new Map<string, ConceptAggregate>();
  for (const conceptId of [...grouped.keys()].sort()) {
    const group = grouped.get(conceptId) ?? [];
    const features = uniqueConceptFeatures(group);
    const normalizedDirections = group.map((instance) =>
      normalizeEvidenceDirection(instance.direction)
    );
    const supportingFeatureIds = features
      .map((feature) => feature.feature_id)
      .sort();
    aggregates.set(conceptId, {
      package_id: packageId,
      concept_id: conceptId,
      direction: aggregateConceptDirection(
        normalizedDirections.map(({ direction }) => direction),
      ),
      instance_count: group.length,
      supporting_feature_ids: supportingFeatureIds,
      source_record_keys: [
        `concept:${conceptId}`,
        ...supportingFeatureIds.map((featureId) => `feature:${featureId}`),
      ],
      exposure_state: allowedConceptIds.includes(conceptId)
        ? "EXPOSED_ALLOWED"
        : "EXPOSED_FORBIDDEN",
      feature_count: supportingFeatureIds.length,
      selected_abs_shap_sum: group.reduce(
        (sum, instance) => sum + instance.selected_abs_shap_sum,
        0,
      ),
      representative_feature: strongestFeature(features),
      normalizations_applied: normalizedDirections.some(
        ({ normalized }) => normalized,
      )
        ? ["evidence_direction_plural_to_claim_singular"]
        : [],
    });
  }
  return aggregates;
}

export function aggregateConceptDirection(
  directions: readonly ClaimValidationFactValues["direction"][],
): ClaimValidationFactValues["direction"] {
  const values = new Set(directions);
  if (values.has("increase_risk") && values.has("decrease_risk")) {
    return "mixed";
  }
  if (values.size === 1 && values.has("increase_risk")) {
    return "increase_risk";
  }
  if (values.size === 1 && values.has("decrease_risk")) {
    return "decrease_risk";
  }
  if (values.size === 1 && values.has("neutral")) {
    return "neutral";
  }
  return "unknown";
}

export function featureExposureState(
  view: EvidenceView,
  featureId: string | null,
): EvidenceExposureState {
  if (!featureId) return "SOURCE_MISSING";
  const exposed = view.exposed_features.some(
    (feature) => feature.feature_id === featureId,
  );
  if (!exposed) return "NOT_EXPOSED";
  return view.allowed_feature_ids.includes(featureId)
    ? "EXPOSED_ALLOWED"
    : "EXPOSED_FORBIDDEN";
}

export function conceptExposureState(
  view: EvidenceView,
  conceptId: string | null,
): EvidenceExposureState {
  if (!conceptId) return "SOURCE_MISSING";
  const exposed = view.exposed_concept_instances.some(
    (concept) => concept.concept === conceptId,
  );
  if (!exposed) return "NOT_EXPOSED";
  return view.allowed_concept_ids.includes(conceptId)
    ? "EXPOSED_ALLOWED"
    : "EXPOSED_FORBIDDEN";
}

export function claimExposureState(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): EvidenceExposureState {
  switch (claim.claim_type) {
    case "feature_presence":
    case "feature_direction":
      return featureExposureState(view, claim.feature_id);
    case "concept_presence":
    case "concept_direction":
      return conceptExposureState(view, claim.concept_id);
    case "ranking":
    case "magnitude":
      if (claim.feature_id) return featureExposureState(view, claim.feature_id);
      if (claim.concept_id) return conceptExposureState(view, claim.concept_id);
      return "SOURCE_MISSING";
    case "numeric":
      if (claim.feature_id) return featureExposureState(view, claim.feature_id);
      if (claim.concept_id) return conceptExposureState(view, claim.concept_id);
      return "NOT_APPLICABLE";
    default:
      return "NOT_APPLICABLE";
  }
}

export function featureFacts(
  claim: AtomicClaimRecord,
  _view: EvidenceView,
): [ClaimValidationFactValues, ClaimValidationFactValues] {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.feature_id = claim.feature_id;
  expected.exposure_status = "EXPOSED";
  observed.exposure_status = "NOT_EXPOSED";
  return [expected, observed];
}

export function conceptFacts(
  claim: AtomicClaimRecord,
): [ClaimValidationFactValues, ClaimValidationFactValues] {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.concept_id = claim.concept_id;
  expected.exposure_status = "EXPOSED";
  observed.exposure_status = "NOT_EXPOSED";
  return [expected, observed];
}

export function compareDirection(
  expected: ClaimValidationFactValues,
  observed: ClaimValidationFactValues,
  normalizations: string[],
): SemanticDecision {
  if (expected.direction === "mixed" || expected.direction === "unknown") {
    return decision(
      REASON_CODE.DIRECTION_MIXED_OR_UNKNOWN,
      expected,
      observed,
      "Claim direction is mixed or unknown.",
      normalizations,
    );
  }
  if (observed.direction === null) {
    return decision(
      REASON_CODE.DIRECTION_SOURCE_MISSING,
      expected,
      observed,
      "Exposed direction source is missing.",
      normalizations,
    );
  }
  if (observed.direction === "mixed" || observed.direction === "unknown") {
    return decision(
      REASON_CODE.DIRECTION_MIXED_OR_UNKNOWN,
      expected,
      observed,
      "Exposed direction is mixed or unknown.",
      normalizations,
    );
  }
  if (observed.direction === "neutral") {
    return decision(
      REASON_CODE.DIRECTION_NEUTRAL,
      expected,
      observed,
      "Exposed SHAP direction is neutral.",
      normalizations,
    );
  }
  if (expected.direction !== observed.direction) {
    return decision(
      REASON_CODE.DIRECTION_REVERSED,
      expected,
      observed,
      "Claimed direction reverses exposed evidence.",
      normalizations,
    );
  }
  return decision(
    normalizations.length > 0 ? REASON_CODE.NORMALIZED_MATCH : REASON_CODE.EXACT_MATCH,
    expected,
    observed,
    "Direction matches exposed evidence.",
    normalizations,
  );
}

export function sourceDirectionForFeature(
  feature: ClaimValidationFeatureEvidence,
): {
  direction: ClaimValidationFactValues["direction"];
  normalized: boolean;
} {
  if (
    Math.abs(feature.shap_value) <=
      CLAIM_VALIDATION_POLICY.near_zero_shap_epsilon
  ) {
    return { direction: "neutral", normalized: false };
  }
  return normalizeEvidenceDirection(feature.direction);
}

export function normalizeEvidenceDirection(value: string): {
  direction: ClaimValidationFactValues["direction"];
  normalized: boolean;
} {
  try {
    const normalized = normalizeDirection(value);
    const direction = claimDirection(normalized);
    return { direction, normalized: normalized !== value };
  } catch {
    return { direction: "unknown", normalized: false };
  }
}

export function findFeature(
  view: EvidenceView,
  featureId: string | null,
): ClaimValidationFeatureEvidence | undefined {
  return featureId
    ? view.exposed_features.find((item) => item.feature_id === featureId)
    : undefined;
}

export function findFeatureCaseInsensitive(
  view: EvidenceView,
  featureId: string | null,
): ClaimValidationFeatureEvidence | undefined {
  const normalized = featureId?.toLowerCase();
  return normalized
    ? view.exposed_features.find(
      (item) => item.feature_id.toLowerCase() === normalized,
    )
    : undefined;
}

export function findConcept(
  view: EvidenceView,
  conceptId: string | null,
): ConceptAggregate | undefined {
  return conceptId ? view.aggregated_concepts.get(conceptId) : undefined;
}

export function numericSourceIsExposed(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): boolean {
  if (claim.numeric_role === "feature_value") {
    return findFeature(view, claim.feature_id)?.value !== undefined;
  }
  return numericSourceValue(claim, view) !== null;
}

export function numericSourceValue(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): number | null {
  const prediction = view.package.prompt_payload.prediction;
  if (claim.numeric_role === "prediction_score") {
    return prediction.probability;
  }
  if (claim.numeric_role === "decision_threshold") {
    return prediction.threshold;
  }
  if (claim.numeric_role === "rank") {
    const rank = findFeature(view, claim.feature_id)?.rank;
    return rank ?? null;
  }
  if (claim.numeric_role === "other" && normalizeNumericUnit(claim.numeric_unit) === "count") {
    const target = claim.normalized_claim_key.match(/\|target:([^|]+)/u)?.[1];
    const context = view.package.prompt_payload.selection_context;
    if (target === "selected_evidence_count") {
      return context.selected_evidence_count ?? null;
    }
    if (target === "concept_group_count") {
      return context.concept_group_count ?? null;
    }
    if (target === "mixed_concept_group_count") {
      return context.mixed_concept_group_count ?? null;
    }
    if (target?.startsWith("factor_member_count:")) {
      const conceptId = target.slice("factor_member_count:".length);
      return findConcept(view, conceptId)?.feature_count ?? null;
    }
  }
  return null;
}

export function normalizeComparableNumbers(
  expected: number,
  observed: number,
  normalization: string,
): { expected: number; observed: number } {
  if (normalization === "PERCENT_TO_UNIT_INTERVAL") {
    return { expected: expected / 100, observed };
  }
  if (normalization === "EXACT_INTEGER") {
    return { expected, observed };
  }
  return { expected, observed };
}

export function isMagnitude(value: string): value is "weak" | "moderate" | "strong" {
  return value === "weak" || value === "moderate" || value === "strong";
}

export function isCertaintyOverclaim(text: string): boolean {
  const normalized = text.toLocaleLowerCase("vi");
  if (
    /(?:không|chưa)\s+(?:thể\s+)?(?:đảm bảo|khẳng định)|không\s+chắc chắn|không[^.]{0,40}(?:hoàn toàn|chính xác|đảm bảo)/iu.test(
      normalized,
    )
  ) {
    return false;
  }
  return /(?:chắc chắn sẽ|đảm bảo(?: rằng)?|hoàn toàn chính xác|chính xác tuyệt đối)/iu.test(
    normalized,
  );
}

export function isGuaranteeOverclaim(text: string): boolean {
  const normalized = text.toLocaleLowerCase("vi");
  if (
    /(?:không|chưa)\s+(?:thể\s+)?(?:đảm bảo|khẳng định)|không\s+chắc chắn/iu.test(
      normalized,
    )
  ) {
    return false;
  }
  return /(?:chắc chắn sẽ|đảm bảo rằng|quyết định cuối cùng chắc chắn|guarantees?\s+that)/iu.test(
    normalized,
  );
}

export function decision(
  reasonCode: ReasonCode,
  expected: ClaimValidationFactValues,
  observed: ClaimValidationFactValues,
  message: string,
  normalizationsApplied: string[] = [],
  sourceRecordKeys: string[] = [],
  metadata: SemanticDecisionMetadata = {},
): SemanticDecision {
  return {
    reasonCode,
    reasonCodes: [
      reasonCode,
      ...(metadata.additionalReasonCodes ?? []),
    ].filter((value, index, values) => values.indexOf(value) === index),
    expected,
    observed,
    message,
    normalizationsApplied,
    sourceRecordKeys,
    policyStatus: metadata.policyStatus ?? "NOT_APPLICABLE",
    validationCoverage: metadata.validationCoverage ?? "DETERMINISTIC",
    unresolvedFacts:
      metadata.unresolvedFacts ?? defaultUnresolvedFacts(reasonCode),
    numericComparison: metadata.numericComparison ?? null,
  };
}

function defaultUnresolvedFacts(reasonCode: ReasonCode): string[] {
  switch (reasonCode) {
    case REASON_CODE.PREDICTION_VALUE_UNAVAILABLE:
      return ["prediction_value"];
    case REASON_CODE.FEATURE_ALIAS_UNRESOLVED:
      return ["feature_alias"];
    case REASON_CODE.DIRECTION_MIXED_OR_UNKNOWN:
      return ["direction_ambiguity"];
    case REASON_CODE.DIRECTION_SOURCE_MISSING:
      return ["direction_source"];
    case REASON_CODE.NUMERIC_ROLE_UNSUPPORTED:
      return ["numeric_role_semantics"];
    case REASON_CODE.NUMERIC_SOURCE_MISSING:
    case REASON_CODE.NUMERIC_NORMALIZATION_FAILED:
      return ["numeric_source"];
    case REASON_CODE.RANK_TIE_AMBIGUOUS:
      return ["rank_tie"];
    case REASON_CODE.RANK_SOURCE_MISSING:
      return ["rank_source"];
    case REASON_CODE.MAGNITUDE_SOURCE_MISSING:
      return ["magnitude_source"];
    case REASON_CODE.MAGNITUDE_SEMANTICS_UNSUPPORTED:
      return ["magnitude_semantics"];
    case REASON_CODE.SEMANTIC_SOURCE_UNFROZEN:
      return ["semantic_source"];
    default:
      return [];
  }
}

function claimDirection(value: string): ClaimValidationFactValues["direction"] {
  switch (value) {
    case "increase_risk":
    case "decrease_risk":
    case "mixed":
    case "neutral":
    case "unknown":
      return value;
    default:
      throw new Error(`Unsupported normalized direction: ${value}`);
  }
}

function uniqueConceptFeatures(
  instances: readonly ClaimValidationConceptEvidence[],
): ClaimValidationFeatureEvidence[] {
  const features = new Map<string, ClaimValidationFeatureEvidence>();
  for (const instance of instances) {
    for (const feature of [
      instance.representative_feature,
      ...instance.supporting_features,
    ]) {
      const current = features.get(feature.feature_id);
      if (
        !current ||
        feature.abs_shap_value > current.abs_shap_value ||
        (
          feature.abs_shap_value === current.abs_shap_value &&
          feature.feature_id.localeCompare(current.feature_id) < 0
        )
      ) {
        features.set(feature.feature_id, feature);
      }
    }
  }
  return [...features.values()].sort((left, right) =>
    left.feature_id.localeCompare(right.feature_id)
  );
}

function strongestFeature(
  features: readonly ClaimValidationFeatureEvidence[],
): ClaimValidationFeatureEvidence | null {
  return [...features].sort(
    (left, right) =>
      right.abs_shap_value - left.abs_shap_value ||
      left.feature_id.localeCompare(right.feature_id),
  )[0] ?? null;
}
