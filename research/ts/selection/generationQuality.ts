import type {
  FrozenSelectionPolicy,
  GenerationQualityInput,
  GenerationQualityResult,
  QualityMetricName,
} from "../../../contracts/validation-selection";
import { FROZEN_SELECTION_POLICY } from "./selectionPolicy";

// Geometric mean khiến một metric rất thấp kéo chất lượng xuống thay vì bị metric khác bù tuyến tính.
export function calculateGenerationQuality(
  input: GenerationQualityInput,
  policy: FrozenSelectionPolicy = FROZEN_SELECTION_POLICY,
): GenerationQualityResult {
  const failures: string[] = [];
  if (!input.usable_output) failures.push("USABLE_OUTPUT_FAILED");
  if (!input.schema_valid) failures.push("SCHEMA_VALID_FAILED");
  if (
    input.contradicted_claim_count >
    policy.generation_quality.hard_gates.maximum_contradicted_claim_count
  ) {
    failures.push("CONTRADICTED_CLAIM_GATE_FAILED");
  }
  if (
    input.causal_overclaim_count >
    policy.generation_quality.hard_gates.maximum_causal_overclaim_count
  ) {
    failures.push("CAUSAL_OVERCLAIM_GATE_FAILED");
  }

  const hardGatePass = failures.length === 0;
  if (!hardGatePass) {
    return {
      ...input,
      hard_gate_pass: false,
      hard_gate_failures: failures,
      generation_quality: policy.generation_quality.hard_gate_failure_score,
      applied_weight_sum: 0,
      excluded_metrics: findNullMetrics(input.metrics),
    };
  }

  let weightedLogSum = 0;
  let appliedWeightSum = 0;
  const excludedMetrics: QualityMetricName[] = [];
  let hasZeroMetric = false;

  for (const [metricName, weight] of Object.entries(
    policy.generation_quality.soft_metric_weights,
  ) as Array<[QualityMetricName, number]>) {
    const value = input.metrics[metricName];
    if (value === null) {
      excludedMetrics.push(metricName);
      continue;
    }
    assertUnitInterval(value, metricName);
    appliedWeightSum += weight;
    if (value === 0) {
      hasZeroMetric = true;
    } else {
      weightedLogSum += weight * Math.log(value);
    }
  }

  const quality =
    appliedWeightSum === 0 || hasZeroMetric
      ? 0
      : Math.exp(weightedLogSum / appliedWeightSum);

  return {
    ...input,
    hard_gate_pass: true,
    hard_gate_failures: [],
    generation_quality: quality,
    applied_weight_sum: appliedWeightSum,
    excluded_metrics: excludedMetrics,
  };
}

function findNullMetrics(
  metrics: GenerationQualityInput["metrics"],
): QualityMetricName[] {
  return (Object.entries(metrics) as Array<[QualityMetricName, number | null]>)
    .filter(([, value]) => value === null)
    .map(([name]) => name);
}

function assertUnitInterval(value: number, metricName: string): void {
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    throw new Error(`${metricName} must be between 0 and 1; found ${value}.`);
  }
}

