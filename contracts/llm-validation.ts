// Các kiểu dữ liệu dùng chung cho bước chuẩn hóa và những bước validation phía sau.
export const CANONICALIZATION_TOOL_VERSION = "canonicalizer_v1.1.0";

export const EVIDENCE_LEVELS = ["S0", "S1", "S2", "S3", "S4", "S5"] as const;

export type EvidenceLevel = (typeof EVIDENCE_LEVELS)[number];
export type JsonObject = Record<string, unknown>;

export type EvidencePackageRecord = JsonObject & {
  package_id: string;
  source_ir_id: string;
  source_evidence_id: string;
  evidence_level: EvidenceLevel;
};

export type GenerationRecordLike = JsonObject & {
  generation_id: string;
  run_id: string;
  experiment_stage: string;
  package_id: string;
  source_ir_id: string;
  source_evidence_id: string;
  evidence_level: EvidenceLevel;
  model_id: string;
  model_revision: string | null;
  prompt_version: string;
  output_schema_version: string;
  repeat_id: number;
  input_package_sha256: string;
  prompt_id: string;
  prompt_message_sha256: string;
};

export type PromptRecordLike = JsonObject & {
  prompt_id: string;
  prompt_version: string;
  output_schema_version: string;
  package_id: string;
  source_ir_id: string;
  evidence_level: EvidenceLevel;
  model_id: string;
  model_revision: string | null;
  message_sha256: string;
};

export type ModelSource = {
  model_id: string;
  generations_path: string;
  prompts_path: string;
  manifest_path?: string;
  is_baseline: boolean;
  eligible_for_selection: boolean;
};

export type UsabilityResult = {
  usable: boolean;
  reason_codes: string[];
};

export type CanonicalGenerationRow = {
  canonical_schema_version: "generation_index_v1";
  canonical_key: string;
  cohort_key: string;
  matrix_role: "main" | "baseline";
  model_order: number;
  case_order: number;
  evidence_level_order: number;
  is_baseline: boolean;
  eligible_for_selection: boolean;

  generation_id: string;
  run_id: string;
  experiment_stage: string;
  model_id: string;
  model_revision: string | null;
  revision_status: "pinned" | "provider_managed_or_unavailable";
  case_id: string | null;
  source_ir_id: string;
  evidence_level: EvidenceLevel;
  repeat_id: number;
  package_id: string;
  source_evidence_id: string;
  prompt_id: string;
  prompt_version: string;
  output_schema_version: string;

  input_package_sha256: string;
  input_package_hash_verified: boolean;
  prompt_message_sha256: string;
  prompt_hash_verified: boolean;

  runtime_status: string | null;
  finish_reason: string | null;
  truncated_response: boolean;
  raw_json_parse_success: boolean;
  schema_valid: boolean;
  usable: boolean;
  usability_reason_codes: string[];

  source_generation_path: string;
  source_generation_file_sha256: string;
  source_generation_line: number;
  source_prompt_path: string;
  source_prompt_file_sha256: string;
  source_prompt_line: number;

  generation_record: GenerationRecordLike;
};

export type IntegrityCheck = {
  check_id: string;
  status: "PASS" | "WARN" | "FAIL";
  expected: string | number | boolean | null;
  actual: string | number | boolean | null;
  detail: string;
};

export type FileProfile = {
  path: string;
  sha256: string;
  byte_count: number;
  format: "jsonl" | "json" | "csv";
  record_count: number;
  invalid_record_count: number;
  top_level_fields?: Record<
    string,
    {
      present_count: number;
      null_count: number;
      types: Record<string, number>;
    }
  >;
  csv_headers?: string[];
  csv_widths?: Record<string, number>;
};

export type ArtifactDescriptor = {
  path: string;
  sha256: string;
  byte_count: number;
  record_count?: number;
};
