// src/server/finalization/run-k-finalize-explanations.ts

import "dotenv/config";

import { runFinalExplanationFinalizer } from "./final-explanation-finalizer";

type CliArgs = {
  runMode?: string;
  generatorType?: string;
  runSlot?: string;
  llmExplanationsPath?: string;
  finalizationCandidatesPath?: string;
  validationDecisionsPath?: string;
  faithfulnessValidationPath?: string;
  outputDir?: string;
};

async function main(): Promise<void> {
  const args = parseCliArgs(process.argv.slice(2));

  console.log("=== Batch K - Final Explanation Finalization ===");
  console.log("This run does NOT call LLM.");
  console.log("This run does NOT call Bedrock.");
  console.log("Config:");
  console.log(JSON.stringify(args, null, 2));

  await runFinalExplanationFinalizer(args);
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
    runMode: normalizeOptionalString(map.get("runMode")),
    generatorType: normalizeOptionalString(map.get("generatorType")),
    runSlot: normalizeOptionalString(map.get("runSlot")),
    llmExplanationsPath: normalizeOptionalString(
      map.get("llmExplanationsPath"),
    ),
    finalizationCandidatesPath: normalizeOptionalString(
      map.get("finalizationCandidatesPath"),
    ),
    validationDecisionsPath: normalizeOptionalString(
      map.get("validationDecisionsPath"),
    ),
    faithfulnessValidationPath: normalizeOptionalString(
      map.get("faithfulnessValidationPath"),
    ),
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
  console.error("\nBatch K finalization failed.");
  console.error(error);
  process.exit(1);
});
