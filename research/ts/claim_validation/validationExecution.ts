import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../contracts/validation-claims";
import { REASON_CODE } from "./constants";
import type { ValidationIndexes } from "./indexes";
import { assertJoinedIdentity } from "./indexes";
import {
  buildErrorResult,
  buildSuccessResult,
  type ResultProvenance,
} from "./result";
import type { ClaimValidationResult } from "./types";
import { validateClaimDeterministically } from "./validators";

/** Emits exactly one SUCCESS or terminal ERROR for every selected claim. */
export function validateSelectedClaims(
  claims: readonly AtomicClaimRecord[],
  indexes: ValidationIndexes,
  provenance: ResultProvenance,
): ClaimValidationResult[] {
  return claims.map((claim) => validateClaim(claim, indexes, provenance));
}

function validateClaim(
  claim: AtomicClaimRecord,
  indexes: ValidationIndexes,
  provenance: ResultProvenance,
): ClaimValidationResult {
  const generation = indexes.generationById.get(claim.generation_id);
  if (!generation) {
    return buildErrorResult({
      claim,
      generation: null,
      evidence: null,
      provenance,
      reasonCode: REASON_CODE.GENERATION_JOIN_FAILED,
      failedStage: "GENERATION_JOIN",
      errorMessage: `No canonical generation for ${claim.generation_id}.`,
    });
  }
  const evidence = indexes.evidenceByPackageId.get(generation.package_id);
  if (!evidence) {
    return buildErrorResult({
      claim,
      generation,
      evidence: null,
      provenance,
      reasonCode: REASON_CODE.EVIDENCE_JOIN_FAILED,
      failedStage: "EVIDENCE_JOIN",
      errorMessage: `No canonical Evidence Package for ${generation.package_id}.`,
    });
  }
  try {
    assertJoinedIdentity(claim, generation, evidence);
  } catch (error) {
    return buildErrorResult({
      claim,
      generation,
      evidence,
      provenance,
      reasonCode: REASON_CODE.EVIDENCE_JOIN_FAILED,
      failedStage: "EVIDENCE_JOIN",
      errorMessage: error instanceof Error ? error.message : String(error),
    });
  }
  return buildSuccessResult({
    claim,
    generation,
    evidence,
    decision: validateClaimDeterministically(claim, evidence),
    provenance,
  });
}
