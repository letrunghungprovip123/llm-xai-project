// src/server/llm/llm-client.ts

import type {
  BuiltPrompt,
  LlmGeneratedJson,
  LlmRawResponse,
  LlmRuntimeConfig,
} from "./explanation-schema";

import { isLlmGeneratedJson } from "./explanation-schema";

/**
 * Batch I v1.0 - LLM Client
 *
 * Responsibility:
 * - Receive a BuiltPrompt from prompt-builder.ts
 * - Call an OpenAI-compatible Chat Completions API
 * - Parse the model response as strict JSON
 * - Validate that the JSON matches LlmGeneratedJson schema
 *
 * Important:
 * - No LangChain here.
 * - Do not use this file from client components.
 * - API key must stay server-side in .env.local.
 */

const DEFAULT_PROVIDER = "openai_compatible";
const DEFAULT_MODEL = "gpt-4o-mini";
const DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions";
const DEFAULT_TEMPERATURE = 0.1;
const DEFAULT_MAX_TOKENS = 1200;
const DEFAULT_PROMPT_VERSION = "batch_i_llm_prompt_v1.0";

export type OpenAiCompatibleChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

type OpenAiCompatibleRequestBody = {
  model: string;
  messages: OpenAiCompatibleChatMessage[];
  temperature: number;
  max_tokens: number;
  response_format?: {
    type: "json_object";
  };
};

type OpenAiCompatibleResponse = {
  id?: string;
  object?: string;
  created?: number;
  model?: string;
  choices?: Array<{
    index?: number;
    message?: {
      role?: string;
      content?: string | null;
    };
    finish_reason?: string | null;
  }>;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
  error?: {
    message?: string;
    type?: string;
    code?: string;
  };
};

/**
 * Reads runtime config from environment variables.
 *
 * .env.local example:
 *
 * LLM_PROVIDER=openai_compatible
 * LLM_MODEL=gpt-4o-mini
 * LLM_API_KEY=your_api_key_here
 * LLM_BASE_URL=https://api.openai.com/v1/chat/completions
 * LLM_TEMPERATURE=0.1
 * LLM_MAX_TOKENS=1200
 */
export function getLlmRuntimeConfig(): LlmRuntimeConfig {
  return {
    provider: process.env.LLM_PROVIDER || DEFAULT_PROVIDER,
    modelName: process.env.LLM_MODEL || DEFAULT_MODEL,
    temperature: parseOptionalNumber(
      process.env.LLM_TEMPERATURE,
      DEFAULT_TEMPERATURE,
    ),
    maxTokens: parseOptionalNumber(
      process.env.LLM_MAX_TOKENS,
      DEFAULT_MAX_TOKENS,
    ),
    promptVersion: process.env.LLM_PROMPT_VERSION || DEFAULT_PROMPT_VERSION,
  };
}

/**
 * Main public function used by explanation-generator.ts.
 */
export async function generateLlmJson(
  prompt: BuiltPrompt,
  config: LlmRuntimeConfig = getLlmRuntimeConfig(),
): Promise<LlmRawResponse> {
  const apiKey = process.env.LLM_API_KEY;
  const baseUrl = process.env.LLM_BASE_URL || DEFAULT_BASE_URL;

  if (!apiKey || apiKey.trim().length === 0) {
    return {
      provider: config.provider,
      modelName: config.modelName,
      rawText: "",
      isParseableJson: false,
      errorMessage:
        "Missing LLM_API_KEY. Please set LLM_API_KEY in .env.local.",
    };
  }

  const requestBody: OpenAiCompatibleRequestBody = {
    model: config.modelName,
    messages: [
      {
        role: "system",
        content: prompt.system,
      },
      {
        role: "user",
        content: prompt.user,
      },
    ],
    temperature: config.temperature,
    max_tokens: config.maxTokens,
    ...(isJsonModeEnabled() && {
      response_format: {
        type: "json_object" as const,
      },
    }),
  };

  try {
    const response = await fetch(baseUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requestBody),
    });

    const responseText = await response.text();

    if (!response.ok) {
      return {
        provider: config.provider,
        modelName: config.modelName,
        rawText: responseText,
        isParseableJson: false,
        errorMessage: `LLM API request failed with status ${response.status}: ${responseText}`,
      };
    }

    const apiResponse = safeJsonParse<OpenAiCompatibleResponse>(responseText);

    if (!apiResponse.ok) {
      return {
        provider: config.provider,
        modelName: config.modelName,
        rawText: responseText,
        isParseableJson: false,
        errorMessage: `Failed to parse LLM API response JSON: ${apiResponse.errorMessage}`,
      };
    }

    if (apiResponse.value.error?.message) {
      return {
        provider: config.provider,
        modelName: config.modelName,
        rawText: responseText,
        isParseableJson: false,
        errorMessage: apiResponse.value.error.message,
      };
    }

    const rawContent =
      apiResponse.value.choices?.[0]?.message?.content?.trim() ?? "";

    if (!rawContent) {
      return {
        provider: config.provider,
        modelName: config.modelName,
        rawText: "",
        isParseableJson: false,
        errorMessage: "LLM API response did not contain message content.",
      };
    }

    const parsed = parseLlmGeneratedJson(rawContent);

    return {
      provider: config.provider,
      modelName: apiResponse.value.model || config.modelName,
      rawText: rawContent,
      parsedJson: parsed.ok ? parsed.value : undefined,
      isParseableJson: parsed.ok,
      errorMessage: parsed.ok ? undefined : parsed.errorMessage,
    };
  } catch (error) {
    return {
      provider: config.provider,
      modelName: config.modelName,
      rawText: "",
      isParseableJson: false,
      errorMessage:
        error instanceof Error
          ? error.message
          : "Unknown error while calling LLM API.",
    };
  }
}

/**
 * Parse and validate the actual text returned by the model.
 *
 * The prompt asks for pure JSON, but this parser is defensive:
 * - accepts pure JSON
 * - tries to extract the first JSON object if the model accidentally wraps it
 */
export function parseLlmGeneratedJson(rawText: string):
  | {
      ok: true;
      value: LlmGeneratedJson;
    }
  | {
      ok: false;
      errorMessage: string;
    } {
  const cleanedText = stripMarkdownJsonFence(rawText.trim());

  const directParse = safeJsonParse<unknown>(cleanedText);

  if (directParse.ok && isLlmGeneratedJson(directParse.value)) {
    return {
      ok: true,
      value: directParse.value,
    };
  }

  const extractedJson = extractFirstJsonObject(cleanedText);

  if (!extractedJson) {
    return {
      ok: false,
      errorMessage:
        "LLM output is not valid JSON and no JSON object could be extracted.",
    };
  }

  const extractedParse = safeJsonParse<unknown>(extractedJson);

  if (!extractedParse.ok) {
    return {
      ok: false,
      errorMessage: `Extracted JSON could not be parsed: ${extractedParse.errorMessage}`,
    };
  }

  if (!isLlmGeneratedJson(extractedParse.value)) {
    return {
      ok: false,
      errorMessage:
        "Parsed JSON does not match required LLM output schema. Required shape: { language: 'vi', sections: { prediction, main_risk_drivers, risk_reducing_factors, limitations }, full_text }.",
    };
  }

  return {
    ok: true,
    value: extractedParse.value,
  };
}

/**
 * Optional test helper.
 *
 * This is not used in the official run unless you explicitly import it.
 * It can stay here safely because official generator uses generateLlmJson().
 */
export async function generateMockLlmJson(
  prompt: BuiltPrompt,
  config: LlmRuntimeConfig = getLlmRuntimeConfig(),
): Promise<LlmRawResponse> {
  const mockJson: LlmGeneratedJson = {
    language: "vi",
    sections: {
      prediction:
        "Mô hình đưa ra dự đoán dựa trên xác suất và ngưỡng phân loại được cung cấp trong Explanation IR.",
      main_risk_drivers:
        "Các yếu tố được phép hiển thị trong contract cho thấy một số thông tin góp phần làm tăng rủi ro dự đoán của mô hình.",
      risk_reducing_factors:
        "Không có yếu tố làm giảm rủi ro nào đủ điều kiện hiển thị trực tiếp trong contract hiện tại.",
      limitations:
        "Các yếu tố trên chỉ mô tả đóng góp vào dự đoán của mô hình, không chứng minh quan hệ nhân quả ngoài thực tế và không phải kết luận chắc chắn về hành vi trả nợ.",
    },
    full_text:
      "Mô hình đưa ra dự đoán dựa trên xác suất và ngưỡng phân loại được cung cấp trong Explanation IR.\n\nCác yếu tố được phép hiển thị trong contract cho thấy một số thông tin góp phần làm tăng rủi ro dự đoán của mô hình.\n\nKhông có yếu tố làm giảm rủi ro nào đủ điều kiện hiển thị trực tiếp trong contract hiện tại.\n\nCác yếu tố trên chỉ mô tả đóng góp vào dự đoán của mô hình, không chứng minh quan hệ nhân quả ngoài thực tế và không phải kết luận chắc chắn về hành vi trả nợ.",
  };

  return {
    provider: `${config.provider}_mock`,
    modelName: `${config.modelName}_mock`,
    rawText: JSON.stringify(mockJson),
    parsedJson: mockJson,
    isParseableJson: true,
  };
}

function safeJsonParse<T>(text: string):
  | {
      ok: true;
      value: T;
    }
  | {
      ok: false;
      errorMessage: string;
    } {
  try {
    return {
      ok: true,
      value: JSON.parse(text) as T,
    };
  } catch (error) {
    return {
      ok: false,
      errorMessage:
        error instanceof Error ? error.message : "Unknown JSON parse error.",
    };
  }
}

/**
 * Removes accidental markdown fences:
 *
 * ```json
 * {...}
 * ```
 */
function stripMarkdownJsonFence(text: string): string {
  let result = text.trim();

  if (result.startsWith("```json")) {
    result = result.slice("```json".length).trim();
  } else if (result.startsWith("```")) {
    result = result.slice("```".length).trim();
  }

  if (result.endsWith("```")) {
    result = result.slice(0, -3).trim();
  }

  return result;
}

/**
 * Extracts the first balanced JSON object from text.
 * Useful if the model accidentally returns extra text before/after JSON.
 */
function extractFirstJsonObject(text: string): string | null {
  const start = text.indexOf("{");

  if (start === -1) {
    return null;
  }

  let depth = 0;
  let inString = false;
  let escaping = false;

  for (let i = start; i < text.length; i++) {
    const char = text[i];

    if (escaping) {
      escaping = false;
      continue;
    }

    if (char === "\\") {
      escaping = true;
      continue;
    }

    if (char === '"') {
      inString = !inString;
      continue;
    }

    if (inString) {
      continue;
    }

    if (char === "{") {
      depth += 1;
      continue;
    }

    if (char === "}") {
      depth -= 1;

      if (depth === 0) {
        return text.slice(start, i + 1);
      }
    }
  }

  return null;
}

function parseOptionalNumber(
  value: string | undefined,
  fallback: number,
): number {
  if (!value) {
    return fallback;
  }

  const parsed = Number(value);

  if (!Number.isFinite(parsed)) {
    return fallback;
  }

  return parsed;
}

function isJsonModeEnabled(): boolean {
  const value = process.env.LLM_ENABLE_JSON_MODE;

  if (!value) {
    return true;
  }

  return value !== "false";
}