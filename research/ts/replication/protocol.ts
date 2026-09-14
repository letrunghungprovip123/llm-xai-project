import protocolJson from "../../../config/research/replication/llm_replication_protocol_v1.json";
import {
  ALL_EVIDENCE_LEVELS,
  DEFAULT_BASE_SEED,
  DEFAULT_CHECKPOINT_EVERY,
  DEFAULT_CONCURRENCY,
  DEFAULT_DECODING_CONFIG,
  DEFAULT_MAX_RETRIES,
  DEFAULT_OUTPUT_SCHEMA_VERSION,
  DEFAULT_PROMPT_VERSION,
  DEFAULT_RETRY_DELAY_MS,
  DEFAULT_TIMEOUT_MS,
  getModelConfig,
} from "../narrative/index";
import {
  ATOMIC_CLAIM_EXTRACTOR_VERSION,
  ATOMIC_CLAIM_PROMPT_VERSION,
} from "../claim_extraction/atomicClaimSchema";
import {
  DEEPSEEK_ATOMIC_CLAIM_EXTRACTOR_DEFAULTS,
  DEEPSEEK_EXTRACTOR_LINEAGE,
} from "../claim_extraction/deepseekAtomicClaimExtractor";
import { sha256, stableStringify } from "../common/utils";

export type ReplicationProtocol = typeof protocolJson;
export const REPLICATION_PROTOCOL: ReplicationProtocol = protocolJson;

export function replicationProtocolSha256(): string {
  return sha256(stableStringify(REPLICATION_PROTOCOL));
}

export function assertReplicationProtocolMatchesCommonRuntime(): void {
  const generation = REPLICATION_PROTOCOL.generation;
  assertEqual(generation.prompt_version, DEFAULT_PROMPT_VERSION, "prompt_version");
  assertEqual(generation.output_schema_version, DEFAULT_OUTPUT_SCHEMA_VERSION, "output_schema_version");
  assertEqual(generation.evidence_levels, ALL_EVIDENCE_LEVELS, "evidence_levels");
  assertEqual(generation.decoding, DEFAULT_DECODING_CONFIG, "decoding");
  assertEqual(generation.execution.timeout_ms, DEFAULT_TIMEOUT_MS, "timeout_ms");
  assertEqual(generation.execution.max_retries, DEFAULT_MAX_RETRIES, "max_retries");
  assertEqual(generation.execution.retry_delay_ms, DEFAULT_RETRY_DELAY_MS, "retry_delay_ms");
  assertEqual(generation.execution.base_seed, DEFAULT_BASE_SEED, "base_seed");
  assertEqual(generation.execution.checkpoint_every, DEFAULT_CHECKPOINT_EVERY, "checkpoint_every");
  assertEqual(generation.execution.default_concurrency, DEFAULT_CONCURRENCY, "default_concurrency");

  for (const frozenModel of generation.models) {
    const runtimeModel = getModelConfig(frozenModel.model_id);
    assertEqual(runtimeModel.provider, frozenModel.provider, `${frozenModel.model_id}.provider`);
    assertEqual(runtimeModel.runtime, frozenModel.runtime, `${frozenModel.model_id}.runtime`);
    assertEqual(runtimeModel.remote_model_id, frozenModel.remote_model_id, `${frozenModel.model_id}.remote_model_id`);
    assertEqual(runtimeModel.output_constraint_mode, frozenModel.output_constraint_mode, `${frozenModel.model_id}.output_constraint_mode`);
    if ("chat_template_kwargs" in frozenModel) {
      assertEqual(runtimeModel.chat_template_kwargs ?? {}, frozenModel.chat_template_kwargs ?? {}, `${frozenModel.model_id}.chat_template_kwargs`);
    }
  }

  const claim = REPLICATION_PROTOCOL.claim_measurement;
  assertEqual(claim.extractor_version, ATOMIC_CLAIM_EXTRACTOR_VERSION, "claim.extractor_version");
  assertEqual(claim.extractor_prompt_version, ATOMIC_CLAIM_PROMPT_VERSION, "claim.extractor_prompt_version");
  const extractorDefaults = DEEPSEEK_ATOMIC_CLAIM_EXTRACTOR_DEFAULTS;
  assertEqual(extractorDefaults.modelId, claim.extractor_model_id, "claim.extractor_model_id");
  assertEqual(DEEPSEEK_EXTRACTOR_LINEAGE.promptSha256, claim.extractor_prompt_sha256, "claim.extractor_prompt_sha256");
  assertEqual(extractorDefaults.temperature, claim.extractor_decoding.temperature, "claim.temperature");
  assertEqual(extractorDefaults.topP, claim.extractor_decoding.top_p, "claim.top_p");
  assertEqual(extractorDefaults.maxTokens, claim.extractor_decoding.max_tokens, "claim.max_tokens");
  assertEqual(extractorDefaults.timeoutMs, claim.extractor_decoding.timeout_ms, "claim.timeout_ms");
  assertEqual(extractorDefaults.maxRetries, claim.extractor_decoding.max_retries, "claim.max_retries");
  assertEqual(extractorDefaults.retryDelayMs, claim.extractor_decoding.retry_delay_ms, "claim.retry_delay_ms");
}

function assertEqual(actual: unknown, expected: unknown, label: string): void {
  if (stableStringify(actual) !== stableStringify(expected)) {
    throw new Error(`Replication protocol drift at ${label}: expected ${stableStringify(expected)}, found ${stableStringify(actual)}.`);
  }
}
