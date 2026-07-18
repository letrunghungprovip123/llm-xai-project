import assert from "node:assert/strict";
import test from "node:test";

import {
  evaluateConfigurationGates,
  findParetoCandidateIds,
  findSupportingEvidenceKnee,
  pairedStratifiedNonInferiority,
  runThresholdSelection,
  wilsonInterval,
} from "../../research/llm/selection/index";
import type {
  ConfigurationCandidate,
  PairedQualityObservation,
} from "../../contracts/validation-selection";
import type { EvidenceLevel } from "../../contracts/llm-validation";

function candidate(
  id: string,
  level: EvidenceLevel,
  overrides: Partial<ConfigurationCandidate["observed_metrics"]> = {},
  usable = 36,
): ConfigurationCandidate {
  return {
    candidate_id: id,
    model_id: id.split("_")[0] ?? "model",
    evidence_level: level,
    planned_generation_count: 36,
    usable_generation_count: usable,
    schema_valid_generation_count: usable,
    contradicted_claim_count: 0,
    evaluable_claim_count: 360,
    causal_overclaim_count: 0,
    observed_metrics: {
      direction_accuracy: 0.98,
      unsupported_claim_rate: 0.02,
      weighted_faithfulness: 0.94,
      shap_mass_coverage: 0.85,
      policy_compliance: 0.99,
      language_compliance: 0.99,
      reliability: usable / 36,
      configuration_quality_point: 0.93,
      configuration_quality_lcb_95: 0.91,
      mean_input_tokens: 1000,
      mean_selected_evidence_count: 8,
      cost_per_faithful_generation: 0.02,
      p95_latency_ms: 3000,
      extractiveness_rate: 0.2,
      narrative_synthesis_score: 0.8,
      ...overrides,
    },
  };
}

function pairedObservations(
  candidateId: string,
  quality: number,
): PairedQualityObservation[] {
  return Array.from({ length: 12 }, (_, index) => ({
    candidate_id: candidateId,
    case_id: `case_${index + 1}`,
    selection_stratum: `stratum_${Math.floor(index / 2) + 1}`,
    quality,
  }));
}

test("36/36 observed success still has Wilson lower bound below one", () => {
  const interval = wilsonInterval(36, 36);
  assert.equal(interval.observed_rate, 1);
  assert.ok(interval.lower > 0.9 && interval.lower < 0.91);
});

test("configuration gate uses the planned denominator", () => {
  assert.equal(evaluateConfigurationGates(candidate("qwen_s2", "S2")).pass, true);
  const failed = evaluateConfigurationGates(candidate("phi_s2", "S2", {}, 35));
  assert.equal(failed.pass, false);
  assert.ok(failed.failed_gates.includes("USABLE_GENERATION_RATE"));
});

test("paired non-inferiority uses the one-sided upper bootstrap bound", () => {
  const observations = [
    ...pairedObservations("best", 0.95),
    ...pairedObservations("close", 0.94),
    ...pairedObservations("far", 0.86),
  ];
  const close = pairedStratifiedNonInferiority(observations, "best", "close");
  const far = pairedStratifiedNonInferiority(observations, "best", "far");
  assert.equal(close.non_inferior, true);
  assert.ok(close.upper_one_sided_bound_95 < 0.03);
  assert.equal(far.non_inferior, false);
});

test("Pareto filtering removes a candidate dominated on every complete metric", () => {
  const strong = candidate("qwen_s2", "S2");
  const weak = candidate("phi_s2", "S2", {
    configuration_quality_lcb_95: 0.8,
    reliability: 0.95,
    cost_per_faithful_generation: 0.04,
    p95_latency_ms: 5000,
    mean_input_tokens: 1400,
    extractiveness_rate: 0.3,
  });
  assert.deepEqual(findParetoCandidateIds([strong, weak]), ["qwen_s2"]);
});

test("selection chooses lower evidence among hard-safe non-inferior Pareto candidates", () => {
  const s2 = candidate("qwen_s2", "S2", {
    configuration_quality_point: 0.93,
    configuration_quality_lcb_95: 0.92,
    mean_input_tokens: 800,
  });
  const s3 = candidate("qwen_s3", "S3", {
    configuration_quality_point: 0.94,
    configuration_quality_lcb_95: 0.93,
    mean_input_tokens: 1100,
  });
  const s5 = candidate("qwen_s5", "S5", {
    configuration_quality_lcb_95: 0.935,
  });
  const observations = [
    ...pairedObservations("qwen_s2", 0.93),
    ...pairedObservations("qwen_s3", 0.94),
  ];
  const result = runThresholdSelection([s2, s3, s5], observations);
  assert.equal(result.decision.status, "SELECTED");
  assert.equal(result.decision.selected_candidate_id, "qwen_s2");
  assert.equal(result.decision.s5_fallback_candidate_id, "qwen_s5");
});

test("knee uses actual token burden for S1-S4 and is supporting evidence only", () => {
  const points = [
    candidate("qwen_s1", "S1", { mean_input_tokens: 100, configuration_quality_lcb_95: 0.6 }),
    candidate("qwen_s2", "S2", { mean_input_tokens: 200, configuration_quality_lcb_95: 0.8 }),
    candidate("qwen_s3", "S3", { mean_input_tokens: 400, configuration_quality_lcb_95: 0.86 }),
    candidate("qwen_s4", "S4", { mean_input_tokens: 800, configuration_quality_lcb_95: 0.88 }),
  ];
  const knee = findSupportingEvidenceKnee(points, "qwen");
  assert.equal(knee?.evidence_level, "S2");
  assert.equal(knee?.role, "SUPPORTING_EVIDENCE_ONLY");
});
