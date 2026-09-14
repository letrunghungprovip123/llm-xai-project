import assert from "node:assert/strict";
import test from "node:test";

import {
  assertNumericTolerancePolicy,
  normalizeNumericUnit,
  numericRuleFor,
  NUMERIC_TOLERANCE_POLICY,
} from "../../../research/ts/claim_validation/numericPolicy";

test("numeric tolerance policy v1 is strict and covers every numeric role", () => {
  assert.doesNotThrow(() => assertNumericTolerancePolicy());
  assert.equal(NUMERIC_TOLERANCE_POLICY.rules.length, 8);
  assert.equal(
    NUMERIC_TOLERANCE_POLICY.unknown_role_behavior,
    "NOT_VERIFIABLE",
  );
});

test("percent and probability formatting use half the displayed unit", () => {
  const percent = numericRuleFor("prediction_score", "%");
  assert.equal(percent.normalization, "PERCENT_TO_UNIT_INTERVAL");
  assert.equal(percent.comparison_mode, "HALF_DISPLAY_UNIT");
  assert.equal(percent.absolute_tolerance, 0.00005);

  const probability = numericRuleFor("decision_threshold", "rate_0_to_1");
  assert.equal(probability.normalization, "UNIT_INTERVAL_IDENTITY");
  assert.equal(probability.absolute_tolerance, 0.00005);
});

test("count and rank policies require exact integer equality", () => {
  const count = numericRuleFor("other", "counts");
  assert.equal(count.normalization, "EXACT_INTEGER");
  assert.equal(count.comparison_mode, "EXACT");
  assert.equal(count.absolute_tolerance, 0);

  const rank = numericRuleFor("rank", "ordinal");
  assert.equal(rank.normalization, "EXACT_INTEGER");
  assert.equal(rank.comparison_mode, "EXACT");
});

test("untrusted feature and other numeric precision remains NOT_VERIFIABLE", () => {
  const feature = numericRuleFor("feature_value", null);
  assert.equal(feature.comparison_mode, "NOT_VERIFIABLE");
  assert.equal(feature.absolute_tolerance, null);

  const otherPercent = numericRuleFor("other", "percent");
  assert.equal(otherPercent.comparison_mode, "NOT_VERIFIABLE");
  assert.equal(otherPercent.relative_tolerance, null);
});

test("numeric unit aliases normalize deterministically", () => {
  assert.equal(normalizeNumericUnit("%"), "percent");
  assert.equal(normalizeNumericUnit("phần trăm"), "percent");
  assert.equal(normalizeNumericUnit("probability_0_to_1"), "probability");
  assert.equal(normalizeNumericUnit("integer"), "count");
  assert.equal(normalizeNumericUnit(null), "unitless");
});

test("numeric tolerance policy rejects semantic configuration hazards", () => {
  const duplicate = structuredClone(NUMERIC_TOLERANCE_POLICY);
  duplicate.rules.push(structuredClone(duplicate.rules[0]));
  assert.throws(
    () => assertNumericTolerancePolicy(duplicate),
    /unique role\/unit/u,
  );

  const unverifiableTolerance = structuredClone(NUMERIC_TOLERANCE_POLICY);
  const unverifiable = unverifiableTolerance.rules.find(
    (rule) => rule.comparison_mode === "NOT_VERIFIABLE",
  )!;
  unverifiable.absolute_tolerance = 0.1;
  assert.throws(
    () => assertNumericTolerancePolicy(unverifiableTolerance),
    /cannot define tolerance/u,
  );

  const exactTolerance = structuredClone(NUMERIC_TOLERANCE_POLICY);
  const exact = exactTolerance.rules.find(
    (rule) => rule.comparison_mode === "EXACT",
  )!;
  exact.absolute_tolerance = 1;
  assert.throws(
    () => assertNumericTolerancePolicy(exactTolerance),
    /zero absolute tolerance/u,
  );

  const absoluteReference = structuredClone(NUMERIC_TOLERANCE_POLICY);
  absoluteReference.source_references[0].path = "/tmp/source.ts";
  assert.throws(
    () => assertNumericTolerancePolicy(absoluteReference),
    /Invalid numeric tolerance policy|project-relative/u,
  );
});
