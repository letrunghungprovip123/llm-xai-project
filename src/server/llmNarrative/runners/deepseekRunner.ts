import type {
  DecodingConfig,
  ModelConfig,
  PromptBuildResult,
  RunnerResult,
} from "../../../types/types";
import { postJsonWithRetry } from "./httpHelpers";

export async function runDeepSeek(
  model: ModelConfig,
  prompt: PromptBuildResult,
  decoding: DecodingConfig,
  timeoutMs: number,
  maxRetries: number,
  retryDelayMs: number,
): Promise<RunnerResult> {
  const apiKeyName = model.api_key_env || "DEEPSEEK_API_KEY";
  const apiKey = process.env[apiKeyName];

  if (!apiKey) {
    return failedResult(
      "MISSING_API_KEY",
      `Missing environment variable: ${apiKeyName}`,
    );
  }

  const baseUrl = (model.api_base_url || "https://api.deepseek.com").replace(
    /\/+$/,
    "",
  );
  const result = await postJsonWithRetry({
    url: `${baseUrl}/chat/completions`,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: {
      model: model.remote_model_id,
      messages: prompt.messages,
      temperature: decoding.temperature,
      top_p: decoding.top_p,
      max_tokens: decoding.max_tokens,
      frequency_penalty: decoding.frequency_penalty,
      presence_penalty: decoding.presence_penalty,
      response_format: {
        type: "json_object",
      },
      stream: false,
      thinking: {
        type: "disabled",
      },
    },
    timeout_ms: timeoutMs,
    max_retries: maxRetries,
    retry_delay_ms: retryDelayMs,
  });

  if (!result.ok) {
    return {
      ...failedResult(
        result.error_type || "DEEPSEEK_REQUEST_FAILED",
        result.error_message || "DeepSeek request failed.",
      ),
      latency_ms: result.latency_ms,
      retry_count: result.retry_count,
    };
  }

  const response = readChatCompletion(result.response_json);
  const cost = estimateCost(
    response.inputTokens,
    response.outputTokens,
    model.input_cost_per_million,
    model.output_cost_per_million,
  );

  return {
    status: "SUCCESS",
    raw_output: response.content,
    finish_reason: response.finishReason,
    latency_ms: result.latency_ms,
    retry_count: result.retry_count,
    input_token_count: response.inputTokens,
    output_token_count: response.outputTokens,
    total_token_count: response.totalTokens,
    provider_request_id: response.requestId,
    provider_returned_model_id: response.modelId,
    provider_api_cost_usd: cost,
    error_type: null,
    error_message: null,
  };
}

function readChatCompletion(value: unknown): {
  content: string | null;
  finishReason: string | null;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  requestId: string | null;
  modelId: string | null;
} {
  if (!value || typeof value !== "object") {
    return emptyResponse();
  }

  const source = value as Record<string, unknown>;
  const choices = Array.isArray(source.choices) ? source.choices : [];
  const firstChoice =
    choices[0] && typeof choices[0] === "object"
      ? (choices[0] as Record<string, unknown>)
      : {};
  const message =
    firstChoice.message && typeof firstChoice.message === "object"
      ? (firstChoice.message as Record<string, unknown>)
      : {};
  const usage =
    source.usage && typeof source.usage === "object"
      ? (source.usage as Record<string, unknown>)
      : {};

  return {
    content: typeof message.content === "string" ? message.content : null,
    finishReason:
      typeof firstChoice.finish_reason === "string"
        ? firstChoice.finish_reason
        : null,
    inputTokens: readNumber(usage.prompt_tokens),
    outputTokens: readNumber(usage.completion_tokens),
    totalTokens: readNumber(usage.total_tokens),
    requestId: typeof source.id === "string" ? source.id : null,
    modelId: typeof source.model === "string" ? source.model : null,
  };
}

function emptyResponse() {
  return {
    content: null,
    finishReason: null,
    inputTokens: null,
    outputTokens: null,
    totalTokens: null,
    requestId: null,
    modelId: null,
  };
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function estimateCost(
  inputTokens: number | null,
  outputTokens: number | null,
  inputCostPerMillion: number | null | undefined,
  outputCostPerMillion: number | null | undefined,
): number | null {
  if (
    inputTokens === null ||
    outputTokens === null ||
    inputCostPerMillion === null ||
    inputCostPerMillion === undefined ||
    outputCostPerMillion === null ||
    outputCostPerMillion === undefined
  ) {
    return null;
  }

  return (
    (inputTokens / 1_000_000) * inputCostPerMillion +
    (outputTokens / 1_000_000) * outputCostPerMillion
  );
}

function failedResult(errorType: string, errorMessage: string): RunnerResult {
  return {
    status: "FAILED",
    raw_output: null,
    finish_reason: null,
    latency_ms: 0,
    retry_count: 0,
    input_token_count: null,
    output_token_count: null,
    total_token_count: null,
    provider_request_id: null,
    provider_returned_model_id: null,
    provider_api_cost_usd: null,
    error_type: errorType,
    error_message: errorMessage,
  };
}
