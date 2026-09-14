import { REASON_CODE } from "./constants";
import type {
  ClaimValidationFactValues,
  ValidationStatus,
} from "./types";
import type { SemanticDecision } from "./validators";

const EXACT_REASON_CODES = new Set<string>([
  REASON_CODE.EXACT_MATCH,
  REASON_CODE.MAGNITUDE_MATCH,
]);

export function assertSemanticDecisionConsistency(
  decision: SemanticDecision,
  evidenceStatus: ValidationStatus,
): void {
  if (EXACT_REASON_CODES.has(decision.reasonCode)) {
    assertComparedFactsEqual(decision.expected, decision.observed, "exact");
  }
  if (decision.reasonCode === REASON_CODE.NORMALIZED_MATCH) {
    if (decision.normalizationsApplied.length === 0) {
      throw new Error("NORMALIZED_MATCH requires a named normalization.");
    }
    const normalizedExpected = applyNormalizations(
      decision.expected,
      decision.normalizationsApplied,
    );
    assertComparedFactsEqual(normalizedExpected, decision.observed, "normalized");
  }
  if (decision.reasonCode === REASON_CODE.TOLERANCE_MATCH) {
    assertToleranceMatch(decision);
  }
  if (evidenceStatus === "CONTRADICTED") {
    if (decision.observed.exposure_status === "SOURCE_MISSING") {
      throw new Error("Source-missing evidence cannot be CONTRADICTED.");
    }
    if (!hasOpposingFact(decision.expected, decision.observed)) {
      throw new Error("CONTRADICTED requires an explicit opposing fact.");
    }
  }
  if (
    evidenceStatus === "NOT_VERIFIABLE" &&
    decision.unresolvedFacts.length === 0
  ) {
    throw new Error("NOT_VERIFIABLE requires an unresolved fact.");
  }
}

function assertComparedFactsEqual(
  expected: ClaimValidationFactValues,
  observed: ClaimValidationFactValues,
  mode: string,
): void {
  for (const key of factKeys(expected)) {
    if (expected[key] !== null && expected[key] !== observed[key]) {
      throw new Error(
        `${mode} fact mismatch at ${key}: `
        + `${String(expected[key])} != ${String(observed[key])}.`,
      );
    }
  }
}

function applyNormalizations(
  facts: ClaimValidationFactValues,
  normalizationIds: readonly string[],
): ClaimValidationFactValues {
  const normalized = { ...facts };
  for (const normalizationId of normalizationIds) {
    switch (normalizationId) {
      case "probabilistic_to_hedged_uncertainty":
        if (normalized.certainty === "probabilistic") {
          normalized.certainty = "hedged";
        }
        break;
      case "evidence_direction_plural_to_claim_singular":
      case "percent_to_unit_interval":
        break;
      default:
        throw new Error(`Unknown fact normalization: ${normalizationId}.`);
    }
  }
  return normalized;
}

function assertToleranceMatch(decision: SemanticDecision): void {
  const comparison = decision.numericComparison;
  if (!comparison) {
    throw new Error("TOLERANCE_MATCH requires numeric comparison metadata.");
  }
  if (comparison.difference > comparison.tolerance) {
    throw new Error("TOLERANCE_MATCH difference exceeds tolerance.");
  }
  const expected =
    decision.expected.numeric_value ?? decision.expected.probability;
  const observed =
    decision.observed.numeric_value ?? decision.observed.probability;
  if (expected === null || observed === null) {
    throw new Error("TOLERANCE_MATCH requires expected and observed numbers.");
  }
  const actualDifference = Math.abs(expected - observed);
  if (Math.abs(actualDifference - comparison.difference) > Number.EPSILON) {
    throw new Error("TOLERANCE_MATCH difference metadata is inconsistent.");
  }
}

function hasOpposingFact(
  expected: ClaimValidationFactValues,
  observed: ClaimValidationFactValues,
): boolean {
  return factKeys(expected).some(
    (key) =>
      expected[key] !== null &&
      observed[key] !== null &&
      expected[key] !== observed[key],
  );
}

function factKeys(
  _facts: ClaimValidationFactValues,
): Array<keyof ClaimValidationFactValues> {
  return [
    "prediction_label",
    "probability",
    "numeric_value",
    "numeric_unit",
    "numeric_role",
    "feature_id",
    "concept_id",
    "direction",
    "magnitude",
    "rank",
    "certainty",
    "causal_strength",
    "exposure_status",
  ];
}
