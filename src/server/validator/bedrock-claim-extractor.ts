// src/server/validator/bedrock-claim-extractor.ts

import "dotenv/config";
import { mkdir, writeFile } from "node:fs/promises";

import {
  BedrockRuntimeClient,
  ConverseCommand,
} from "@aws-sdk/client-bedrock-runtime";

import {
  CLAIM_EXTRACTION_JSON_SCHEMA,
  CLAIM_EXTRACTION_STAGE_VERSION,
  ClaimExtractionPayload,
  REQUIRED_EXPLANATION_SECTIONS,
  validateClaimExtractionPayload,
} from "./claim-schema";

export type BedrockClaimExtractorConfig = {
  regionName: string;
  modelId: string;
  maxTokens: number;
  temperature: number;
  extractorVersion: string;
};

export type GeneratedExplanationRecord = Record<string, unknown>;

export type BedrockClaimExtractionCallResult = {
  payload: ClaimExtractionPayload;
  prompt: string;
  rawResponse: unknown;
  rawText: string;
  usage: unknown;
  stopReason: string | null;
};

export function getDefaultBedrockClaimExtractorConfig(): BedrockClaimExtractorConfig {
  return {
    regionName: process.env.AWS_REGION ?? "us-east-1",
    modelId:
      process.env.BEDROCK_MODEL_ID ??
      "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    maxTokens: Number(process.env.BEDROCK_MAX_TOKENS ?? "3000"),
    temperature: Number(process.env.BEDROCK_TEMPERATURE ?? "0"),
    extractorVersion: CLAIM_EXTRACTION_STAGE_VERSION,
  };
}

export class BedrockStructuredClaimExtractor {
  private readonly client: BedrockRuntimeClient;
  private readonly config: BedrockClaimExtractorConfig;

  constructor(config = getDefaultBedrockClaimExtractorConfig()) {
    validateConfig(config);

    this.config = config;

    this.client = new BedrockRuntimeClient({
      region: config.regionName,
    });
  }

  getConfig(): BedrockClaimExtractorConfig {
    return this.config;
  }

  async extractClaimsFromExplanation(
    explanationRecord: GeneratedExplanationRecord,
  ): Promise<ClaimExtractionPayload> {
    const result =
      await this.extractClaimsFromExplanationWithRaw(explanationRecord);

    return result.payload;
  }

  async extractClaimsFromExplanationWithRaw(
    explanationRecord: GeneratedExplanationRecord,
  ): Promise<BedrockClaimExtractionCallResult> {
    const prompt = this.buildClaimExtractionPrompt(explanationRecord);

    const command = new ConverseCommand({
      modelId: this.config.modelId,
      messages: [
        {
          role: "user",
          content: [
            {
              text: prompt,
            },
          ],
        },
      ],
      inferenceConfig: {
        maxTokens: this.config.maxTokens,
        temperature: this.config.temperature,
      },
      outputConfig: {
        textFormat: {
          type: "json_schema",
          structure: {
            jsonSchema: {
              name: "batch_j_claim_extraction",
              description:
                "Extract structured claims from generated credit-risk explanations for Batch J faithfulness validation.",
              schema: JSON.stringify(CLAIM_EXTRACTION_JSON_SCHEMA),
            },
          },
        },
      },
    } as any);

    const response = await this.client.send(command);
    const rawText = extractTextFromConverseResponse(response);

    await maybeWriteBedrockDebugOutput({
      response,
      rawText,
      prompt,
      config: this.config,
    });

    let parsedJson: unknown;

    try {
      parsedJson = JSON.parse(rawText);
    } catch (error) {
      throw new Error(
        [
          "Bedrock response was not valid JSON.",
          `Parse error: ${(error as Error).message}`,
          `Raw preview: ${rawText.slice(0, 1000)}`,
        ].join("\n"),
      );
    }

    const payload = validateClaimExtractionPayload(parsedJson);

    return {
      payload,
      prompt,
      rawResponse: response,
      rawText,
      usage: (response as any)?.usage ?? null,
      stopReason:
        typeof (response as any)?.stopReason === "string"
          ? (response as any).stopReason
          : null,
    };
  }

  private buildClaimExtractionPrompt(
    record: GeneratedExplanationRecord,
  ): string {
    const sections = getSections(record);
    const fullText = getFullText(record, sections);

    const extractionInput = {
      task: "Batch J.1 Claim Extraction",
      language: "vi",
      role_of_this_stage:
        "Convert generated explanation text into structured claim JSON. Do not validate faithfulness.",
      important_rules: [
        "Extract only validation-relevant claims that appear in the explanation text or are directly represented in metadata.",
        "Do not invent customer facts.",
        "Do not invent evidence ids.",
        "Do not decide PASS or FAIL.",
        "Do not validate faithfulness in this stage.",
        "Preserve original text spans when useful, but avoid excessive phrase-level splitting.",

        "Use one claim for one distinct validation-relevant factual statement, not for every small phrase.",
        "Avoid duplicate claims for the same probability, threshold, feature, concept, evidence group, or limitation.",
        "Prefer compact section-level extraction over overly granular sentence splitting.",

        "For the prediction section, create at most 3 claims: predicted risk/probability, threshold comparison, and prediction limitation if present.",
        "For contribution_overview, create at most 2 claims: total/local contribution accounting and baseline/final probability if explicitly mentioned.",
        "For main_risk_drivers, extract only the top explicitly mentioned risk-driving factors. Prefer factors with numeric contribution values.",
        "For supporting_evidence_groups, extract compact group-level claims. Do not create one claim for every descriptive phrase.",
        "For risk_reducing_factors, extract only the top explicitly mentioned reducing factors, or one compact summary claim if no numeric contribution values are present.",
        "For limitations, extract only the core safety limitations: not causal, not a final credit decision, not a certain conclusion, model-contribution-only.",

        "Keep the total number of claims preferably between 8 and 18.",
        "If the explanation contains many similar feature or concept mentions, summarize them into compact concept-level claims.",
        "If direction is unclear, use unknown.",
        "If no numeric value is mentioned, use an empty string for value_mentioned.",
        "If no explicit evidence reference is present, use an empty array for evidence_refs.",
        "Extract forbidden wording and raw technical leakage if present; do not hide unsafe wording.",
        "Use safe Vietnamese concept-level normalized_subject when feature names are technical or unclear.",
      ],
      required_sections: REQUIRED_EXPLANATION_SECTIONS,
      claim_extraction_budget: {
        preferred_min_claims: 8,
        preferred_max_claims: 18,
        hard_max_claims: 22,
        reason:
          "Batch J.2 validates faithfulness against Explanation IR. The extractor should capture validation-relevant claims, not every phrase.",
      },
      explanation_record: {
        ir_id: getIrId(record, 0),
        explanation_id: getExplanationId(record),
        generator_type: getGeneratorType(record),
        sections,
        full_text: fullText,
        referenced_terms: getArrayField(record, "referenced_terms"),
        evidence_items_used: getArrayField(record, "evidence_items_used"),
        evidence_groups_used: getArrayField(record, "evidence_groups_used"),
      },
    };

    return JSON.stringify(extractionInput, null, 2);
  }
}

export function getSections(
  record: GeneratedExplanationRecord,
): Record<string, string> {
  const direct = record.sections;
  if (isPlainObject(direct)) return stringifyRecordValues(direct);

  const explanation = record.explanation;
  if (isPlainObject(explanation) && isPlainObject(explanation.sections)) {
    return stringifyRecordValues(explanation.sections);
  }

  const llmOutput = record.llm_output;
  if (isPlainObject(llmOutput) && isPlainObject(llmOutput.sections)) {
    return stringifyRecordValues(llmOutput.sections);
  }

  return {};
}

export function getFullText(
  record: GeneratedExplanationRecord,
  sections: Record<string, string>,
): string {
  const direct = getStringField(record, "full_text");
  if (direct) return direct;

  const explanation = record.explanation;
  if (isPlainObject(explanation)) {
    const text = getStringField(explanation, "full_text");
    if (text) return text;
  }

  const llmOutput = record.llm_output;
  if (isPlainObject(llmOutput)) {
    const text = getStringField(llmOutput, "full_text");
    if (text) return text;
  }

  return REQUIRED_EXPLANATION_SECTIONS.map(
    (sectionName) => sections[sectionName],
  )
    .filter((value) => typeof value === "string" && value.trim().length > 0)
    .join("\n\n");
}

export function getIrId(
  record: GeneratedExplanationRecord,
  index: number,
): string {
  /**
   * Batch I v1.2 LLM explanation records store the IR id as source_ir_id.
   * Older/other records may store it as ir_id or under nested source/metadata.
   */
  const sourceIrId = getStringField(record, "source_ir_id");
  if (sourceIrId) return sourceIrId;

  const direct = getStringField(record, "ir_id");
  if (direct) return direct;

  const source = record.source;
  if (isPlainObject(source)) {
    const sourceIrId = getStringField(source, "ir_id");
    if (sourceIrId) return sourceIrId;
  }

  const metadata = record.metadata;
  if (isPlainObject(metadata)) {
    const metadataIrId = getStringField(metadata, "ir_id");
    if (metadataIrId) return metadataIrId;
  }

  const explanation = record.explanation;
  if (isPlainObject(explanation)) {
    const explanationIrId = getStringField(explanation, "ir_id");
    if (explanationIrId) return explanationIrId;
  }

  const llmOutput = record.llm_output;
  if (isPlainObject(llmOutput)) {
    const llmOutputIrId = getStringField(llmOutput, "ir_id");
    if (llmOutputIrId) return llmOutputIrId;
  }

  const explanationId = getExplanationId(record, index);
  const inferred = inferIrIdFromExplanationId(explanationId);

  if (inferred) return inferred;

  return `missing_ir_id_row_${String(index).padStart(4, "0")}`;
}

export function getExplanationId(
  record: GeneratedExplanationRecord,
  index = 0,
): string {
  for (const key of ["explanation_id", "llm_explanation_id", "id"]) {
    const value = getStringField(record, key);
    if (value) return value;
  }

  return `explanation_row_${String(index).padStart(4, "0")}`;
}

export function getCustomerId(
  record: GeneratedExplanationRecord,
): string | null {
  for (const key of ["customer_id", "SK_ID_CURR", "sk_id_curr"]) {
    const value = record[key];
    if (value !== undefined && value !== null) return String(value);
  }

  const customer = record.customer;
  if (isPlainObject(customer)) {
    for (const key of ["customer_id", "SK_ID_CURR", "sk_id_curr"]) {
      const value = customer[key];
      if (value !== undefined && value !== null) return String(value);
    }
  }

  return null;
}

export function getGeneratorType(record: GeneratedExplanationRecord): string {
  const direct = getStringField(record, "generator_type");
  if (direct) return direct;

  const generator = record.generator;
  if (isPlainObject(generator)) {
    const generatorType = getStringField(generator, "generator_type");
    if (generatorType) return generatorType;
  }

  const metadata = record.metadata;
  if (isPlainObject(metadata)) {
    const metadataGeneratorType = getStringField(metadata, "generator_type");
    if (metadataGeneratorType) return metadataGeneratorType;
  }

  return "";
}

function inferIrIdFromExplanationId(explanationId: string): string {
  if (!explanationId) return "";

  let normalized = explanationId;

  if (normalized.startsWith("llm_api_")) {
    normalized = normalized.slice("llm_api_".length);
  } else if (normalized.startsWith("llm_")) {
    normalized = normalized.slice("llm_".length);
  }

  normalized = normalized.replace(/_attempt_\d+$/, "");

  /**
   * Examples:
   * llm_api_ir_xai_hist_gradient_boosting_v1_156227_top_high_risk_156227
   * → ir_xai_hist_gradient_boosting_v1_156227_top_high_risk
   *
   * llm_api_ir_xai_hist_gradient_boosting_v1_163956_top_high_risk_163956_attempt_1
   * → ir_xai_hist_gradient_boosting_v1_163956_top_high_risk
   */
  const match = normalized.match(
    /^(ir_xai_.+?_\d+_(?:top_high_risk|low_risk))(?:_\d+)?$/,
  );

  return match?.[1] ?? "";
}

function validateConfig(config: BedrockClaimExtractorConfig): void {
  if (!config.modelId) {
    throw new Error("BEDROCK_MODEL_ID is missing.");
  }

  if (!config.regionName) {
    throw new Error("AWS_REGION is missing.");
  }

  if (!Number.isFinite(config.maxTokens) || config.maxTokens <= 0) {
    throw new Error(`Invalid BEDROCK_MAX_TOKENS: ${config.maxTokens}`);
  }

  if (!Number.isFinite(config.temperature) || config.temperature < 0) {
    throw new Error(`Invalid BEDROCK_TEMPERATURE: ${config.temperature}`);
  }
}

function extractTextFromConverseResponse(response: any): string {
  const content = response?.output?.message?.content;

  if (!Array.isArray(content)) {
    throw new Error("Bedrock response missing output.message.content.");
  }

  const text = content
    .map((item) => {
      if (typeof item?.text === "string") return item.text;
      return "";
    })
    .filter(Boolean)
    .join("\n")
    .trim();

  if (!text) {
    throw new Error("Bedrock response did not contain text content.");
  }

  return text;
}

function getStringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value.trim() : "";
}

function getArrayField(
  record: Record<string, unknown>,
  key: string,
): unknown[] {
  const direct = record[key];

  if (Array.isArray(direct)) {
    return direct;
  }

  const explanation = record.explanation;

  if (isPlainObject(explanation) && Array.isArray(explanation[key])) {
    return explanation[key];
  }

  const llmOutput = record.llm_output;

  if (isPlainObject(llmOutput) && Array.isArray(llmOutput[key])) {
    return llmOutput[key];
  }

  return [];
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringifyRecordValues(
  record: Record<string, unknown>,
): Record<string, string> {
  const out: Record<string, string> = {};

  for (const [key, value] of Object.entries(record)) {
    if (typeof value === "string") {
      out[key] = value;
    } else if (value === null || value === undefined) {
      out[key] = "";
    } else {
      out[key] = String(value);
    }
  }

  return out;
}

async function maybeWriteBedrockDebugOutput(input: {
  response: unknown;
  rawText: string;
  prompt: string;
  config: BedrockClaimExtractorConfig;
}): Promise<void> {
  if (process.env.BEDROCK_DEBUG_OUTPUT !== "1") return;

  const debugDir = "data/reports/faithfulness_validation/debug";
  await mkdir(debugDir, { recursive: true });

  await writeFile(
    `${debugDir}/bedrock_debug_prompt.json`,
    JSON.stringify(
      {
        created_at: new Date().toISOString(),
        config: input.config,
        prompt: input.prompt,
      },
      null,
      2,
    ),
    "utf8",
  );

  await writeFile(
    `${debugDir}/bedrock_raw_response.json`,
    JSON.stringify(input.response, null, 2),
    "utf8",
  );

  await writeFile(
    `${debugDir}/bedrock_raw_text.json`,
    JSON.stringify(
      {
        created_at: new Date().toISOString(),
        rawText: input.rawText,
      },
      null,
      2,
    ),
    "utf8",
  );
}

function buildDirectTestExplanationRecord(): GeneratedExplanationRecord {
  return {
    ir_id: "ir_direct_test_001",
    explanation_id: "exp_direct_test_001",
    generator_type: "direct_bedrock_test",

    sections: {
      prediction:
        "Mô hình ước tính khách hàng có rủi ro gặp khó khăn trong thanh toán với xác suất 52.34%, cao hơn ngưỡng 50.00%.",
      contribution_overview:
        "Tổng đóng góp của các yếu tố quan trọng làm tăng nhẹ rủi ro so với mức nền của mô hình.",
      main_risk_drivers:
        "Một tín hiệu thuộc nhóm lịch sử thanh toán góp phần làm tăng rủi ro thêm +6.84 điểm phần trăm.",
      supporting_evidence_groups:
        "Các nhóm bằng chứng hỗ trợ gồm lịch sử thanh toán, thông tin khoản vay và tín hiệu hồ sơ khách hàng.",
      risk_reducing_factors:
        "Một số yếu tố khác làm giảm nhẹ rủi ro, nhưng không đủ để đảo chiều dự đoán.",
      limitations:
        "Lời giải thích này chỉ mô tả đóng góp vào dự đoán của mô hình, không chứng minh quan hệ nhân quả ngoài thực tế, không phải quyết định tín dụng cuối cùng và không phải kết luận chắc chắn.",
    },

    full_text: `
Mô hình ước tính khách hàng có rủi ro gặp khó khăn trong thanh toán với xác suất 52.34%, cao hơn ngưỡng 50.00%.

Tổng đóng góp của các yếu tố quan trọng làm tăng nhẹ rủi ro so với mức nền của mô hình.

Một tín hiệu thuộc nhóm lịch sử thanh toán góp phần làm tăng rủi ro thêm +6.84 điểm phần trăm.

Các nhóm bằng chứng hỗ trợ gồm lịch sử thanh toán, thông tin khoản vay và tín hiệu hồ sơ khách hàng.

Một số yếu tố khác làm giảm nhẹ rủi ro, nhưng không đủ để đảo chiều dự đoán.

Lời giải thích này chỉ mô tả đóng góp vào dự đoán của mô hình, không chứng minh quan hệ nhân quả ngoài thực tế, không phải quyết định tín dụng cuối cùng và không phải kết luận chắc chắn.
`.trim(),

    referenced_terms: [
      "rủi ro gặp khó khăn trong thanh toán",
      "xác suất",
      "ngưỡng",
      "đóng góp",
      "không chứng minh quan hệ nhân quả",
      "không phải quyết định tín dụng cuối cùng",
    ],

    evidence_items_used: ["ev_direct_test_001"],
    evidence_groups_used: ["group_payment_history"],
  };
}

async function runDirectClaimExtractionTest(): Promise<void> {
  const debugDir = "data/reports/faithfulness_validation/debug";
  await mkdir(debugDir, { recursive: true });

  console.log("Running direct Bedrock claim extraction test...");
  console.log("AWS_REGION:", process.env.AWS_REGION);
  console.log("BEDROCK_MODEL_ID:", process.env.BEDROCK_MODEL_ID);
  console.log("BEDROCK_MAX_TOKENS:", process.env.BEDROCK_MAX_TOKENS);
  console.log("BEDROCK_TEMPERATURE:", process.env.BEDROCK_TEMPERATURE);
  console.log("BEDROCK_DEBUG_OUTPUT:", process.env.BEDROCK_DEBUG_OUTPUT);

  const extractor = new BedrockStructuredClaimExtractor();
  const config = extractor.getConfig();

  console.log("\nResolved extractor config:");
  console.log(JSON.stringify(config, null, 2));

  const sampleRecord = buildDirectTestExplanationRecord();
  const result = await extractor.extractClaimsFromExplanation(sampleRecord);

  console.log("\nParsed claim extraction result:");
  console.log(JSON.stringify(result, null, 2));

  const outputPath =
    "data/reports/faithfulness_validation/debug/bedrock_claim_extractor_direct_test.json";

  await writeFile(
    outputPath,
    JSON.stringify(
      {
        test_name: "bedrock_claim_extractor_direct_test",
        created_at: new Date().toISOString(),
        config,
        input: sampleRecord,
        output: result,
        checks: {
          has_claims_array: Array.isArray(result.claims),
          claim_count_matches_array_length:
            result.claim_count === result.claims.length,
          claim_count: result.claim_count,
          has_prediction_claim: result.claims.some(
            (claim) => claim.claim_type === "prediction",
          ),
          has_limitation_claim: result.claims.some(
            (claim) => claim.claim_type === "limitation",
          ),
        },
      },
      null,
      2,
    ),
    "utf8",
  );

  console.log("\nDirect Bedrock claim extraction test passed.");
  console.log("Debug output written to:", outputPath);
}

const isDirectRun =
  process.argv[1] && process.argv[1].endsWith("bedrock-claim-extractor.ts");

if (isDirectRun) {
  runDirectClaimExtractionTest().catch((error) => {
    console.error("\nDirect Bedrock claim extraction test failed.");
    console.error(error);
    process.exit(1);
  });
}
