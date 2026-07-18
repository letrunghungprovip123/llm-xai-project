export type EvidenceLevel = "S0" | "S1" | "S2" | "S3" | "S4" | "S5";

export type ModelProvider = "template" | "huggingface" | "deepseek";
export type ModelRuntime = "template" | "vllm" | "api";
export type OutputConstraintMode = "none" | "json_object" | "json_schema";
export type ExperimentStage = "development" | "evaluation";


export interface PredictionPayload {
  predicted_class?: number;
  predicted_label?: string;
  probability?: number;
  probability_display?: string;
  probability_percent_display?: string;
  threshold?: number;
  threshold_display?: string;
  threshold_percent_display?: string;
  threshold_comparison?: string;
  is_above_threshold?: boolean;
}


export interface EvidenceItem {
  feature_id?: string;
  feature_name?: string;
  display_name?: string;
  display_name_source?: string;
  concept?: string;
  concept_display_name?: string;
  shap_value?: number;
  abs_shap_value?: number;
  direction?: string;
  rank?: number;
  strength?: string;
  safe_phrase?: string;
  value?: unknown;
}


export interface ConceptEvidenceItem {
  concept?: string;
  concept_display_name?: string;
  direction?: string;
  representative_feature?: EvidenceItem;
  supporting_features?: EvidenceItem[];
  selected_feature_ids?: string[];
  feature_count?: number;
  selected_abs_shap_sum?: number;
}


export interface NarrativePolicy {
  must_include_uncertainty?: boolean;
  avoid_single_cause_wording?: boolean;
  allow_main_reason_wording?: boolean;
  must_include_distributed_evidence_note?: boolean;
  must_not_give_specific_feature_reason?: boolean;
  must_include_partial_evidence_note?: boolean;
  must_not_claim_evidence_is_complete?: boolean;
  mention_mixed_signals?: boolean;
  backend_controls_factor_order?: boolean;
  must_follow_backend_skeleton?: boolean;
  must_not_add_factor_outside_skeleton?: boolean;
}


export interface ClaimPolicy {
  allow_prediction_claim?: boolean;
  allow_uncertainty_claim?: boolean;
  allow_feature_claim?: boolean;
  allow_concept_claim?: boolean;
  allow_direction_claim?: boolean;
  allow_magnitude_claim?: boolean;
  allow_causal_claim?: boolean;
  allow_financial_advice?: boolean;
  allow_absolute_decision_claim?: boolean;
  allow_true_label_claim?: boolean;
}


export interface ConstraintsPayload {
  allowed_claim_ids?: string[];
  allowed_feature_ids?: string[];
  allowed_concept_ids?: string[];
  forbidden_rule_ids?: string[];
  claim_policy?: ClaimPolicy;
}


export interface SelectionContext {
  selected_evidence_count?: number;
  adaptive_k?: number;
  coverage?: number;
  coverage_threshold?: number;
  coverage_status?: string;
  normalized_entropy?: number;
  entropy_level?: string;
  concept_group_count?: number;
  mixed_concept_group_count?: number;
}


export interface BackendFactorSlot {
  feature_id?: string;
  display_name?: string;
  concept?: string;
  concept_display_name?: string;
  direction?: string;
  rank?: number;
  safe_phrase?: string;
}


export interface BackendExplanationSkeleton {
  prediction_statement?: PredictionPayload;
  required_section_order?: string[];
  main_factor_slots?: BackendFactorSlot[];
  required_uncertainty_note?: boolean;
  must_follow_factor_order?: boolean;
  must_not_add_factor_outside_skeleton?: boolean;
  forbidden_wording?: string[];
}


export interface PromptPayload {
  evidence_level: EvidenceLevel;
  prediction: PredictionPayload;
  selected_evidence: EvidenceItem[];
  concept_evidence: ConceptEvidenceItem[];
  selection_context: SelectionContext;
  narrative_policy: NarrativePolicy;
  constraints: ConstraintsPayload;
  backend_explanation_skeleton?: BackendExplanationSkeleton;
}


export interface EvidencePackage {
  package_id: string;
  source_ir_id: string;
  source_evidence_id?: string;
  trace_id?: string;
  run_mode?: string;
  ir_schema_version?: string;
  evidence_package_schema_version?: string;
  evidence_level: EvidenceLevel;
  internal_metadata?: Record<string, unknown>;
  prediction?: PredictionPayload;
  selected_evidence?: EvidenceItem[];
  concept_evidence?: ConceptEvidenceItem[];
  selection_metrics?: Record<string, unknown>;
  narrative_policy?: NarrativePolicy;
  constraints?: ConstraintsPayload;
  audit_trace?: Record<string, unknown>;
  prompt_payload: PromptPayload;
  backend_explanation_skeleton?: BackendExplanationSkeleton;
}


export interface DecodingConfig {
  temperature: number;
  top_p: number;
  max_tokens: number;
  frequency_penalty: number;
  presence_penalty: number;
}


export interface ModelConfig {
  id: string;
  provider: ModelProvider;
  family: string;
  runtime: ModelRuntime;
  remote_model_id: string;
  revision: string | null;
  output_constraint_mode: OutputConstraintMode;
  api_base_url?: string;
  api_key_env?: string;
  chat_template_kwargs?: Record<string, unknown>;
  input_cost_per_million?: number | null;
  output_cost_per_million?: number | null;
  enabled: boolean;
  note?: string;
}


export interface RunOptions {
  input_path: string;
  output_dir: string;
  run_id: string;
  model_ids: string[];
  levels: EvidenceLevel[];
  repeat_ids: number[];
  decoding: DecodingConfig;
  prompt_version: string;
  output_schema_version: string;
  experiment_stage: ExperimentStage;
  limit_cases?: number;
  chunk_start: number;
  chunk_size?: number;
  concurrency: number;
  checkpoint_every: number;
  timeout_ms: number;
  max_retries: number;
  retry_delay_ms: number;
  base_seed: number;
  resume: boolean;
}


export interface PromptMessage {
  role: "system" | "user";
  content: string;
}


export interface PromptSectionFlags {
  has_prediction_section: boolean;
  has_evidence_section: boolean;
  has_constraints_section: boolean;
  has_output_schema_section: boolean;
  has_entropy_policy_section: boolean;
  has_concept_grouping_section: boolean;
  has_backend_skeleton_section: boolean;
}


export interface PromptBuildResult {
  prompt_id: string;
  prompt_version: string;
  model_id: string;
  package_id: string;
  messages: PromptMessage[];
  message_text: string;
  message_sha256: string;
  section_flags: PromptSectionFlags;
}


export interface RunnerResult {
  status: "SUCCESS" | "FAILED";
  raw_output: string | null;
  finish_reason: string | null;
  latency_ms: number;
  retry_count: number;
  input_token_count: number | null;
  output_token_count: number | null;
  total_token_count: number | null;
  provider_request_id: string | null;
  provider_returned_model_id: string | null;
  provider_api_cost_usd: number | null;
  error_type: string | null;
  error_message: string | null;
}


export type FactorRole = "main" | "supporting";
export type FactorDirection = "increase_risk" | "decrease_risk" | "mixed" | "unknown";


export interface ExplanationFactor {
  factor_id: string;
  role: FactorRole;
  factor_name: string;
  declared_feature_ids: string[];
  declared_concept_ids: string[];
  direction: FactorDirection;
  explanation: string;
}


export interface ExplanationOutput {
  prediction_summary: string;
  factors: ExplanationFactor[];
  uncertainty_note: string;
  distributed_evidence_note: string;
  safe_summary: string;
}


export interface ParseResult {
  raw_json_parse_success: boolean;
  json_parse_success: boolean;
  cleaned_output: string | null;
  cleanup_type: "none" | "removed_code_fence" | "extracted_json_object" | "failed";
  parsed_output: ExplanationOutput | null;
  schema_valid: boolean;
  missing_required_fields: string[];
  validation_errors: string[];
}


export interface PromptMetrics {
  prompt_char_count: number;
  prompt_estimated_token_count: number;
  has_prediction_section: boolean;
  has_evidence_section: boolean;
  has_constraints_section: boolean;
  has_output_schema_section: boolean;
  has_entropy_policy_section: boolean;
  has_concept_grouping_section: boolean;
  has_backend_skeleton_section: boolean;
}


export interface SchemaMetrics {
  raw_json_parse_success: boolean;
  json_parse_success: boolean;
  schema_valid: boolean;
  missing_required_field_count: number;
  validation_error_count: number;
  cleanup_type: string;
}


export interface ContentMetrics {
  has_prediction_summary: boolean;
  has_factors: boolean;
  has_uncertainty_note: boolean;
  has_distributed_evidence_note: boolean;
  has_safe_summary: boolean;
  main_factor_count: number;
  supporting_factor_count: number;
  total_factor_count: number;
  output_char_count: number;
  output_word_count: number;
  sentence_count: number;
  average_sentence_length: number | null;
  technical_term_count: number;
  technical_term_ratio: number | null;
  too_short: boolean;
  too_long: boolean;
}


export interface PolicyMetrics {
  uncertainty_required: boolean;
  uncertainty_compliant: boolean | null;
  distributed_note_required: boolean;
  distributed_note_compliant: boolean | null;
  partial_evidence_note_required: boolean;
  partial_evidence_note_compliant: boolean | null;
  single_cause_violation: boolean;
  forbidden_phrase_violation: boolean;
  forbidden_phrase_matches: string[];
}


export interface EvidenceMentionMetrics {
  selected_feature_count: number;
  selected_feature_mention_count: number;
  selected_feature_mention_rate: number | null;
  top1_mention_rate: number | null;
  top3_mention_rate: number | null;
  top5_mention_rate: number | null;
  exposed_concept_count: number;
  concept_mention_count: number;
  concept_mention_rate: number | null;
  declared_feature_count: number;
  valid_declared_feature_count: number;
  invalid_declared_feature_count: number;
  declared_concept_count: number;
  valid_declared_concept_count: number;
  invalid_declared_concept_count: number;
}


export interface InputSnapshot {
  selected_evidence_count: number;
  coverage: number | null;
  coverage_threshold: number | null;
  coverage_status: string | null;
  adaptive_k: number | null;
  entropy_level: string | null;
  normalized_entropy: number | null;
  concept_group_count: number;
  mixed_concept_group_count: number;
  has_concept_evidence: boolean;
  has_constraints: boolean;
  has_forbidden_rules: boolean;
  has_narrative_policy: boolean;
}


export interface CaseMetadata {
  customer_id: string | number | null;
  selection_stratum: string | null;
  prediction_outcome: "TP" | "TN" | "FP" | "FN" | null;
  true_label: number | null;
}


export interface RuntimeMetrics extends RunnerResult {
  empty_response: boolean;
  truncated_response: boolean;
  infrastructure_cost_usd: number | null;
  total_cost_usd: number | null;
}


export interface GenerationRecord {
  generation_id: string;
  run_id: string;
  experiment_stage: ExperimentStage;
  package_id: string;
  source_ir_id: string;
  source_evidence_id: string | null;
  evidence_level: EvidenceLevel;
  case_metadata: CaseMetadata;
  model_provider: ModelProvider;
  model_id: string;
  remote_model_id: string;
  model_family: string;
  model_revision: string | null;
  prompt_version: string;
  output_schema_version: string;
  repeat_id: number;
  generation_seed: number | null;
  request_order_index: number;
  output_constraint_mode: OutputConstraintMode;
  decoding_config: DecodingConfig;
  input_package_sha256: string;
  prompt_id: string;
  prompt_message_sha256: string;
  input_snapshot: InputSnapshot;
  prompt_metrics: PromptMetrics;
  runtime_metrics: RuntimeMetrics;
  raw_output: string | null;
  cleaned_output: string | null;
  parsed_output: ExplanationOutput | null;
  schema_metrics: SchemaMetrics;
  content_metrics: ContentMetrics;
  policy_metrics: PolicyMetrics;
  evidence_mention_metrics: EvidenceMentionMetrics;
  created_at: string;
}


export interface PromptInstanceRecord {
  prompt_id: string;
  prompt_version: string;
  output_schema_version: string;
  package_id: string;
  source_ir_id: string;
  evidence_level: EvidenceLevel;
  model_id: string;
  model_revision: string | null;
  messages: PromptMessage[];
  message_sha256: string;
  prompt_char_count: number;
  prompt_estimated_token_count: number;
  section_flags: PromptSectionFlags;
  created_at: string;
}


export interface PipelineResult {
  run_id: string;
  shard_count: number;
  planned_generation_count: number;
  completed_generation_count: number;
  failed_generation_count: number;
  shard_paths: string[];
}
