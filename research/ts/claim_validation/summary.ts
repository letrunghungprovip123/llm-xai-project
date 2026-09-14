import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../contracts/validation-claims";
import {
  CLAIM_VALIDATION_SUMMARY_VERSION,
  EXECUTION_STATUS,
  VALIDATION_STATUS,
} from "./constants";
import { reasonCodeByName } from "./reasonCodes";
import type { ClaimValidationGenerationRow } from "./runtimeTypes";
import {
  VALIDATION_STATUSES,
  type ClaimValidationResult,
} from "./types";

export function buildClaimValidationSummary(
  claims: readonly AtomicClaimRecord[],
  results: readonly ClaimValidationResult[],
): Record<string, unknown> {
  const claimById = new Map(claims.map((claim) => [claim.claim_id, claim]));
  return {
    schema_version: CLAIM_VALIDATION_SUMMARY_VERSION,
    result_count: results.length,
    execution_status_counts: countBy(results, (result) => result.execution_status),
    validation_status_counts: countBy(
      results,
      (result) => result.validation_status ?? "null",
    ),
    reason_code_counts: countBy(results, (result) => result.reason_code),
    reason_family_counts: countBy(results, (result) =>
      reasonCodeByName(result.reason_code).family,
    ),
    hard_safety_count: results.filter(
      (result) => reasonCodeByName(result.reason_code).is_hard_safety_failure,
    ).length,
    by_model: groupedSummary(results, (result) => result.model_id),
    by_evidence_level: groupedSummary(
      results,
      (result) => result.evidence_level,
    ),
    by_claim_type: groupedSummary(results, (result) => result.claim_type),
    by_claim_origin: groupedSummary(
      results,
      (result) =>
        claimById.get(result.claim_id)?.claim_origin ?? "unknown",
    ),
  };
}

export function buildGenerationValidationSummary(
  generations: readonly ClaimValidationGenerationRow[],
  results: readonly ClaimValidationResult[],
): Array<Record<string, unknown>> {
  const byGeneration = groupBy(results, (result) => result.generation_id);
  return generations.map((generation) => {
    const identity = {
      generation_id: generation.generation_id,
      case_id: generation.case_id,
      model_id: generation.model_id,
      evidence_level: generation.evidence_level,
      repeat_id: generation.repeat_id,
      usable: generation.usable,
    };
    if (!generation.usable) {
      return {
        ...identity,
        total_claims: 0,
        failure_reason: generation.usability_reason_codes.join("|"),
        contract_usability_metadata: {
          runtime_status: generation.runtime_status,
          finish_reason: generation.finish_reason,
          truncated_response: generation.truncated_response,
          raw_json_parse_success: generation.raw_json_parse_success,
          schema_valid: generation.schema_valid,
          usability_reason_codes: generation.usability_reason_codes,
        },
      };
    }
    const rows = byGeneration.get(generation.generation_id) ?? [];
    const statusCounts = countBy(
      rows,
      (result) => result.validation_status ?? "null",
    );
    return {
      ...identity,
      total_claims: rows.length,
      supported_count: statusCounts[VALIDATION_STATUS.SUPPORTED] ?? 0,
      unsupported_count: statusCounts[VALIDATION_STATUS.UNSUPPORTED] ?? 0,
      contradicted_count: statusCounts[VALIDATION_STATUS.CONTRADICTED] ?? 0,
      not_verifiable_count: statusCounts[VALIDATION_STATUS.NOT_VERIFIABLE] ?? 0,
      not_applicable_count: statusCounts[VALIDATION_STATUS.NOT_APPLICABLE] ?? 0,
      execution_error_count: rows.filter(
        (result) => result.execution_status === EXECUTION_STATUS.ERROR,
      ).length,
      hard_safety_count: rows.filter(
        (result) => reasonCodeByName(result.reason_code).is_hard_safety_failure,
      ).length,
      reason_family_counts: countBy(rows, (result) =>
        reasonCodeByName(result.reason_code).family,
      ),
    };
  });
}

export function reasonCodeCsvRows(
  results: readonly ClaimValidationResult[],
): Array<Record<string, unknown>> {
  const counts = countBy(results, (result) => result.reason_code);
  return Object.keys(counts)
    .sort()
    .map((reasonCode) => {
      const reason = reasonCodeByName(reasonCode);
      return {
        reason_code: reasonCode,
        reason_family: reason.family,
        execution_status: reason.execution_status,
        validation_status: reason.validation_status,
        count: counts[reasonCode],
        hard_safety: reason.is_hard_safety_failure,
      };
    });
}

function groupedSummary(
  results: readonly ClaimValidationResult[],
  keyOf: (result: ClaimValidationResult) => string,
): Array<Record<string, unknown>> {
  const groups = groupBy(results, keyOf);
  return [...groups.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, rows]) => {
      const semanticDenominator = rows.filter(
        (result) => result.execution_status === EXECUTION_STATUS.SUCCESS,
      ).length;
      const statusCounts = countBy(
        rows,
        (result) => result.validation_status ?? "null",
      );
      return {
        key,
        result_count: rows.length,
        semantic_denominator: semanticDenominator,
        execution_error_count: rows.length - semanticDenominator,
        status_counts: Object.fromEntries(
          VALIDATION_STATUSES.map((status) => [status, statusCounts[status] ?? 0]),
        ),
        supported_rate:
          semanticDenominator === 0
            ? null
            : (statusCounts[VALIDATION_STATUS.SUPPORTED] ?? 0) /
              semanticDenominator,
      };
    });
}

export function countBy<T>(
  values: readonly T[],
  keyOf: (value: T) => string,
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const value of values) {
    const key = keyOf(value);
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return Object.fromEntries(
    Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)),
  );
}

function groupBy<T>(
  values: readonly T[],
  keyOf: (value: T) => string,
): Map<string, T[]> {
  const groups = new Map<string, T[]>();
  for (const value of values) {
    const key = keyOf(value);
    const group = groups.get(key) ?? [];
    group.push(value);
    groups.set(key, group);
  }
  return groups;
}
