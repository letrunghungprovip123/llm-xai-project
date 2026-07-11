import dotenv from "dotenv";
import {
  ALL_EVIDENCE_LEVELS,
  DEFAULT_BASE_SEED,
  DEFAULT_CHECKPOINT_EVERY,
  DEFAULT_CONCURRENCY,
  DEFAULT_DECODING_CONFIG,
  DEFAULT_INPUT_PATH,
  DEFAULT_MAX_RETRIES,
  DEFAULT_OUTPUT_DIR,
  DEFAULT_OUTPUT_SCHEMA_VERSION,
  DEFAULT_PROMPT_VERSION,
  DEFAULT_RETRY_DELAY_MS,
  DEFAULT_TIMEOUT_MS,
} from "../../src/server/llmNarrative/config";
import { runNarrativePipeline } from "../../src/server/llmNarrative/pipeline";
import type {
  EvidenceLevel,
  ExperimentStage,
  RunOptions,
} from "../../src/types/types";

dotenv.config({ path: ".env.local" });
dotenv.config({ path: ".env" });

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const options = buildRunOptions(args);
  const result = await runNarrativePipeline(options);

  console.log("Batch I generation finished.");
  console.log(`Run ID: ${result.run_id}`);
  console.log(`Shard count: ${result.shard_count}`);
  console.log(`Planned generations: ${result.planned_generation_count}`);
  console.log(`Successful generations: ${result.completed_generation_count}`);
  console.log(`Failed generations: ${result.failed_generation_count}`);
  console.log("Shard paths:");
  for (const shardPath of result.shard_paths) {
    console.log(`- ${shardPath}`);
  }

  if (result.failed_generation_count > 0) {
    process.exitCode = 1;
  }
}

function buildRunOptions(args: Record<string, string | boolean>): RunOptions {
  const inputPath = readString(args, "input", DEFAULT_INPUT_PATH);
  const outputDir = readString(args, "output-dir", DEFAULT_OUTPUT_DIR);
  const runId = readRequiredString(args, "run-id");
  const modelIds = splitList(readRequiredString(args, "models"));
  const levels = parseLevels(
    readString(args, "levels", ALL_EVIDENCE_LEVELS.join(",")),
  );
  const repeatIds = parseRepeatIds(args);
  const experimentStage = parseExperimentStage(
    readString(args, "experiment-stage", "development"),
  );

  return {
    input_path: inputPath,
    output_dir: outputDir,
    run_id: runId,
    model_ids: modelIds,
    levels,
    repeat_ids: repeatIds,
    decoding: {
      temperature: readNumber(
        args,
        "temperature",
        DEFAULT_DECODING_CONFIG.temperature,
      ),
      top_p: readNumber(args, "top-p", DEFAULT_DECODING_CONFIG.top_p),
      max_tokens: readInteger(
        args,
        "max-tokens",
        DEFAULT_DECODING_CONFIG.max_tokens,
      ),
      frequency_penalty: readNumber(
        args,
        "frequency-penalty",
        DEFAULT_DECODING_CONFIG.frequency_penalty,
      ),
      presence_penalty: readNumber(
        args,
        "presence-penalty",
        DEFAULT_DECODING_CONFIG.presence_penalty,
      ),
    },
    prompt_version: readString(args, "prompt-version", DEFAULT_PROMPT_VERSION),
    output_schema_version: readString(
      args,
      "output-schema-version",
      DEFAULT_OUTPUT_SCHEMA_VERSION,
    ),
    experiment_stage: experimentStage,
    limit_cases: readOptionalInteger(args, "limit"),
    chunk_start: readInteger(args, "chunk-start", 0),
    chunk_size: readOptionalInteger(args, "chunk-size"),
    concurrency: readInteger(args, "concurrency", DEFAULT_CONCURRENCY),
    checkpoint_every: readInteger(
      args,
      "checkpoint-every",
      DEFAULT_CHECKPOINT_EVERY,
    ),
    timeout_ms: readInteger(args, "timeout-ms", DEFAULT_TIMEOUT_MS),
    max_retries: readInteger(args, "max-retries", DEFAULT_MAX_RETRIES),
    retry_delay_ms: readInteger(args, "retry-delay-ms", DEFAULT_RETRY_DELAY_MS),
    base_seed: readInteger(args, "base-seed", DEFAULT_BASE_SEED),
    resume: readBoolean(args, "resume", false),
  };
}

function parseRepeatIds(args: Record<string, string | boolean>): number[] {
  const repeatIdsText = readOptionalString(args, "repeat-ids");
  if (repeatIdsText) {
    return splitList(repeatIdsText).map((value) =>
      parsePositiveInteger(value, "repeat-ids"),
    );
  }

  const repeatCountText = readOptionalString(args, "repeat-count");
  if (repeatCountText) {
    const count = parsePositiveInteger(repeatCountText, "repeat-count");
    return Array.from({ length: count }, (_, index) => index + 1);
  }

  const repeatText = readOptionalString(args, "repeat");
  if (repeatText) {
    return [parsePositiveInteger(repeatText, "repeat")];
  }

  return [1];
}

function parseArgs(values: string[]): Record<string, string | boolean> {
  const result: Record<string, string | boolean> = {};

  for (let index = 0; index < values.length; index += 1) {
    const current = values[index];

    if (!current.startsWith("--")) {
      throw new Error(`Unexpected argument: ${current}`);
    }

    const key = current.slice(2);
    const next = values[index + 1];

    if (!next || next.startsWith("--")) {
      result[key] = true;
      continue;
    }

    result[key] = next;
    index += 1;
  }

  return result;
}

function parseLevels(value: string): EvidenceLevel[] {
  const levels = splitList(value) as EvidenceLevel[];
  const allowed = new Set(ALL_EVIDENCE_LEVELS);

  for (const level of levels) {
    if (!allowed.has(level)) {
      throw new Error(`Invalid evidence level: ${level}`);
    }
  }

  return levels;
}

function parseExperimentStage(value: string): ExperimentStage {
  if (value !== "development" && value !== "evaluation") {
    throw new Error("experiment-stage must be development or evaluation.");
  }

  return value;
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function readRequiredString(
  args: Record<string, string | boolean>,
  key: string,
): string {
  const value = args[key];

  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Missing required argument: --${key}`);
  }

  return value.trim();
}

function readString(
  args: Record<string, string | boolean>,
  key: string,
  defaultValue: string,
): string {
  const value = args[key];
  return typeof value === "string" ? value : defaultValue;
}

function readOptionalString(
  args: Record<string, string | boolean>,
  key: string,
): string | null {
  const value = args[key];
  return typeof value === "string" ? value : null;
}

function readNumber(
  args: Record<string, string | boolean>,
  key: string,
  defaultValue: number,
): number {
  const value = args[key];
  if (typeof value !== "string") {
    return defaultValue;
  }

  const result = Number(value);
  if (!Number.isFinite(result)) {
    throw new Error(`--${key} must be a number.`);
  }

  return result;
}

function readInteger(
  args: Record<string, string | boolean>,
  key: string,
  defaultValue: number,
): number {
  const value = args[key];
  if (typeof value !== "string") {
    return defaultValue;
  }

  return parseInteger(value, key);
}

function readOptionalInteger(
  args: Record<string, string | boolean>,
  key: string,
): number | undefined {
  const value = args[key];
  if (typeof value !== "string") {
    return undefined;
  }

  return parseInteger(value, key);
}

function parseInteger(value: string, key: string): number {
  const result = Number(value);
  if (!Number.isInteger(result) || result < 0) {
    throw new Error(`--${key} must be a non-negative integer.`);
  }

  return result;
}

function parsePositiveInteger(value: string, key: string): number {
  const result = Number(value);
  if (!Number.isInteger(result) || result < 1) {
    throw new Error(`--${key} must be a positive integer.`);
  }

  return result;
}

function readBoolean(
  args: Record<string, string | boolean>,
  key: string,
  defaultValue: boolean,
): boolean {
  const value = args[key];
  if (value === undefined) {
    return defaultValue;
  }

  if (typeof value === "boolean") {
    return value;
  }

  return value === "true" || value === "1";
}

main().catch((error) => {
  const message =
    error instanceof Error ? error.stack || error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
