import dotenv from "dotenv";
import { aggregateNarrativeRun } from "./aggregate";
import type { EvidenceLevel } from "../../../contracts/narrative";

dotenv.config({ path: ".env.local" });
dotenv.config({ path: ".env" });

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const runId = readRequiredString(args, "run-id");
  const shardsDir = readRequiredString(args, "shards-dir");
  const outputDir = readRequiredString(args, "output-dir");
  const stage = readString(args, "experiment-stage", "development");

  if (stage !== "development" && stage !== "evaluation") {
    throw new Error("experiment-stage must be development or evaluation.");
  }

  const result = await aggregateNarrativeRun({
    run_id: runId,
    shards_dir: shardsDir,
    output_dir: outputDir,
    experiment_stage: stage,
    input_path: readOptionalString(args, "input") || undefined,
    model_ids: readOptionalList(args, "models"),
    levels: readOptionalList(args, "levels") as EvidenceLevel[] | undefined,
    repeat_ids: parseRepeatIds(args),
    chunk_start: readOptionalInteger(args, "chunk-start"),
    chunk_size: readOptionalInteger(args, "chunk-size"),
    limit_cases: readOptionalInteger(args, "limit"),
  });

  console.log(`Aggregation status: ${result.status}`);
  console.log(`Generation count: ${result.generation_count}`);
  console.log(
    `Duplicate generation count: ${result.duplicate_generation_count}`,
  );
  console.log(`Missing generation count: ${result.missing_generation_count}`);
  console.log(`Main output: ${result.output_path}`);

  if (result.status === "FAILED") {
    process.exitCode = 1;
  }
}

function parseRepeatIds(
  args: Record<string, string | boolean>,
): number[] | undefined {
  const repeatIds = readOptionalList(args, "repeat-ids");
  if (repeatIds) {
    return repeatIds.map((value) => parsePositiveInteger(value, "repeat-ids"));
  }

  const repeatCountValue = readOptionalString(args, "repeat-count");
  if (repeatCountValue) {
    const count = parsePositiveInteger(repeatCountValue, "repeat-count");
    return Array.from({ length: count }, (_, index) => index + 1);
  }

  return undefined;
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
  return typeof args[key] === "string" ? (args[key] as string) : defaultValue;
}

function readOptionalString(
  args: Record<string, string | boolean>,
  key: string,
): string | null {
  return typeof args[key] === "string" ? (args[key] as string) : null;
}

function readOptionalList(
  args: Record<string, string | boolean>,
  key: string,
): string[] | undefined {
  const value = readOptionalString(args, key);
  if (!value) {
    return undefined;
  }

  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function readOptionalInteger(
  args: Record<string, string | boolean>,
  key: string,
): number | undefined {
  const value = readOptionalString(args, key);
  if (!value) {
    return undefined;
  }

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

main().catch((error) => {
  const message =
    error instanceof Error ? error.stack || error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
