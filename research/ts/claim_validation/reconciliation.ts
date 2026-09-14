import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../contracts/validation-claims";
import type { ClaimValidationResult } from "./types";

export type ReconciliationAudit = {
  input_claim_count: number;
  output_result_count: number;
  unique_input_claim_ids: number;
  unique_output_claim_ids: number;
  unique_validation_ids: number;
  missing_claim_ids: string[];
  unexpected_claim_ids: string[];
};

/** Fails closed unless every input claim has one unique terminal result. */
export function assertResultReconciliation(
  claims: readonly AtomicClaimRecord[],
  results: readonly ClaimValidationResult[],
): void {
  const audit = reconciliation(claims, results);
  const countsMatch =
    audit.input_claim_count === audit.output_result_count &&
    audit.unique_input_claim_ids === audit.input_claim_count &&
    audit.unique_output_claim_ids === audit.output_result_count &&
    audit.unique_validation_ids === audit.output_result_count;
  if (
    !countsMatch ||
    audit.missing_claim_ids.length > 0 ||
    audit.unexpected_claim_ids.length > 0
  ) {
    throw new Error(`Claim/result reconciliation failed: ${JSON.stringify(audit)}`);
  }
}

export function reconciliation(
  claims: readonly AtomicClaimRecord[],
  results: readonly ClaimValidationResult[],
): ReconciliationAudit {
  const inputIds = new Set(claims.map((claim) => claim.claim_id));
  const outputIds = new Set(results.map((result) => result.claim_id));
  return {
    input_claim_count: claims.length,
    output_result_count: results.length,
    unique_input_claim_ids: inputIds.size,
    unique_output_claim_ids: outputIds.size,
    unique_validation_ids: new Set(results.map((result) => result.validation_id))
      .size,
    missing_claim_ids: difference(inputIds, outputIds),
    unexpected_claim_ids: difference(outputIds, inputIds),
  };
}

function difference(left: Set<string>, right: Set<string>): string[] {
  return [...left].filter((value) => !right.has(value)).sort();
}
