import assert from "node:assert/strict";
import test from "node:test";

import {
  EXECUTION_STATUS,
  REASON_CODE,
  VALIDATION_STATUS,
} from "../../../research/ts/claim_validation/constants";
import { buildValidationIndexes } from "../../../research/ts/claim_validation/indexes";
import { reasonCodeByName } from "../../../research/ts/claim_validation/reasonCodes";
import {
  buildErrorResult,
  buildSuccessResult,
  CLAIM_VALIDATOR_VERSION,
} from "../../../research/ts/claim_validation/result";
import { createValidationId } from "../../../research/ts/claim_validation/schema";
import { validateSelectedClaims } from "../../../research/ts/claim_validation/validationExecution";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";
import {
  numericTestClaim,
  testClaim,
  testEvidence,
  testGeneration,
  testProvenance,
} from "./claimValidationTestFixtures";

test("validation identity depends only on claim and version identities", () => {
  const input = {
    claim_id: "claim_001",
    validator_version: CLAIM_VALIDATOR_VERSION,
    policy_version: "claim_validation_policy_v1",
  };
  const first = createValidationId(input);
  const timestampChanged = createValidationId({ ...input });
  const policyChanged = createValidationId({
    ...input,
    policy_version: "claim_validation_policy_v2",
  });
  const validatorChanged = createValidationId({
    ...input,
    validator_version: "claim_validator_v3.0.1",
  });
  assert.equal(first, timestampChanged);
  assert.notEqual(first, policyChanged);
  assert.notEqual(first, validatorChanged);
});

test("semantic validation is isolated to the exact exposed package", () => {
  const claim = testClaim({
    claim_type: "feature_direction",
    feature_id: "feature_a",
    direction: "increase_risk",
  });
  const exposed = testEvidence();
  const withDifferentHiddenIr = {
    ...exposed,
    hidden_ir: { feature_a: { direction: "decreases_risk" } },
  };
  const first = validateClaimDeterministically(claim, exposed);
  const hiddenChanged = validateClaimDeterministically(
    claim,
    withDifferentHiddenIr,
  );
  assert.deepEqual(first, hiddenChanged);

  const anotherLevel = testEvidence({
    level: "S4",
    features: [{
      feature_id: "feature_a",
      shap_value: -0.2,
      abs_shap_value: 0.2,
      direction: "decreases_risk",
      rank: 1,
    }],
  });
  assert.deepEqual(
    validateClaimDeterministically(claim, exposed),
    validateClaimDeterministically(claim, exposed),
  );
  assert.notEqual(
    validateClaimDeterministically(claim, anotherLevel).reasonCode,
    first.reasonCode,
  );
});

test("index insertion order and claim order cannot change canonical results", () => {
  const claims = [
    testClaim({ claim_type: "prediction", direction: "increase_risk" }),
    testClaim({
      claim_type: "feature_presence",
      feature_id: "feature_a",
      claim_id: "claim_feature_second",
    }),
  ].sort((left, right) => left.claim_id.localeCompare(right.claim_id));
  const generations = [testGeneration()];
  const packages = [testEvidence()];
  const forward = buildValidationIndexes({
    claims,
    generations,
    evidencePackages: packages,
  });
  const reverse = buildValidationIndexes({
    claims: [...claims].reverse(),
    generations: [...generations].reverse(),
    evidencePackages: [...packages].reverse(),
  });
  const first = validateSelectedClaims(claims, forward, testProvenance());
  const second = validateSelectedClaims(claims, reverse, testProvenance());
  assert.deepEqual(first, second);
});

test("equivalent percent and proportion normalization follows frozen policy", () => {
  const evidence = testEvidence({ probability: 0.5 });
  const percent = validateClaimDeterministically(
    numericTestClaim({ value: 50, unit: "percent", role: "prediction_score" }),
    evidence,
  );
  const proportion = validateClaimDeterministically(
    numericTestClaim({
      value: 0.5,
      unit: "probability",
      role: "prediction_score",
    }),
    evidence,
  );
  assert.equal(percent.reasonCode, REASON_CODE.NORMALIZED_MATCH);
  assert.equal(proportion.reasonCode, REASON_CODE.EXACT_MATCH);

  const unsupported = validateClaimDeterministically(
    numericTestClaim({
      value: 2,
      unit: null,
      role: "feature_value",
      featureId: "feature_a",
    }),
    evidence,
  );
  assert.equal(unsupported.reasonCode, REASON_CODE.NUMERIC_ROLE_UNSUPPORTED);
});

test("result status and reason invariants hold for SUCCESS and ERROR", () => {
  const claim = testClaim({ claim_type: "prediction", direction: "increase_risk" });
  const evidence = testEvidence();
  const success = buildSuccessResult({
    claim,
    generation: testGeneration(),
    evidence,
    decision: validateClaimDeterministically(claim, evidence),
    provenance: testProvenance(),
  });
  assert.equal(success.execution_status, EXECUTION_STATUS.SUCCESS);
  assert.notEqual(success.validation_status, null);
  assert.equal(
    reasonCodeByName(success.reason_code).validation_status,
    success.validation_status,
  );
  if (success.validation_status === VALIDATION_STATUS.SUPPORTED) {
    assert.equal(reasonCodeByName(success.reason_code).family, "MATCH");
  }

  const error = buildErrorResult({
    claim,
    generation: null,
    evidence: null,
    provenance: testProvenance(),
    reasonCode: REASON_CODE.GENERATION_JOIN_FAILED,
    failedStage: "GENERATION_JOIN",
    errorMessage: "Missing generation.",
  });
  assert.equal(error.execution_status, EXECUTION_STATUS.ERROR);
  assert.equal(error.validation_status, null);
  assert.equal(reasonCodeByName(error.reason_code).family, "SYSTEM");
});
