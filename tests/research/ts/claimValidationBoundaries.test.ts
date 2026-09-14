import assert from "node:assert/strict";
import test from "node:test";

import { REASON_CODE } from "../../../research/ts/claim_validation/constants";
import type { ClaimValidationFeatureEvidence } from "../../../research/ts/claim_validation/runtimeTypes";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";
import {
  numericTestClaim,
  testClaim,
  testEvidence,
} from "./claimValidationTestFixtures";
import { emptyClaimValidationFactValues } from "../../../research/ts/claim_validation/types";
import {
  buildEvidenceView,
  claimExposureState,
  compareDirection,
  conceptExposureState,
  featureExposureState,
  isCertaintyOverclaim,
  isGuaranteeOverclaim,
  normalizeEvidenceDirection,
} from "../../../research/ts/claim_validation/validators/shared";

test("direction epsilon boundary is exactly 1e-12", async (t) => {
  const cases: Array<{
    name: string;
    shap: number;
    exposedDirection: ClaimValidationFeatureEvidence["direction"];
    claimedDirection: "increase_risk" | "decrease_risk";
    reason: string;
  }> = [
    {
      name: "-1e-12 is neutral",
      shap: -1e-12,
      exposedDirection: "decreases_risk",
      claimedDirection: "decrease_risk",
      reason: REASON_CODE.DIRECTION_NEUTRAL,
    },
    {
      name: "just below -1e-12 is directional",
      shap: -1.000001e-12,
      exposedDirection: "decreases_risk",
      claimedDirection: "decrease_risk",
      reason: REASON_CODE.NORMALIZED_MATCH,
    },
    {
      name: "zero is neutral",
      shap: 0,
      exposedDirection: "increases_risk",
      claimedDirection: "increase_risk",
      reason: REASON_CODE.DIRECTION_NEUTRAL,
    },
    {
      name: "+1e-12 is neutral",
      shap: 1e-12,
      exposedDirection: "increases_risk",
      claimedDirection: "increase_risk",
      reason: REASON_CODE.DIRECTION_NEUTRAL,
    },
    {
      name: "just above +1e-12 is directional",
      shap: 1.000001e-12,
      exposedDirection: "increases_risk",
      claimedDirection: "increase_risk",
      reason: REASON_CODE.NORMALIZED_MATCH,
    },
  ];
  for (const item of cases) {
    await t.test(item.name, () => {
      const feature = featureAt(item.shap, item.exposedDirection);
      const claim = testClaim({
        claim_type: "feature_direction",
        feature_id: "feature_a",
        direction: item.claimedDirection,
      });
      const result = validateClaimDeterministically(
        claim,
        testEvidence({ features: [feature] }),
      );
      assert.equal(result.reasonCode, item.reason);
    });
  }
});

test("numeric tolerance boundary is exactly 0.00005", async (t) => {
  const cases: Array<[string, number, string]> = [
    ["delta zero", 0, REASON_CODE.NORMALIZED_MATCH],
    ["delta just below", 0.0000499, REASON_CODE.TOLERANCE_MATCH],
    ["delta exactly", 0.00005, REASON_CODE.TOLERANCE_MATCH],
    ["delta just above", 0.0000501, REASON_CODE.NUMERIC_OUTSIDE_TOLERANCE],
  ];
  for (const [name, delta, reason] of cases) {
    await t.test(name, () => {
      const claim = numericTestClaim({
        value: (0.5 + delta) * 100,
        unit: "percent",
        role: "prediction_score",
      });
      const result = validateClaimDeterministically(
        claim,
        testEvidence({ probability: 0.5 }),
      );
      assert.equal(result.reasonCode, reason);
    });
  }
});

test("numeric tolerance includes an exactly representable configured boundary", () => {
  const result = validateClaimDeterministically(
    numericTestClaim({
      value: 0.00005,
      unit: "probability",
      role: "prediction_score",
    }),
    testEvidence({ probability: 0 }),
  );
  assert.equal(result.reasonCode, REASON_CODE.TOLERANCE_MATCH);
  assert.equal(result.numericComparison?.difference, 0.00005);
  assert.equal(result.numericComparison?.tolerance, 0.00005);
});

test("S0 prohibits support for all hidden evidence families", () => {
  const claims = [
    testClaim({ claim_type: "feature_presence", feature_id: "feature_a", evidence_level: "S0" }),
    testClaim({ claim_type: "feature_direction", feature_id: "feature_a", direction: "increase_risk", evidence_level: "S0" }),
    testClaim({ claim_type: "concept_presence", concept_id: "concept_a", evidence_level: "S0" }),
    testClaim({ claim_type: "concept_direction", concept_id: "concept_a", direction: "increase_risk", evidence_level: "S0" }),
    testClaim({ claim_type: "ranking", feature_id: "feature_a", evidence_level: "S0" }),
    testClaim({ claim_type: "magnitude", feature_id: "feature_a", magnitude: "moderate", evidence_level: "S0" }),
  ];
  for (const claim of claims) {
    const result = validateClaimDeterministically(
      claim,
      testEvidence({ level: "S0" }),
    );
    assert.notEqual(result.reasonCode, REASON_CODE.EXACT_MATCH);
    assert.equal(result.observed.exposure_status, "NOT_EXPOSED");
  }
});

test("mixed and unknown exposed directions are not verifiable", () => {
  for (const direction of ["mixed", "unknown"] as const) {
    const result = validateClaimDeterministically(
      testClaim({
        claim_type: "feature_direction",
        feature_id: "feature_a",
        direction: "increase_risk",
      }),
      testEvidence({ features: [featureAt(0.2, direction)] }),
    );
    assert.equal(result.reasonCode, REASON_CODE.DIRECTION_MIXED_OR_UNKNOWN);
  }
});

test("numeric and ranking source branches fail closed deterministically", () => {
  const evidence = testEvidence();
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "numeric",
        numeric_value: null,
        numeric_role: null,
      }),
      evidence,
    ).reasonCode,
    REASON_CODE.NUMERIC_SOURCE_MISSING,
  );
  assert.equal(
    validateClaimDeterministically(
      numericTestClaim({
        value: 0.5,
        unit: "probability",
        role: "decision_threshold",
      }),
      {
        ...evidence,
        prompt_payload: {
          ...evidence.prompt_payload,
          prediction: {
            ...evidence.prompt_payload.prediction,
            threshold: null as unknown as number,
          },
        },
      },
    ).reasonCode,
    REASON_CODE.NUMERIC_SOURCE_MISSING,
  );
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "ranking",
        claim_subtype: "FEATURE_RANK",
        feature_id: null,
        concept_id: null,
      }),
      evidence,
    ).reasonCode,
    REASON_CODE.RANK_SOURCE_MISSING,
  );
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "ranking",
        claim_subtype: "FEATURE_RANK",
        feature_id: "missing",
      }),
      evidence,
    ).reasonCode,
    REASON_CODE.RANKING_UNSUPPORTED,
  );
  const tied = testEvidence({
    features: [
      featureAt(0.2, "increases_risk"),
      {
        ...featureAt(-0.2, "decreases_risk"),
        feature_id: "feature_b",
        rank: 2,
      },
    ],
  });
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "ranking",
        claim_subtype: "FEATURE_RANK",
        feature_id: "feature_a",
      }),
      tied,
    ).reasonCode,
    REASON_CODE.RANK_TIE_AMBIGUOUS,
  );
  assert.equal(
    validateClaimDeterministically(
      numericTestClaim({
        value: 1,
        unit: "rank",
        role: "rank",
        featureId: "feature_a",
      }),
      evidence,
    ).reasonCode,
    REASON_CODE.EXACT_MATCH,
  );
  assert.equal(
    validateClaimDeterministically(
      numericTestClaim({
        value: 2,
        unit: "rank",
        role: "rank",
        featureId: "feature_a",
      }),
      evidence,
    ).reasonCode,
    REASON_CODE.NUMERIC_EXACT_MISMATCH,
  );
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "ranking",
        claim_subtype: "CONCEPT_RANK",
        concept_id: "missing",
      }),
      evidence,
    ).reasonCode,
    REASON_CODE.RANKING_UNSUPPORTED,
  );
});

test("shared semantic helpers cover every exposure and wording boundary", () => {
  const evidence = testEvidence();
  evidence.prompt_payload.constraints.allowed_feature_ids = ["feature_a"];
  evidence.prompt_payload.constraints.allowed_concept_ids = [];
  const view = buildEvidenceView(evidence);
  assert.equal(featureExposureState(view, null), "SOURCE_MISSING");
  assert.equal(featureExposureState(view, "missing"), "NOT_EXPOSED");
  assert.equal(featureExposureState(view, "feature_a"), "EXPOSED_ALLOWED");
  assert.equal(featureExposureState(view, "feature_b"), "EXPOSED_FORBIDDEN");
  assert.equal(conceptExposureState(view, null), "SOURCE_MISSING");
  assert.equal(conceptExposureState(view, "missing"), "NOT_EXPOSED");
  assert.equal(conceptExposureState(view, "concept_a"), "EXPOSED_FORBIDDEN");
  assert.equal(
    claimExposureState(
      testClaim({ claim_type: "numeric", feature_id: null, concept_id: null }),
      view,
    ),
    "NOT_APPLICABLE",
  );
  assert.equal(
    claimExposureState(
      testClaim({ claim_type: "ranking", feature_id: null, concept_id: null }),
      view,
    ),
    "SOURCE_MISSING",
  );
  assert.deepEqual(normalizeEvidenceDirection("increases_risk"), {
    direction: "increase_risk",
    normalized: true,
  });
  assert.deepEqual(normalizeEvidenceDirection("not_a_direction"), {
    direction: "unknown",
    normalized: false,
  });
  assert.equal(isGuaranteeOverclaim("Không thể đảm bảo kết quả."), false);
  assert.equal(isGuaranteeOverclaim("Điều này guarantees that kết quả."), true);
  assert.equal(isCertaintyOverclaim("Không chắc chắn về kết quả."), false);
  assert.equal(isCertaintyOverclaim("Kết quả hoàn toàn chính xác."), true);

  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.direction = "unknown";
  observed.direction = "increase_risk";
  assert.equal(
    compareDirection(expected, observed, []).reasonCode,
    REASON_CODE.DIRECTION_MIXED_OR_UNKNOWN,
  );
});

function featureAt(
  shapValue: number,
  direction: ClaimValidationFeatureEvidence["direction"],
): ClaimValidationFeatureEvidence {
  return {
    feature_id: "feature_a",
    shap_value: shapValue,
    abs_shap_value: Math.abs(shapValue),
    direction,
    rank: 1,
    strength: "weak",
  };
}
