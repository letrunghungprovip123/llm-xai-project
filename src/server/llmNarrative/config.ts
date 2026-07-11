import type { DecodingConfig, EvidenceLevel } from "../../types/types";

export const DEFAULT_INPUT_PATH =
  "data/reports/evidence_exposure/development/evidence_packages.jsonl";

export const DEFAULT_OUTPUT_DIR = "data/reports/llm_narratives/development";

export const DEFAULT_PROMPT_VERSION = "prompt_v1";
export const DEFAULT_OUTPUT_SCHEMA_VERSION = "1.0";

export const ALL_EVIDENCE_LEVELS: EvidenceLevel[] = [
  "S0",
  "S1",
  "S2",
  "S3",
  "S4",
  "S5",
];

export const DEFAULT_DECODING_CONFIG: DecodingConfig = {
  temperature: 0.2,
  top_p: 1.0,
  max_tokens: 2000,
  frequency_penalty: 0,
  presence_penalty: 0,
};

export const DEFAULT_TIMEOUT_MS = 120_000;
export const DEFAULT_MAX_RETRIES = 2;
export const DEFAULT_RETRY_DELAY_MS = 2_000;
export const DEFAULT_CONCURRENCY = 1;
export const DEFAULT_CHECKPOINT_EVERY = 10;
export const DEFAULT_BASE_SEED = 20260710;

export const FORBIDDEN_PROMPT_KEYS = new Set([
  "true_label",
  "true_label_text",
  "has_ground_truth",
  "case_type",
  "selection_stratum",
  "prediction_outcome",
  "selection_rank",
  "row_index",
  "SK_ID_CURR",
  "customer_id",
]);

export const COMMON_FORBIDDEN_PHRASES = [
  "nguyên nhân duy nhất",
  "lý do duy nhất",
  "chắc chắn vỡ nợ",
  "chắc chắn không trả được nợ",
  "đảm bảo sẽ vỡ nợ",
  "gây ra trực tiếp",
  "direct cause",
  "guarantee",
  "certainly default",
  "only reason",
];

export const MIN_OUTPUT_WORDS = 35;
export const MAX_OUTPUT_WORDS = 350;
