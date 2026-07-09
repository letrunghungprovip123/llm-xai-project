// src/server/llm/explanation-generator.ts

import type {
  ExplanationIrRecord,
  InputSource,
  LlmEvidenceGroupUsed,
  LlmEvidenceItemUsed,
  LlmExplanationPayload,
  LlmExplanationRecord,
  LlmGeneratedSections,
  LlmGeneratorInfo,
  LlmRawResponse,
  LlmReferencedTerm,
  LlmRuntimeConfig,
  RegenerationFeedback,
  RunMode,
} from "./explanation-schema";

import {
  asArray,
  asRecord,
  getCustomerId,
  normalizeRunMode,
} from "./explanation-schema";

import { buildExplanationPrompt } from "./prompt-builder";
import { generateLlmJson, getLlmRuntimeConfig } from "./llm-client";

/**
 * Batch I v1.2 - Explanation Generator
 *
 * One Explanation IR record -> one LLM API explanation record.
 *
 * Feedback-ready design:
 * - attempt = 0: normal first-generation explanation.
 * - attempt > 0: controlled regeneration using Batch J feedback.
 *
 * Important:
 * - This file does NOT implement auto-loop.
 * - It only exposes a reusable generator function that can receive feedback.
 */

export type GenerateExplanationOptions = {
  runMode?: RunMode;
  batchId: string;
  inputSource: InputSource;
  config?: LlmRuntimeConfig;

  /**
   * Optional feedback from Batch J validation.
   * This is used only for manual/controlled regeneration.
   */
  feedback?: RegenerationFeedback | null;

  /**
   * 0 = first generation.
   * 1+ = regeneration attempt.
   */
  generationAttempt?: number;
};

export async function generateExplanationFromIr(
  irRecord: ExplanationIrRecord,
  options: GenerateExplanationOptions,
): Promise<LlmExplanationRecord> {
  const config = options.config ?? getLlmRuntimeConfig();
  const feedback = options.feedback ?? null;
  const generationAttempt = options.generationAttempt ?? feedback?.attempt ?? 0;

  const prompt = buildExplanationPrompt(irRecord, feedback);
  const llmResponse = await generateLlmJson(prompt, config);

  return buildExplanationRecord({
    irRecord,
    llmResponse,
    runMode: options.runMode ?? normalizeRunMode(irRecord.run_mode),
    batchId: options.batchId,
    inputSource: options.inputSource,
    config,
    promptVersion: prompt.promptVersion,
    feedback,
    generationAttempt,
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
  feedback: RegenerationFeedback | null;
  generationAttempt: number;
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
    feedback,
    generationAttempt,
  } = input;

  const now = new Date().toISOString();
  const customerId = getCustomerId(irRecord.customer);
  const parsedJson = llmResponse.parsedJson;

  const sections = parsedJson?.sections ?? emptySections();
  const fullText = buildFullTextFromSections(sections);

  const referencedTerms = normalizeReferencedTerms(
    parsedJson?.referenced_terms ?? [],
  );

  const evidenceItemsUsed = normalizeEvidenceItemsUsed(
    parsedJson?.evidence_items_used ?? [],
  );

  const evidenceGroupsUsed = normalizeEvidenceGroupsUsed(
    parsedJson?.evidence_groups_used ?? [],
  );

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
    errors.push("LLM output does not contain all required v1.2 sections.");
  }

  if (fullText.trim().length === 0) {
    errors.push("Generated full_text is empty.");
  }

  if (fullText.length > 8000) {
    warnings.push("Generated explanation is unusually long.");
  }

  if (referencedTerms.length === 0) {
    warnings.push("LLM output does not include referenced_terms.");
  }

  if (evidenceItemsUsed.length === 0) {
    warnings.push("LLM output does not include evidence_items_used.");
  }

  if (evidenceGroupsUsed.length === 0) {
    warnings.push("LLM output does not include evidence_groups_used.");
  }

  if (feedback) {
    warnings.push(`Generated with Batch J feedback: ${feedback.feedback_id}.`);
  }

  const containsForbidden = containsForbiddenWording(fullText);
  const containsRawTechnical = containsRawTechnicalName(fullText);

  if (containsForbidden) {
    warnings.push("Generated explanation contains forbidden wording.");
  }

  if (containsRawTechnical) {
    warnings.push(
      "Generated explanation may contain raw technical feature name.",
    );
  }

  const generator: LlmGeneratorInfo = {
    generator_type: "llm_api",
    generator_name: "nextjs_server_llm_generator",
    generator_version: "v1.2",
    uses_external_ai_api: true,
    provider: llmResponse.provider || config.provider,
    model_name: llmResponse.modelName || config.modelName,
    prompt_version: promptVersion,
  };

  const explanation: LlmExplanationPayload = {
    language: "vi",
    sections,
    full_text: fullText,
    referenced_terms: referencedTerms,
    evidence_items_used: evidenceItemsUsed,
    evidence_groups_used: evidenceGroupsUsed,
  };

  return {
    explanation_id: buildExplanationId(irRecord, customerId, generationAttempt),
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
    explanation,
    source_contract_summary: buildSourceContractSummary(irRecord),
    quality: {
      is_parseable_json: llmResponse.isParseableJson,
      has_required_sections: hasRequiredSections,
      section_count: countNonEmptySections(sections),
      character_count: fullText.length,
      has_referenced_terms: referencedTerms.length > 0,
      has_evidence_items_used: evidenceItemsUsed.length > 0,
      has_evidence_groups_used: evidenceGroupsUsed.length > 0,
      contains_forbidden_wording: containsForbidden,
      contains_raw_technical_name: containsRawTechnical,
      warnings,
      errors,
    },
    raw_response: {
      provider: llmResponse.provider,
      model_name: llmResponse.modelName,
      raw_text_preview: llmResponse.rawText.slice(0, 2000),
      usage: llmResponse.usage,
    },
    metadata: {
      created_at: now,
      batch_id: batchId,
      batch_version: "v1.2",
      input_source: inputSource,
      source_batch: irRecord.source_batch,
      ir_schema_version: irRecord.ir_schema_version,
      generation_attempt: generationAttempt,
      has_regeneration_feedback: Boolean(feedback),
      feedback_id: feedback?.feedback_id,
      parent_explanation_id: feedback?.explanation_id,
    },
  };
}

function emptySections(): LlmGeneratedSections {
  return {
    prediction: "",
    contribution_overview: "",
    main_risk_drivers: "",
    supporting_evidence_groups: "",
    risk_reducing_factors: "",
    limitations: "",
  };
}

function buildFullTextFromSections(sections: LlmGeneratedSections): string {
  return [
    sections.prediction,
    sections.contribution_overview,
    sections.main_risk_drivers,
    sections.supporting_evidence_groups,
    sections.risk_reducing_factors,
    sections.limitations,
  ]
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
    .join("\n\n");
}

function checkRequiredSections(sections: LlmGeneratedSections): boolean {
  return (
    isNonEmptyString(sections.prediction) &&
    isNonEmptyString(sections.contribution_overview) &&
    isNonEmptyString(sections.main_risk_drivers) &&
    isNonEmptyString(sections.supporting_evidence_groups) &&
    isNonEmptyString(sections.risk_reducing_factors) &&
    isNonEmptyString(sections.limitations)
  );
}

function countNonEmptySections(sections: LlmGeneratedSections): number {
  return [
    sections.prediction,
    sections.contribution_overview,
    sections.main_risk_drivers,
    sections.supporting_evidence_groups,
    sections.risk_reducing_factors,
    sections.limitations,
  ].filter(isNonEmptyString).length;
}

function isNonEmptyString(value: string): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

function normalizeReferencedTerms(value: unknown[]): LlmReferencedTerm[] {
  return asArray<Record<string, unknown>>(value)
    .map((item) => ({
      term_id: String(item.term_id ?? item.termId ?? "").trim(),
      term_type: String(item.term_type ?? item.termType ?? "").trim(),
      mention: String(item.mention ?? "").trim(),
    }))
    .filter(
      (item) =>
        item.term_id.length > 0 &&
        item.term_type.length > 0 &&
        item.mention.length > 0,
    );
}

function normalizeEvidenceItemsUsed(value: unknown[]): LlmEvidenceItemUsed[] {
  return asArray<Record<string, unknown>>(value)
    .map((item) => ({
      evidence_id: String(item.evidence_id ?? item.evidenceId ?? "").trim(),
      evidence_type: String(
        item.evidence_type ?? item.evidenceType ?? "",
      ).trim(),
      direction: String(item.direction ?? "unknown"),
      usage: String(item.usage ?? "unknown"),
    }))
    .filter(
      (item) => item.evidence_id.length > 0 && item.evidence_type.length > 0,
    );
}

function normalizeEvidenceGroupsUsed(value: unknown[]): LlmEvidenceGroupUsed[] {
  return asArray<Record<string, unknown>>(value)
    .map((item) => ({
      group_id: String(item.group_id ?? item.groupId ?? "").trim(),
      concept_id:
        item.concept_id === null || item.conceptId === null
          ? null
          : String(item.concept_id ?? item.conceptId ?? "").trim() || null,
      usage: String(item.usage ?? "unknown"),
    }))
    .filter((item) => item.group_id.length > 0);
}

function buildSourceContractSummary(irRecord: ExplanationIrRecord) {
  const contract = asRecord(irRecord.llm_input_contract);

  const requiredOutputSections = asArray<string>(
    contract.required_output_sections ?? contract.requiredOutputSections,
  );

  const primaryFeatures = asArray(
    contract.primary_features ?? contract.primaryFeatures,
  );

  const supportingGroups = asArray(
    contract.supporting_feature_groups ?? contract.supportingFeatureGroups,
  );

  return {
    required_output_sections:
      requiredOutputSections.length > 0
        ? requiredOutputSections
        : [
            "prediction",
            "contribution_overview",
            "main_risk_drivers",
            "supporting_evidence_groups",
            "risk_reducing_factors",
            "limitations",
          ],
    allowed_claim_count: asArray(
      contract.allowed_claim_ids ?? contract.allowedClaimIds,
    ).length,
    forbidden_rule_count: asArray(
      contract.forbidden_rule_ids ?? contract.forbiddenRuleIds,
    ).length,
    primary_feature_count: primaryFeatures.length,
    supporting_group_count: supportingGroups.length,
    has_contribution_accounting: Boolean(
      contract.contribution_accounting ?? contract.contributionAccounting,
    ),
  };
}

function containsForbiddenWording(text: string): boolean {
  const forbidden = [
    "vỡ nợ",
    "chắc chắn không trả",
    "chắc chắn sẽ trả",
    "TARGET",
    "true_label",
    "true positive",
    "false positive",
    "false negative",
  ];

  const lowered = text.toLowerCase();
  return forbidden.some((item) => lowered.includes(item.toLowerCase()));
}

function containsRawTechnicalName(text: string): boolean {
  const lowered = text.toLowerCase();

  const suspicious = [
    "ext_source",
    "bureau credit",
    "bureau balance",
    "installment_",
    "pos_cash",
    "credit_card",
    "occupation_type",
    "name_income_type",
    "__",
  ];

  return suspicious.some((item) => lowered.includes(item));
}

function buildExplanationId(
  irRecord: ExplanationIrRecord,
  customerId: string,
  generationAttempt: number,
): string {
  const safeIrId = sanitizeId(irRecord.ir_id);
  const safeCustomerId = sanitizeId(customerId);

  const base = `llm_api_${safeIrId}_${safeCustomerId}`;

  if (generationAttempt > 0) {
    return `${base}_attempt_${generationAttempt}`;
  }

  return base;
}

function sanitizeId(value: string): string {
  return value
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/**
 * Legacy compatibility wrapper.
 *
 * Some older pipeline/validator files still import generateExplanation().
 * Batch I v1.2 official path should use generateExplanationFromIr().
 *
 * This wrapper is kept only to avoid breaking older code paths.
 */
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
      ?.map((feature) => {
        const name = feature.displayName ?? "yếu tố không xác định";
        const value =
          feature.value === null || feature.value === undefined
            ? ""
            : `=${String(feature.value)}`;

        return `${name}${value}`;
      })
      .join(", ") || "không có yếu tố làm tăng rủi ro nổi bật";

  const negativeText =
    ir.topNegativeFeatures
      ?.map((feature) => {
        const name = feature.displayName ?? "yếu tố không xác định";
        const value =
          feature.value === null || feature.value === undefined
            ? ""
            : `=${String(feature.value)}`;

        return `${name}${value}`;
      })
      .join(", ") || "không có yếu tố làm giảm rủi ro nổi bật";

  return {
    audience,
    text:
      `Mô hình dự đoán nhãn '${label}' với xác suất ${probability} so với ngưỡng ${threshold}. ` +
      `Các yếu tố làm tăng rủi ro chính: ${positiveText}. ` +
      `Các yếu tố làm giảm rủi ro chính: ${negativeText}. ` +
      `Diễn giải này chỉ dựa trên thông tin XAI IR được cung cấp, không phải kết luận chắc chắn và không chứng minh quan hệ nhân quả ngoài thực tế.`,
    promptVersion: "legacy_compat_v0.1",
    llmModel: "legacy-compat-wrapper",
  };
}
