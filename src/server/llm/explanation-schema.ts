// src/server/llm/explanation-schema.ts

/**
 * Batch I v1.1 - LLM API Explanation Layer
 *
 * Shared schemas/types for:
 * - Explanation IR input from Batch H
 * - Safe LLM input contract
 * - LLM-generated JSON output
 * - Batch I output records
 *
 * Design rule:
 * The LLM may write naturally, but it must not invent evidence.
 */

export type RunMode = "evaluation" | "inference";

export type InputSource = "precomputed_ir" | "inference_ready" | "raw_batch";

export type GeneratorType = "template" | "llm_api";

export type ExplanationLanguage = "vi";

export type RiskDirection =
  | "increases_risk"
  | "decreases_risk"
  | "neutral"
  | "mixed"
  | "neutral_or_mixed"
  | "unknown"
  | string;

export type ContributionStrength =
  | "strong"
  | "moderate"
  | "weak"
  | "neutral"
  | "unknown"
  | string;

export type PredictionLabel = "high_default_risk" | "low_default_risk" | string;

export type ThresholdComparison =
  | "above_threshold"
  | "above_or_equal_threshold"
  | "below_threshold"
  | "below_or_equal_threshold"
  | "unknown"
  | string;

export type DisplayPolicy =
  | "feature_level_allowed"
  | "concept_level_only"
  | "hidden"
  | string;

export type EvidenceUsage =
  | "primary"
  | "supporting"
  | "risk_reducing"
  | "remaining_summary"
  | "supporting_group"
  | string;

export type ExplanationGenerationRequest = {
  runMode: RunMode;
  batchId: string;
  inputSource: InputSource;
  irId?: string;
  customerId?: string;
  limit?: number;

  /**
   * Optional Batch J.3 feedback file.
   * When provided, Batch I performs controlled regeneration for matching IR records.
   */
  feedbackPath?: string;

  /**
   * Artifact sub-directory under:
   * data/reports/llm_explanations/<runMode>/.../llm_api/<artifactSubdir>/
   *
   * Examples:
   * - base
   * - regeneration_attempt_1
   *
   * This prevents regeneration runs from overwriting the base Batch I output.
   */
  artifactSubdir?: string;
};

export type IrModelInfo = {
  model_name?: string;
  modelName?: string;
  model_version?: string;
  modelVersion?: string;
  model_family?: string;
  modelFamily?: string;
  dataset_branch?: string;
  datasetBranch?: string;
  [key: string]: unknown;
};

export type IrCustomerInfo = {
  SK_ID_CURR?: number | string;
  sk_id_curr?: number | string;
  [key: string]: unknown;
};

export type IrPredictionSummary = {
  predicted_class?: number | string;
  predicted_label?: PredictionLabel;
  predictedLabel?: PredictionLabel;
  probability?: number;
  predicted_probability?: number;
  predictedProbability?: number;
  threshold?: number;
  threshold_comparison?: ThresholdComparison;
  thresholdComparison?: ThresholdComparison;
  probability_display?: string;
  probability_percent_display?: string;
  threshold_display?: string;
  threshold_percent_display?: string;
  [key: string]: unknown;
};

export type LlmContractConcept = {
  concept_id?: string;
  conceptId?: string;
  display_name?: string;
  displayName?: string;
  direction?: RiskDirection;
  strength?: ContributionStrength;
  contribution_percent?: number;
  contributionPercent?: number;
  net_contribution_points_display?: string;
  feature_count?: number;
  claimable?: boolean;
  llm_visible?: boolean;
  llmVisible?: boolean;
  [key: string]: unknown;
};

export type LlmContractFeatureFactor = {
  factor_id?: string;
  factorId?: string;
  feature_id?: string;
  featureId?: string;
  feature_name?: string;
  featureName?: string;
  display_name?: string;
  displayName?: string;
  concept?: string;
  concept_id?: string;
  conceptId?: string;
  concept_display_name?: string;
  conceptDisplayName?: string;
  value?: unknown;
  value_display?: string;
  valueDisplay?: string;
  formatted_value?: string;
  formattedValue?: string;
  shap_value?: number;
  shapValue?: number;
  shap_value_display?: string;
  shapValueDisplay?: string;
  contribution_points_display?: string;
  contributionPointsDisplay?: string;
  direction?: RiskDirection;
  strength?: ContributionStrength;
  contribution_percent?: number;
  contributionPercent?: number;
  contribution_percent_display?: string;
  contributionPercentDisplay?: string;
  claimable?: boolean;
  llm_visible?: boolean;
  llmVisible?: boolean;
  sensitive?: boolean;
  allowed_in_user_explanation?: boolean | "limited" | string;
  display_policy?: DisplayPolicy;
  displayPolicy?: DisplayPolicy;
  usage?: EvidenceUsage;
  feature_note?: string;
  featureNote?: string;
  [key: string]: unknown;
};


export type RegenerationFeedbackIssue = {
  claim_id?: string;
  claim_type?: string;
  section?: string;
  claim_text: string;
  failure_type:
    | "prediction_value_mismatch"
    | "direction_mismatch"
    | "ungrounded_feature"
    | "ambiguous_feature_reference"
    | "unsupported_concept"
    | "missing_required_limitation"
    | "schema_or_format_issue"
    | "unknown";
  validator_rule_id?: string;
  severity: "warning" | "error";
  reason: string;
  repair_instruction: string;
  evidence?: Record<string, unknown>;
};

export type RegenerationFeedback = {
  feedback_id: string;
  created_at?: string;
  ir_id: string;
  explanation_id?: string;
  validation_id?: string;
  attempt: number;
  source_batch: "Batch J.2" | "Batch J.3" | string;
  status: "FAIL" | "PASS_WITH_WARN";
  summary: {
    total_issues: number;
    error_count: number;
    warning_count: number;
  };
  issues: RegenerationFeedbackIssue[];
  global_repair_instructions: string[];
};

export type LlmSupportingFeatureGroup = {
  group_id?: string;
  groupId?: string;
  concept_id?: string;
  conceptId?: string;
  display_name?: string;
  displayName?: string;
  feature_count?: number;
  featureCount?: number;
  direction?: RiskDirection;
  strength?: ContributionStrength;
  net_contribution_points_display?: string;
  netContributionPointsDisplay?: string;
  top_feature_display_names?: string[];
  topFeatureDisplayNames?: string[];
  factor_ids?: string[];
  factorIds?: string[];
  concept_note?: string;
  conceptNote?: string;
  [key: string]: unknown;
};

export type LlmAllowedTerm = {
  term_id?: string;
  termId?: string;
  term_type?: string;
  termType?: string;
  mention?: string;
  display_name?: string;
  displayName?: string;
  [key: string]: unknown;
};

export type LlmInputContract = {
  language?: ExplanationLanguage | string;
  audience?: string;
  style?: string;

  prediction?: IrPredictionSummary;

  contribution_accounting?: Record<string, unknown>;
  contributionAccounting?: Record<string, unknown>;

  primary_features?: LlmContractFeatureFactor[];
  primaryFeatures?: LlmContractFeatureFactor[];

  supporting_feature_groups?: LlmSupportingFeatureGroup[];
  supportingFeatureGroups?: LlmSupportingFeatureGroup[];

  remaining_features_summary?: Record<string, unknown>;
  remainingFeaturesSummary?: Record<string, unknown>;

  feature_tiers?: Record<string, unknown>;
  featureTiers?: Record<string, unknown>;

  main_concepts?: LlmContractConcept[];
  mainConcepts?: LlmContractConcept[];

  main_risk_increasing_factors?: LlmContractFeatureFactor[];
  mainRiskIncreasingFactors?: LlmContractFeatureFactor[];

  main_risk_decreasing_factors?: LlmContractFeatureFactor[];
  mainRiskDecreasingFactors?: LlmContractFeatureFactor[];

  allowed_terms?: LlmAllowedTerm[];
  allowedTerms?: LlmAllowedTerm[];

  allowed_claim_ids?: string[];
  allowedClaimIds?: string[];

  forbidden_rule_ids?: string[];
  forbiddenRuleIds?: string[];

  must_include?: string[];
  mustInclude?: string[];

  must_not?: string[];
  mustNot?: string[];

  writing_rules?: Record<string, unknown>;
  writingRules?: Record<string, unknown>;

  forbidden_content?: string[];
  forbiddenContent?: string[];

  required_output_sections?: string[];
  requiredOutputSections?: string[];

  [key: string]: unknown;
};

export type ExplanationIrRecord = {
  ir_id: string;
  source_evidence_id?: string;
  trace_id?: string;
  run_mode?: RunMode | string;
  has_ground_truth?: boolean;
  ir_schema_version?: string;
  created_at?: string;
  source_batch?: string;
  model?: IrModelInfo;
  customer?: IrCustomerInfo;
  prediction_summary?: IrPredictionSummary;
  llm_input_contract?: LlmInputContract;
  allowed_claims?: unknown[];
  forbidden_claims?: unknown[];
  validation_contract?: Record<string, unknown>;
  evidence_trace?: Record<string, unknown>;
  quality?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};

export type LlmGeneratedSections = {
  prediction: string;
  contribution_overview: string;
  main_risk_drivers: string;
  supporting_evidence_groups: string;
  risk_reducing_factors: string;
  limitations: string;
};

export type LlmReferencedTerm = {
  term_id: string;
  term_type: string;
  mention: string;
};

export type LlmEvidenceItemUsed = {
  evidence_id: string;
  evidence_type: string;
  direction: RiskDirection;
  usage: EvidenceUsage;
};

export type LlmEvidenceGroupUsed = {
  group_id: string;
  concept_id: string | null;
  usage: EvidenceUsage;
};

/**
 * Strict JSON shape returned by the LLM.
 *
 * Important:
 * - LLM does NOT return full_text.
 * - Server builds full_text from sections to avoid section/full_text mismatch.
 */
export type LlmGeneratedJson = {
  language: ExplanationLanguage;
  sections: LlmGeneratedSections;
  referenced_terms?: LlmReferencedTerm[];
  evidence_items_used?: LlmEvidenceItemUsed[];
  evidence_groups_used?: LlmEvidenceGroupUsed[];
};

export type LlmRawResponse = {
  provider: string;
  modelName: string;
  rawText: string;
  parsedJson?: LlmGeneratedJson;
  isParseableJson: boolean;
  errorMessage?: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
};

export type LlmGeneratorInfo = {
  generator_type: GeneratorType;
  generator_name: string;
  generator_version: string;
  uses_external_ai_api: boolean;
  provider?: string;
  model_name?: string;
  prompt_version?: string;
};

export type LlmExplanationPayload = {
  language: ExplanationLanguage;
  sections: LlmGeneratedSections;
  full_text: string;
  referenced_terms: LlmReferencedTerm[];
  evidence_items_used: LlmEvidenceItemUsed[];
  evidence_groups_used: LlmEvidenceGroupUsed[];
};

export type LlmExplanationRecord = {
  explanation_id: string;
  source_ir_id: string;
  source_evidence_id?: string;
  trace_id?: string;
  run_mode: RunMode;
  has_ground_truth: boolean;
  customer: IrCustomerInfo;
  model?: IrModelInfo;
  prediction_summary?: IrPredictionSummary;
  generator: LlmGeneratorInfo;
  explanation: LlmExplanationPayload;
  source_contract_summary: {
    required_output_sections: string[];
    allowed_claim_count: number;
    forbidden_rule_count: number;
    primary_feature_count: number;
    supporting_group_count: number;
    has_contribution_accounting: boolean;
  };
  quality: {
    is_parseable_json: boolean;
    has_required_sections: boolean;
    section_count: number;
    character_count: number;
    has_referenced_terms: boolean;
    has_evidence_items_used: boolean;
    has_evidence_groups_used: boolean;
    contains_forbidden_wording: boolean;
    contains_raw_technical_name: boolean;
    warnings: string[];
    errors: string[];
  };
  raw_response?: {
    provider: string;
    model_name: string;
    raw_text_preview: string;
    usage?: {
      prompt_tokens?: number;
      completion_tokens?: number;
      total_tokens?: number;
    };
  };
  metadata: {
    created_at: string;
    batch_id: string;
    batch_version: string;
    input_source: InputSource;
    source_batch?: string;
    ir_schema_version?: string;

    /**
     * Regeneration metadata.
     * attempt = 0 means first generation.
     * attempt > 0 means generated with validation feedback.
     */
    generation_attempt?: number;
    has_regeneration_feedback?: boolean;
    feedback_id?: string;
    parent_explanation_id?: string;
  };
};

export type BuiltPrompt = {
  system: string;
  user: string;
  promptVersion: string;
};

export type LlmRuntimeConfig = {
  provider: string;
  modelName: string;
  temperature: number;
  maxTokens: number;
  promptVersion: string;
};

export function isExplanationIrRecord(
  value: unknown,
): value is ExplanationIrRecord {
  if (!value || typeof value !== "object") {
    return false;
  }

  const obj = value as Record<string, unknown>;
  return typeof obj.ir_id === "string";
}

export function isLlmGeneratedJson(value: unknown): value is LlmGeneratedJson {
  if (!value || typeof value !== "object") {
    return false;
  }

  const obj = value as Record<string, unknown>;

  if (obj.language !== "vi") {
    return false;
  }

  if (!obj.sections || typeof obj.sections !== "object") {
    return false;
  }

  const sections = obj.sections as Record<string, unknown>;

  return (
    typeof sections.prediction === "string" &&
    typeof sections.contribution_overview === "string" &&
    typeof sections.main_risk_drivers === "string" &&
    typeof sections.supporting_evidence_groups === "string" &&
    typeof sections.risk_reducing_factors === "string" &&
    typeof sections.limitations === "string"
  );
}

export function pickString(
  obj: Record<string, unknown> | undefined,
  keys: string[],
  fallback = "",
): string {
  if (!obj) return fallback;

  for (const key of keys) {
    const value = obj[key];

    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }

  return fallback;
}

export function pickNumber(
  obj: Record<string, unknown> | undefined,
  keys: string[],
  fallback = 0,
): number {
  if (!obj) return fallback;

  for (const key of keys) {
    const value = obj[key];

    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }

    if (typeof value === "string") {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }

  return fallback;
}

export function pickBoolean(
  obj: Record<string, unknown> | undefined,
  keys: string[],
  fallback = false,
): boolean {
  if (!obj) return fallback;

  for (const key of keys) {
    const value = obj[key];

    if (typeof value === "boolean") {
      return value;
    }
  }

  return fallback;
}

export function getCustomerId(customer: IrCustomerInfo | undefined): string {
  if (!customer) return "unknown_customer";

  const raw = customer.SK_ID_CURR ?? customer.sk_id_curr ?? "unknown_customer";
  return String(raw);
}

export function normalizeRunMode(
  value: unknown,
  fallback: RunMode = "evaluation",
): RunMode {
  if (value === "evaluation" || value === "inference") {
    return value;
  }

  return fallback;
}

export function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }

  return value as Record<string, unknown>;
}

export function asArray<T = unknown>(value: unknown): T[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value as T[];
}
