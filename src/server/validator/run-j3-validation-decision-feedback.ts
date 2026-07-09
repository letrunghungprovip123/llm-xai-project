// src/server/validator/run-j3-validation-decision-feedback.ts

import dotenv from "dotenv";

import {
  runValidationDecisionFeedbackBuilder,
  type J3GeneratorType,
  type J3RunMode,
} from "./validation-decision-feedback-builder";

dotenv.config({ path: ".env" });
dotenv.config({ path: ".env.local", override: false });

/**
 * Batch J.3 runner.
 *
 * Default:
 * npx tsx src/server/validator/run-j3-validation-decision-feedback.ts
 *
 * Explicit:
 * npx tsx src/server/validator/run-j3-validation-decision-feedback.ts \
 *   --runMode evaluation \
 *   --generatorType llm_api
 *
 * Generate feedback also for WARN-only records:
 * npx tsx src/server/validator/run-j3-validation-decision-feedback.ts \
 *   --generateFeedbackForWarnings true
 */

type CliArgs = {
  runMode: J3RunMode;
  generatorType: J3GeneratorType;
  validationDir?: string;
  validationJsonlPath?: string;
  validationSummaryJsonPath?: string;
  validationFailuresJsonPath?: string;
  generateFeedbackForWarnings: boolean;
  nextAttempt: number;
};

async function main() {
  const args = parseCliArgs(process.argv.slice(2));

  console.log("=== Batch J.3 - Validation Decision & Feedback Builder ===");
  console.log("This run does NOT call DeepSeek.");
  console.log("This run does NOT call Bedrock.");
  console.log("Config:");
  console.log(JSON.stringify(args, null, 2));

  const result = await runValidationDecisionFeedbackBuilder({
    runMode: args.runMode,
    generatorType: args.generatorType,
    validationDir: args.validationDir,
    validationJsonlPath: args.validationJsonlPath,
    validationSummaryJsonPath: args.validationSummaryJsonPath,
    validationFailuresJsonPath: args.validationFailuresJsonPath,
    generateFeedbackForWarnings: args.generateFeedbackForWarnings,
    nextAttempt: args.nextAttempt,
  });

  console.log("\n=== Batch J.3 completed ===");
  console.log("Summary:");
  console.log(JSON.stringify(result.summary.counts, null, 2));
  console.log("Artifacts:");
  console.log(
    JSON.stringify(
      {
        validation_decisions_jsonl: result.paths.validationDecisionsJsonlPath,
        regeneration_feedback_jsonl: result.paths.regenerationFeedbackJsonlPath,
        regeneration_feedback_summary_json:
          result.paths.regenerationFeedbackSummaryJsonPath,
        finalization_candidates_jsonl:
          result.paths.finalizationCandidatesJsonlPath,
        validation_decision_report_md:
          result.paths.validationDecisionReportMdPath,
      },
      null,
      2,
    ),
  );

  if (result.summary.counts.system_error_records > 0) {
    console.warn(
      `Warning: ${result.summary.counts.system_error_records} records have SYSTEM_ERROR decision.`,
    );
    process.exitCode = 1;
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
  const generatorType = map.get("generatorType") ?? "llm_api";

  const generateFeedbackForWarnings = parseBoolean(
    map.get("generateFeedbackForWarnings") ?? "false",
  );

  const nextAttemptRaw = map.get("nextAttempt") ?? "1";
  const nextAttempt = Number(nextAttemptRaw);

  if (!Number.isFinite(nextAttempt) || nextAttempt <= 0) {
    throw new Error(`Invalid --nextAttempt value: ${nextAttemptRaw}`);
  }

  return {
    runMode,
    generatorType,
    validationDir: map.get("validationDir"),
    validationJsonlPath: map.get("validationJsonlPath"),
    validationSummaryJsonPath: map.get("validationSummaryJsonPath"),
    validationFailuresJsonPath: map.get("validationFailuresJsonPath"),
    generateFeedbackForWarnings,
    nextAttempt,
  };
}

function parseRunMode(value: string): J3RunMode {
  if (value === "evaluation" || value === "inference") {
    return value;
  }

  throw new Error(`Invalid --runMode value: ${value}`);
}

function parseBoolean(value: string): boolean {
  const normalized = value.trim().toLowerCase();

  if (["true", "1", "yes", "y"].includes(normalized)) {
    return true;
  }

  if (["false", "0", "no", "n"].includes(normalized)) {
    return false;
  }

  throw new Error(`Invalid boolean value: ${value}`);
}

main().catch((error) => {
  console.error("\nBatch J.3 failed.");
  console.error(error);
  process.exit(1);
});
