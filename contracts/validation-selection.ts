import type { EvidenceLevel } from "./llm-validation";

export const QUALITY_METRIC_NAMES = [
  "faithfulness",
  "direction",
  "shap_coverage",
  "policy",
  "narrative",
  "language",
] as const;

export type QualityMetricName = (typeof QUALITY_METRIC_NAMES)[number];

export type GenerationQualityInput = {
  generation_id: string;
  model_id: string;
  case_id: string;
  selection_stratum: string;
  evidence_level: EvidenceLevel;
  usable_output: boolean;
  schema_valid: boolean;
  contradicted_claim_count: number;
  causal_overclaim_count: number;
  metrics: Record<QualityMetricName, number | null>;
};

export type GenerationQualityResult = GenerationQualityInput & {
  hard_gate_pass: boolean;
  hard_gate_failures: string[];
  generation_quality: number;
  applied_weight_sum: number;
  excluded_metrics: QualityMetricName[];
};

export type ConfigurationCandidate = {
  candidate_id: string;
  model_id: string;
  evidence_level: EvidenceLevel;
  planned_generation_count: number;
  usable_generation_count: number;
  schema_valid_generation_count: number;
  contradicted_claim_count: number;
  evaluable_claim_count: number;
  causal_overclaim_count: number;
  observed_metrics: {
    direction_accuracy: number | null;
    unsupported_claim_rate: number | null;
    weighted_faithfulness: number | null;
    shap_mass_coverage: number | null;
    policy_compliance: number | null;
    language_compliance: number | null;
    reliability: number;
    configuration_quality_point: number;
    configuration_quality_lcb_95: number | null;
    mean_input_tokens: number | null;
    mean_selected_evidence_count: number | null;
    cost_per_faithful_generation: number | null;
    p95_latency_ms: number | null;
    extractiveness_rate: number | null;
    narrative_synthesis_score: number | null;
  };
};

export type WilsonInterval = {
  observed_rate: number;
  lower: number;
  upper: number;
  numerator: number;
  denominator: number;
};

export type ConfigurationGateResult = {
  candidate_id: string;
  pass: boolean;
  failed_gates: string[];
  wilson_intervals: {
    usable_generation_rate: WilsonInterval;
    schema_validity_rate: WilsonInterval;
  };
};

export type PairedQualityObservation = {
  candidate_id: string;
  case_id: string;
  selection_stratum: string;
  quality: number;
};

export type NonInferiorityResult = {
  best_candidate_id: string;
  candidate_id: string;
  paired_case_count: number;
  mean_best_minus_candidate: number;
  lower_one_sided_bound_95: number;
  upper_one_sided_bound_95: number;
  bound_method: "paired_stratified_percentile_bootstrap";
  margin: number;
  non_inferior: boolean;
};

export type SelectionDecision = {
  policy_version: string;
  status: "SELECTED" | "NO_CANDIDATE_PASSED_HARD_GATES";
  selected_candidate_id: string | null;
  lowest_risk_candidate_id: string | null;
  eligible_candidate_ids: string[];
  pareto_candidate_ids: string[];
  s5_fallback_candidate_id: string | null;
  requires_human_review: boolean;
  reasons: string[];
};

export type FrozenSelectionPolicy = {
  policy_name: string;
  policy_version: string;
  status: string;
  generation_quality: {
    hard_gates: {
      usable_output: boolean;
      schema_valid: boolean;
      maximum_contradicted_claim_count: number;
      maximum_causal_overclaim_count: number;
    };
    soft_metric_weights: Record<QualityMetricName, number>;
    combination: "weighted_geometric_mean";
    null_metric_rule: "exclude_and_renormalize_weights";
    hard_gate_failure_score: number;
  };
  configuration_hard_gates: {
    minimum_observed_usable_generation_rate: number;
    minimum_observed_schema_validity_rate: number;
    maximum_contradicted_claim_rate: number;
    maximum_causal_overclaim_rate: number;
    minimum_direction_accuracy: number;
    maximum_unsupported_claim_rate: number;
    minimum_weighted_faithfulness: number;
    minimum_shap_mass_coverage: number;
    minimum_policy_compliance: number;
    minimum_language_compliance: number;
    confidence: number;
  };
  paired_bootstrap: {
    iterations: number;
    confidence: number;
    seed: number;
  };
  non_inferiority: {
    margin: number;
  };
  minimum_sufficient_evidence: {
    default_candidate_levels: EvidenceLevel[];
    excluded_baseline_level: EvidenceLevel;
    separate_fallback_level: EvidenceLevel;
  };
};
