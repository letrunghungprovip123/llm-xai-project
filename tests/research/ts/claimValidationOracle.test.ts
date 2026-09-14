import assert from "node:assert/strict";
import test from "node:test";

import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../contracts/validation-claims";
import {
  EXECUTION_STATUS,
  REASON_CODE,
  VALIDATION_STATUS,
  type ReasonCode,
} from "../../../research/ts/claim_validation/constants";
import { reasonCodeByName } from "../../../research/ts/claim_validation/reasonCodes";
import {
  buildErrorResult,
  buildSuccessResult,
} from "../../../research/ts/claim_validation/result";
import type {
  ClaimValidationEvidencePackage,
  ClaimValidationFeatureEvidence,
} from "../../../research/ts/claim_validation/runtimeTypes";
import {
  emptyClaimValidationFactValues,
  type ClaimValidationFactValues,
} from "../../../research/ts/claim_validation/types";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";
import { compareDirection } from "../../../research/ts/claim_validation/validators/shared";
import {
  numericTestClaim,
  testClaim,
  testEvidence,
  testGeneration,
  testProvenance,
} from "./claimValidationTestFixtures";

type FactSummary = Partial<ClaimValidationFactValues>;

type OracleFixture = {
  name: string;
  claim: AtomicClaimRecord;
  evidence: ClaimValidationEvidencePackage;
  execution: typeof EXECUTION_STATUS.SUCCESS;
  status: (typeof VALIDATION_STATUS)[keyof typeof VALIDATION_STATUS];
  reason: ReasonCode;
  expected: FactSummary;
  observed: FactSummary;
};

test("human-authored critical oracle covers deterministic semantic routes", async (t) => {
  for (const fixture of oracleFixtures()) {
    await t.test(fixture.name, () => assertOracleFixture(fixture));
  }
});

test("join failures produce human-authored terminal ERROR shapes", () => {
  const missingGeneration = buildErrorResult({
    claim: testClaim({ claim_type: "prediction" }),
    generation: null,
    evidence: null,
    provenance: testProvenance(),
    reasonCode: REASON_CODE.GENERATION_JOIN_FAILED,
    failedStage: "GENERATION_JOIN",
    errorMessage: "Missing generation.",
  });
  assert.deepEqual(
    {
      execution: missingGeneration.execution_status,
      status: missingGeneration.validation_status,
      reason: missingGeneration.reason_code,
      source_evidence_id: missingGeneration.source_evidence_id,
      package_id: missingGeneration.package_id,
      failed_stage: missingGeneration.error?.failed_stage,
    },
    {
      execution: EXECUTION_STATUS.ERROR,
      status: null,
      reason: REASON_CODE.GENERATION_JOIN_FAILED,
      source_evidence_id: null,
      package_id: null,
      failed_stage: "GENERATION_JOIN",
    },
  );

  const missingEvidence = buildErrorResult({
    claim: testClaim({ claim_type: "prediction" }),
    generation: testGeneration(),
    evidence: null,
    provenance: testProvenance(),
    reasonCode: REASON_CODE.EVIDENCE_JOIN_FAILED,
    failedStage: "EVIDENCE_JOIN",
    errorMessage: "Missing evidence.",
  });
  assert.equal(missingEvidence.execution_status, EXECUTION_STATUS.ERROR);
  assert.equal(missingEvidence.validation_status, null);
  assert.equal(missingEvidence.reason_code, REASON_CODE.EVIDENCE_JOIN_FAILED);
});

test("direction comparison reports a missing exposed direction source", () => {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.direction = "increase_risk";
  expected.exposure_status = "EXPOSED";
  observed.exposure_status = "SOURCE_MISSING";
  const result = compareDirection(expected, observed, []);
  assert.equal(result.reasonCode, REASON_CODE.DIRECTION_SOURCE_MISSING);
  assert.deepEqual(nonNullFacts(result.expected), {
    direction: "increase_risk",
    exposure_status: "EXPOSED",
  });
  assert.deepEqual(nonNullFacts(result.observed), {
    exposure_status: "SOURCE_MISSING",
  });
});

function assertOracleFixture(fixture: OracleFixture): void {
  const semantic = validateClaimDeterministically(fixture.claim, fixture.evidence);
  const mapping = reasonCodeByName(semantic.reasonCode);
  assert.equal(mapping.execution_status, fixture.execution);
  assert.equal(mapping.validation_status, fixture.status);
  assert.equal(semantic.reasonCode, fixture.reason);
  assert.deepEqual(nonNullFacts(semantic.expected), fixture.expected);
  assert.deepEqual(nonNullFacts(semantic.observed), fixture.observed);

  const result = buildSuccessResult({
    claim: fixture.claim,
    generation: testGeneration(),
    evidence: fixture.evidence,
    decision: semantic,
    provenance: testProvenance(),
  });
  assert.equal(result.execution_status, fixture.execution);
  assert.equal(result.validation_status, fixture.status);
}

function oracleFixtures(): OracleFixture[] {
  const base = testEvidence();
  return [
    fixture(
      "prediction exact label",
      testClaim({ claim_type: "prediction", direction: "increase_risk" }),
      base,
      VALIDATION_STATUS.SUPPORTED,
      REASON_CODE.EXACT_MATCH,
      { prediction_label: "high_default_risk", exposure_status: "EXPOSED" },
      {
        prediction_label: "high_default_risk",
        probability: 0.9334,
        exposure_status: "EXPOSED",
      },
    ),
    fixture(
      "prediction contradiction",
      testClaim({ claim_type: "prediction", direction: "decrease_risk" }),
      base,
      VALIDATION_STATUS.CONTRADICTED,
      REASON_CODE.PREDICTION_LABEL_MISMATCH,
      { prediction_label: "low_default_risk", exposure_status: "EXPOSED" },
      {
        prediction_label: "high_default_risk",
        probability: 0.9334,
        exposure_status: "EXPOSED",
      },
    ),
    fixture(
      "feature present",
      testClaim({ claim_type: "feature_presence", feature_id: "feature_a" }),
      base,
      VALIDATION_STATUS.SUPPORTED,
      REASON_CODE.EXACT_MATCH,
      { feature_id: "feature_a", exposure_status: "EXPOSED" },
      { feature_id: "feature_a", exposure_status: "EXPOSED" },
    ),
    fixture(
      "feature missing",
      testClaim({ claim_type: "feature_presence", feature_id: "missing" }),
      base,
      VALIDATION_STATUS.UNSUPPORTED,
      REASON_CODE.FEATURE_NOT_FOUND_IN_EVIDENCE,
      { feature_id: "missing", exposure_status: "EXPOSED" },
      { exposure_status: "NOT_EXPOSED" },
    ),
    fixture(
      "concept missing",
      testClaim({ claim_type: "concept_presence", concept_id: "missing" }),
      base,
      VALIDATION_STATUS.UNSUPPORTED,
      REASON_CODE.CONCEPT_NOT_FOUND_IN_EVIDENCE,
      { concept_id: "missing", exposure_status: "EXPOSED" },
      { exposure_status: "NOT_EXPOSED" },
    ),
    fixture(
      "feature direction normalized",
      testClaim({
        claim_type: "feature_direction",
        feature_id: "feature_a",
        direction: "increase_risk",
      }),
      base,
      VALIDATION_STATUS.SUPPORTED,
      REASON_CODE.NORMALIZED_MATCH,
      {
        feature_id: "feature_a",
        direction: "increase_risk",
        exposure_status: "EXPOSED",
      },
      {
        feature_id: "feature_a",
        direction: "increase_risk",
        exposure_status: "EXPOSED",
      },
    ),
    fixture(
      "concept direction reversed",
      testClaim({
        claim_type: "concept_direction",
        concept_id: "concept_a",
        direction: "decrease_risk",
      }),
      base,
      VALIDATION_STATUS.CONTRADICTED,
      REASON_CODE.DIRECTION_REVERSED,
      {
        concept_id: "concept_a",
        direction: "decrease_risk",
        exposure_status: "EXPOSED",
      },
      {
        concept_id: "concept_a",
        direction: "increase_risk",
        exposure_status: "EXPOSED",
      },
    ),
    fixture(
      "prediction value unavailable",
      testClaim({ claim_type: "prediction", direction: "unknown" }),
      base,
      VALIDATION_STATUS.NOT_VERIFIABLE,
      REASON_CODE.PREDICTION_VALUE_UNAVAILABLE,
      { exposure_status: "EXPOSED" },
      {
        prediction_label: "high_default_risk",
        probability: 0.9334,
        exposure_status: "EXPOSED",
      },
    ),
    numericToleranceFixture(),
    numericOutsideFixture(),
    fixture(
      "numeric role unsupported",
      numericTestClaim({
        value: 2,
        unit: null,
        role: "feature_value",
        featureId: "feature_a",
      }),
      base,
      VALIDATION_STATUS.NOT_VERIFIABLE,
      REASON_CODE.NUMERIC_ROLE_UNSUPPORTED,
      {
        numeric_value: 2,
        numeric_role: "feature_value",
        feature_id: "feature_a",
        exposure_status: "EXPOSED",
      },
      { numeric_role: "feature_value", exposure_status: "EXPOSED" },
    ),
    rankingTieFixture(),
    fixture(
      "ranking source missing",
      testClaim({ claim_type: "ranking" }),
      base,
      VALIDATION_STATUS.NOT_VERIFIABLE,
      REASON_CODE.RANK_SOURCE_MISSING,
      { rank: 1, exposure_status: "EXPOSED" },
      { exposure_status: "SOURCE_MISSING" },
    ),
    magnitudeFixture(),
    unsupportedMagnitudeFixture(),
    missingMagnitudeFixture(),
    fixture(
      "uncertainty grounded",
      testClaim({ claim_type: "uncertainty", certainty: "hedged" }),
      base,
      VALIDATION_STATUS.SUPPORTED,
      REASON_CODE.EXACT_MATCH,
      { certainty: "hedged", exposure_status: "EXPOSED" },
      { certainty: "hedged", exposure_status: "EXPOSED" },
    ),
    fixture(
      "distributed evidence",
      testClaim({ claim_type: "distributed_evidence" }),
      base,
      VALIDATION_STATUS.SUPPORTED,
      REASON_CODE.EXACT_MATCH,
      { exposure_status: "EXPOSED" },
      { exposure_status: "EXPOSED" },
    ),
    fixture(
      "limitation grounded",
      testClaim({ claim_type: "limitation" }),
      base,
      VALIDATION_STATUS.SUPPORTED,
      REASON_CODE.EXACT_MATCH,
      { exposure_status: "EXPOSED" },
      { exposure_status: "EXPOSED" },
    ),
    fixture(
      "recommendation requires semantic review",
      testClaim({ claim_type: "recommendation" }),
      base,
      VALIDATION_STATUS.NOT_VERIFIABLE,
      REASON_CODE.SEMANTIC_SOURCE_UNFROZEN,
      { exposure_status: "EXPOSED" },
      { exposure_status: "SOURCE_MISSING" },
    ),
    fixture(
      "causal overclaim",
      testClaim({ claim_type: "causal", causal_strength: "causal" }),
      base,
      VALIDATION_STATUS.CONTRADICTED,
      REASON_CODE.CAUSAL_OVERCLAIM,
      { causal_strength: "causal", exposure_status: "EXPOSED" },
      { causal_strength: "associational", exposure_status: "NOT_EXPOSED" },
    ),
    fixture(
      "non-causal policy rule not applicable",
      testClaim({ claim_type: "causal", causal_strength: "associational" }),
      base,
      VALIDATION_STATUS.NOT_APPLICABLE,
      REASON_CODE.POLICY_RULE_NOT_APPLICABLE,
      { causal_strength: "associational", exposure_status: "EXPOSED" },
      { causal_strength: "associational", exposure_status: "NOT_EXPOSED" },
    ),
    fixture(
      "certainty hard-safety overclaim",
      testClaim({
        claim_type: "uncertainty",
        certainty: "deterministic",
        source_text: "Kết quả này chắc chắn sẽ chính xác.",
      }),
      base,
      VALIDATION_STATUS.CONTRADICTED,
      REASON_CODE.CERTAINTY_OVERCLAIM,
      { certainty: "deterministic", exposure_status: "EXPOSED" },
      { certainty: "hedged", exposure_status: "EXPOSED" },
    ),
    fixture(
      "guarantee hard-safety overclaim",
      testClaim({
        claim_type: "recommendation",
        source_text: "Khuyến nghị này đảm bảo rằng kết quả sẽ đúng.",
      }),
      base,
      VALIDATION_STATUS.CONTRADICTED,
      REASON_CODE.GUARANTEE_OVERCLAIM,
      { exposure_status: "EXPOSED" },
      { exposure_status: "NOT_EXPOSED" },
    ),
  ];
}

function numericToleranceFixture(): OracleFixture {
  return fixture(
    "numeric tolerance match",
    numericTestClaim({ value: 93.344, unit: "percent", role: "prediction_score" }),
    testEvidence(),
    VALIDATION_STATUS.SUPPORTED,
    REASON_CODE.TOLERANCE_MATCH,
    {
      numeric_value: 0.9334399999999999,
      numeric_unit: "percent",
      numeric_role: "prediction_score",
      exposure_status: "EXPOSED",
    },
    {
      numeric_value: 0.9334,
      numeric_unit: "percent",
      numeric_role: "prediction_score",
      exposure_status: "EXPOSED",
    },
  );
}

function numericOutsideFixture(): OracleFixture {
  return fixture(
    "numeric outside tolerance",
    numericTestClaim({ value: 93.5, unit: "percent", role: "prediction_score" }),
    testEvidence(),
    VALIDATION_STATUS.CONTRADICTED,
    REASON_CODE.NUMERIC_OUTSIDE_TOLERANCE,
    {
      numeric_value: 0.935,
      numeric_unit: "percent",
      numeric_role: "prediction_score",
      exposure_status: "EXPOSED",
    },
    {
      numeric_value: 0.9334,
      numeric_unit: "percent",
      numeric_role: "prediction_score",
      exposure_status: "EXPOSED",
    },
  );
}

function rankingTieFixture(): OracleFixture {
  const tied: ClaimValidationFeatureEvidence[] = [
    {
      feature_id: "feature_a",
      shap_value: 0.2,
      abs_shap_value: 0.2,
      direction: "increases_risk",
      rank: 1,
    },
    {
      feature_id: "feature_b",
      shap_value: -0.2,
      abs_shap_value: 0.2,
      direction: "decreases_risk",
      rank: 1,
    },
  ];
  return fixture(
    "ranking tie",
    testClaim({ claim_type: "ranking", feature_id: "feature_a" }),
    testEvidence({ features: tied }),
    VALIDATION_STATUS.NOT_VERIFIABLE,
    REASON_CODE.RANK_TIE_AMBIGUOUS,
    { feature_id: "feature_a", rank: 1, exposure_status: "EXPOSED" },
    { feature_id: "feature_a", rank: 1, exposure_status: "EXPOSED" },
  );
}

function magnitudeFixture(): OracleFixture {
  const feature: ClaimValidationFeatureEvidence = {
    feature_id: "feature_a",
    shap_value: 0.2,
    abs_shap_value: 0.2,
    direction: "increases_risk",
    rank: 1,
    strength: "moderate",
  };
  return fixture(
    "magnitude overstated",
    testClaim({
      claim_type: "magnitude",
      feature_id: "feature_a",
      magnitude: "strong",
    }),
    testEvidence({ features: [feature] }),
    VALIDATION_STATUS.CONTRADICTED,
    REASON_CODE.MAGNITUDE_OVERSTATED,
    {
      feature_id: "feature_a",
      magnitude: "strong",
      exposure_status: "EXPOSED",
    },
    {
      feature_id: "feature_a",
      magnitude: "moderate",
      exposure_status: "EXPOSED",
    },
  );
}

function unsupportedMagnitudeFixture(): OracleFixture {
  return fixture(
    "magnitude target unsupported",
    testClaim({
      claim_type: "magnitude",
      feature_id: "missing",
      magnitude: "strong",
    }),
    testEvidence(),
    VALIDATION_STATUS.UNSUPPORTED,
    REASON_CODE.MAGNITUDE_UNSUPPORTED,
    {
      feature_id: "missing",
      magnitude: "strong",
      exposure_status: "EXPOSED",
    },
    { exposure_status: "NOT_EXPOSED" },
  );
}

function missingMagnitudeFixture(): OracleFixture {
  const feature: ClaimValidationFeatureEvidence = {
    feature_id: "feature_a",
    shap_value: 0.2,
    abs_shap_value: 0.2,
    direction: "increases_risk",
    rank: 1,
  };
  return fixture(
    "magnitude source missing",
    testClaim({
      claim_type: "magnitude",
      feature_id: "feature_a",
      magnitude: "strong",
    }),
    testEvidence({ features: [feature] }),
    VALIDATION_STATUS.NOT_VERIFIABLE,
    REASON_CODE.MAGNITUDE_SOURCE_MISSING,
    {
      feature_id: "feature_a",
      magnitude: "strong",
      exposure_status: "EXPOSED",
    },
    { exposure_status: "SOURCE_MISSING" },
  );
}

function fixture(
  name: string,
  claim: AtomicClaimRecord,
  evidence: ClaimValidationEvidencePackage,
  status: OracleFixture["status"],
  reason: ReasonCode,
  expected: FactSummary,
  observed: FactSummary,
): OracleFixture {
  return {
    name,
    claim,
    evidence,
    execution: EXECUTION_STATUS.SUCCESS,
    status,
    reason,
    expected,
    observed,
  };
}

function nonNullFacts(facts: ClaimValidationFactValues): FactSummary {
  return Object.fromEntries(
    Object.entries(facts).filter(([, value]) => value !== null),
  );
}
