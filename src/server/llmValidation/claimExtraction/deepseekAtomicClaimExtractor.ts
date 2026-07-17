import "dotenv/config";

import extractionPrompt from "../../../../config/llm-validation/claim_extraction_prompt_v3.json";
import type {
  AtomicClaimExtractionPayload,
  ClaimExtractionRawResponse,
} from "../../../types/validation-claims";
import { sha256 } from "../../../utils/llmNarrative/utils";
import { postJsonWithRetry } from "../../llmNarrative/runners/httpHelpers";
import {
  ATOMIC_CLAIM_EXTRACTOR_VERSION,
  ATOMIC_CLAIM_PROMPT_VERSION,
  ATOMIC_CLAIM_RESPONSE_JSON_SCHEMA,
  validateAndNormalizeClaimPayload,
} from "./atomicClaimSchema";
import type { GenerationTextDocument } from "./generationTextAdapter";

// Khóa version trong code với prompt config để cache không thể dùng sai lineage.
if (extractionPrompt.prompt_version !== ATOMIC_CLAIM_PROMPT_VERSION) {
  throw new Error(
    `Claim prompt version mismatch: ${extractionPrompt.prompt_version}`,
  );
}

export type DeepSeekAtomicClaimExtractorConfig = {
  baseUrl: string;
  apiKeyEnv: string;
  modelId: string;
  maxTokens: number;
  temperature: number;
  topP: number;
  timeoutMs: number;
  maxRetries: number;
  retryDelayMs: number;
  inputCostPerMillion: number | null;
  outputCostPerMillion: number | null;
};

export class ClaimProviderCallError extends Error {
  readonly providerErrorType: string;

  constructor(providerErrorType: string, message: string) {
    super(message);
    this.name = "ClaimProviderCallError";
    this.providerErrorType = providerErrorType;
  }
}

export class ClaimResponseJsonError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ClaimResponseJsonError";
  }
}

// Client dùng đúng endpoint/config DeepSeek đã chạy batch 720 generation.
export class DeepSeekAtomicClaimExtractor {
  private readonly config: DeepSeekAtomicClaimExtractorConfig;

  constructor(config = getDefaultDeepSeekAtomicClaimExtractorConfig()) {
    validateConfig(config);
    this.config = config;
  }

  getConfig(): DeepSeekAtomicClaimExtractorConfig {
    return this.config;
  }

  async extractRaw(
    document: GenerationTextDocument,
  ): Promise<ClaimExtractionRawResponse> {
    const apiKey = process.env[this.config.apiKeyEnv];
    if (!apiKey?.trim()) {
      return failedRawResponse({
        errorType: "MISSING_API_KEY",
        errorMessage: `Missing environment variable: ${this.config.apiKeyEnv}`,
      });
    }

    const result = await postJsonWithRetry({
      url: buildChatCompletionsUrl(this.config.baseUrl),
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: {
        model: this.config.modelId,
        messages: [
          {
            role: "system",
            content: extractionPrompt.system_instruction,
          },
          {
            role: "user",
            content: buildPrompt(document),
          },
        ],
        temperature: this.config.temperature,
        top_p: this.config.topP,
        max_tokens: this.config.maxTokens,
        frequency_penalty: 0,
        presence_penalty: 0,
        response_format: {
          type: "json_object",
        },
        stream: false,
        thinking: {
          type: "disabled",
        },
      },
      timeout_ms: this.config.timeoutMs,
      max_retries: this.config.maxRetries,
      retry_delay_ms: this.config.retryDelayMs,
    });

    if (!result.ok) {
      return failedRawResponse({
        rawText: result.response_text,
        responseReceived: result.status_code !== null,
        retryCount: result.retry_count,
        httpStatus: result.status_code,
        errorType: result.error_type ?? "DEEPSEEK_REQUEST_FAILED",
        errorMessage: result.error_message ?? "DeepSeek request failed.",
      });
    }

    return readChatCompletion(
      result.response_json,
      result.response_text,
      result.retry_count,
      result.status_code,
    );
  }
}

// Parse tách khỏi network để response lỗi vẫn giữ hash, usage và provider metadata.
export function parseClaimExtractionResponse(
  rawText: string | null,
  document: GenerationTextDocument,
): AtomicClaimExtractionPayload {
  if (!rawText?.trim()) {
    throw new ClaimResponseJsonError("DeepSeek response content is empty.");
  }

  const parsed = parseJsonObject(rawText);
  if (parsed === null) {
    throw new ClaimResponseJsonError(
      "DeepSeek response does not contain a valid JSON object.",
    );
  }

  return validateAndNormalizeClaimPayload(parsed, document);
}

export function getDefaultDeepSeekAtomicClaimExtractorConfig(): DeepSeekAtomicClaimExtractorConfig {
  return {
    baseUrl: process.env.DEEPSEEK_BASE_URL ?? "https://api.deepseek.com",
    apiKeyEnv: "DEEPSEEK_API_KEY",
    modelId:
      process.env.DEEPSEEK_CLAIM_EXTRACTOR_MODEL_ID ??
      "deepseek-v4-flash",
    maxTokens: readPositiveInteger(
      process.env.DEEPSEEK_CLAIM_MAX_TOKENS,
      3000,
    ),
    temperature: 0,
    topP: 1,
    timeoutMs: readPositiveInteger(
      process.env.DEEPSEEK_CLAIM_TIMEOUT_MS,
      120_000,
    ),
    maxRetries: readNonNegativeInteger(
      process.env.DEEPSEEK_CLAIM_MAX_RETRIES,
      3,
    ),
    retryDelayMs: readPositiveInteger(
      process.env.DEEPSEEK_CLAIM_RETRY_DELAY_MS,
      1000,
    ),
    inputCostPerMillion: readOptionalNonNegativeNumber(
      process.env.DEEPSEEK_INPUT_COST_PER_MILLION,
    ),
    outputCostPerMillion: readOptionalNonNegativeNumber(
      process.env.DEEPSEEK_OUTPUT_COST_PER_MILLION,
    ),
  };
}

function buildPrompt(document: GenerationTextDocument): string {
  return JSON.stringify(
    {
      task: "Atomic claim extraction only; do not validate faithfulness.",
      language: "vi",
      prompt_version: ATOMIC_CLAIM_PROMPT_VERSION,
      response_contract: "Return exactly one JSON object and no prose.",
      rules: extractionPrompt.rules,
      generation_text: buildSemanticGenerationText(document),
      available_source_sections: document.section_spans
        .filter((span) => span.source_section !== "factor_name")
        .map((span) => ({
          source_section: span.source_section,
          source_factor_id: span.source_factor_id ?? "",
        })),
      factor_metadata_without_model_identity: document.factor_metadata,
      output_json_schema: ATOMIC_CLAIM_RESPONSE_JSON_SCHEMA,
    },
    null,
    2,
  );
}

// factor_name đã được xử lý deterministic nên không gửi lại để giảm input token.
function buildSemanticGenerationText(
  document: GenerationTextDocument,
): string {
  return document.section_spans
    .filter((span) => span.source_section !== "factor_name")
    .map((span) => {
      const factorLabel = span.source_factor_id
        ? `:${span.source_factor_id}`
        : "";
      const sourceText = document.generation_text.slice(span.start, span.end);
      return `[${span.source_section}${factorLabel}]\n${sourceText}`;
    })
    .join("\n\n");
}

function readChatCompletion(
  value: unknown,
  rawProviderText: string | null,
  retryCount: number,
  httpStatus: number | null,
): ClaimExtractionRawResponse {
  if (!value || typeof value !== "object") {
    return failedRawResponse({
      rawText: rawProviderText,
      responseReceived: true,
      retryCount,
      httpStatus,
      errorType: "PROVIDER_RESPONSE_NOT_JSON",
      errorMessage: "DeepSeek returned a non-JSON API response.",
    });
  }

  const source = value as Record<string, unknown>;
  const choices = Array.isArray(source.choices) ? source.choices : [];
  const firstChoice = isObject(choices[0]) ? choices[0] : {};
  const message = isObject(firstChoice.message) ? firstChoice.message : {};
  const usage = isObject(source.usage) ? source.usage : {};
  const content = typeof message.content === "string"
    ? message.content.trim()
    : "";

  if (!content) {
    return failedRawResponse({
      rawText: rawProviderText,
      responseReceived: true,
      usage,
      retryCount,
      httpStatus,
      providerRequestId: readStringOrNull(source.id),
      providerReturnedModelId: readStringOrNull(source.model),
      errorType: "EMPTY_PROVIDER_CONTENT",
      errorMessage: "DeepSeek response did not contain message content.",
    });
  }

  return {
    raw_text: content,
    usage,
    stop_reason: readStringOrNull(firstChoice.finish_reason),
    response_received: true,
    provider_request_id: readStringOrNull(source.id),
    provider_returned_model_id: readStringOrNull(source.model),
    retry_count: retryCount,
    http_status: httpStatus,
    api_error_type: null,
    api_error_message: null,
  };
}

function failedRawResponse(input: {
  rawText?: string | null;
  responseReceived?: boolean;
  usage?: unknown;
  retryCount?: number;
  httpStatus?: number | null;
  providerRequestId?: string | null;
  providerReturnedModelId?: string | null;
  errorType: string;
  errorMessage: string;
}): ClaimExtractionRawResponse {
  return {
    raw_text: input.rawText ?? null,
    usage: input.usage ?? null,
    stop_reason: null,
    response_received: input.responseReceived ?? false,
    provider_request_id: input.providerRequestId ?? null,
    provider_returned_model_id: input.providerReturnedModelId ?? null,
    retry_count: input.retryCount ?? 0,
    http_status: input.httpStatus ?? null,
    api_error_type: input.errorType,
    api_error_message: input.errorMessage,
  };
}

function parseJsonObject(rawText: string): unknown | null {
  const trimmed = stripMarkdownFence(rawText.trim());
  try {
    const direct = JSON.parse(trimmed) as unknown;
    return isObject(direct) ? direct : null;
  } catch {
    const extracted = extractFirstJsonObject(trimmed);
    if (!extracted) return null;
    try {
      const parsed = JSON.parse(extracted) as unknown;
      return isObject(parsed) ? parsed : null;
    } catch {
      return null;
    }
  }
}

function stripMarkdownFence(value: string): string {
  const match = value.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/iu);
  return match?.[1]?.trim() ?? value;
}

function extractFirstJsonObject(value: string): string | null {
  const start = value.indexOf("{");
  if (start < 0) return null;

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < value.length; index += 1) {
    const character = value[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') inString = false;
      continue;
    }
    if (character === '"') inString = true;
    else if (character === "{") depth += 1;
    else if (character === "}") {
      depth -= 1;
      if (depth === 0) return value.slice(start, index + 1);
    }
  }
  return null;
}

function buildChatCompletionsUrl(baseUrl: string): string {
  const normalized = baseUrl.replace(/\/+$/u, "");
  return normalized.endsWith("/chat/completions")
    ? normalized
    : `${normalized}/chat/completions`;
}

function validateConfig(config: DeepSeekAtomicClaimExtractorConfig): void {
  if (!config.baseUrl.trim()) throw new Error("DeepSeek base URL is required.");
  if (!config.apiKeyEnv.trim()) throw new Error("DeepSeek API key env is required.");
  if (!config.modelId.trim()) throw new Error("DeepSeek model ID is required.");
  if (!Number.isInteger(config.maxTokens) || config.maxTokens < 1) {
    throw new Error("DeepSeek maxTokens must be a positive integer.");
  }
  if (config.temperature !== 0) {
    throw new Error("Atomic claim extraction temperature must stay frozen at 0.");
  }
  if (config.topP !== 1) {
    throw new Error("Atomic claim extraction topP must stay frozen at 1.");
  }
}

function readPositiveInteger(value: string | undefined, fallback: number): number {
  const parsed = value === undefined ? fallback : Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`Expected a positive integer, received: ${String(value)}`);
  }
  return parsed;
}

function readNonNegativeInteger(
  value: string | undefined,
  fallback: number,
): number {
  const parsed = value === undefined ? fallback : Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`Expected a non-negative integer, received: ${String(value)}`);
  }
  return parsed;
}

function readOptionalNonNegativeNumber(value: string | undefined): number | null {
  if (value === undefined || !value.trim()) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new Error(`Expected a non-negative number, received: ${value}`);
  }
  return parsed;
}

function readStringOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export const DEEPSEEK_EXTRACTOR_LINEAGE = {
  extractorVersion: ATOMIC_CLAIM_EXTRACTOR_VERSION,
  promptVersion: ATOMIC_CLAIM_PROMPT_VERSION,
  promptSha256: sha256(JSON.stringify(extractionPrompt)),
} as const;
