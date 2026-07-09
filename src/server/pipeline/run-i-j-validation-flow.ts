// src/server/pipeline/run-i-j-validation-flow.ts

import dotenv from "dotenv";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  runLlmExplanationBatch,
  type RunLlmExplanationBatchResult,
} from "../llm/batch-runner";

import type { InputSource, RunMode } from "../llm/explanation-schema";

import { runJ1BedrockClaimExtraction } from "../validator/claim-extraction-runner";
import { runJ2FaithfulnessValidation } from "../validator/faithfulness-validator";

import {
  runValidationDecisionFeedbackBuilder,
  type J3GeneratorType,
  type J3RunMode,
} from "../validator/validation-decision-feedback-builder";

dotenv.config({ path: ".env" });
dotenv.config({ path: ".env.local", override: false });

type FlowMode = "base" | "regeneration";

type FeedbackRecord = {
  ir_id?: unknown;
  attempt?: unknown;
  feedback_id?: unknown;
};

type CliArgs = {
  runMode: RunMode;
  batchId: string;
  inputSource: InputSource;

  limit?: number;
  irId?: string;
  customerId?: string;

  feedbackPath?: string;
  attempt?: number;
  runSlot?: string;

  forceJ1: boolean;
  runJ3: boolean;
  generateFeedbackForWarnings: boolean;
};

type ResolvedFlowConfig = {
  projectRoot: string;
  runMode: RunMode;
  batchId: string;
  inputSource: InputSource;

  flowMode: FlowMode;
  currentAttempt: number;
  nextAttemptIfFail: number;
  runSlot: string;

  limit?: number;
  irId?: string;
  customerId?: string;
  feedbackPath?: string;

  forceJ1: boolean;
  runJ3: boolean;
  generateFeedbackForWarnings: boolean;

  validationOutputDir: string;
};

type FlowSummary = {
  flow_name: "Batch I + Batch J Single-Pass Validation Flow";
  created_at: string;
  flow_mode: FlowMode;
  run_slot: string;
  current_attempt: number;
  next_attempt_if_fail: number;
  run_mode: RunMode;
  batch_id: string;
  input_source: InputSource;
  selected_filters: {
    limit?: number;
    ir_id?: string;
    customer_id?: string;
    feedback_path?: string;
  };
  paths: {
    llm_explanations_jsonl: string;
    claim_extractions_jsonl: string;
    faithfulness_validation_jsonl: string;
    faithfulness_validation_summary_json: string;
    faithfulness_validation_failures_json: string;
    validation_decisions_jsonl?: string;
    regeneration_feedback_jsonl?: string;
    finalization_candidates_jsonl?: string;
    flow_summary_json: string;
  };
  counts: {
    batch_i_records: number;
    batch_i_records_with_errors: number;
    batch_i_records_with_warnings: number;
    batch_i_records_with_feedback: number;
    j1_selected_records?: number;
    j1_failed?: number;
    j1_total_claims?: number;
    j2_status?: string;
    j2_validated_records?: number;
    j2_fail_records?: number;
    j2_pass_with_warn_records?: number;
    j3_regeneration_feedback_records?: number;
    j3_finalization_candidate_records?: number;
  };
  final_decision: {
    j2_status?: string;
    needs_regeneration: boolean;
    can_finalize: boolean;
    note: string;
  };
};

/**
 * Single-pass orchestrator:
 *
 * Batch I  -> generate LLM explanation
 * Batch J1 -> Bedrock structured claim extraction
 * Batch J2 -> rule-based faithfulness validation
 * Batch J3 -> decision + feedback artifacts
 *
 * This runner does NOT auto-loop.
 * If J2 fails, J3 writes feedback for the next attempt and this process stops.
 */
async function main(): Promise<void> {
  const args = parseCliArgs(process.argv.slice(2));
  const config = await resolveFlowConfig(args);

  printResolvedConfig(config);

  const batchIResult = await runBatchI(config);
  assertBatchIResultIsUsable(batchIResult);

  const llmExplanationsPath = batchIResult.artifactPaths.explanationsJsonl;

  const claimExtractionsPath = path.join(
    config.validationOutputDir,
    "claim_extractions.jsonl",
  );

  const faithfulnessValidationJsonlPath = path.join(
    config.validationOutputDir,
    "faithfulness_validation.jsonl",
  );

  const faithfulnessValidationSummaryPath = path.join(
    config.validationOutputDir,
    "faithfulness_validation_summary.json",
  );

  const faithfulnessValidationFailuresPath = path.join(
    config.validationOutputDir,
    "faithfulness_validation_failures.json",
  );

  const j1Summary = await runBatchJ1({
    config,
    llmExplanationsPath,
  });

  const j2Summary = await runBatchJ2({
    config,
    claimExtractionsPath,
  });

  const j3Result = config.runJ3
    ? await runBatchJ3({
        config,
      })
    : null;

  const flowSummaryPath = path.join(
    config.validationOutputDir,
    "ij_flow_summary.json",
  );

  const flowSummary = buildFlowSummary({
    config,
    batchIResult,
    j1Summary,
    j2Summary,
    j3Result,
    paths: {
      llmExplanationsPath,
      claimExtractionsPath,
      faithfulnessValidationJsonlPath,
      faithfulnessValidationSummaryPath,
      faithfulnessValidationFailuresPath,
      flowSummaryPath,
    },
  });

  await mkdir(config.validationOutputDir, { recursive: true });
  await writeFile(
    flowSummaryPath,
    JSON.stringify(flowSummary, null, 2),
    "utf8",
  );

  console.log("\n=== Single-pass flow completed ===");
  console.log(JSON.stringify(flowSummary, null, 2));

  /**
   * Do not abort before J3. J3 must have a chance to create feedback.
   * After the full single pass, fail process only if J2 says FAIL.
   */
  if (flowSummary.final_decision.needs_regeneration) {
    process.exitCode = 1;
  }
}

async function runBatchI(
  config: ResolvedFlowConfig,
): Promise<RunLlmExplanationBatchResult> {
  console.log("\n=== Step 1/4: Batch I - LLM Explanation Generation ===");

  /**
   * artifactSubdir is intentionally passed as an extra option.
   * If the current Batch I writer supports it, it will write into base/
   * or regeneration_attempt_N/. If ignored by older code, the returned
   * artifactPaths are still the source of truth for J.1 input.
   */
  const batchIOptions = {
    runMode: config.runMode,
    batchId: config.batchId,
    inputSource: config.inputSource,
    limit: config.limit,
    irId: config.irId,
    customerId: config.customerId,
    feedbackPath: config.feedbackPath,
    artifactSubdir: config.runSlot,
  } as Parameters<typeof runLlmExplanationBatch>[0] & {
    artifactSubdir?: string;
  };

  return runLlmExplanationBatch(batchIOptions);
}

async function runBatchJ1(input: {
  config: ResolvedFlowConfig;
  llmExplanationsPath: string;
}) {
  const { config, llmExplanationsPath } = input;

  console.log("\n=== Step 2/4: Batch J.1 - Bedrock Claim Extraction ===");

  return runJ1BedrockClaimExtraction({
    runName: config.runSlot,
    inputPath: llmExplanationsPath,
    outputDir: config.validationOutputDir,
    limit: null,
    forceReextract: config.forceJ1,
    matchIrIdsFromPath: null,
  });
}

async function runBatchJ2(input: {
  config: ResolvedFlowConfig;
  claimExtractionsPath: string;
}) {
  const { config, claimExtractionsPath } = input;

  console.log("\n=== Step 3/4: Batch J.2 - Faithfulness Validation ===");

  process.env.J2_CLAIM_EXTRACTIONS_PATH = claimExtractionsPath;
  process.env.J2_OUTPUT_DIR = config.validationOutputDir;

  /**
   * Keep default Explanation IR path unless explicitly configured outside.
   * Existing default:
   * data/reports/explanation_ir/evaluation/explanation_ir.jsonl
   */
  return runJ2FaithfulnessValidation();
}

async function runBatchJ3(input: { config: ResolvedFlowConfig }) {
  const { config } = input;

  console.log("\n=== Step 4/4: Batch J.3 - Decision & Feedback Builder ===");

  return runValidationDecisionFeedbackBuilder({
    runMode: config.runMode as J3RunMode,
    generatorType: "llm_api" as J3GeneratorType,
    validationDir: config.validationOutputDir,
    generateFeedbackForWarnings: config.generateFeedbackForWarnings,
    nextAttempt: config.nextAttemptIfFail,
  });
}

async function resolveFlowConfig(args: CliArgs): Promise<ResolvedFlowConfig> {
  const projectRoot = process.cwd();

  const feedbackInfo = args.feedbackPath
    ? await readFeedbackInfo(args.feedbackPath)
    : {
        records: [] as FeedbackRecord[],
        uniqueIrIds: [] as string[],
        inferredAttempt: 0,
      };

  const flowMode: FlowMode = args.feedbackPath ? "regeneration" : "base";

  const currentAttempt =
    flowMode === "base"
      ? 0
      : (args.attempt ?? feedbackInfo.inferredAttempt) || 1;

  if (flowMode === "base" && currentAttempt !== 0) {
    throw new Error(
      "Invalid config: base flow must not have --attempt > 0. Remove --attempt or provide --feedbackPath.",
    );
  }

  if (flowMode === "regeneration" && currentAttempt <= 0) {
    throw new Error(
      "Invalid config: regeneration flow requires a positive attempt number.",
    );
  }

  let effectiveIrId = args.irId;

  /**
   * Safety rule:
   * In feedback mode, do not accidentally regenerate unrelated IR records.
   * If feedback file contains exactly one IR id, auto-use it.
   * If it contains multiple IR ids, require explicit --irId for now.
   */
  if (flowMode === "regeneration" && !effectiveIrId && !args.customerId) {
    if (feedbackInfo.uniqueIrIds.length === 1) {
      effectiveIrId = feedbackInfo.uniqueIrIds[0];
    } else {
      throw new Error(
        [
          "Feedback file contains multiple or zero IR ids.",
          "This single-pass runner prevents accidental regeneration of unrelated records.",
          "Provide --irId for the record you want to regenerate, or split feedback into one file per record.",
          `Feedback IR ids found: ${feedbackInfo.uniqueIrIds.join(", ") || "none"}`,
        ].join("\n"),
      );
    }
  }

  const runSlot =
    args.runSlot ??
    (flowMode === "base" ? "base" : `regeneration_attempt_${currentAttempt}`);

  const validationOutputDir = buildValidationOutputDir({
    runMode: args.runMode,
    batchId: args.batchId,
    runSlot,
  });

  return {
    projectRoot,
    runMode: args.runMode,
    batchId: args.batchId,
    inputSource: args.inputSource,
    flowMode,
    currentAttempt,
    nextAttemptIfFail: currentAttempt + 1,
    runSlot,
    limit: flowMode === "regeneration" ? undefined : args.limit,
    irId: effectiveIrId,
    customerId: args.customerId,
    feedbackPath: args.feedbackPath,
    forceJ1: args.forceJ1,
    runJ3: args.runJ3,
    generateFeedbackForWarnings: args.generateFeedbackForWarnings,
    validationOutputDir,
  };
}

function buildValidationOutputDir(input: {
  runMode: RunMode;
  batchId: string;
  runSlot: string;
}): string {
  if (input.runMode === "evaluation") {
    return path.join(
      "data",
      "reports",
      "faithfulness_validation",
      "evaluation",
      "llm_api",
      sanitizePathPart(input.runSlot),
    );
  }

  return path.join(
    "data",
    "reports",
    "faithfulness_validation",
    "inference",
    sanitizePathPart(input.batchId),
    "llm_api",
    sanitizePathPart(input.runSlot),
  );
}

async function readFeedbackInfo(feedbackPath: string): Promise<{
  records: FeedbackRecord[];
  uniqueIrIds: string[];
  inferredAttempt: number;
}> {
  const records = feedbackPath.endsWith(".jsonl")
    ? await readJsonlFile<FeedbackRecord>(feedbackPath)
    : await readJsonArrayFile<FeedbackRecord>(feedbackPath);

  const uniqueIrIds = Array.from(
    new Set(
      records
        .map((record) => String(record.ir_id ?? "").trim())
        .filter(Boolean),
    ),
  );

  const attempts = records
    .map((record) => Number(record.attempt))
    .filter((value) => Number.isInteger(value) && value > 0);

  return {
    records,
    uniqueIrIds,
    inferredAttempt: attempts.length > 0 ? Math.max(...attempts) : 1,
  };
}

async function readJsonlFile<T>(filePath: string): Promise<T[]> {
  const content = await readFile(filePath, "utf8");

  return content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      try {
        return JSON.parse(line) as T;
      } catch (error) {
        throw new Error(
          `Invalid JSONL at ${filePath}, line ${index + 1}: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      }
    });
}

async function readJsonArrayFile<T>(filePath: string): Promise<T[]> {
  const raw = (await readFile(filePath, "utf8")).trim();

  if (!raw) {
    return [];
  }

  const parsed = JSON.parse(raw) as unknown;

  if (Array.isArray(parsed)) {
    return parsed as T[];
  }

  return [parsed as T];
}

function assertBatchIResultIsUsable(
  result: RunLlmExplanationBatchResult,
): void {
  if (result.records.length === 0) {
    throw new Error("Batch I generated zero records. Stop before J.1.");
  }

  const recordsWithErrors = result.records.filter(
    (record) => record.quality.errors.length > 0,
  );

  if (recordsWithErrors.length > 0) {
    throw new Error(
      [
        `Batch I generated ${recordsWithErrors.length} record(s) with errors. Stop before J.1.`,
        ...recordsWithErrors
          .slice(0, 5)
          .map((record) =>
            [
              `- ${record.explanation_id}`,
              ...record.quality.errors.map((error) => `  • ${error}`),
            ].join("\n"),
          ),
      ].join("\n"),
    );
  }
}

function buildFlowSummary(input: {
  config: ResolvedFlowConfig;
  batchIResult: RunLlmExplanationBatchResult;
  j1Summary: any;
  j2Summary: any;
  j3Result: any | null;
  paths: {
    llmExplanationsPath: string;
    claimExtractionsPath: string;
    faithfulnessValidationJsonlPath: string;
    faithfulnessValidationSummaryPath: string;
    faithfulnessValidationFailuresPath: string;
    flowSummaryPath: string;
  };
}): FlowSummary {
  const { config, batchIResult, j1Summary, j2Summary, j3Result, paths } = input;

  const batchIRecordsWithErrors = batchIResult.records.filter(
    (record) => record.quality.errors.length > 0,
  ).length;

  const batchIRecordsWithWarnings = batchIResult.records.filter(
    (record) => record.quality.warnings.length > 0,
  ).length;

  const batchIRecordsWithFeedback = batchIResult.records.filter(
    (record) => record.metadata.has_regeneration_feedback,
  ).length;

  const j2Status = String(j2Summary?.status ?? "UNKNOWN");
  const needsRegeneration = j2Status === "FAIL";
  const canFinalize = j2Status === "PASS" || j2Status === "PASS_WITH_WARN";

  return {
    flow_name: "Batch I + Batch J Single-Pass Validation Flow",
    created_at: new Date().toISOString(),
    flow_mode: config.flowMode,
    run_slot: config.runSlot,
    current_attempt: config.currentAttempt,
    next_attempt_if_fail: config.nextAttemptIfFail,
    run_mode: config.runMode,
    batch_id: config.batchId,
    input_source: config.inputSource,
    selected_filters: {
      limit: config.limit,
      ir_id: config.irId,
      customer_id: config.customerId,
      feedback_path: config.feedbackPath,
    },
    paths: {
      llm_explanations_jsonl: paths.llmExplanationsPath,
      claim_extractions_jsonl: paths.claimExtractionsPath,
      faithfulness_validation_jsonl: paths.faithfulnessValidationJsonlPath,
      faithfulness_validation_summary_json:
        paths.faithfulnessValidationSummaryPath,
      faithfulness_validation_failures_json:
        paths.faithfulnessValidationFailuresPath,
      validation_decisions_jsonl: j3Result?.paths?.validationDecisionsJsonlPath,
      regeneration_feedback_jsonl:
        j3Result?.paths?.regenerationFeedbackJsonlPath,
      finalization_candidates_jsonl:
        j3Result?.paths?.finalizationCandidatesJsonlPath,
      flow_summary_json: paths.flowSummaryPath,
    },
    counts: {
      batch_i_records: batchIResult.records.length,
      batch_i_records_with_errors: batchIRecordsWithErrors,
      batch_i_records_with_warnings: batchIRecordsWithWarnings,
      batch_i_records_with_feedback: batchIRecordsWithFeedback,
      j1_selected_records: j1Summary?.selected_records,
      j1_failed: j1Summary?.failed,
      j1_total_claims: j1Summary?.total_claims,
      j2_status: j2Status,
      j2_validated_records: j2Summary?.counts?.validated_records,
      j2_fail_records: j2Summary?.counts?.fail_records,
      j2_pass_with_warn_records: j2Summary?.counts?.pass_with_warn_records,
      j3_regeneration_feedback_records:
        j3Result?.summary?.counts?.regeneration_feedback_records,
      j3_finalization_candidate_records:
        j3Result?.summary?.counts?.finalization_candidate_records,
    },
    final_decision: {
      j2_status: j2Status,
      needs_regeneration: needsRegeneration,
      can_finalize: canFinalize,
      note: needsRegeneration
        ? "J.2 failed. J.3 feedback was generated for the next attempt if runJ3=true. This runner does not auto-loop."
        : canFinalize
          ? "J.2 did not fail. Explanation can move to finalization policy."
          : "Unknown J.2 status. Review artifacts manually.",
    },
  };
}

function printResolvedConfig(config: ResolvedFlowConfig): void {
  console.log("=== Batch I + Batch J Single-Pass Flow ===");
  console.log("This runner WILL call the configured LLM API in Batch I.");
  console.log("This runner WILL call Bedrock in Batch J.1.");
  console.log("This runner does NOT auto-loop.");
  console.log("");
  console.log("Resolved config:");
  console.log(
    JSON.stringify(
      {
        runMode: config.runMode,
        batchId: config.batchId,
        inputSource: config.inputSource,
        flowMode: config.flowMode,
        currentAttempt: config.currentAttempt,
        nextAttemptIfFail: config.nextAttemptIfFail,
        runSlot: config.runSlot,
        limit: config.limit,
        irId: config.irId,
        customerId: config.customerId,
        feedbackPath: config.feedbackPath,
        forceJ1: config.forceJ1,
        runJ3: config.runJ3,
        generateFeedbackForWarnings: config.generateFeedbackForWarnings,
        validationOutputDir: config.validationOutputDir,
      },
      null,
      2,
    ),
  );
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

  const limit = parseOptionalPositiveInteger(map.get("limit"), "limit");
  const attempt = parseOptionalPositiveInteger(map.get("attempt"), "attempt");

  return {
    runMode: parseRunMode(map.get("runMode") ?? "evaluation"),
    batchId: normalizeOptionalString(map.get("batchId")) ?? "evaluation",
    inputSource: parseInputSource(map.get("inputSource") ?? "precomputed_ir"),
    limit,
    irId: normalizeOptionalString(map.get("irId")),
    customerId: normalizeOptionalString(map.get("customerId")),
    feedbackPath: normalizeOptionalString(map.get("feedbackPath")),
    attempt,
    runSlot: normalizeOptionalString(map.get("runSlot")),
    forceJ1: parseBoolean(map.get("forceJ1") ?? map.get("force"), true),
    runJ3: parseBoolean(map.get("runJ3"), true),
    generateFeedbackForWarnings: parseBoolean(
      map.get("generateFeedbackForWarnings"),
      false,
    ),
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

function parseBoolean(
  value: string | undefined,
  defaultValue: boolean,
): boolean {
  if (value === undefined) {
    return defaultValue;
  }

  const normalized = value.trim().toLowerCase();

  if (["true", "1", "yes", "y"].includes(normalized)) {
    return true;
  }

  if (["false", "0", "no", "n"].includes(normalized)) {
    return false;
  }

  return defaultValue;
}

function parseOptionalPositiveInteger(
  value: string | undefined,
  name: string,
): number | undefined {
  if (!value) {
    return undefined;
  }

  const parsed = Number(value);

  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`Invalid --${name} value: ${value}`);
  }

  return parsed;
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

function sanitizePathPart(value: string): string {
  const trimmed = value.trim();

  if (!trimmed) {
    return "unknown";
  }

  return trimmed.replace(/[^a-zA-Z0-9_-]+/g, "_");
}

main().catch((error: unknown) => {
  console.error("\nBatch I + Batch J single-pass flow failed.");
  console.error(error);
  process.exit(1);
});
