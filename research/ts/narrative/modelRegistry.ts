import type { ModelConfig } from "../../../contracts/narrative";
import { safeNumber } from "../common/utils";

function readOptionalNumber(name: string): number | null {
  return safeNumber(process.env[name]);
}

export function getModelRegistry(): Record<string, ModelConfig> {
  return {
    template_baseline: {
      id: "template_baseline",
      provider: "template",
      family: "deterministic_template",
      runtime: "template",
      remote_model_id: "template_baseline",
      revision: "1.0",
      output_constraint_mode: "none",
      enabled: true,
      note: "Deterministic pipeline baseline, not an LLM.",
    },

    deepseek_v4_flash: {
      id: "deepseek_v4_flash",
      provider: "deepseek",
      family: "deepseek",
      runtime: "api",
      remote_model_id: "deepseek-v4-flash",
      revision: process.env.DEEPSEEK_MODEL_REVISION || null,
      output_constraint_mode: "json_object",
      api_base_url: process.env.DEEPSEEK_BASE_URL || "https://api.deepseek.com",
      api_key_env: "DEEPSEEK_API_KEY",
      input_cost_per_million: readOptionalNumber(
        "DEEPSEEK_INPUT_COST_PER_MILLION",
      ),
      output_cost_per_million: readOptionalNumber(
        "DEEPSEEK_OUTPUT_COST_PER_MILLION",
      ),
      enabled: true,
      note: "External API reference model. Pricing is read from environment variables.",
    },

    qwen3_8b: {
      id: "qwen3_8b",
      provider: "huggingface",
      family: "qwen",
      runtime: "vllm",
      remote_model_id: "Qwen/Qwen3-8B",
      revision: process.env.QWEN3_8B_REVISION || null,
      output_constraint_mode: "json_schema",
      api_base_url: process.env.VLLM_BASE_URL || "http://localhost:8000/v1",
      api_key_env: "VLLM_API_KEY",
      chat_template_kwargs: {
        enable_thinking: false,
      },
      enabled: true,
    },

    gemma3_4b_it: {
      id: "gemma3_4b_it",
      provider: "huggingface",
      family: "gemma",
      runtime: "vllm",
      remote_model_id: "google/gemma-3-4b-it",
      revision: process.env.GEMMA3_4B_IT_REVISION || null,
      output_constraint_mode: "json_schema",
      api_base_url: process.env.VLLM_BASE_URL || "http://localhost:8000/v1",
      api_key_env: "VLLM_API_KEY",
      enabled: true,
    },

    mistral_7b_instruct_v03: {
      id: "mistral_7b_instruct_v03",
      provider: "huggingface",
      family: "mistral",
      runtime: "vllm",
      remote_model_id: "mistralai/Mistral-7B-Instruct-v0.3",
      revision: process.env.MISTRAL_7B_V03_REVISION || null,
      output_constraint_mode: "json_schema",
      api_base_url: process.env.VLLM_BASE_URL || "http://localhost:8000/v1",
      api_key_env: "VLLM_API_KEY",
      enabled: true,
    },

    phi4_mini_instruct: {
      id: "phi4_mini_instruct",
      provider: "huggingface",
      family: "phi",
      runtime: "vllm",
      remote_model_id: "microsoft/Phi-4-mini-instruct",
      revision: process.env.PHI4_MINI_REVISION || null,
      output_constraint_mode: "json_schema",
      api_base_url: process.env.VLLM_BASE_URL || "http://localhost:8000/v1",
      api_key_env: "VLLM_API_KEY",
      enabled: true,
    },

    llama31_8b_instruct: {
      id: "llama31_8b_instruct",
      provider: "huggingface",
      family: "llama",
      runtime: "vllm",
      remote_model_id: "meta-llama/Llama-3.1-8B-Instruct",
      revision: process.env.LLAMA31_8B_REVISION || null,
      output_constraint_mode: "json_schema",
      api_base_url: process.env.VLLM_BASE_URL || "http://localhost:8000/v1",
      api_key_env: "VLLM_API_KEY",
      enabled: process.env.ENABLE_LLAMA31_8B === "true",
      note: "Optional gated model. Enable only after access and license checks.",
    },
  };
}

const MODEL_ALIASES: Record<string, string> = {
  deepseek_chat: "deepseek_v4_flash",
};

export function resolveModelId(modelId: string): string {
  return MODEL_ALIASES[modelId] || modelId;
}

export function getModelConfig(modelId: string): ModelConfig {
  const resolvedId = resolveModelId(modelId);
  const registry = getModelRegistry();
  const model = registry[resolvedId];

  if (!model) {
    throw new Error(`Unknown model id: ${modelId}`);
  }

  if (!model.enabled) {
    throw new Error(`Model is disabled in modelRegistry.ts: ${resolvedId}`);
  }

  return model;
}
