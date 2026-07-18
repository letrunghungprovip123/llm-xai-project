import type {
  ConfigurationCandidate,
  ConfigurationGateResult,
  FrozenSelectionPolicy,
  NonInferiorityResult,
  PairedQualityObservation,
  SelectionDecision,
  WilsonInterval,
} from "../../../contracts/validation-selection";
import type { EvidenceLevel } from "../../../contracts/llm-validation";
import { FROZEN_SELECTION_POLICY } from "./selectionPolicy";

const EVIDENCE_LEVEL_ORDER: Record<EvidenceLevel, number> = {
  S0: 0, S1: 1, S2: 2, S3: 3, S4: 4, S5: 5,
};

export type SelectionRunResult = {
  decision: SelectionDecision;
  gate_results: ConfigurationGateResult[];
  non_inferiority_results: NonInferiorityResult[];
};

export type EvidenceKneeResult = {
  model_id: string;
  candidate_id: string;
  evidence_level: EvidenceLevel;
  normalized_distance_above_chord: number;
  role: "SUPPORTING_EVIDENCE_ONLY";
};

// Wilson interval được báo cùng observed rate để tránh diễn giải 36/36 như population certainty.
export function wilsonInterval(
  numerator: number,
  denominator: number,
  z = 1.959963984540054,
): WilsonInterval {
  if (!Number.isInteger(numerator) || !Number.isInteger(denominator)) {
    throw new Error("Wilson numerator and denominator must be integers.");
  }
  if (denominator <= 0 || numerator < 0 || numerator > denominator) {
    throw new Error("Invalid Wilson numerator or denominator.");
  }
  const rate = numerator / denominator;
  const zSquared = z * z;
  const denominatorAdjustment = 1 + zSquared / denominator;
  const center = (rate + zSquared / (2 * denominator)) / denominatorAdjustment;
  const halfWidth =
    (z / denominatorAdjustment) *
    Math.sqrt(
      (rate * (1 - rate)) / denominator +
        zSquared / (4 * denominator * denominator),
    );
  return {
    observed_rate: rate,
    lower: Math.max(0, center - halfWidth),
    upper: Math.min(1, center + halfWidth),
    numerator,
    denominator,
  };
}

export function evaluateConfigurationGates(
  candidate: ConfigurationCandidate,
  policy: FrozenSelectionPolicy = FROZEN_SELECTION_POLICY,
): ConfigurationGateResult {
  if (candidate.planned_generation_count <= 0) {
    throw new Error(`${candidate.candidate_id} has no planned generations.`);
  }
  const gates = policy.configuration_hard_gates;
  const usableRate =
    candidate.usable_generation_count / candidate.planned_generation_count;
  const schemaRate =
    candidate.schema_valid_generation_count / candidate.planned_generation_count;
  const contradictionRate = safeRate(
    candidate.contradicted_claim_count,
    candidate.evaluable_claim_count,
  );
  const causalRate = safeRate(
    candidate.causal_overclaim_count,
    candidate.evaluable_claim_count,
  );
  const metrics = candidate.observed_metrics;
  const failed: string[] = [];

  if (usableRate < gates.minimum_observed_usable_generation_rate) {
    failed.push("USABLE_GENERATION_RATE");
  }
  if (schemaRate < gates.minimum_observed_schema_validity_rate) {
    failed.push("SCHEMA_VALIDITY_RATE");
  }
  if (contradictionRate > gates.maximum_contradicted_claim_rate) {
    failed.push("CONTRADICTED_CLAIM_RATE");
  }
  if (causalRate > gates.maximum_causal_overclaim_rate) {
    failed.push("CAUSAL_OVERCLAIM_RATE");
  }
  checkMinimum(metrics.direction_accuracy, gates.minimum_direction_accuracy, "DIRECTION_ACCURACY", failed);
  checkMaximum(metrics.unsupported_claim_rate, gates.maximum_unsupported_claim_rate, "UNSUPPORTED_CLAIM_RATE", failed);
  checkMinimum(metrics.weighted_faithfulness, gates.minimum_weighted_faithfulness, "WEIGHTED_FAITHFULNESS", failed);
  checkMinimum(metrics.shap_mass_coverage, gates.minimum_shap_mass_coverage, "SHAP_MASS_COVERAGE", failed);
  checkMinimum(metrics.policy_compliance, gates.minimum_policy_compliance, "POLICY_COMPLIANCE", failed);
  checkMinimum(metrics.language_compliance, gates.minimum_language_compliance, "LANGUAGE_COMPLIANCE", failed);

  return {
    candidate_id: candidate.candidate_id,
    pass: failed.length === 0,
    failed_gates: failed,
    wilson_intervals: {
      usable_generation_rate: wilsonInterval(
        candidate.usable_generation_count,
        candidate.planned_generation_count,
      ),
      schema_validity_rate: wilsonInterval(
        candidate.schema_valid_generation_count,
        candidate.planned_generation_count,
      ),
    },
  };
}

// Bootstrap resample case trong từng stratum và luôn giữ cặp best-candidate của cùng case.
export function pairedStratifiedNonInferiority(
  observations: PairedQualityObservation[],
  bestCandidateId: string,
  candidateId: string,
  policy: FrozenSelectionPolicy = FROZEN_SELECTION_POLICY,
): NonInferiorityResult {
  if (bestCandidateId === candidateId) {
    const caseCount = observations.filter(
      (item) => item.candidate_id === candidateId,
    ).length;
    return {
      best_candidate_id: bestCandidateId,
      candidate_id: candidateId,
      paired_case_count: caseCount,
      mean_best_minus_candidate: 0,
      lower_one_sided_bound_95: 0,
      upper_one_sided_bound_95: 0,
      bound_method: "paired_stratified_percentile_bootstrap",
      margin: policy.non_inferiority.margin,
      non_inferior: true,
    };
  }

  const bestByCase = buildObservationMap(observations, bestCandidateId);
  const candidateByCase = buildObservationMap(observations, candidateId);
  assertSameCaseSet(bestByCase, candidateByCase, bestCandidateId, candidateId);

  const differencesByStratum = new Map<string, number[]>();
  for (const [caseId, best] of bestByCase) {
    const candidate = candidateByCase.get(caseId)!;
    if (best.selection_stratum !== candidate.selection_stratum) {
      throw new Error(`Stratum mismatch for paired case ${caseId}.`);
    }
    const values = differencesByStratum.get(best.selection_stratum) ?? [];
    values.push(best.quality - candidate.quality);
    differencesByStratum.set(best.selection_stratum, values);
  }

  const allDifferences = [...differencesByStratum.values()].flat();
  const pointDifference = mean(allDifferences);
  const random = mulberry32(policy.paired_bootstrap.seed + hashString(candidateId));
  const bootstrapMeans: number[] = [];

  for (let iteration = 0; iteration < policy.paired_bootstrap.iterations; iteration += 1) {
    let sum = 0;
    let count = 0;
    for (const differences of differencesByStratum.values()) {
      for (let draw = 0; draw < differences.length; draw += 1) {
        const index = Math.floor(random() * differences.length);
        sum += differences[index] ?? 0;
        count += 1;
      }
    }
    bootstrapMeans.push(sum / count);
  }

  bootstrapMeans.sort((left, right) => left - right);
  const alpha = 1 - policy.paired_bootstrap.confidence;
  const lower = percentile(bootstrapMeans, alpha);
  const upper = percentile(bootstrapMeans, 1 - alpha);
  const margin = policy.non_inferiority.margin;

  return {
    best_candidate_id: bestCandidateId,
    candidate_id: candidateId,
    paired_case_count: allDifferences.length,
    mean_best_minus_candidate: pointDifference,
    lower_one_sided_bound_95: lower,
    upper_one_sided_bound_95: upper,
    bound_method: "paired_stratified_percentile_bootstrap",
    margin,
    non_inferior: upper <= margin,
  };
}

// Pareto chỉ cho phép domination khi mọi metric cần so sánh đều có dữ liệu ở cả hai bên.
export function findParetoCandidateIds(
  candidates: ConfigurationCandidate[],
): string[] {
  return candidates
    .filter(
      (candidate) =>
        !candidates.some(
          (other) =>
            other.candidate_id !== candidate.candidate_id &&
            dominates(other, candidate),
        ),
    )
    .map((candidate) => candidate.candidate_id)
    .sort();
}

export function findSupportingEvidenceKnee(
  candidates: ConfigurationCandidate[],
  modelId: string,
): EvidenceKneeResult | null {
  const levels = new Set<EvidenceLevel>(["S1", "S2", "S3", "S4"]);
  const points = candidates
    .filter(
      (candidate) => candidate.model_id === modelId && levels.has(candidate.evidence_level),
    )
    .map((candidate) => ({
      candidate,
      x: candidate.observed_metrics.mean_input_tokens,
      y: candidate.observed_metrics.configuration_quality_lcb_95,
    }));
  if (points.length !== 4 || points.some((point) => point.x === null || point.y === null)) {
    return null;
  }
  const complete = points as Array<{
    candidate: ConfigurationCandidate;
    x: number;
    y: number;
  }>;
  complete.sort((left, right) => left.x - right.x);
  if (new Set(complete.map((point) => point.x)).size !== complete.length) return null;

  const minX = complete[0]!.x;
  const maxX = complete[complete.length - 1]!.x;
  const minY = Math.min(...complete.map((point) => point.y));
  const maxY = Math.max(...complete.map((point) => point.y));
  if (maxX === minX || maxY === minY) return null;

  const scored = complete.map((point) => {
    const x = (point.x - minX) / (maxX - minX);
    const y = (point.y - minY) / (maxY - minY);
    return { point, distance: y - x };
  });
  scored.sort(
    (left, right) =>
      right.distance - left.distance ||
      EVIDENCE_LEVEL_ORDER[left.point.candidate.evidence_level] -
        EVIDENCE_LEVEL_ORDER[right.point.candidate.evidence_level],
  );
  const winner = scored[0]!;
  return {
    model_id: modelId,
    candidate_id: winner.point.candidate.candidate_id,
    evidence_level: winner.point.candidate.evidence_level,
    normalized_distance_above_chord: winner.distance,
    role: "SUPPORTING_EVIDENCE_ONLY",
  };
}

// Orchestrator áp dụng tuần tự; không hợp nhất risk, statistics và knee thành một số threshold.
export function runThresholdSelection(
  candidates: ConfigurationCandidate[],
  observations: PairedQualityObservation[],
  policy: FrozenSelectionPolicy = FROZEN_SELECTION_POLICY,
): SelectionRunResult {
  assertCandidateIdsUnique(candidates);
  const gateResults = candidates.map((candidate) =>
    evaluateConfigurationGates(candidate, policy),
  );
  const gateById = new Map(gateResults.map((result) => [result.candidate_id, result]));
  const defaultLevels = new Set(policy.minimum_sufficient_evidence.default_candidate_levels);
  const defaultCandidates = candidates.filter((candidate) =>
    defaultLevels.has(candidate.evidence_level),
  );
  const passingDefault = defaultCandidates.filter(
    (candidate) => gateById.get(candidate.candidate_id)?.pass,
  );
  const fallback = chooseBestFallback(candidates, gateById, policy);

  if (passingDefault.length === 0) {
    const lowestRisk = chooseLowestRisk(defaultCandidates);
    return {
      decision: {
        policy_version: policy.policy_version,
        status: "NO_CANDIDATE_PASSED_HARD_GATES",
        selected_candidate_id: null,
        lowest_risk_candidate_id: lowestRisk?.candidate_id ?? null,
        eligible_candidate_ids: [],
        pareto_candidate_ids: [],
        s5_fallback_candidate_id: fallback?.candidate_id ?? null,
        requires_human_review: true,
        reasons: [
          "No S1-S4 configuration passed every frozen configuration hard gate.",
          "Thresholds were not relaxed; lowest-risk output is analysis-only.",
        ],
      },
      gate_results: gateResults,
      non_inferiority_results: [],
    };
  }

  const best = chooseReferenceBest(passingDefault);
  const nonInferiority = passingDefault.map((candidate) =>
    pairedStratifiedNonInferiority(
      observations,
      best.candidate_id,
      candidate.candidate_id,
      policy,
    ),
  );
  const nonInferiorIds = new Set(
    nonInferiority
      .filter((result) => result.non_inferior)
      .map((result) => result.candidate_id),
  );
  const eligible = passingDefault.filter((candidate) =>
    nonInferiorIds.has(candidate.candidate_id),
  );
  const paretoIds = findParetoCandidateIds(eligible);
  const paretoSet = new Set(paretoIds);
  const selected = chooseLexicographically(
    eligible.filter((candidate) => paretoSet.has(candidate.candidate_id)),
  );

  return {
    decision: {
      policy_version: policy.policy_version,
      status: "SELECTED",
      selected_candidate_id: selected.candidate_id,
      lowest_risk_candidate_id: null,
      eligible_candidate_ids: eligible.map((candidate) => candidate.candidate_id).sort(),
      pareto_candidate_ids: paretoIds,
      s5_fallback_candidate_id: fallback?.candidate_id ?? null,
      requires_human_review: false,
      reasons: [
        "Selected only after frozen hard gates, paired non-inferiority and Pareto filtering.",
        "Final tie-break prioritizes the minimum sufficient evidence level before efficiency metrics.",
      ],
    },
    gate_results: gateResults,
    non_inferiority_results: nonInferiority,
  };
}

function chooseReferenceBest(
  candidates: ConfigurationCandidate[],
): ConfigurationCandidate {
  const complete = candidates.filter(
    (candidate) => candidate.observed_metrics.configuration_quality_lcb_95 !== null,
  );
  if (complete.length !== candidates.length) {
    throw new Error("Every hard-gate-passing candidate needs a quality LCB before selection.");
  }
  return [...complete].sort(
    (left, right) =>
      (right.observed_metrics.configuration_quality_lcb_95 ?? -Infinity) -
        (left.observed_metrics.configuration_quality_lcb_95 ?? -Infinity) ||
      right.observed_metrics.configuration_quality_point -
        left.observed_metrics.configuration_quality_point ||
      left.candidate_id.localeCompare(right.candidate_id),
  )[0]!;
}

function chooseBestFallback(
  candidates: ConfigurationCandidate[],
  gateById: Map<string, ConfigurationGateResult>,
  policy: FrozenSelectionPolicy,
): ConfigurationCandidate | null {
  const choices = candidates.filter(
    (candidate) =>
      candidate.evidence_level ===
        policy.minimum_sufficient_evidence.separate_fallback_level &&
      gateById.get(candidate.candidate_id)?.pass,
  );
  if (choices.length === 0) return null;
  return [...choices].sort(
    (left, right) =>
      nullableDescending(
        left.observed_metrics.configuration_quality_lcb_95,
        right.observed_metrics.configuration_quality_lcb_95,
      ) || left.candidate_id.localeCompare(right.candidate_id),
  )[0]!;
}

function chooseLowestRisk(
  candidates: ConfigurationCandidate[],
): ConfigurationCandidate | null {
  if (candidates.length === 0) return null;
  return [...candidates].sort((left, right) => {
    const leftContradiction = safeRate(left.contradicted_claim_count, left.evaluable_claim_count);
    const rightContradiction = safeRate(right.contradicted_claim_count, right.evaluable_claim_count);
    const leftCausal = safeRate(left.causal_overclaim_count, left.evaluable_claim_count);
    const rightCausal = safeRate(right.causal_overclaim_count, right.evaluable_claim_count);
    return (
      leftContradiction - rightContradiction ||
      leftCausal - rightCausal ||
      right.observed_metrics.reliability - left.observed_metrics.reliability ||
      nullableDescending(left.observed_metrics.weighted_faithfulness, right.observed_metrics.weighted_faithfulness) ||
      left.candidate_id.localeCompare(right.candidate_id)
    );
  })[0]!;
}

function chooseLexicographically(
  candidates: ConfigurationCandidate[],
): ConfigurationCandidate {
  if (candidates.length === 0) {
    throw new Error("No candidate remains after Pareto filtering.");
  }
  return [...candidates].sort(
    (left, right) =>
      EVIDENCE_LEVEL_ORDER[left.evidence_level] - EVIDENCE_LEVEL_ORDER[right.evidence_level] ||
      nullableAscending(left.observed_metrics.cost_per_faithful_generation, right.observed_metrics.cost_per_faithful_generation) ||
      nullableAscending(left.observed_metrics.p95_latency_ms, right.observed_metrics.p95_latency_ms) ||
      nullableAscending(left.observed_metrics.extractiveness_rate, right.observed_metrics.extractiveness_rate) ||
      nullableDescending(left.observed_metrics.narrative_synthesis_score, right.observed_metrics.narrative_synthesis_score) ||
      left.candidate_id.localeCompare(right.candidate_id),
  )[0]!;
}

function dominates(
  left: ConfigurationCandidate,
  right: ConfigurationCandidate,
): boolean {
  const comparisons: Array<[number | null, number | null, "max" | "min"]> = [
    [left.observed_metrics.configuration_quality_lcb_95, right.observed_metrics.configuration_quality_lcb_95, "max"],
    [left.observed_metrics.reliability, right.observed_metrics.reliability, "max"],
    [left.observed_metrics.cost_per_faithful_generation, right.observed_metrics.cost_per_faithful_generation, "min"],
    [left.observed_metrics.p95_latency_ms, right.observed_metrics.p95_latency_ms, "min"],
    [left.observed_metrics.mean_input_tokens, right.observed_metrics.mean_input_tokens, "min"],
    [left.observed_metrics.extractiveness_rate, right.observed_metrics.extractiveness_rate, "min"],
  ];
  if (comparisons.some(([a, b]) => a === null || b === null)) return false;
  const noWorse = comparisons.every(([a, b, direction]) =>
    direction === "max" ? (a as number) >= (b as number) : (a as number) <= (b as number),
  );
  const strictlyBetter = comparisons.some(([a, b, direction]) =>
    direction === "max" ? (a as number) > (b as number) : (a as number) < (b as number),
  );
  return noWorse && strictlyBetter;
}

function buildObservationMap(
  observations: PairedQualityObservation[],
  candidateId: string,
): Map<string, PairedQualityObservation> {
  const result = new Map<string, PairedQualityObservation>();
  for (const item of observations.filter((row) => row.candidate_id === candidateId)) {
    if (result.has(item.case_id)) {
      throw new Error(`Duplicate observation for ${candidateId}, case ${item.case_id}.`);
    }
    if (item.quality < 0 || item.quality > 1) {
      throw new Error(`Quality outside [0,1] for ${candidateId}, case ${item.case_id}.`);
    }
    result.set(item.case_id, item);
  }
  if (result.size === 0) throw new Error(`No observations for ${candidateId}.`);
  return result;
}

function assertSameCaseSet(
  left: Map<string, PairedQualityObservation>,
  right: Map<string, PairedQualityObservation>,
  leftId: string,
  rightId: string,
): void {
  if (left.size !== right.size || [...left.keys()].some((key) => !right.has(key))) {
    throw new Error(`Paired case set mismatch between ${leftId} and ${rightId}.`);
  }
}

function checkMinimum(
  value: number | null,
  threshold: number,
  code: string,
  failures: string[],
): void {
  if (value === null || value < threshold) failures.push(code);
}

function checkMaximum(
  value: number | null,
  threshold: number,
  code: string,
  failures: string[],
): void {
  if (value === null || value > threshold) failures.push(code);
}

function safeRate(numerator: number, denominator: number): number {
  return denominator > 0 ? numerator / denominator : Number.POSITIVE_INFINITY;
}

function mean(values: number[]): number {
  if (values.length === 0) throw new Error("Cannot average an empty array.");
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function percentile(sorted: number[], probability: number): number {
  if (sorted.length === 0) throw new Error("Cannot take percentile of an empty array.");
  const position = probability * (sorted.length - 1);
  const lowerIndex = Math.floor(position);
  const upperIndex = Math.ceil(position);
  const lower = sorted[lowerIndex]!;
  const upper = sorted[upperIndex]!;
  return lower + (upper - lower) * (position - lowerIndex);
}

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function hashString(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function nullableAscending(left: number | null, right: number | null): number {
  if (left === null && right === null) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  return left - right;
}

function nullableDescending(left: number | null, right: number | null): number {
  if (left === null && right === null) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  return right - left;
}

function assertCandidateIdsUnique(candidates: ConfigurationCandidate[]): void {
  const ids = candidates.map((candidate) => candidate.candidate_id);
  if (new Set(ids).size !== ids.length) {
    throw new Error("Configuration candidate IDs must be unique.");
  }
}
