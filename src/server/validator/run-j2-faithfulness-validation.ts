// src/server/validator/run-j2-faithfulness-validation.ts

import "dotenv/config";

import { runJ2FaithfulnessValidation } from "./faithfulness-validator";

/**
 * Batch J.2 runner.
 *
 * Base:
 * npx tsx src/server/validator/run-j2-faithfulness-validation.ts \
 *   --claimExtractionsPath data/reports/faithfulness_validation/evaluation/llm_api/base/claim_extractions.jsonl \
 *   --outputDir data/reports/faithfulness_validation/evaluation/llm_api/base
 *
 * Regeneration attempt:
 * npx tsx src/server/validator/run-j2-faithfulness-validation.ts \
 *   --claimExtractionsPath data/reports/faithfulness_validation/evaluation/llm_api/regeneration_attempt_1/claim_extractions.jsonl \
 *   --outputDir data/reports/faithfulness_validation/evaluation/llm_api/regeneration_attempt_1
 */

type CliArgs = {
  claimExtractionsPath?: string;
  explanationIrPath?: string;
  outputDir?: string;
};

async function main(): Promise<void> {
  const args = parseCliArgs(process.argv.slice(2));

  if (args.claimExtractionsPath) {
    process.env.J2_CLAIM_EXTRACTIONS_PATH = args.claimExtractionsPath;
  }

  if (args.explanationIrPath) {
    process.env.J2_EXPLANATION_IR_PATH = args.explanationIrPath;
  }

  if (args.outputDir) {
    process.env.J2_OUTPUT_DIR = args.outputDir;
  }

  console.log("=== Batch J.2 - Faithfulness Validation ===");
  console.log("Config:");
  console.log(JSON.stringify(args, null, 2));

  await runJ2FaithfulnessValidation();
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

  return {
    claimExtractionsPath: normalizeOptionalString(
      map.get("claimExtractionsPath") ?? map.get("inputPath"),
    ),
    explanationIrPath: normalizeOptionalString(map.get("explanationIrPath")),
    outputDir: normalizeOptionalString(map.get("outputDir")),
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

main().catch((error: unknown) => {
  console.error("\nBatch J.2 Faithfulness Validation failed.");
  console.error(error);
  process.exit(1);
});
