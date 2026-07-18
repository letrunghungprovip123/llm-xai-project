// src/server/llm/batch-runner.ts

import { readFile } from "node:fs/promises";
import path from "node:path";

import type {
  ExplanationGenerationRequest,
  ExplanationIrRecord,
  LlmExplanationRecord,
  RegenerationFeedback,
  RunMode,
} from "./explanation-schema";

import { isExplanationIrRecord, normalizeRunMode } from "./explanation-schema";
import { generateExplanationFromIr } from "./explanation-generator";
import { writeLlmExplanationArtifacts } from "./artifact-writer";

/**
 * Batch I v1.2 - LLM API Batch Runner
 *
 * Reads Explanation IR JSONL -> calls LLM explanation generator -> writes artifacts.
 *
 * Feedback-ready design:
 * - Normal generation: no feedbackPath.
 * - Controlled regeneration: provide feedbackPath from Batch J.3.
 *
 * Artifact-lineage rule:
 * - Normal generation defaults to artifactSubdir="base".
 * - Regeneration defaults to artifactSubdir="regeneration_attempt_<n>".
 *
 * Important:
 * - This runner does NOT implement auto-loop.
 * - It only passes matching feedback records into Batch I generation.
 */

export type RunLlmExplanationBatchOptions = ExplanationGenerationRequest & {
  projectRoot?: string;
};

export type RunLlmExplanationBatchResult = {
  records: LlmExplanationRecord[];
  artifactPaths: {
    outputDir: string;
    explanationsJsonl: string;
    summaryCsv: string;
    qualityReportJson: string;
    manifestJson: string;
  };
};

export async function runLlmExplanationBatch(
  options: RunLlmExplanationBatchOptions,
): Promise<RunLlmExplanationBatchResult> {
  if (options.inputSource !== "precomputed_ir") {
    throw new Error(
      `Batch I v1.2 currently supports inputSource="precomputed_ir" only. Received: ${options.inputSource}`,
    );
  }

  const projectRoot = options.projectRoot ?? process.cwd();

  const irPath = buildIrInputPath({
    projectRoot,
    runMode: options.runMode,
    batchId: options.batchId,
  });

  const allIrRecords = await readJsonlFile<ExplanationIrRecord>(irPath);
  const validIrRecords = allIrRecords.filter(isExplanationIrRecord);
  const filtered = filterIrRecords(validIrRecords, options);

  const feedbackByIrId = options.feedbackPath
    ? await readFeedbackByIrId(options.feedbackPath)
    : new Map<string, RegenerationFeedback>();

  const artifactSubdir = resolveArtifactSubdir({
    requestedArtifactSubdir: options.artifactSubdir,
    feedbackByIrId,
    hasFeedbackPath: Boolean(options.feedbackPath),
  });

  const limited =
    typeof options.limit === "number" && options.limit > 0
      ? filtered.slice(0, options.limit)
      : filtered;

  const outputRecords: LlmExplanationRecord[] = [];

  console.log("[Batch I v1.2 LLM API] IR input:", irPath);
  console.log(
    "[Batch I v1.2 LLM API] Valid IR records:",
    validIrRecords.length,
  );
  console.log("[Batch I v1.2 LLM API] Selected records:", limited.length);
  console.log(
    "[Batch I v1.2 LLM API] Feedback path:",
    options.feedbackPath ?? "none",
  );
  console.log("[Batch I v1.2 LLM API] Feedback records:", feedbackByIrId.size);
  console.log("[Batch I v1.2 LLM API] Artifact subdir:", artifactSubdir);

  for (let index = 0; index < limited.length; index += 1) {
    const irRecord = limited[index];
    const feedback = feedbackByIrId.get(irRecord.ir_id) ?? null;
    const generationAttempt = feedback ? feedback.attempt : 0;

    console.log(
      `[Batch I v1.2 LLM API] Generating ${index + 1}/${limited.length}: ${
        irRecord.ir_id
      }${feedback ? ` with feedback ${feedback.feedback_id}` : ""}`,
    );

    const record = await generateExplanationFromIr(irRecord, {
      runMode: normalizeRunMode(irRecord.run_mode, options.runMode),
      batchId: options.batchId,
      inputSource: options.inputSource,
      feedback,
      generationAttempt,
    });

    outputRecords.push(record);

    if (record.quality.errors.length > 0) {
      console.warn(
        `[Batch I v1.2 LLM API] Record ${record.explanation_id} has errors:`,
      );
      for (const error of record.quality.errors) {
        console.warn(`  - ${error}`);
      }
    }

    if (record.quality.warnings.length > 0) {
      console.warn(
        `[Batch I v1.2 LLM API] Record ${record.explanation_id} has warnings:`,
      );
      for (const warning of record.quality.warnings.slice(0, 5)) {
        console.warn(`  - ${warning}`);
      }
    }
  }

  const artifactPaths = await writeLlmExplanationArtifacts(outputRecords, {
    projectRoot,
    runMode: options.runMode,
    batchId: options.batchId,
    inputSource: options.inputSource,
    artifactSubdir,
  });

  return {
    records: outputRecords,
    artifactPaths,
  };
}

export function buildIrInputPath(input: {
  projectRoot: string;
  runMode: RunMode;
  batchId: string;
}): string {
  if (input.runMode === "evaluation") {
    return path.join(
      input.projectRoot,
      "data",
      "reports",
      "explanation_ir",
      "evaluation",
      "explanation_ir.jsonl",
    );
  }

  return path.join(
    input.projectRoot,
    "data",
    "reports",
    "explanation_ir",
    "inference",
    input.batchId,
    "explanation_ir.jsonl",
  );
}

async function readJsonlFile<T>(filePath: string): Promise<T[]> {
  const content = await readFile(filePath, "utf-8");
  const records: T[] = [];

  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];

    try {
      records.push(JSON.parse(line) as T);
    } catch (error) {
      throw new Error(
        `Failed to parse JSONL file at ${filePath}, line ${index + 1}: ${
          error instanceof Error ? error.message : "Unknown parse error"
        }`,
      );
    }
  }

  return records;
}

async function readJsonArrayFile<T>(filePath: string): Promise<T[]> {
  const content = (await readFile(filePath, "utf-8")).trim();

  if (!content) {
    return [];
  }

  try {
    const parsed = JSON.parse(content) as unknown;

    if (Array.isArray(parsed)) {
      return parsed as T[];
    }

    return [parsed as T];
  } catch (error) {
    throw new Error(
      `Failed to parse JSON feedback file at ${filePath}: ${
        error instanceof Error ? error.message : "Unknown parse error"
      }`,
    );
  }
}

async function readFeedbackByIrId(
  feedbackPath: string,
): Promise<Map<string, RegenerationFeedback>> {
  const feedbackRecords = feedbackPath.endsWith(".jsonl")
    ? await readJsonlFile<RegenerationFeedback>(feedbackPath)
    : await readJsonArrayFile<RegenerationFeedback>(feedbackPath);

  const map = new Map<string, RegenerationFeedback>();

  for (const feedback of feedbackRecords) {
    if (!feedback || typeof feedback.ir_id !== "string") {
      continue;
    }

    const existing = map.get(feedback.ir_id);

    if (!existing || feedback.attempt >= existing.attempt) {
      map.set(feedback.ir_id, feedback);
    }
  }

  return map;
}

function filterIrRecords(
  records: ExplanationIrRecord[],
  options: RunLlmExplanationBatchOptions,
): ExplanationIrRecord[] {
  return records.filter((record) => {
    if (options.irId && record.ir_id !== options.irId) {
      return false;
    }

    if (options.customerId) {
      const customer = record.customer;
      const customerId = String(
        customer?.SK_ID_CURR ?? customer?.sk_id_curr ?? "",
      );

      if (customerId !== String(options.customerId)) {
        return false;
      }
    }

    return true;
  });
}

function resolveArtifactSubdir(input: {
  requestedArtifactSubdir?: string;
  feedbackByIrId: Map<string, RegenerationFeedback>;
  hasFeedbackPath: boolean;
}): string {
  const requested = normalizeArtifactSubdir(input.requestedArtifactSubdir);

  if (requested) {
    return requested;
  }

  if (!input.hasFeedbackPath) {
    return "base";
  }

  const attempts = Array.from(input.feedbackByIrId.values())
    .map((feedback) => Number(feedback.attempt))
    .filter((attempt) => Number.isFinite(attempt) && attempt > 0);

  const maxAttempt = attempts.length > 0 ? Math.max(...attempts) : 1;

  return `regeneration_attempt_${maxAttempt}`;
}

function normalizeArtifactSubdir(
  value: string | undefined,
): string | undefined {
  if (!value) {
    return undefined;
  }

  const trimmed = value.trim();

  if (!trimmed || trimmed === "true") {
    return undefined;
  }

  return trimmed.replace(/[^a-zA-Z0-9_-]+/g, "_");
}
