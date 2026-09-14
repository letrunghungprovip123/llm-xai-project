import type {
  ClaimValidationClaimPolicy,
  ClaimValidationNarrativePolicy,
  ClaimValidationSelectionContext,
} from "./runtimeTypes";
import {
  optionalBoolean,
  optionalFiniteNumber,
  optionalNonNegativeInteger,
  optionalString,
  requireObject,
} from "./parseHelpers";

const narrativeBooleanFields = [
  "must_include_uncertainty",
  "avoid_single_cause_wording",
  "allow_main_reason_wording",
  "must_include_distributed_evidence_note",
  "must_not_give_specific_feature_reason",
  "must_include_partial_evidence_note",
  "must_not_claim_evidence_is_complete",
  "mention_mixed_signals",
  "backend_controls_factor_order",
  "must_follow_backend_skeleton",
  "must_not_add_factor_outside_skeleton",
] as const;

const claimPolicyBooleanFields = [
  "allow_prediction_claim",
  "allow_uncertainty_claim",
  "allow_feature_claim",
  "allow_concept_claim",
  "allow_direction_claim",
  "allow_magnitude_claim",
  "allow_causal_claim",
  "allow_financial_advice",
  "allow_absolute_decision_claim",
  "allow_true_label_claim",
] as const;

export function parseNarrativePolicy(
  value: unknown,
  context: string,
): ClaimValidationNarrativePolicy {
  const policy = requireObject(value, context);
  const parsed: ClaimValidationNarrativePolicy = {};
  for (const field of narrativeBooleanFields) {
    const fieldValue = optionalBoolean(policy[field], `${context}.${field}`);
    if (fieldValue !== undefined) parsed[field] = fieldValue;
  }
  return parsed;
}

export function parseClaimPolicy(
  value: unknown,
  context: string,
): ClaimValidationClaimPolicy {
  const policy = requireObject(value, context);
  const parsed: ClaimValidationClaimPolicy = {};
  for (const field of claimPolicyBooleanFields) {
    const fieldValue = optionalBoolean(policy[field], `${context}.${field}`);
    if (fieldValue !== undefined) parsed[field] = fieldValue;
  }
  return parsed;
}

export function parseSelectionContext(
  value: unknown,
  context: string,
): ClaimValidationSelectionContext {
  const selection = requireObject(value, context);
  return {
    selected_evidence_count:
      optionalNonNegativeInteger(
        selection.selected_evidence_count,
        `${context}.selected_evidence_count`,
      ) ?? 0,
    ...optionalNumberField(selection, "adaptive_k", context, true),
    ...optionalNumberField(selection, "coverage", context),
    ...optionalNumberField(selection, "coverage_threshold", context),
    ...optionalNumberField(selection, "normalized_entropy", context),
    ...optionalNumberField(selection, "concept_group_count", context, true),
    ...optionalNumberField(selection, "mixed_concept_group_count", context, true),
    ...optionalTextField(selection, "coverage_status", context),
    ...optionalTextField(selection, "entropy_level", context),
  };
}

function optionalNumberField(
  source: Record<string, unknown>,
  field: keyof ClaimValidationSelectionContext,
  context: string,
  integer = false,
): Partial<ClaimValidationSelectionContext> {
  const value = integer
    ? optionalNonNegativeInteger(source[field], `${context}.${field}`)
    : optionalFiniteNumber(source[field], `${context}.${field}`);
  return value === undefined ? {} : { [field]: value };
}

function optionalTextField(
  source: Record<string, unknown>,
  field: keyof ClaimValidationSelectionContext,
  context: string,
): Partial<ClaimValidationSelectionContext> {
  const value = optionalString(source[field], `${context}.${field}`);
  return value === undefined ? {} : { [field]: value };
}
