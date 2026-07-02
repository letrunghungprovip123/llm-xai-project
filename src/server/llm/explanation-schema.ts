// src/server/llm/explanation-schema.ts

/**
 * Batch I v1.0 - LLM API Explanation Layer
 *
 * This file defines shared TypeScript schemas/types for:
 * - Explanation IR input from Batch H
 * - LLM input contract
 * - LLM-generated explanation output
 * - Batch/run configuration
 *
 * Important design rule:
 * The LLM layer depends on Explanation IR, not raw data, not SHAP directly,
 * and not the trained model directly.
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
  | "unknown";

export type ContributionStrength =
  | "strong"
  | "moderate"
  | "weak"
  | "neutral"
  | "unknown";

export type PredictionLabel = "high_default_risk" | "low_default_risk" | string;

export type ThresholdComparison =
  | "above_threshold"
  | "above_or_equal_threshold"
  | "below_threshold"
  | "below_or_equal_threshold"
  | "unknown"
  | string;

/**
 * Request shape used by both:
 * - offline script runner
 * - Next.js API route
 *
 * Current main implementation:
 * inputSource = "precomputed_ir"
 *
 * Future extension:
 * inputSource = "raw_batch" or "inference_ready"
 */
export type ExplanationGenerationRequest = {
  runMode: RunMode;
  batchId: string;
  inputSource: InputSource;

  /**
   * Optional filters.
   * Used when UI wants to generate explanation for one customer/IR only.
   */
  irId?: string;
  customerId?: string;

  /**
   * Useful for testing before calling the LLM on all records.
   */
  limit?: number;
};

/**
 * Minimal model metadata carried from IR.
 */
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

/**
 * Minimal customer identity carried from IR.
 */
export type IrCustomerInfo = {
  SK_ID_CURR?: number | string;
  sk_id_curr?: number | string;

  [key: string]: unknown;
};

/**
 * Prediction summary produced before the LLM layer.
 */
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

  [key: string]: unknown;
};

/**
 * A concept-level item allowed for user-facing explanation.
 */
export type LlmContractConcept = {
  concept_id?: string;
  conceptId?: string;

  display_name?: string;
  displayName?: string;

  direction?: RiskDirection;
  strength?: ContributionStrength;

  contribution_percent?: number;
  contributionPercent?: number;

  claimable?: boolean;
  llm_visible?: boolean;
  llmVisible?: boolean;

  [key: string]: unknown;
};

/**
 * A feature-level item allowed for user-facing explanation.
 */
export type LlmContractFeatureFactor = {
  feature_id?: string;
  featureId?: string;

  display_name?: string;
  displayName?: string;

  value?: unknown;

  shap_value?: number;
  shapValue?: number;

  direction?: RiskDirection;
  strength?: ContributionStrength;

  contribution_percent?: number;
  contributionPercent?: number;

  claimable?: boolean;
  llm_visible?: boolean;
  llmVisible?: boolean;

  [key: string]: unknown;
};

/**
 * The controlled contract that the prompt builder will expose to the LLM.
 *
 * This is the most important input for Batch I v1.0.
 * The LLM should verbalize this contract, not invent new evidence.
 */
export type LlmInputContract = {
  language?: ExplanationLanguage | string;

  prediction?: IrPredictionSummary;

  main_concepts?: LlmContractConcept[];
  mainConcepts?: LlmContractConcept[];

  main_risk_increasing_factors?: LlmContractFeatureFactor[];
  mainRiskIncreasingFactors?: LlmContractFeatureFactor[];

  main_risk_decreasing_factors?: LlmContractFeatureFactor[];
  mainRiskDecreasingFactors?: LlmContractFeatureFactor[];

  allowed_claim_ids?: string[];
  allowedClaimIds?: string[];

  forbidden_rule_ids?: string[];
  forbiddenRuleIds?: string[];

  must_include?: string[];
  mustInclude?: string[];

  must_not?: string[];
  mustNot?: string[];

  required_output_sections?: string[];
  requiredOutputSections?: string[];

  [key: string]: unknown;
};

/**
 * Minimal shape of an Explanation IR record from Batch H.
 * We keep it flexible because Python-generated JSON may use snake_case.
 */
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

/**
 * Strict JSON shape we want the LLM to return.
 */
export type LlmGeneratedSections = {
  prediction: string;
  main_risk_drivers: string;
  risk_reducing_factors: string;
  limitations: string;
};

export type LlmGeneratedJson = {
  language: ExplanationLanguage;
  sections: LlmGeneratedSections;
  full_text: string;
};

/**
 * Raw LLM response metadata.
 */
export type LlmRawResponse = {
  provider: string;
  modelName: string;
  rawText: string;
  parsedJson?: LlmGeneratedJson;
  isParseableJson: boolean;
  errorMessage?: string;
};

/**
 * Generator metadata saved into each explanation record.
 */
export type LlmGeneratorInfo = {
  generator_type: GeneratorType;
  generator_name: string;
  generator_version: string;
  uses_external_ai_api: boolean;
  provider?: string;
  model_name?: string;
  prompt_version?: string;
};

/**
 * Output record from Batch I v1.0.
 */
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

  sections: LlmGeneratedSections;
  full_text: string;

  quality: {
    is_parseable_json: boolean;
    has_required_sections: boolean;
    section_count: number;
    character_count: number;
    warnings: string[];
    errors: string[];
  };

  metadata: {
    created_at: string;
    batch_id: string;
    input_source: InputSource;
    source_batch?: string;
    ir_schema_version?: string;
  };
};

/**
 * Prompt object passed to llm-client.
 */
export type BuiltPrompt = {
  system: string;
  user: string;
  promptVersion: string;
};

/**
 * Runtime config for the LLM generator.
 */
export type LlmRuntimeConfig = {
  provider: string;
  modelName: string;
  temperature: number;
  maxTokens: number;
  promptVersion: string;
};

/**
 * Type guard: checks whether an unknown object looks like ExplanationIrRecord.
 */
export function isExplanationIrRecord(
  value: unknown,
): value is ExplanationIrRecord {
  if (!value || typeof value !== "object") {
    return false;
  }

  const obj = value as Record<string, unknown>;

  return typeof obj.ir_id === "string";
}

/**
 * Type guard: checks whether LLM JSON has the required output shape.
 */
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
    typeof sections.main_risk_drivers === "string" &&
    typeof sections.risk_reducing_factors === "string" &&
    typeof sections.limitations === "string" &&
    typeof obj.full_text === "string"
  );
}

/**
 * Helper for reading both snake_case and camelCase keys.
 */
export function pickString(
  obj: Record<string, unknown> | undefined,
  keys: string[],
  fallback = "",
): string {
  if (!obj) return fallback;

  for (const key of keys) {
    const value = obj[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }
  }

  return fallback;
}

/**
 * Helper for reading numeric values safely.
 */
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

/**
 * Normalizes customer id from IR.
 */
export function getCustomerId(customer: IrCustomerInfo | undefined): string {
  if (!customer) return "unknown_customer";

  const raw = customer.SK_ID_CURR ?? customer.sk_id_curr ?? "unknown_customer";

  return String(raw);
}

/**
 * Normalizes run mode from IR or request.
 */
export function normalizeRunMode(
  value: unknown,
  fallback: RunMode = "evaluation",
): RunMode {
  if (value === "evaluation" || value === "inference") {
    return value;
  }

  return fallback;
}
