// scripts/run-i-llm-api-explanation.ts

import { runLlmExplanationBatch } from "../llm/batch-runner";
import type {
  InputSource,
  RunMode,
} from "../llm/explanation-schema";
import dotenv from "dotenv";

dotenv.config({ path: ".env" });
/**
 * CLI runner for Batch I v1.0.
 *
 * Example:
 * npx tsx scripts/run-i-llm-api-explanation.ts --limit 1
 *
 * Full evaluation:
 * npx tsx scripts/run-i-llm-api-explanation.ts --limit 30
 *
 * Inference extension later:
 * npx tsx scripts/run-i-llm-api-explanation.ts --runMode inference --batchId 2026_07
 */

type CliArgs = {
  runMode: RunMode;
  batchId: string;
  inputSource: InputSource;
  limit?: number;
  irId?: string;
  customerId?: string;
};

async function main() {
  const args = parseCliArgs(process.argv.slice(2));

  console.log("=== Batch I v1.0 - LLM API Explanation Layer ===");
  console.log("Config:");
  console.log(JSON.stringify(args, null, 2));

  const result = await runLlmExplanationBatch({
    runMode: args.runMode,
    batchId: args.batchId,
    inputSource: args.inputSource,
    limit: args.limit,
    irId: args.irId,
    customerId: args.customerId,
  });

  console.log("\n=== Batch I v1.0 completed ===");
  console.log(`Generated records: ${result.records.length}`);
  console.log("Artifacts:");
  console.log(JSON.stringify(result.artifactPaths, null, 2));

  const failedCount = result.records.filter(
    (record) => record.quality.errors.length > 0,
  ).length;

  if (failedCount > 0) {
    console.warn(`Warning: ${failedCount} records have generation errors.`);
  }
}

function parseCliArgs(rawArgs: string[]): CliArgs {
  const map = new Map<string, string>();

  for (let i = 0; i < rawArgs.length; i++) {
    const current = rawArgs[i];

    if (!current.startsWith("--")) {
      continue;
    }

    const key = current.slice(2);
    const next = rawArgs[i + 1];

    if (!next || next.startsWith("--")) {
      map.set(key, "true");
    } else {
      map.set(key, next);
      i += 1;
    }
  }

  const runMode = parseRunMode(map.get("runMode") ?? "evaluation");
  const batchId = map.get("batchId") ?? "evaluation";
  const inputSource = parseInputSource(
    map.get("inputSource") ?? "precomputed_ir",
  );

  const limitRaw = map.get("limit");
  const limit = limitRaw ? Number(limitRaw) : undefined;

  if (limitRaw && (!Number.isFinite(limit) || Number(limit) <= 0)) {
    throw new Error(`Invalid --limit value: ${limitRaw}`);
  }

  return {
    runMode,
    batchId,
    inputSource,
    limit,
    irId: map.get("irId"),
    customerId: map.get("customerId"),
  };
}

function parseRunMode(value: string): RunMode {
  if (value === "evaluation" || value === "inference") {
    return value;
  }

  throw new Error(`Invalid --runMode value: ${value}`);
}

function parseInputSource(value: string): InputSource {
  if (
    value === "precomputed_ir" ||
    value === "inference_ready" ||
    value === "raw_batch"
  ) {
    return value;
  }

  throw new Error(`Invalid --inputSource value: ${value}`);
}

main().catch((error) => {
  console.error("\nBatch I v1.0 failed.");
  console.error(error);
  process.exit(1);
});
