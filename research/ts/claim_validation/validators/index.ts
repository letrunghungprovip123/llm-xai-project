import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../../contracts/validation-claims";
import { REASON_CODE } from "../constants";
import { emptyClaimValidationFactValues } from "../types";
import type { ClaimValidationEvidencePackage } from "../runtimeTypes";
import { validateNumeric, validateRanking, validateMagnitude } from "./numericRankingMagnitude";
import {
  validateCausal,
  validateDistributedEvidence,
  validateLimitation,
  validateRecommendation,
  validateUncertainty,
} from "./policyClaims";
import {
  validateConceptDirection,
  validateConceptPresence,
  validateFeatureDirection,
  validateFeaturePresence,
  validatePrediction,
} from "./predictionFeatureConcept";
import {
  buildEvidenceView,
  decision,
  type SemanticDecision,
} from "./shared";

/** Routes an atomic claim to its deterministic, side-effect-free validator. */
export function validateClaimDeterministically(
  claim: AtomicClaimRecord,
  evidence: ClaimValidationEvidencePackage,
): SemanticDecision {
  if (claim.claim_subtype.startsWith("UNRESOLVED_")) {
    const expected = emptyClaimValidationFactValues();
    const observed = emptyClaimValidationFactValues();
    return decision(
      REASON_CODE.SEMANTIC_SUBTYPE_UNRESOLVED,
      expected,
      observed,
      `No exact frozen semantic rule resolved ${claim.claim_type}/${claim.claim_subtype}.`,
      [],
      [],
      {
        policyStatus: "NOT_APPLICABLE",
        validationCoverage: "SEMANTIC_REQUIRED",
        unresolvedFacts: [`claim_subtype:${claim.claim_type}`],
      },
    );
  }

  const view = buildEvidenceView(evidence);
  switch (claim.claim_type) {
    case "prediction":
      return validatePrediction(claim, view);
    case "feature_presence":
      return validateFeaturePresence(claim, view);
    case "feature_direction":
      return validateFeatureDirection(claim, view);
    case "concept_presence":
      return validateConceptPresence(claim, view);
    case "concept_direction":
      return validateConceptDirection(claim, view);
    case "numeric":
      return validateNumeric(claim, view);
    case "ranking":
      return validateRanking(claim, view);
    case "magnitude":
      return validateMagnitude(claim, view);
    case "uncertainty":
      return validateUncertainty(claim, view);
    case "distributed_evidence":
      return validateDistributedEvidence(claim, view);
    case "recommendation":
      return validateRecommendation(claim, view);
    case "causal":
      return validateCausal(claim, view);
    case "limitation":
      return validateLimitation(claim, view);
  }
  throw new Error("Unsupported claim type.");
}
