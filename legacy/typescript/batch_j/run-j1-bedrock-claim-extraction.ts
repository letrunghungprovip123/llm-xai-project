// src/server/validator/run-j1-bedrock-claim-extraction.ts

import "dotenv/config";

import {
  runJ1BedrockClaimExtraction,
  type J1RunnerOptions,
} from "./claim-extraction-runner";

/**
 * Batch J.1 runner.
 *
 * Base:
 * npx tsx src/server/validator/run-j1-bedrock-claim-extraction.ts \
 *   --runName base \
 *   --inputPath data/reports/llm_explanations/evaluation/llm_api/base/llm_explanations.jsonl \
 *   --outputDir data/reports/faithfulness_validation/evaluation/llm_api/base \
 *   --force
 *
 * Regeneration attempt:
 * npx tsx src/server/validator/run-j1-bedrock-claim-extraction.ts \
 *   --runName regeneration_attempt_1 \
 *   --inputPath data/reports/llm_explanations/evaluation/llm_api/regeneration_attempt_1/llm_explanations.jsonl \
 *   --outputDir data/reports/faithfulness_validation/evaluation/llm_api/regeneration_attempt_1 \
 *   --force
 */

type CliArgs = Partial<J1RunnerOptions>;

async function main(): Promise<void> {
  const args = parseCliArgs(process.argv.slice(2));

  console.log("=== Batch J.1 - Bedrock Claim Extraction ===");
  console.log("Config:");
  console.log(JSON.stringify(args, null, 2));

  await runJ1BedrockClaimExtraction(args);
}

function parseCliArgs(rawArgs: string[]): CliArgs {
  const map = new Map<string, string>();

  for (let i = 0; i < rawArgs.length; i += 1) {
    const current = rawArgs[i];

    if (!current.startsWith("--")) {
      continue;
    }

    const withoutPrefix = current.slice(2);

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

  const limitRaw = map.get("limit");
  const limit = limitRaw ? Number(limitRaw) : undefined;

  if (limitRaw && (!Number.isInteger(limit) || Number(limit) <= 0)) {
    throw new Error(`Invalid --limit value: ${limitRaw}`);
  }

  return {
    runName: normalizeOptionalString(map.get("runName")),
    inputPath: normalizeOptionalString(map.get("inputPath")),
    outputDir: normalizeOptionalString(map.get("outputDir")),
    matchIrIdsFromPath: normalizeOptionalString(map.get("matchIrIdsFromPath")),
    limit: limit ?? null,
    forceReextract: parseBooleanFlag(map, "force", "forceReextract"),
  };
}

function parseBooleanFlag(
  map: Map<string, string>,
  primaryKey: string,
  secondaryKey?: string,
): boolean | undefined {
  const raw =
    map.get(primaryKey) ?? (secondaryKey ? map.get(secondaryKey) : undefined);

  if (raw === undefined) {
    return undefined;
  }

  if (raw === "true" || raw === "1" || raw === "yes") {
    return true;
  }

  if (raw === "false" || raw === "0" || raw === "no") {
    return false;
  }

  return Boolean(raw);
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

main().catch((error: unknown) => {
  console.error("\nBatch J.1 Bedrock claim extraction failed.");
  console.error(error);
  process.exit(1);
});
