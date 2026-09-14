import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../../contracts/validation-claims";
import { REASON_CODE } from "../constants";
import { emptyClaimValidationFactValues } from "../types";
import type { SemanticDecision, EvidenceView } from "./shared";
import {
  compareDirection,
  conceptFacts,
  decision,
  featureFacts,
  findConcept,
  findFeature,
  findFeatureCaseInsensitive,
  isGuaranteeOverclaim,
  sourceDirectionForFeature,
} from "./shared";

export function validatePrediction(
  claim: Extract<AtomicClaimRecord, { claim_type: "prediction" }>,
  view: EvidenceView,
): SemanticDecision {
  if (
    claim.certainty === "deterministic" &&
    isGuaranteeOverclaim(claim.source_text)
  ) {
    const expected = emptyClaimValidationFactValues();
    const observed = emptyClaimValidationFactValues();
    expected.exposure_status = "EXPOSED";
    observed.exposure_status = "EXPOSED";
    return decision(
      REASON_CODE.GUARANTEE_OVERCLAIM,
      expected,
      observed,
      "Prediction uses prohibited guarantee wording.",
      [],
      [],
      { policyStatus: "VIOLATION" },
    );
  }
  switch (claim.claim_subtype) {
    case "OVERALL_LABEL":
    case "OVERALL_PREDICTION_SUMMARY":
      return validatePredictionLabel(claim, view);
    case "OVERALL_PROBABILITY":
      return validateOverallProbability(claim, view);
    case "THRESHOLD_COMPARISON":
      return validateThresholdComparison(claim, view);
  }
  throw new Error(`Unsupported prediction subtype: ${claim.claim_subtype}`);
}

function validatePredictionLabel(
  claim: Extract<AtomicClaimRecord, { claim_type: "prediction" }>,
  view: EvidenceView,
): SemanticDecision {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  const prediction = view.package.prompt_payload.prediction;
  expected.prediction_label = predictionLabel(claim.direction, view);
  expected.exposure_status = "EXPOSED";
  observed.prediction_label = prediction.predicted_label ?? null;
  observed.probability = prediction.probability ?? null;
  observed.exposure_status = prediction.predicted_label ? "EXPOSED" : "SOURCE_MISSING";

  if (!prediction.predicted_label) {
    return decision(
      REASON_CODE.PREDICTION_VALUE_UNAVAILABLE,
      expected,
      observed,
      "Exposed prediction label is unavailable.",
    );
  }
  if (!expected.prediction_label) {
    return decision(
      REASON_CODE.PREDICTION_VALUE_UNAVAILABLE,
      expected,
      observed,
      "Claim does not encode a deterministic prediction direction.",
    );
  }
  if (expected.prediction_label !== observed.prediction_label) {
    return decision(
      REASON_CODE.PREDICTION_LABEL_MISMATCH,
      expected,
      observed,
      "Claimed prediction label contradicts the exposed package.",
    );
  }
  return decision(
    REASON_CODE.EXACT_MATCH,
    expected,
    observed,
    "Prediction label exactly matches exposed evidence.",
  );
}

function validateOverallProbability(
  claim: Extract<AtomicClaimRecord, { claim_type: "prediction" }>,
  view: EvidenceView,
): SemanticDecision {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  const claimedProbability = probabilityFromText(claim.source_text);
  const exposedProbability = view.package.prompt_payload.prediction.probability;
  expected.probability = claimedProbability;
  expected.exposure_status = "EXPOSED";
  observed.probability = exposedProbability;
  observed.exposure_status = "EXPOSED";
  if (claimedProbability === null) {
    return decision(
      REASON_CODE.SEMANTIC_SOURCE_UNFROZEN,
      expected,
      observed,
      "Overall-probability claim has no deterministic numeric expression.",
      [],
      [],
      {
        validationCoverage: "SEMANTIC_REQUIRED",
        unresolvedFacts: ["claimed_probability"],
      },
    );
  }
  const difference = Math.abs(claimedProbability - exposedProbability);
  const tolerance = 0.00005;
  if (difference > tolerance) {
    return decision(
      REASON_CODE.PREDICTION_PROBABILITY_MISMATCH,
      expected,
      observed,
      "Claimed overall probability contradicts exposed probability.",
      ["percent_to_unit_interval"],
      [],
      {
        numericComparison: {
          difference,
          tolerance,
          tolerancePolicyId:
            "numeric_tolerance_policy_v1:prediction_score:percent",
        },
      },
    );
  }
  return decision(
    difference === 0 ? REASON_CODE.NORMALIZED_MATCH : REASON_CODE.TOLERANCE_MATCH,
    expected,
    observed,
    "Claimed overall probability matches exposed probability.",
    ["percent_to_unit_interval"],
    [],
    {
      numericComparison: {
        difference,
        tolerance,
        tolerancePolicyId:
          "numeric_tolerance_policy_v1:prediction_score:percent",
      },
    },
  );
}

function validateThresholdComparison(
  claim: Extract<AtomicClaimRecord, { claim_type: "prediction" }>,
  view: EvidenceView,
): SemanticDecision {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  const prediction = view.package.prompt_payload.prediction;
  expected.prediction_label =
    claim.direction === "increase_risk"
      ? "above_or_equal_threshold"
      : claim.direction === "decrease_risk"
        ? "below_threshold"
        : null;
  observed.prediction_label = prediction.is_above_threshold
    ? "above_or_equal_threshold"
    : "below_threshold";
  expected.exposure_status = "EXPOSED";
  observed.exposure_status = "EXPOSED";
  if (!expected.prediction_label) {
    return decision(
      REASON_CODE.PREDICTION_VALUE_UNAVAILABLE,
      expected,
      observed,
      "Threshold-comparison claim does not encode an explicit direction.",
      [],
      [],
      { unresolvedFacts: ["threshold_comparison_direction"] },
    );
  }
  const matches = expected.prediction_label === observed.prediction_label;
  return decision(
    matches
      ? REASON_CODE.EXACT_MATCH
      : REASON_CODE.PREDICTION_THRESHOLD_MISMATCH,
    expected,
    observed,
    matches
      ? "Threshold comparison exactly matches exposed prediction fields."
      : "Threshold comparison contradicts exposed prediction fields.",
  );
}

function probabilityFromText(text: string): number | null {
  const match = text.match(/(\d+(?:[.,]\d+)?)\s*%/u);
  if (!match) return null;
  const value = Number(match[1].replace(",", "."));
  return Number.isFinite(value) ? value / 100 : null;
}

function predictionLabel(
  direction: AtomicClaimRecord["direction"],
  view: EvidenceView,
): string | null {
  const semantics = view.package.prompt_payload.target_semantics
    ?? view.package.target_semantics;
  if (direction === "increase_risk") {
    return semantics?.positive_label ?? "high_default_risk";
  }
  if (direction === "decrease_risk") {
    return semantics?.negative_label ?? "low_default_risk";
  }
  return null;
}

export function validateFeaturePresence(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): SemanticDecision {
  const [expected, observed] = featureFacts(claim, view);
  if (claim.evidence_level === "S0") {
    observed.exposure_status = "NOT_EXPOSED";
    return decision(
      REASON_CODE.FEATURE_NOT_EXPOSED,
      expected,
      observed,
      "S0 does not expose feature evidence.",
    );
  }
  const feature = findFeature(view, claim.feature_id);
  if (!feature) {
    const alias = findFeatureCaseInsensitive(view, claim.feature_id);
    return decision(
      alias ? REASON_CODE.FEATURE_ALIAS_UNRESOLVED : REASON_CODE.FEATURE_NOT_FOUND_IN_EVIDENCE,
      expected,
      observed,
      alias
        ? "A case-insensitive feature alias exists but no frozen alias rule resolves it."
        : "Claimed feature is absent from exposed evidence.",
    );
  }
  observed.feature_id = feature.feature_id ?? null;
  observed.exposure_status = "EXPOSED";
  return decision(
    REASON_CODE.EXACT_MATCH,
    expected,
    observed,
    "Feature identity exactly matches exposed evidence.",
    [],
    [`feature:${feature.feature_id}`],
  );
}

export function validateFeatureDirection(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): SemanticDecision {
  const [expected, observed] = featureFacts(claim, view);
  expected.direction = claim.direction;
  if (claim.evidence_level === "S0") {
    observed.exposure_status = "NOT_EXPOSED";
    return decision(
      REASON_CODE.DIRECTION_NOT_EXPOSED,
      expected,
      observed,
      "S0 does not expose feature direction.",
    );
  }
  const feature = findFeature(view, claim.feature_id);
  if (!feature) {
    return decision(
      REASON_CODE.FEATURE_NOT_FOUND_IN_EVIDENCE,
      expected,
      observed,
      "Directional feature is absent from exposed evidence.",
    );
  }
  observed.feature_id = feature.feature_id ?? null;
  observed.exposure_status = "EXPOSED";
  const sourceDirection = sourceDirectionForFeature(feature);
  observed.direction = sourceDirection.direction;
  const normalizations = sourceDirection.normalized
    ? ["evidence_direction_plural_to_claim_singular"]
    : [];
  return compareDirection(expected, observed, normalizations);
}

export function validateConceptPresence(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): SemanticDecision {
  const [expected, observed] = conceptFacts(claim);
  if (claim.evidence_level === "S0") {
    observed.exposure_status = "NOT_EXPOSED";
    return decision(
      REASON_CODE.CONCEPT_NOT_EXPOSED,
      expected,
      observed,
      "S0 does not expose concept evidence.",
    );
  }
  const concept = findConcept(view, claim.concept_id);
  if (!concept) {
    return decision(
      REASON_CODE.CONCEPT_NOT_FOUND_IN_EVIDENCE,
      expected,
      observed,
      "Claimed concept is absent from exposed concept evidence.",
    );
  }
  observed.concept_id = concept.concept_id;
  observed.exposure_status = "EXPOSED";
  return decision(
    REASON_CODE.EXACT_MATCH,
    expected,
    observed,
    "Concept identity exactly matches exposed evidence.",
    [],
    [...concept.source_record_keys],
  );
}

export function validateConceptDirection(
  claim: AtomicClaimRecord,
  view: EvidenceView,
): SemanticDecision {
  const [expected, observed] = conceptFacts(claim);
  expected.direction = claim.direction;
  if (claim.evidence_level === "S0") {
    observed.exposure_status = "NOT_EXPOSED";
    return decision(
      REASON_CODE.DIRECTION_NOT_EXPOSED,
      expected,
      observed,
      "S0 does not expose concept direction.",
    );
  }
  const concept = findConcept(view, claim.concept_id);
  if (!concept) {
    return decision(
      REASON_CODE.CONCEPT_NOT_FOUND_IN_EVIDENCE,
      expected,
      observed,
      "Directional concept is absent from exposed concept evidence.",
    );
  }
  observed.concept_id = concept.concept_id;
  observed.exposure_status = "EXPOSED";
  observed.direction = concept.direction;
  return compareDirection(
    expected,
    observed,
    [...concept.normalizations_applied],
  );
}
