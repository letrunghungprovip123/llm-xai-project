import type { EvidenceLevel } from "./llm-validation";

export const CLAIM_TYPES = [
  "prediction",
  "feature_presence",
  "feature_direction",
  "concept_presence",
  "concept_direction",
  "magnitude",
  "ranking",
  "numeric",
  "causal",
  "uncertainty",
  "distributed_evidence",
  "recommendation",
  "limitation",
] as const;

export const CLAIM_SOURCE_SECTIONS = [
  "prediction_summary",
  "factor_name",
  "factor_explanation",
  "uncertainty_note",
  "distributed_evidence_note",
  "safe_summary",
] as const;

export const CLAIM_DIRECTIONS = [
  "increase_risk",
  "decrease_risk",
  "mixed",
  "neutral",
  "unknown",
] as const;

export const CLAIM_NUMERIC_ROLES = [
  "prediction_score",
  "decision_threshold",
  "feature_value",
  "rank",
  "other",
  "not_applicable",
] as const;

export const CLAIM_ORIGINS = [
  "llm",
  "deterministic_metadata",
  "derived_numeric",
] as const;

export type ClaimType = (typeof CLAIM_TYPES)[number];
export type ClaimSourceSection = (typeof CLAIM_SOURCE_SECTIONS)[number];
export type ClaimDirection = (typeof CLAIM_DIRECTIONS)[number];
export type ClaimNumericRole = Exclude<
  (typeof CLAIM_NUMERIC_ROLES)[number],
  "not_applicable"
>;
export type ClaimOrigin = (typeof CLAIM_ORIGINS)[number];
export type ClaimExtractorProvider = "amazon_bedrock" | "deepseek";
export type ClaimSubjectType =
  | "prediction"
  | "feature"
  | "concept"
  | "evidence"
  | "narrative"
  | "none";
export type ClaimMagnitude = "weak" | "moderate" | "strong" | "unknown";
export type ClaimCertainty =
  | "deterministic"
  | "probabilistic"
  | "hedged"
  | "unknown";
export type ClaimCausalStrength =
  | "associational"
  | "causal"
  | "none"
  | "unknown";

// Provider chỉ trả nội dung ngữ nghĩa; chỉ số và source span do code xác định.
export type ProviderAtomicClaimDraft = {
  source_section: ClaimSourceSection;
  source_factor_id: string;
  source_text: string;
  claim_type: ClaimType;
  subject_type: ClaimSubjectType;
  feature_id: string;
  concept_id: string;
  direction: ClaimDirection;
  magnitude: ClaimMagnitude | "not_applicable";
  certainty: ClaimCertainty;
  causal_strength: ClaimCausalStrength;
  numeric_value_text: string;
  numeric_unit: string;
  numeric_role: ClaimNumericRole | "not_applicable";
  normalized_claim_key: string;
};

export type ProviderAtomicClaimPayload = {
  claims: ProviderAtomicClaimDraft[];
};

// Claim sau chuẩn hóa luôn có vị trí nguồn và thứ tự ổn định để audit lại được.
export type AtomicClaimDraft = {
  local_claim_index: number;
  source_section: ClaimSourceSection;
  source_factor_id: string | null;
  source_text: string;
  source_span_start: number;
  source_span_end: number;
  claim_type: ClaimType;
  subject_type: ClaimSubjectType;
  feature_id: string | null;
  concept_id: string | null;
  direction: ClaimDirection;
  magnitude: ClaimMagnitude | null;
  certainty: ClaimCertainty;
  causal_strength: ClaimCausalStrength;
  numeric_value: number | null;
  numeric_unit: string | null;
  numeric_role: ClaimNumericRole | null;
  claim_origin: ClaimOrigin;
  model_normalized_claim_key: string | null;
  semantic_signature: string;
  normalized_claim_key: string;
};

export type AtomicClaimExtractionPayload = {
  claims: AtomicClaimDraft[];
  postprocess_metrics: ClaimExtractionPostprocessMetrics;
};

// Metrics này giúp audit phần code bổ sung claim và các section bị bỏ sót.
export type ClaimExtractionPostprocessMetrics = {
  llm_claim_count: number;
  deterministic_claim_count_added: number;
  derived_numeric_claim_count_added: number;
  causal_overclaim_count_demoted: number;
  semantic_duplicate_count_removed: number;
  final_claim_count: number;
  nonempty_source_slot_count: number;
  claimed_source_slot_count: number;
  semantically_redundant_source_slots: string[];
  unclaimed_source_slots: string[];
  effective_source_coverage_rate: number;
};

export type ClaimExtractionPostprocessTotals = {
  llm_claims_received: number;
  deterministic_claims_added: number;
  derived_numeric_claims_added: number;
  causal_overclaims_demoted: number;
  semantic_duplicates_removed: number;
  final_claims_created: number;
  source_slots_covered: number;
  source_slots_total: number;
  unclaimed_source_slots: number;
};

export type ClaimExtractionUsage = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

export type ClaimExtractionRawResponse = {
  raw_text: string | null;
  usage: unknown;
  stop_reason: string | null;
  response_received: boolean;
  provider_request_id: string | null;
  provider_returned_model_id: string | null;
  retry_count: number;
  http_status: number | null;
  api_error_type: string | null;
  api_error_message: string | null;
};

export type AtomicClaimRecord = AtomicClaimDraft & {
  claim_schema_version: "claims_v2";
  claim_id: string;
  generation_id: string;
  model_id: string;
  source_ir_id: string;
  case_id: string | null;
  evidence_level: EvidenceLevel;
  repeat_id: number;
  source_input_sha256: string;
  source_text_sha256: string;
  extractor_provider: "deepseek";
  extractor_model_id: string;
  extractor_version: string;
  extractor_prompt_version: string;
  extractor_prompt_sha256: string;
  extractor_status: "SUCCESS";
};

export type ClaimExtractionFailureCode =
  | "GENERATION_UNUSABLE"
  | "SOURCE_TEXT_EMPTY"
  | "BEDROCK_CALL_FAILED"
  | "PROVIDER_CALL_FAILED"
  | "RESPONSE_NOT_JSON"
  | "RESPONSE_SCHEMA_INVALID"
  | "SOURCE_SPAN_INVALID"
  | "NO_CLAIMS_EXTRACTED";

export type ClaimExtractionFailureV1 = {
  failure_schema_version: "claim_extraction_failure_v1";
  generation_id: string;
  canonical_key: string;
  source_ir_id: string;
  case_id: string | null;
  evidence_level: EvidenceLevel;
  repeat_id: number;
  attempted: boolean;
  failure_code: ClaimExtractionFailureCode;
  failure_message: string;
  source_input_sha256: string | null;
  extractor_model_id: string | null;
  extractor_version: string;
};

export type ClaimExtractionFailure = {
  failure_schema_version: "claim_extraction_failure_v2";
  generation_id: string;
  canonical_key: string;
  source_ir_id: string;
  case_id: string | null;
  evidence_level: EvidenceLevel;
  repeat_id: number;
  attempted: boolean;
  failure_code: ClaimExtractionFailureCode;
  failure_message: string;
  source_input_sha256: string | null;
  extractor_provider: "deepseek" | null;
  extractor_model_id: string | null;
  extractor_version: string;
  extractor_prompt_version: string;
  extractor_prompt_sha256: string;
};

export type StoredClaimExtractionFailure =
  | ClaimExtractionFailureV1
  | ClaimExtractionFailure;

type ClaimExtractionAttemptCore = {
  attempt_id: string;
  generation_id: string;
  canonical_key: string;
  source_ir_id: string;
  case_id: string | null;
  evidence_level: EvidenceLevel;
  repeat_id: number;
  attempt_number: number;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  status:
    | "SUCCESS"
    | "VALIDATION_FAILED"
    | "BEDROCK_FAILED"
    | "PROVIDER_FAILED";
  failure_code: ClaimExtractionFailureCode | null;
  failure_message: string | null;
  result_claim_count: number;
  source_input_sha256: string;
  extractor_provider: ClaimExtractorProvider;
  extractor_model_id: string;
  extractor_version: string;
  extractor_prompt_version: string;
  response_received: boolean;
  raw_response_sha256: string | null;
  raw_response_text: string | null;
  stop_reason: string | null;
  usage: ClaimExtractionUsage;
};

// Giữ type v1 để runner vẫn đọc được attempt log đã tạo từ smoke test cũ.
export type ClaimExtractionAttemptRecordV1 = ClaimExtractionAttemptCore & {
  attempt_schema_version: "claim_extraction_attempt_v1";
  extractor_provider: "amazon_bedrock";
};

// Mỗi provider call có một audit record, kể cả khi parse hoặc hậu kiểm thất bại.
export type ClaimExtractionAttemptRecord = ClaimExtractionAttemptCore & {
  attempt_schema_version: "claim_extraction_attempt_v2";
  extractor_provider: "deepseek";
  extractor_prompt_sha256: string;
  provider_request_id: string | null;
  provider_returned_model_id: string | null;
  retry_count: number;
  http_status: number | null;
  postprocess_metrics: ClaimExtractionPostprocessMetrics | null;
};

export type StoredClaimExtractionAttemptRecord =
  | ClaimExtractionAttemptRecordV1
  | ClaimExtractionAttemptRecord;
