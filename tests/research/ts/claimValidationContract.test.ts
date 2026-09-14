import assert from "node:assert/strict";
import test from "node:test";

import {
  assertClaimValidationV2Result,
  assertClaimValidationV3Result,
  assertClaimValidationResult,
  createValidationId,
} from "../../../research/ts/claim_validation/schema";
import {
  CLAIM_VALIDATION_SCHEMA_VERSION,
  CLAIM_VALIDATOR_VERSION,
} from "../../../research/ts/claim_validation/constants";
import {
  emptyClaimValidationFactValues,
} from "../../../research/ts/claim_validation/types";

test("claim validation v4 accepts SUCCESS and pre-evidence ERROR results", () => {
  assert.doesNotThrow(() => assertClaimValidationResult(validSuccess()));
  assert.doesNotThrow(() => assertClaimValidationResult(validError()));
});

test("claim validation v4 enforces execution and semantic status invariants", () => {
  const successWithoutStatus = validSuccess();
  successWithoutStatus.validation_status = null;
  assert.throws(
    () => assertClaimValidationResult(successWithoutStatus),
    /Invalid claim_validation_v4 result/u,
  );

  const errorWithSemanticStatus = validError();
  errorWithSemanticStatus.validation_status = "UNSUPPORTED";
  errorWithSemanticStatus.evidence_status = "UNSUPPORTED";
  assert.throws(
    () => assertClaimValidationResult(errorWithSemanticStatus),
    /Invalid claim_validation_v4 result/u,
  );

  const errorWithNonSystemReason = validError();
  errorWithNonSystemReason.reason_code = "FEATURE_NOT_EXPOSED";
  errorWithNonSystemReason.primary_reason_code = "FEATURE_NOT_EXPOSED";
  errorWithNonSystemReason.reason_codes = ["FEATURE_NOT_EXPOSED"];
  assert.throws(
    () => assertClaimValidationResult(errorWithNonSystemReason),
    /Invalid claim_validation_v4 result|SYSTEM reason/u,
  );
});

test("claim validation v4 rejects invalid provenance and identity", () => {
  const absolutePath = validSuccess();
  absolutePath.claims_input_path = "/tmp/claims.jsonl";
  assert.throws(
    () => assertClaimValidationResult(absolutePath),
    /Invalid claim_validation_v4 result|project-relative/u,
  );

  const invalidSha = validSuccess();
  invalidSha.claims_input_sha256 = "bad";
  assert.throws(
    () => assertClaimValidationResult(invalidSha),
    /Invalid claim_validation_v4 result/u,
  );

  const invalidLevel = validSuccess();
  invalidLevel.evidence_level = "S7";
  assert.throws(
    () => assertClaimValidationResult(invalidLevel),
    /Invalid claim_validation_v4 result/u,
  );

  const invalidId = validSuccess();
  invalidId.validation_id = `validation_${"0".repeat(64)}`;
  assert.throws(
    () => assertClaimValidationResult(invalidId),
    /Invalid deterministic validation_id/u,
  );
});

test("claim validation v4 rejects unknown fields and claim types", () => {
  const extraProperty = validSuccess();
  extraProperty.unexpected = true;
  assert.throws(
    () => assertClaimValidationResult(extraProperty),
    /Invalid claim_validation_v4 result/u,
  );

  const unsupportedClaimType = validSuccess();
  unsupportedClaimType.claim_type = "unsupported_type";
  assert.throws(
    () => assertClaimValidationResult(unsupportedClaimType),
    /Invalid claim_validation_v4 result/u,
  );
});

test("PARTIALLY_SUPPORTED is not part of claim validation v4", () => {
  const result = validSuccess();
  result.validation_status = "PARTIALLY_SUPPORTED";
  result.evidence_status = "PARTIALLY_SUPPORTED";
  assert.throws(
    () => assertClaimValidationResult(result),
    /Invalid claim_validation_v4 result/u,
  );
});

test("v4 SUCCESS requires evidence identity and cannot carry error details", () => {
  const missingIdentity = validSuccess();
  missingIdentity.source_evidence_id = null;
  missingIdentity.package_id = null;
  assert.throws(
    () => assertClaimValidationResult(missingIdentity),
    /Invalid claim_validation_v4 result/u,
  );

  const successWithError = validSuccess();
  successWithError.error = {
    error_code: "OUTPUT_SCHEMA_FAILED",
    error_message: "Synthetic.",
    failed_stage: "OUTPUT_SCHEMA",
  };
  assert.throws(
    () => assertClaimValidationResult(successWithError),
    /Invalid claim_validation_v4 result/u,
  );
});

test("v4 ERROR permits null evidence identity but requires error details", () => {
  const error = validError();
  error.source_evidence_id = null;
  error.package_id = null;
  assert.doesNotThrow(() => assertClaimValidationResult(error));
  error.error = null;
  assert.throws(
    () => assertClaimValidationResult(error),
    /Invalid claim_validation_v4 result/u,
  );
});

test("frozen v2/v3 contracts reject active v4 results", () => {
  const v2 = legacyResult("claim_validation_v2");
  assert.doesNotThrow(() => assertClaimValidationV2Result(v2));

  const v2Error = legacyResult("claim_validation_v2");
  v2Error.execution_status = "ERROR";
  v2Error.validation_status = null;
  v2Error.reason_code = "CLAIM_JOIN_FAILED";
  v2Error.source_evidence_id = null;
  v2Error.package_id = null;
  v2Error.error = {
    error_code: "CLAIM_JOIN_FAILED",
    error_message: "Missing join.",
    failed_stage: "CLAIM_JOIN",
  };
  assert.throws(
    () => assertClaimValidationV2Result(v2Error),
    /Invalid historical claim validation v2 result/u,
  );

  assert.throws(
    () => assertClaimValidationV2Result(validSuccess()),
    /Invalid historical claim validation v2 result/u,
  );
  const v3 = legacyResult("claim_validation_v3");
  assert.doesNotThrow(() => assertClaimValidationV3Result(v3));
  assert.throws(
    () => assertClaimValidationV3Result(validSuccess()),
    /Invalid historical claim validation v3 result/u,
  );
  assert.throws(
    () => assertClaimValidationResult(v2),
    /Invalid claim_validation_v4 result/u,
  );
});

test("expected and observed facts must match the claim type", () => {
  const result = validSuccess();
  const expected = result.expected as Record<string, unknown>;
  const observed = result.observed as Record<string, unknown>;
  expected.feature_id = "feature_not_valid_for_prediction";
  observed.feature_id = "feature_not_valid_for_prediction";
  assert.throws(
    () => assertClaimValidationResult(result),
    /expected\.feature_id is incompatible with claim_type prediction/u,
  );
});

function validSuccess(): Record<string, unknown> {
  const validatorVersion = CLAIM_VALIDATOR_VERSION;
  const policyVersion = "claim_validation_policy_v1";
  const claimId = "claim_001";
  const expected = emptyClaimValidationFactValues();
  expected.prediction_label = "high_default_risk";
  expected.exposure_status = "EXPOSED";
  const observed = structuredClone(expected);
  return {
    schema_version: CLAIM_VALIDATION_SCHEMA_VERSION,
    validation_id: createValidationId({
      claim_id: claimId,
      validator_version: validatorVersion,
      policy_version: policyVersion,
    }),
    claim_id: claimId,
    generation_id: "generation_001",
    case_id: "case_001",
    model_id: "model_001",
    evidence_level: "S0",
    repeat_id: 1,
    claim_type: "prediction",
    claim_subtype: "OVERALL_LABEL",
    claim_schema_version: "claims_v3",
    parent_claim_id: "claim_parent_001",
    finalizer_version: "claim_finalizer_v2.0.0",
    finalization_policy_version: "claim_finalization_policy_v3",
    execution_status: "SUCCESS",
    validation_status: "SUPPORTED",
    evidence_status: "SUPPORTED",
    policy_status: "NOT_APPLICABLE",
    validation_coverage: "DETERMINISTIC",
    reason_code: "EXACT_MATCH",
    primary_reason_code: "EXACT_MATCH",
    reason_codes: ["EXACT_MATCH"],
    validator_mode: "DETERMINISTIC",
    validator_version: validatorVersion,
    policy_version: policyVersion,
    created_at: "2026-07-23T00:00:00.000Z",
    claims_input_path: "data/claims.jsonl",
    claims_input_sha256: "1".repeat(64),
    generation_index_path: "data/generation_index.jsonl",
    generation_index_sha256: "2".repeat(64),
    evidence_packages_path: "data/evidence_packages.jsonl",
    evidence_packages_sha256: "3".repeat(64),
    source_evidence_id: "evidence_001",
    package_id: "package_001",
    source_ir_id: "ir_001",
    expected,
    observed,
    message: "Prediction label matches exposed evidence.",
    normalizations_applied: [],
    source_record_keys: ["claim:claim_001", "package:package_001"],
    unresolved_facts: [],
    numeric_comparison: null,
    feature_exposure_status: "NOT_APPLICABLE",
    concept_exposure_status: "NOT_APPLICABLE",
    error: null,
  };
}

function validError(): Record<string, unknown> {
  const result = validSuccess();
  result.execution_status = "ERROR";
  result.validation_status = null;
  result.evidence_status = null;
  result.policy_status = null;
  result.validation_coverage = "UNVALIDATED";
  result.reason_code = "CLAIM_JOIN_FAILED";
  result.primary_reason_code = "CLAIM_JOIN_FAILED";
  result.reason_codes = ["CLAIM_JOIN_FAILED"];
  result.message = "Claim could not be joined to its generation.";
  result.error = {
    error_code: "CLAIM_JOIN_FAILED",
    error_message: "No generation row for claim_001.",
    failed_stage: "CLAIM_JOIN",
  };
  return result;
}

function legacyResult(
  schemaVersion: "claim_validation_v2" | "claim_validation_v3",
): Record<string, unknown> {
  const result = validSuccess();
  result.schema_version = schemaVersion;
  for (const field of [
    "parent_claim_id",
    "claim_subtype",
    "claim_schema_version",
    "finalizer_version",
    "finalization_policy_version",
    "evidence_status",
    "policy_status",
    "validation_coverage",
    "primary_reason_code",
    "reason_codes",
    "unresolved_facts",
    "numeric_comparison",
    "feature_exposure_status",
    "concept_exposure_status",
  ]) {
    delete result[field];
  }
  return result;
}
