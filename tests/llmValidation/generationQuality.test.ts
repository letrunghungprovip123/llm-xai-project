import assert from "node:assert/strict";
import test from "node:test";

import {
  calculateGenerationQuality,
  calibratedAcceptProbability,
  shouldAcceptAtRuntime,
} from "../../research/llm/selection/index";
import type { GenerationQualityInput } from "../../contracts/validation-selection";

function qualityInput(
  overrides: Partial<GenerationQualityInput> = {},
): GenerationQualityInput {
  return {
    generation_id: "generation_1",
    model_id: "qwen3_8b",
    case_id: "case_1",
    selection_stratum: "near_threshold",
    evidence_level: "S2",
    usable_output: true,
    schema_valid: true,
    contradicted_claim_count: 0,
    causal_overclaim_count: 0,
    metrics: {
      faithfulness: 0.81,
      direction: 0.9,
      shap_coverage: null,
      policy: null,
      narrative: null,
      language: null,
    },
    ...overrides,
  };
}

test("generation quality renormalizes weights when metrics are not applicable", () => {
  const result = calculateGenerationQuality(qualityInput());
  const expected = Math.exp((0.3 * Math.log(0.81) + 0.25 * Math.log(0.9)) / 0.55);
  assert.ok(Math.abs(result.generation_quality - expected) < 1e-12);
  assert.equal(result.applied_weight_sum, 0.55);
  assert.deepEqual(result.excluded_metrics.sort(), ["language", "narrative", "policy", "shap_coverage"]);
});

test("a hard-gate failure always makes generation quality zero", () => {
  const result = calculateGenerationQuality(
    qualityInput({ contradicted_claim_count: 1 }),
  );
  assert.equal(result.hard_gate_pass, false);
  assert.equal(result.generation_quality, 0);
});

test("runtime acceptance uses calibrated probability and still requires hard gate", () => {
  const probability = calibratedAcceptProbability(0.9, -5, 10);
  assert.ok(probability > 0.9);
  assert.equal(
    shouldAcceptAtRuntime({
      hardGatePass: true,
      calibratedAcceptProbability: probability,
    }),
    true,
  );
  assert.equal(
    shouldAcceptAtRuntime({
      hardGatePass: false,
      calibratedAcceptProbability: 0.999,
    }),
    false,
  );
});
