import type { EvidenceLevel } from "./llm-validation";

// Một record contract luôn đại diện cho đúng một ô trong canonical generation matrix.
export type GenerationContractMetrics = {
  contract_schema_version: "generation_contract_metrics_v1";
  contract_validator_version: string;
  generation_id: string;
  canonical_key: string;
  model_id: string;
  case_id: string | null;
  source_ir_id: string;
  evidence_level: EvidenceLevel;
  repeat_id: number;
  package_id: string;
  raw_metrics: {
    request_attempted: true;
    request_success: boolean;
    runtime_status: string | null;
    finish_reason: string | null;
    retry_count: number | null;
    empty_response: boolean;
    truncated: boolean;
    max_token_hit: boolean;
    raw_json_parse_success: boolean;
    json_parse_success: boolean;
    schema_valid: boolean;
    usable_output: boolean;
  };
  structural_metrics: {
    required_sections_present: boolean;
    missing_required_sections: string[];
    factor_id_unique: boolean | null;
    duplicate_factor_ids: string[];
    factor_count_actual: number | null;
    factor_count_expected: number | null;
    factor_count_accuracy: boolean | null;
    factor_order_accuracy: boolean | null;
    factor_role_accuracy: boolean | null;
    skeleton_compliance: boolean | null;
    allowed_feature_compliance: boolean | null;
    invalid_feature_ids: string[];
    allowed_concept_compliance: boolean | null;
    invalid_concept_ids: string[];
  };
  surface_metrics: {
    language_compliance: boolean | null;
    mixed_language_flag: boolean | null;
    too_short: boolean | null;
    too_long: boolean | null;
    redundancy_indicator: number | null;
    empty_section_count: number | null;
  };
  evidence_reference_metrics: {
    selected_evidence_mention_rate: number | null;
    top1_mention: number | null;
    top3_mention: number | null;
    top5_mention: number | null;
    concept_group_coverage: number | null;
    direction_surface_match: number | null;
  };
  contract_pass: boolean;
  issue_codes: string[];
};

