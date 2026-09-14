import assert from "node:assert/strict";
import test from "node:test";

import { REASON_CODE } from "../../../research/ts/claim_validation/constants";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";
import {
  testClaim,
  testEvidence,
} from "./claimValidationTestFixtures";

test("prediction subtypes use their own deterministic sources", () => {
  const evidence = testEvidence();
  const matchingLabel = validateClaimDeterministically(
    testClaim({
      claim_type: "prediction",
      claim_subtype: "OVERALL_LABEL",
      direction: "increase_risk",
    }),
    evidence,
  );
  assert.equal(matchingLabel.reasonCode, REASON_CODE.EXACT_MATCH);

  const mismatchingLabel = validateClaimDeterministically(
    testClaim({
      claim_type: "prediction",
      claim_subtype: "OVERALL_LABEL",
      direction: "decrease_risk",
    }),
    evidence,
  );
  assert.equal(
    mismatchingLabel.reasonCode,
    REASON_CODE.PREDICTION_LABEL_MISMATCH,
  );

  const probability = validateClaimDeterministically(
    testClaim({
      claim_type: "prediction",
      claim_subtype: "OVERALL_PROBABILITY",
      source_text: "Xác suất dự đoán là 93.34%.",
    }),
    evidence,
  );
  assert.equal(probability.reasonCode, REASON_CODE.NORMALIZED_MATCH);
  assert.equal(probability.expected.probability, 0.9334);
  assert.equal(probability.observed.probability, 0.9334);

  const threshold = validateClaimDeterministically(
    testClaim({
      claim_type: "prediction",
      claim_subtype: "THRESHOLD_COMPARISON",
      direction: "increase_risk",
    }),
    evidence,
  );
  assert.equal(threshold.reasonCode, REASON_CODE.EXACT_MATCH);

  const mismatch = validateClaimDeterministically(
    testClaim({
      claim_type: "prediction",
      claim_subtype: "THRESHOLD_COMPARISON",
      direction: "decrease_risk",
    }),
    evidence,
  );
  assert.equal(
    mismatch.reasonCode,
    REASON_CODE.PREDICTION_THRESHOLD_MISMATCH,
  );

  const factor = validateClaimDeterministically(
    testClaim({
      claim_type: "feature_direction",
      claim_subtype: "FEATURE_RISK_DIRECTION",
      feature_id: "feature_a",
      subject_type: "feature",
      direction: "increase_risk",
      source_section: "safe_summary",
    }),
    evidence,
  );
  assert.equal(factor.reasonCode, REASON_CODE.NORMALIZED_MATCH);
  assert.equal(factor.expected.prediction_label, null);
});

test("prediction routing fails closed for missing, ambiguous and prohibited sources", () => {
  const missingLabelEvidence = testEvidence();
  missingLabelEvidence.prompt_payload.prediction.predicted_label = "";
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "prediction",
        claim_subtype: "OVERALL_LABEL",
        direction: "increase_risk",
      }),
      missingLabelEvidence,
    ).reasonCode,
    REASON_CODE.PREDICTION_VALUE_UNAVAILABLE,
  );
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "prediction",
        claim_subtype: "OVERALL_LABEL",
        direction: "unknown",
      }),
      testEvidence(),
    ).reasonCode,
    REASON_CODE.PREDICTION_VALUE_UNAVAILABLE,
  );
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "prediction",
        claim_subtype: "OVERALL_PROBABILITY",
        source_text: "Không có phần trăm.",
      }),
      testEvidence(),
    ).reasonCode,
    REASON_CODE.SEMANTIC_SOURCE_UNFROZEN,
  );
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "prediction",
        claim_subtype: "OVERALL_PROBABILITY",
        source_text: "Xác suất 93,341%.",
      }),
      testEvidence(),
    ).reasonCode,
    REASON_CODE.TOLERANCE_MATCH,
  );
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "prediction",
        claim_subtype: "OVERALL_PROBABILITY",
        source_text: "Xác suất 12%.",
      }),
      testEvidence(),
    ).reasonCode,
    REASON_CODE.PREDICTION_PROBABILITY_MISMATCH,
  );
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "prediction",
        claim_subtype: "THRESHOLD_COMPARISON",
        direction: "unknown",
      }),
      testEvidence(),
    ).reasonCode,
    REASON_CODE.PREDICTION_VALUE_UNAVAILABLE,
  );
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "prediction",
        claim_subtype: "OVERALL_LABEL",
        certainty: "deterministic",
        source_text: "Mô hình đảm bảo rằng kết quả này đúng.",
      }),
      testEvidence(),
    ).reasonCode,
    REASON_CODE.GUARANTEE_OVERCLAIM,
  );
});

test("uncertainty subtypes map to exact sources without broad grounding", () => {
  const evidence = testEvidence();
  evidence.prompt_payload.constraints.claim_policy.allow_true_label_claim =
    false;
  evidence.prompt_payload.constraints.claim_policy
    .allow_absolute_decision_claim = false;
  evidence.prompt_payload.narrative_policy
    .must_include_partial_evidence_note = true;

  for (const subtype of [
    "PROBABILITY_HEDGE",
    "MODEL_PREDICTION_NOT_OUTCOME",
    "NO_GUARANTEE",
    "EVIDENCE_SCOPE_UNCERTAINTY",
  ] as const) {
    const decision = validateClaimDeterministically(
      testClaim({
        claim_type: "uncertainty",
        claim_subtype: subtype,
        certainty: "hedged",
      }),
      evidence,
    );
    assert.equal(decision.reasonCode, REASON_CODE.EXACT_MATCH, subtype);
  }

  const mismatch = validateClaimDeterministically(
    testClaim({
      claim_type: "uncertainty",
      claim_subtype: "PROBABILITY_HEDGE",
      certainty: "deterministic",
      source_text: "Có độ không chắc chắn nhất định.",
    }),
    evidence,
  );
  assert.equal(mismatch.reasonCode, REASON_CODE.UNCERTAINTY_NOT_GROUNDED);
  assert.notEqual(mismatch.expected.certainty, mismatch.observed.certainty);

  const confidence = validateClaimDeterministically(
    testClaim({
      claim_type: "uncertainty",
      claim_subtype: "CONFIDENCE_STRENGTH",
      certainty: "hedged",
    }),
    evidence,
  );
  assert.equal(confidence.reasonCode, REASON_CODE.SEMANTIC_SOURCE_UNFROZEN);
  assert.equal(confidence.validationCoverage, "SEMANTIC_REQUIRED");
});

test("distributed-evidence subtypes inspect the asserted scope", () => {
  const evidence = testEvidence();
  evidence.prompt_payload.narrative_policy
    .must_include_distributed_evidence_note = true;
  const exactSubtypes = [
    "MULTIPLE_FEATURES",
    "MIXED_DIRECTIONS",
    "DISTRIBUTED_SHAP_MASS",
  ] as const;
  for (const subtype of exactSubtypes) {
    const decision = validateClaimDeterministically(
      testClaim({
        claim_type: "distributed_evidence",
        claim_subtype: subtype,
      }),
      evidence,
    );
    assert.equal(decision.reasonCode, REASON_CODE.EXACT_MATCH, subtype);
  }

  const multipleConcepts = validateClaimDeterministically(
    testClaim({
      claim_type: "distributed_evidence",
      claim_subtype: "MULTIPLE_CONCEPTS",
    }),
    evidence,
  );
  assert.equal(
    multipleConcepts.reasonCode,
    REASON_CODE.POLICY_RULE_NOT_APPLICABLE,
  );

  const synthesis = validateClaimDeterministically(
    testClaim({
      claim_type: "distributed_evidence",
      claim_subtype: "CROSS_SECTION_SYNTHESIS",
    }),
    evidence,
  );
  assert.equal(synthesis.reasonCode, REASON_CODE.SEMANTIC_SOURCE_UNFROZEN);
  assert.deepEqual(synthesis.unresolvedFacts, ["distributed_evidence_scope"]);
});

test("limitation subtypes cannot borrow unrelated policy flags", () => {
  const evidence = testEvidence();
  const payload = evidence.prompt_payload;
  payload.constraints.claim_policy.allow_causal_claim = false;
  payload.constraints.claim_policy.allow_financial_advice = false;
  payload.constraints.claim_policy.allow_absolute_decision_claim = false;
  payload.constraints.claim_policy.allow_true_label_claim = false;
  payload.narrative_policy.must_include_partial_evidence_note = true;
  payload.narrative_policy.must_include_uncertainty = true;

  for (const subtype of [
    "NON_CAUSAL",
    "NOT_FINANCIAL_ADVICE",
    "NOT_SOLE_DECISION_BASIS",
    "INCOMPLETE_EVIDENCE",
    "MODEL_NOT_CERTAIN",
  ] as const) {
    const decision = validateClaimDeterministically(
      testClaim({ claim_type: "limitation", claim_subtype: subtype }),
      evidence,
    );
    assert.equal(decision.reasonCode, REASON_CODE.EXACT_MATCH, subtype);
  }

  payload.narrative_policy.must_include_partial_evidence_note = false;
  payload.narrative_policy.must_not_claim_evidence_is_complete = false;
  const unrelated = validateClaimDeterministically(
    testClaim({
      claim_type: "limitation",
      claim_subtype: "INCOMPLETE_EVIDENCE",
    }),
    evidence,
  );
  assert.equal(
    unrelated.reasonCode,
    REASON_CODE.POLICY_RULE_NOT_APPLICABLE,
  );

  payload.constraints.forbidden_rule_ids = [];
  payload.constraints.claim_policy.allow_causal_claim = true;
  const causalAllowed = validateClaimDeterministically(
    testClaim({
      claim_type: "limitation",
      claim_subtype: "NON_CAUSAL",
    }),
    evidence,
  );
  assert.equal(
    causalAllowed.reasonCode,
    REASON_CODE.POLICY_RULE_NOT_APPLICABLE,
  );
});

test("recommendation separates semantic support from policy compliance", () => {
  const evidence = testEvidence({ allowFinancialAdvice: false });
  const caution = validateClaimDeterministically(
    testClaim({
      claim_type: "recommendation",
      claim_subtype: "CAUTION_IN_DECISION_USE",
    }),
    evidence,
  );
  assert.equal(caution.reasonCode, REASON_CODE.SEMANTIC_SOURCE_UNFROZEN);
  assert.equal(caution.policyStatus, "COMPLIANT");
  assert.equal(caution.validationCoverage, "SEMANTIC_REQUIRED");

  const prescriptive = validateClaimDeterministically(
    testClaim({
      claim_type: "recommendation",
      claim_subtype: "PRESCRIPTIVE_FINANCIAL_ACTION",
    }),
    evidence,
  );
  assert.equal(prescriptive.reasonCode, REASON_CODE.SEMANTIC_SOURCE_UNFROZEN);
  assert.equal(prescriptive.policyStatus, "VIOLATION");
  assert.ok(
    prescriptive.reasonCodes.includes(REASON_CODE.UNSUPPORTED_RECOMMENDATION),
  );
});


test("unresolved semantic subtypes fail closed", () => {
  const claims = [
    testClaim({
      claim_type: "prediction",
      claim_subtype: "UNRESOLVED_PREDICTION",
    }),
    testClaim({
      claim_type: "magnitude",
      claim_subtype: "UNRESOLVED_MAGNITUDE",
    }),
    testClaim({
      claim_type: "uncertainty",
      claim_subtype: "UNRESOLVED_UNCERTAINTY",
    }),
    testClaim({
      claim_type: "distributed_evidence",
      claim_subtype: "UNRESOLVED_DISTRIBUTED_EVIDENCE",
    }),
    testClaim({
      claim_type: "recommendation",
      claim_subtype: "UNRESOLVED_RECOMMENDATION",
    }),
    testClaim({
      claim_type: "limitation",
      claim_subtype: "UNRESOLVED_LIMITATION",
    }),
  ];

  for (const claim of claims) {
    const result = validateClaimDeterministically(
      claim,
      testEvidence(),
    );
    assert.equal(
      result.reasonCode,
      REASON_CODE.SEMANTIC_SUBTYPE_UNRESOLVED,
      `${claim.claim_type}/${claim.claim_subtype}`,
    );
    assert.equal(result.policyStatus, "NOT_APPLICABLE");
    assert.equal(result.validationCoverage, "SEMANTIC_REQUIRED");
    assert.deepEqual(
      result.unresolvedFacts,
      [`claim_subtype:${claim.claim_type}`],
    );
  }
});

test("magnitude distinguishes match, overstatement and understatement", () => {
  const evidence = testEvidence();
  const evaluate = (
    magnitude: "weak" | "moderate" | "strong",
    subtype: "FEATURE_STRENGTH" | "COMPARATIVE_STRENGTH" =
      "FEATURE_STRENGTH",
  ) =>
    validateClaimDeterministically(
      testClaim({
        claim_type: "magnitude",
        claim_subtype: subtype,
        feature_id: subtype === "FEATURE_STRENGTH" ? "feature_a" : null,
        magnitude,
      }),
      evidence,
    );

  assert.equal(evaluate("moderate").reasonCode, REASON_CODE.MAGNITUDE_MATCH);
  assert.equal(
    evaluate("strong").reasonCode,
    REASON_CODE.MAGNITUDE_OVERSTATED,
  );
  assert.equal(
    evaluate("weak").reasonCode,
    REASON_CODE.MAGNITUDE_UNDERSTATED,
  );
  assert.equal(
    evaluate("strong", "COMPARATIVE_STRENGTH").reasonCode,
    REASON_CODE.MAGNITUDE_SEMANTICS_UNSUPPORTED,
  );
  assert.equal(
    validateClaimDeterministically(
      testClaim({
        claim_type: "magnitude",
        claim_subtype: "FEATURE_STRENGTH",
        feature_id: "missing",
        subject_type: "feature",
        magnitude: "strong",
      }),
      evidence,
    ).reasonCode,
    REASON_CODE.MAGNITUDE_UNSUPPORTED,
  );
});
