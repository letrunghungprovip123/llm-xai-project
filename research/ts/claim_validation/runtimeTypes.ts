import type { EvidenceLevel } from "../../../contracts/llm-validation";

export type ExposedDirection =
  | "increases_risk"
  | "decreases_risk"
  | "increase_risk"
  | "decrease_risk"
  | "mixed"
  | "neutral"
  | "unknown";

export type ClaimValidationGenerationRecord = {
  generation_id: string;
  package_id: string;
  source_ir_id: string;
  source_evidence_id: string;
  evidence_level: EvidenceLevel;
  model_id: string;
  repeat_id: number;
};

export type ClaimValidationGenerationRow = {
  canonical_schema_version: "generation_index_v1";
  generation_id: string;
  package_id: string;
  source_evidence_id: string;
  source_ir_id: string;
  model_id: string;
  case_id: string;
  repeat_id: number;
  evidence_level: EvidenceLevel;
  usable: boolean;
  runtime_status: string;
  finish_reason: string;
  truncated_response: boolean;
  raw_json_parse_success: boolean;
  schema_valid: boolean;
  usability_reason_codes: string[];
  generation_record: ClaimValidationGenerationRecord;
};

export type ClaimValidationPrediction = {
  predicted_label: string;
  probability: number;
  threshold: number;
  probability_display: string;
  probability_percent_display: string;
  threshold_display: string;
  threshold_percent_display: string;
  threshold_comparison: string;
  is_above_threshold: boolean;
};


export type ClaimValidationTargetSemantics = {
  canonical_name?: string;
  semantic_name?: string;
  prediction_horizon?: string | null;
  positive_class?: number;
  negative_class?: number;
  positive_label: string;
  negative_label: string;
  prediction_subject: string;
  positive_display_name: string;
  negative_display_name: string;
  positive_direction_phrase: string;
  negative_direction_phrase: string;
};

export type ClaimValidationFeatureEvidence = {
  feature_id: string;
  shap_value: number;
  abs_shap_value: number;
  direction: ExposedDirection;
  rank: number;
  strength?: "weak" | "moderate" | "strong";
  value?: number;
};

export type ClaimValidationConceptEvidence = {
  concept: string;
  direction: ExposedDirection;
  representative_feature: ClaimValidationFeatureEvidence;
  supporting_features: ClaimValidationFeatureEvidence[];
  selected_feature_ids: string[];
  feature_count: number;
  selected_abs_shap_sum: number;
};

export type ClaimValidationSelectionContext = {
  selected_evidence_count: number;
  adaptive_k?: number;
  coverage?: number;
  coverage_threshold?: number;
  coverage_status?: string;
  normalized_entropy?: number;
  entropy_level?: string;
  concept_group_count?: number;
  mixed_concept_group_count?: number;
};

export type ClaimValidationNarrativePolicy = {
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
};

export type ClaimValidationClaimPolicy = {
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
};

export type ClaimValidationConstraints = {
  allowed_feature_ids: string[];
  allowed_concept_ids: string[];
  forbidden_rule_ids: string[];
  claim_policy: ClaimValidationClaimPolicy;
};

export type ClaimValidationPromptPayload = {
  evidence_level: EvidenceLevel;
  prediction: ClaimValidationPrediction;
  target_semantics?: ClaimValidationTargetSemantics;
  selected_evidence: ClaimValidationFeatureEvidence[];
  concept_evidence: ClaimValidationConceptEvidence[];
  selection_context: ClaimValidationSelectionContext;
  narrative_policy: ClaimValidationNarrativePolicy;
  constraints: ClaimValidationConstraints;
};

export type ClaimValidationEvidencePackage = {
  package_id: string;
  source_ir_id: string;
  source_evidence_id: string;
  evidence_level: EvidenceLevel;
  target_semantics?: ClaimValidationTargetSemantics;
  prompt_payload: ClaimValidationPromptPayload;
};
