import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../../contracts/validation-claims";
import type {
  ClaimValidationFeatureEvidence,
} from "../runtimeTypes";
import {
  numericRuleFor,
  type NumericToleranceRule,
} from "../numericPolicy";
import { REASON_CODE } from "../constants";
import { emptyClaimValidationFactValues } from "../types";
import type { ConceptAggregate, SemanticDecision, EvidenceView } from "./shared";
import { decision, findConcept, findFeature, isMagnitude, normalizeComparableNumbers, numericSourceIsExposed, numericSourceValue } from "./shared";

export function validateNumeric(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): SemanticDecision {
  const { expected, observed } = numericFacts(claim);

  if (claim.numeric_value === null || claim.numeric_role === null) {
    observed.exposure_status = "SOURCE_MISSING";
    return decision(
      REASON_CODE.NUMERIC_SOURCE_MISSING,
      expected,
      observed,
      "Numeric claim is missing its typed value or role.",
    );
  }
  const rule = numericRuleFor(claim.numeric_role, claim.numeric_unit);
  if (rule.comparison_mode === "NOT_VERIFIABLE") {
    observed.exposure_status = numericSourceIsExposed(claim, view)
      ? "EXPOSED"
      : "SOURCE_MISSING";
    return decision(
      REASON_CODE.NUMERIC_ROLE_UNSUPPORTED,
      expected,
      observed,
      "Frozen numeric policy does not define reliable precision for this role.",
    );
  }
  const source = numericSourceValue(claim, view);
  if (source === null) {
    observed.exposure_status = "SOURCE_MISSING";
    return decision(
      REASON_CODE.NUMERIC_SOURCE_MISSING,
      expected,
      observed,
      "Required numeric source is unavailable in the exposed package.",
    );
  }
  observed.exposure_status = "EXPOSED";
  observed.numeric_unit = claim.numeric_unit;
  const normalized = normalizeComparableNumbers(
    claim.numeric_value,
    source,
    rule.normalization,
  );
  expected.numeric_value = normalized.expected;
  observed.numeric_value = normalized.observed;
  return compareNumericValue(expected, observed, rule);
}

function compareNumericValue(
  expected: ReturnType<typeof emptyClaimValidationFactValues>,
  observed: ReturnType<typeof emptyClaimValidationFactValues>,
  rule: NumericToleranceRule,
): SemanticDecision {
  const normalizations = numericNormalizations(rule);
  const expectedValue = expected.numeric_value ?? 0;
  const observedValue = observed.numeric_value ?? 0;
  const delta = Math.abs(expectedValue - observedValue);
  if (rule.comparison_mode === "EXACT") {
    return decision(
      delta === 0 ? REASON_CODE.EXACT_MATCH : REASON_CODE.NUMERIC_EXACT_MISMATCH,
      expected,
      observed,
      delta === 0
        ? "Numeric value exactly matches exposed evidence."
        : "Numeric value differs from exact exposed evidence.",
      normalizations,
    );
  }
  const tolerance = rule.absolute_tolerance ?? 0;
  if (delta <= tolerance) {
    return decision(
      numericMatchReason(delta, normalizations.length),
      expected,
      observed,
      "Numeric value matches within frozen display precision.",
      normalizations,
      [],
      {
        numericComparison: {
          difference: delta,
          tolerance,
          tolerancePolicyId:
            `numeric_tolerance_policy_v1:${rule.numeric_role}:${rule.unit}`,
        },
      },
    );
  }
  return decision(
    REASON_CODE.NUMERIC_OUTSIDE_TOLERANCE,
    expected,
    observed,
    `Numeric delta ${delta} exceeds frozen tolerance ${tolerance}.`,
    normalizations,
  );
}

function numericFacts(claim: AtomicClaimRecord): {
  expected: ReturnType<typeof emptyClaimValidationFactValues>;
  observed: ReturnType<typeof emptyClaimValidationFactValues>;
} {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.numeric_value = claim.numeric_value;
  expected.numeric_unit = claim.numeric_unit;
  expected.numeric_role = claim.numeric_role;
  expected.feature_id = claim.feature_id;
  expected.concept_id = claim.concept_id;
  expected.exposure_status = "EXPOSED";
  observed.numeric_role = claim.numeric_role;
  return { expected, observed };
}

function numericNormalizations(rule: NumericToleranceRule): string[] {
  if (rule.normalization === "PERCENT_TO_UNIT_INTERVAL") {
    return ["percent_to_unit_interval"];
  }
  return [];
}

export function validateRanking(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): SemanticDecision {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.feature_id = claim.feature_id;
  expected.concept_id = claim.concept_id;
  expected.rank = 1;
  expected.exposure_status = "EXPOSED";
  if (claim.evidence_level === "S0") {
    observed.exposure_status = "NOT_EXPOSED";
    return decision(
      REASON_CODE.RANKING_NOT_EXPOSED,
      expected,
      observed,
      "S0 does not expose ranking evidence.",
    );
  }
  if (claim.feature_id) {
    return validateFeatureRanking(claim.feature_id, view, expected, observed);
  }
  if (claim.concept_id) {
    return validateConceptRanking(claim.concept_id, view, expected, observed);
  }
  observed.exposure_status = "SOURCE_MISSING";
  return decision(
    REASON_CODE.RANK_SOURCE_MISSING,
    expected,
    observed,
    "Ranking claim has no canonical feature or concept target.",
  );
}

export function validateMagnitude(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): SemanticDecision {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.feature_id = claim.feature_id;
  expected.concept_id = claim.concept_id;
  expected.magnitude = claim.magnitude;
  expected.exposure_status = "EXPOSED";
  if (claim.evidence_level === "S0") {
    observed.exposure_status = "NOT_EXPOSED";
    return decision(
      REASON_CODE.MAGNITUDE_NOT_EXPOSED,
      expected,
      observed,
      "S0 does not expose magnitude.",
    );
  }
  if (
    claim.claim_subtype === "COMPARATIVE_STRENGTH" ||
    claim.claim_subtype === "OVERALL_BALANCE"
  ) {
    observed.exposure_status = "SOURCE_MISSING";
    return decision(
      REASON_CODE.MAGNITUDE_SEMANTICS_UNSUPPORTED,
      expected,
      observed,
      "Magnitude subtype has no frozen deterministic comparison semantics.",
      [],
      [],
      {
        validationCoverage: "SEMANTIC_REQUIRED",
        unresolvedFacts: ["magnitude_comparison_semantics"],
      },
    );
  }
  const source = magnitudeSource(claim, view);
  if (!source?.strength || !isMagnitude(source.strength)) {
    observed.exposure_status = source ? "SOURCE_MISSING" : "NOT_EXPOSED";
    return decision(
      source
        ? REASON_CODE.MAGNITUDE_SOURCE_MISSING
        : REASON_CODE.MAGNITUDE_UNSUPPORTED,
      expected,
      observed,
      "Exposed package has no deterministic magnitude source for this target.",
      [],
      [],
      {
        validationCoverage: "DETERMINISTIC",
        unresolvedFacts: ["magnitude_source"],
      },
    );
  }
  observed.feature_id = claim.feature_id;
  observed.concept_id = claim.concept_id;
  observed.magnitude = source.strength;
  observed.exposure_status = "EXPOSED";
  const comparison = compareMagnitude(expected.magnitude, observed.magnitude);
  return decision(
    comparison === 0
      ? REASON_CODE.MAGNITUDE_MATCH
      : comparison > 0
        ? REASON_CODE.MAGNITUDE_OVERSTATED
        : REASON_CODE.MAGNITUDE_UNDERSTATED,
    expected,
    observed,
    comparison === 0
      ? "Magnitude exactly matches exposed strength."
      : comparison > 0
        ? "Claimed magnitude overstates exposed strength."
        : "Claimed magnitude understates exposed strength.",
  );
}

function compareMagnitude(
  expected: AtomicClaimRecord["magnitude"],
  observed: AtomicClaimRecord["magnitude"],
): number {
  const order = { weak: 0, moderate: 1, strong: 2 } as const;
  if (!expected || expected === "unknown") return 0;
  if (!observed || observed === "unknown") return 0;
  return order[expected] - order[observed];
}

function numericMatchReason(
  delta: number,
  normalizationCount: number,
): typeof REASON_CODE.EXACT_MATCH
  | typeof REASON_CODE.NORMALIZED_MATCH
  | typeof REASON_CODE.TOLERANCE_MATCH {
  if (delta !== 0) return REASON_CODE.TOLERANCE_MATCH;
  if (normalizationCount > 0) return REASON_CODE.NORMALIZED_MATCH;
  return REASON_CODE.EXACT_MATCH;
}

function validateFeatureRanking(
  featureId: string,
  view: EvidenceView,
  expected: ReturnType<typeof emptyClaimValidationFactValues>,
  observed: ReturnType<typeof emptyClaimValidationFactValues>,
): SemanticDecision {
  const feature = findFeature(view, featureId);
  if (!feature) {
    observed.exposure_status = "NOT_EXPOSED";
    return decision(
      REASON_CODE.RANKING_UNSUPPORTED,
      expected,
      observed,
      "Feature ranking source is unavailable.",
    );
  }
  populateFeatureRank(feature, observed);
  const ties = view.exposed_features.filter(
    (item) => item.abs_shap_value === feature.abs_shap_value,
  );
  if (ties.length > 1) {
    return decision(
      REASON_CODE.RANK_TIE_AMBIGUOUS,
      expected,
      observed,
      "Exposed feature ranking contains a tie.",
    );
  }
  return compareTopRank(expected, observed);
}

function validateConceptRanking(
  conceptId: string,
  view: EvidenceView,
  expected: ReturnType<typeof emptyClaimValidationFactValues>,
  observed: ReturnType<typeof emptyClaimValidationFactValues>,
): SemanticDecision {
  const concept = findConcept(view, conceptId);
  if (!concept) {
    observed.exposure_status = "NOT_EXPOSED";
    return decision(
      REASON_CODE.RANKING_UNSUPPORTED,
      expected,
      observed,
      "Concept ranking source is unavailable.",
    );
  }
  const ordered = [...view.aggregated_concepts.values()].sort(
    (left, right) => right.selected_abs_shap_sum - left.selected_abs_shap_sum,
  );
  populateConceptRank(concept, ordered, observed);
  const ties = ordered.filter(
    (item) => item.selected_abs_shap_sum === concept.selected_abs_shap_sum,
  );
  if (ties.length > 1) {
    return decision(
      REASON_CODE.RANK_TIE_AMBIGUOUS,
      expected,
      observed,
      "Exposed concept ranking contains a tie.",
    );
  }
  return compareTopRank(expected, observed);
}

function populateFeatureRank(
  feature: ClaimValidationFeatureEvidence,
  observed: ReturnType<typeof emptyClaimValidationFactValues>,
): void {
  observed.feature_id = feature.feature_id;
  observed.rank = feature.rank;
  observed.exposure_status = "EXPOSED";
}

function populateConceptRank(
  concept: ConceptAggregate,
  ordered: readonly ConceptAggregate[],
  observed: ReturnType<typeof emptyClaimValidationFactValues>,
): void {
  observed.concept_id = concept.concept_id;
  observed.rank = ordered.indexOf(concept) + 1;
  observed.exposure_status = "EXPOSED";
}

function compareTopRank(
  expected: ReturnType<typeof emptyClaimValidationFactValues>,
  observed: ReturnType<typeof emptyClaimValidationFactValues>,
): SemanticDecision {
  const matches = observed.rank === expected.rank;
  return decision(
    matches ? REASON_CODE.EXACT_MATCH : REASON_CODE.RANKING_UNSUPPORTED,
    expected,
    observed,
    matches
      ? "Top-rank claim matches exposed ordering."
      : "Claimed top rank does not match exposed ordering.",
  );
}

function magnitudeSource(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): ClaimValidationFeatureEvidence | undefined {
  if (claim.feature_id) return findFeature(view, claim.feature_id);
  if (!claim.concept_id) return undefined;
  return findConcept(view, claim.concept_id)?.representative_feature ?? undefined;
}
