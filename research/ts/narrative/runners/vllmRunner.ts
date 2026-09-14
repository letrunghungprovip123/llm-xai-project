import { EXPLANATION_JSON_SCHEMA } from "../outputSchema";
import type {
  DecodingConfig,
  ModelConfig,
  PromptBuildResult,
  RunnerResult,
} from "../../../../contracts/narrative";
import { postJsonWithRetry } from "./httpHelpers";

export async function runVllm(
  model: ModelConfig,
  prompt: PromptBuildResult,
  decoding: DecodingConfig,
  generationSeed: number,
  timeoutMs: number,
  maxRetries: number,
  retryDelayMs: number,
): Promise<RunnerResult> {
  const baseUrl = (model.api_base_url || "http://localhost:8000/v1").replace(
    /\/+$/,
    "",
  );
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (model.api_key_env && process.env[model.api_key_env]) {
    headers.Authorization = `Bearer ${process.env[model.api_key_env]}`;
  }

  const body: Record<string, unknown> = {
    model: model.remote_model_id,
    messages: prompt.messages,
    temperature: decoding.temperature,
    top_p: decoding.top_p,
    max_tokens: decoding.max_tokens,
    frequency_penalty: decoding.frequency_penalty,
    presence_penalty: decoding.presence_penalty,
    seed: generationSeed,
    stream: false,
  };

  if (model.output_constraint_mode === "json_schema") {
    body.response_format = {
      type: "json_schema",
      json_schema: {
        name: "llm_xai_explanation",
        strict: true,
        schema: EXPLANATION_JSON_SCHEMA,
      },
    };
  } else if (model.output_constraint_mode === "json_object") {
    body.response_format = {
      type: "json_object",
    };
  }

  if (model.chat_template_kwargs) {
    body.chat_template_kwargs = model.chat_template_kwargs;
  }

  const result = await postJsonWithRetry({
    url: `${baseUrl}/chat/completions`,
    headers,
    body,
    timeout_ms: timeoutMs,
    max_retries: maxRetries,
    retry_delay_ms: retryDelayMs,
  });

  if (!result.ok) {
    return {
      status: "FAILED",
      raw_output: null,
      finish_reason: null,
      latency_ms: result.latency_ms,
      retry_count: result.retry_count,
      input_token_count: null,
      output_token_count: null,
      total_token_count: null,
      provider_request_id: null,
      provider_returned_model_id: null,
      provider_api_cost_usd: 0,
      error_type: result.error_type || "VLLM_REQUEST_FAILED",
      error_message: result.error_message || "vLLM request failed.",
    };
  }

  const response = readChatCompletion(result.response_json);

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
    provider_api_cost_usd: 0,
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

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
