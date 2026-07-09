// src/server/llm/llm-client.ts

import type {
  BuiltPrompt,
  LlmGeneratedJson,
  LlmRawResponse,
  LlmRuntimeConfig,
} from "./explanation-schema";

import { isLlmGeneratedJson } from "./explanation-schema";

/**
 * Batch I v1.1 - LLM Client
 *
 * Calls an OpenAI-compatible Chat Completions API such as DeepSeek.
 */

const DEFAULT_PROVIDER = "deepseek";
const DEFAULT_MODEL = "deepseek-v4-flash";
const DEFAULT_BASE_URL = "https://api.deepseek.com/chat/completions";
const DEFAULT_TEMPERATURE = 0.45;
const DEFAULT_MAX_TOKENS = 2400;
const DEFAULT_PROMPT_VERSION = "batch_i_llm_prompt_v1.1";

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
  thinking?: {
    type: "enabled" | "disabled";
  };
  reasoning_effort?: "high" | "max";
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
        "Missing LLM_API_KEY. Please set LLM_API_KEY in .env or .env.local.",
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
    thinking: {
      type: getDeepSeekThinkingMode(),
    },
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
        usage: apiResponse.value.usage,
      };
    }

    const rawContent =
      apiResponse.value.choices?.[0]?.message?.content?.trim() ?? "";

    if (!rawContent) {
      return {
        provider: config.provider,
        modelName: apiResponse.value.model || config.modelName,
        rawText: "",
        isParseableJson: false,
        errorMessage: "LLM API response did not contain message content.",
        usage: apiResponse.value.usage,
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
      usage: apiResponse.value.usage,
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
      value: normalizeOptionalArrays(directParse.value),
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
        "Parsed JSON does not match required LLM output schema. Required shape: { language: 'vi', sections: { prediction, contribution_overview, main_risk_drivers, supporting_evidence_groups, risk_reducing_factors, limitations }, referenced_terms?, evidence_items_used?, evidence_groups_used? }.",
    };
  }

  return {
    ok: true,
    value: normalizeOptionalArrays(extractedParse.value),
  };
}

function normalizeOptionalArrays(value: LlmGeneratedJson): LlmGeneratedJson {
  return {
    ...value,
    referenced_terms: Array.isArray(value.referenced_terms)
      ? value.referenced_terms
      : [],
    evidence_items_used: Array.isArray(value.evidence_items_used)
      ? value.evidence_items_used
      : [],
    evidence_groups_used: Array.isArray(value.evidence_groups_used)
      ? value.evidence_groups_used
      : [],
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

function getDeepSeekThinkingMode(): "enabled" | "disabled" {
  const value = process.env.LLM_THINKING_MODE;

  if (value === "enabled") {
    return "enabled";
  }

  return "disabled";
}