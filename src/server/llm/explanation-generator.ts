// src/server/llm/explanation-generator.ts

import type {
  ExplanationIrRecord,
  LlmExplanationRecord,
  LlmGeneratorInfo,
  LlmRawResponse,
  LlmRuntimeConfig,
  RunMode,
  InputSource,
} from "./explanation-schema";

import { getCustomerId, normalizeRunMode } from "./explanation-schema";

import { buildExplanationPrompt } from "./prompt-builder";
import { generateLlmJson, getLlmRuntimeConfig } from "./llm-client";

/**
 * Batch I v1.0 - Explanation Generator
 *
 * Responsibility:
 * One Explanation IR record -> one LLM explanation record.
 *
 * This file does not read/write files.
 * It only transforms objects.
 */

export type GenerateExplanationOptions = {
  runMode?: RunMode;
  batchId: string;
  inputSource: InputSource;
  config?: LlmRuntimeConfig;
};

export async function generateExplanationFromIr(
  irRecord: ExplanationIrRecord,
  options: GenerateExplanationOptions,
): Promise<LlmExplanationRecord> {
  const config = options.config ?? getLlmRuntimeConfig();

  const prompt = buildExplanationPrompt(irRecord);
  const llmResponse = await generateLlmJson(prompt, config);

  return buildExplanationRecord({
    irRecord,
    llmResponse,
    runMode: options.runMode ?? normalizeRunMode(irRecord.run_mode),
    batchId: options.batchId,
    inputSource: options.inputSource,
    config,
    promptVersion: prompt.promptVersion,
  });
}

type BuildExplanationRecordInput = {
  irRecord: ExplanationIrRecord;
  llmResponse: LlmRawResponse;
  runMode: RunMode;
  batchId: string;
  inputSource: InputSource;
  config: LlmRuntimeConfig;
  promptVersion: string;
};

function buildExplanationRecord(
  input: BuildExplanationRecordInput,
): LlmExplanationRecord {
  const {
    irRecord,
    llmResponse,
    runMode,
    batchId,
    inputSource,
    config,
    promptVersion,
  } = input;

  const now = new Date().toISOString();
  const customerId = getCustomerId(irRecord.customer);

  const parsedJson = llmResponse.parsedJson;

  const sections = parsedJson?.sections ?? {
    prediction: "",
    main_risk_drivers: "",
    risk_reducing_factors: "",
    limitations: "",
  };

  const fullText =
    parsedJson?.full_text ??
    [
      sections.prediction,
      sections.main_risk_drivers,
      sections.risk_reducing_factors,
      sections.limitations,
    ]
      .filter((item) => item.trim().length > 0)
      .join("\n\n");

  const errors: string[] = [];
  const warnings: string[] = [];

  if (!llmResponse.isParseableJson) {
    errors.push(
      llmResponse.errorMessage ??
        "LLM response is not parseable as required JSON.",
    );
  }

  const hasRequiredSections = checkRequiredSections(sections);

  if (!hasRequiredSections) {
    errors.push("LLM output does not contain all required sections.");
  }

  if (fullText.trim().length === 0) {
    errors.push("Generated full_text is empty.");
  }

  if (fullText.length > 6000) {
    warnings.push("Generated explanation is unusually long.");
  }

  const generator: LlmGeneratorInfo = {
    generator_type: "llm_api",
    generator_name: "nextjs_server_llm_generator",
    generator_version: "v1.0",
    uses_external_ai_api: true,
    provider: llmResponse.provider || config.provider,
    model_name: llmResponse.modelName || config.modelName,
    prompt_version: promptVersion,
  };

  return {
    explanation_id: buildExplanationId(irRecord, customerId),

    source_ir_id: irRecord.ir_id,
    source_evidence_id: irRecord.source_evidence_id,
    trace_id: irRecord.trace_id,

    run_mode: runMode,
    has_ground_truth: Boolean(irRecord.has_ground_truth),

    customer: irRecord.customer ?? {
      SK_ID_CURR: customerId,
    },
    model: irRecord.model,
    prediction_summary: irRecord.prediction_summary,

    generator,

    sections,
    full_text: fullText,

    quality: {
      is_parseable_json: llmResponse.isParseableJson,
      has_required_sections: hasRequiredSections,
      section_count: countNonEmptySections(sections),
      character_count: fullText.length,
      warnings,
      errors,
    },

    metadata: {
      created_at: now,
      batch_id: batchId,
      input_source: inputSource,
      source_batch: irRecord.source_batch,
      ir_schema_version: irRecord.ir_schema_version,
    },
  };
}

function buildExplanationId(
  irRecord: ExplanationIrRecord,
  customerId: string,
): string {
  const safeIrId = sanitizeId(irRecord.ir_id);
  const safeCustomerId = sanitizeId(customerId);

  return `llm_api_${safeIrId}_${safeCustomerId}`;
}

function sanitizeId(value: string): string {
  return value
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function checkRequiredSections(
  sections: LlmExplanationRecord["sections"],
): boolean {
  return (
    typeof sections.prediction === "string" &&
    sections.prediction.trim().length > 0 &&
    typeof sections.main_risk_drivers === "string" &&
    sections.main_risk_drivers.trim().length > 0 &&
    typeof sections.risk_reducing_factors === "string" &&
    sections.risk_reducing_factors.trim().length > 0 &&
    typeof sections.limitations === "string" &&
    sections.limitations.trim().length > 0
  );
}

function countNonEmptySections(
  sections: LlmExplanationRecord["sections"],
): number {
  return [
    sections.prediction,
    sections.main_risk_drivers,
    sections.risk_reducing_factors,
    sections.limitations,
  ].filter((item) => item.trim().length > 0).length;
}

export async function generateExplanation(input: {
  ir: {
    prediction?: {
      label?: string;
      probability?: number;
      threshold?: number;
    };
    topPositiveFeatures?: Array<{
      displayName?: string;
      value?: string | number | boolean | null;
    }>;
    topNegativeFeatures?: Array<{
      displayName?: string;
      value?: string | number | boolean | null;
    }>;
    modelMetadata?: {
      modelName?: string;
      modelVersion?: string;
    };
  };
  audience?: string;
}): Promise<{
  text: string;
  audience: string;
  promptVersion: string;
  llmModel: string;
}> {
  const ir = input.ir;
  const audience = input.audience ?? "general";

  const label = ir.prediction?.label ?? "unknown";
  const probability = ir.prediction?.probability ?? 0;
  const threshold = ir.prediction?.threshold ?? 0.5;

  const positiveText =
    ir.topPositiveFeatures
      ?.map(
        (feature) =>
          `${feature.displayName ?? "unknown"}=${String(feature.value ?? "")}`,
      )
      .join(", ") || "không có yếu tố làm tăng rủi ro nổi bật";

  const negativeText =
    ir.topNegativeFeatures
      ?.map(
        (feature) =>
          `${feature.displayName ?? "unknown"}=${String(feature.value ?? "")}`,
      )
      .join(", ") || "không có yếu tố làm giảm rủi ro nổi bật";

  return {
    audience,
    text:
      `Mô hình dự đoán nhãn '${label}' với xác suất ${probability} so với ngưỡng ${threshold}. ` +
      `Các yếu tố làm tăng rủi ro chính: ${positiveText}. ` +
      `Các yếu tố làm giảm rủi ro chính: ${negativeText}. ` +
      `Diễn giải này chỉ dựa trên thông tin XAI IR được cung cấp và không phải kết luận chắc chắn.`,
    promptVersion: "legacy_compat_v0.1",
    llmModel: "legacy-compat-wrapper",
  };
}