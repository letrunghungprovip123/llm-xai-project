import assert from "node:assert/strict";
import test from "node:test";

import { REASON_CODE } from "../../../research/ts/claim_validation/constants";
import { assertSemanticDecisionConsistency } from "../../../research/ts/claim_validation/factConsistency";
import { buildSuccessResult } from "../../../research/ts/claim_validation/result";
import { emptyClaimValidationFactValues } from "../../../research/ts/claim_validation/types";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";
import { decision } from "../../../research/ts/claim_validation/validators/shared";
import {
  testClaim,
  testEvidence,
  testGeneration,
  testProvenance,
} from "./claimValidationTestFixtures";

test("fact-consistency rejects inconsistent exact and normalized matches", () => {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.certainty = "deterministic";
  observed.certainty = "hedged";
  expected.exposure_status = "EXPOSED";
  observed.exposure_status = "EXPOSED";

  assert.throws(
    () =>
      assertSemanticDecisionConsistency(
        decision(REASON_CODE.EXACT_MATCH, expected, observed, "Invalid exact."),
        "SUPPORTED",
      ),
    /exact fact mismatch/u,
  );
  assert.throws(
    () =>
      assertSemanticDecisionConsistency(
        decision(
          REASON_CODE.NORMALIZED_MATCH,
          expected,
          observed,
          "Missing normalization.",
        ),
        "SUPPORTED",
      ),
    /named normalization/u,
  );
});

test("tolerance, contradiction and unresolved-fact invariants fail closed", () => {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.numeric_value = 0.5;
  observed.numeric_value = 0.6;
  expected.exposure_status = "EXPOSED";
  observed.exposure_status = "EXPOSED";

  assert.throws(
    () =>
      assertSemanticDecisionConsistency(
        decision(
          REASON_CODE.TOLERANCE_MATCH,
          expected,
          observed,
          "Invalid tolerance.",
          [],
          [],
          {
            numericComparison: {
              difference: 0.1,
              tolerance: 0.01,
              tolerancePolicyId: "test",
            },
          },
        ),
        "SUPPORTED",
      ),
    /exceeds tolerance/u,
  );

  observed.numeric_value = null;
  observed.exposure_status = "SOURCE_MISSING";
  assert.throws(
    () =>
      assertSemanticDecisionConsistency(
        decision(
          REASON_CODE.NUMERIC_EXACT_MISMATCH,
          expected,
          observed,
          "Invalid contradiction.",
        ),
        "CONTRADICTED",
      ),
    /Source-missing/u,
  );

  const unresolved = decision(
    REASON_CODE.NUMERIC_ROLE_UNSUPPORTED,
    expected,
    observed,
    "Missing semantic source.",
  );
  unresolved.unresolvedFacts = [];
  assert.throws(
    () =>
      assertSemanticDecisionConsistency(unresolved, "NOT_VERIFIABLE"),
    /unresolved fact/u,
  );
});

test("S5 exposed-forbidden evidence remains supported with policy violation", () => {
  const evidence = testEvidence({ level: "S5" });
  evidence.prompt_payload.constraints.allowed_feature_ids = ["feature_a"];
  const claim = testClaim({
    claim_type: "feature_presence",
    claim_subtype: "FEATURE_MENTION",
    feature_id: "feature_b",
    subject_type: "feature",
    evidence_level: "S5",
  });
  const semantic = validateClaimDeterministically(claim, evidence);
  const result = buildSuccessResult({
    claim,
    generation: testGeneration(),
    evidence,
    decision: semantic,
    provenance: testProvenance(),
  });

  assert.equal(result.evidence_status, "SUPPORTED");
  assert.equal(result.validation_status, result.evidence_status);
  assert.equal(result.policy_status, "VIOLATION");
  assert.equal(result.feature_exposure_status, "EXPOSED_FORBIDDEN");
  assert.equal(result.concept_exposure_status, "NOT_APPLICABLE");
  assert.equal(result.primary_reason_code, REASON_CODE.EXACT_MATCH);
  assert.deepEqual(result.reason_codes, [REASON_CODE.EXACT_MATCH]);
  assert.equal(result.claim_subtype, "FEATURE_MENTION");
  assert.equal(result.claim_schema_version, "claims_v3");
});
