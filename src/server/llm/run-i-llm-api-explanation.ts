// src/server/llm/run-i-llm-api-explanation.ts

import dotenv from "dotenv";

import { runLlmExplanationBatch } from "./batch-runner";
import type { InputSource, RunMode } from "./explanation-schema";

dotenv.config({ path: ".env" });
dotenv.config({ path: ".env.local", override: false });

/**
 * CLI runner for Batch I v1.2 LLM API.
 *
 * Normal/base generation:
 * npx tsx src/server/llm/run-i-llm-api-explanation.ts \
 *   --limit 5 \
 *   --artifactSubdir base
 *
 * Single-record generation:
 * npx tsx src/server/llm/run-i-llm-api-explanation.ts \
 *   --irId ir_xai_hist_gradient_boosting_v1_163956_top_high_risk \
 *   --artifactSubdir base
 *
 * Controlled regeneration with Batch J.3 feedback:
 * npx tsx src/server/llm/run-i-llm-api-explanation.ts \
 *   --irId ir_xai_hist_gradient_boosting_v1_163956_top_high_risk \
 *   --feedbackPath data/reports/faithfulness_validation/evaluation/llm_api/regeneration_feedback.jsonl \
 *   --artifactSubdir regeneration_attempt_1
 *
 * Important:
 * - This runner does NOT implement auto-loop.
 * - It only passes feedbackPath into Batch I when explicitly provided.
 * - It writes outputs into artifactSubdir to prevent overwriting base outputs.
 */
type CliArgs = {
  runMode: RunMode;
  batchId: string;
  inputSource: InputSource;
  limit?: number;
  irId?: string;
  customerId?: string;
  feedbackPath?: string;
  artifactSubdir?: string;
};

async function main(): Promise<void> {
  const args = parseCliArgs(process.argv.slice(2));

  console.log("=== Batch I v1.2 - LLM API Explanation Layer ===");
  console.log("This run WILL call the configured LLM API.");

  console.log("Config:");
  console.log(JSON.stringify(args, null, 2));

  console.log("Feedback path:", args.feedbackPath ?? "none");
  console.log("Artifact subdir:", args.artifactSubdir ?? "auto");

  console.log("LLM config:");
  console.log(
    JSON.stringify(
      {
        provider: process.env.LLM_PROVIDER ?? "deepseek",
        model: process.env.LLM_MODEL ?? "deepseek-v4-flash",
        baseUrl:
          process.env.LLM_BASE_URL ??
          "https://api.deepseek.com/chat/completions",
        temperature: process.env.LLM_TEMPERATURE ?? "0.45",
        maxTokens: process.env.LLM_MAX_TOKENS ?? "2400",
        jsonMode: process.env.LLM_ENABLE_JSON_MODE ?? "true",
        promptVersion:
          process.env.LLM_PROMPT_VERSION ??
          "batch_i_llm_prompt_v1.2_compact_feedback_ready",
        hasApiKey: Boolean(process.env.LLM_API_KEY),
      },
      null,
      2,
    ),
  );

  const result = await runLlmExplanationBatch({
    runMode: args.runMode,
    batchId: args.batchId,
    inputSource: args.inputSource,
    limit: args.limit,
    irId: args.irId,
    customerId: args.customerId,
    feedbackPath: args.feedbackPath,
    artifactSubdir: args.artifactSubdir,
  });

  console.log("\n=== Batch I v1.2 completed ===");
  console.log(`Generated records: ${result.records.length}`);

  console.log("Artifacts:");
  console.log(JSON.stringify(result.artifactPaths, null, 2));

  const failedCount = result.records.filter(
    (record) => record.quality.errors.length > 0,
  ).length;

  const warningCount = result.records.filter(
    (record) => record.quality.warnings.length > 0,
  ).length;

  const feedbackRecordCount = result.records.filter(
    (record) => record.metadata.has_regeneration_feedback,
  ).length;

  const totalTokens = result.records.reduce(
    (sum, record) =>
      sum + Number(record.raw_response?.usage?.total_tokens ?? 0),
    0,
  );

  console.log(`Records with errors: ${failedCount}`);
  console.log(`Records with warnings: ${warningCount}`);
  console.log(`Records generated with feedback: ${feedbackRecordCount}`);
  console.log(`Reported total tokens: ${totalTokens}`);

  if (failedCount > 0) {
    console.warn(`Warning: ${failedCount} records have generation errors.`);
    process.exitCode = 1;
  }
}

function parseCliArgs(rawArgs: string[]): CliArgs {
  const map = new Map<string, string>();

  for (let i = 0; i < rawArgs.length; i += 1) {
    const current = rawArgs[i];

    if (!current.startsWith("--")) {
      continue;
    }

    const withoutPrefix = current.slice(2);

    /**
     * Supports both:
     * --key value
     * --key=value
     */
    if (withoutPrefix.includes("=")) {
      const [key, ...valueParts] = withoutPrefix.split("=");
      map.set(key, valueParts.join("="));
      continue;
    }

    const key = withoutPrefix;
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

  const feedbackPath = normalizeOptionalString(map.get("feedbackPath"));
  const artifactSubdir = normalizeOptionalString(map.get("artifactSubdir"));
  const irId = normalizeOptionalString(map.get("irId"));
  const customerId = normalizeOptionalString(map.get("customerId"));

  return {
    runMode,
    batchId,
    inputSource,
    limit,
    irId,
    customerId,
    feedbackPath,
    artifactSubdir,
  };
}

function normalizeOptionalString(
  value: string | undefined,
): string | undefined {
  if (!value) {
    return undefined;
  }

  const trimmed = value.trim();

  if (!trimmed || trimmed === "true") {
    return undefined;
  }

  return trimmed;
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

main().catch((error: unknown) => {
  console.error("\nBatch I v1.2 failed.");
  console.error(error);
  process.exit(1);
});
