// src/server/llm/batch-runner.ts

import { readFile } from "node:fs/promises";
import path from "node:path";

import type {
  ExplanationGenerationRequest,
  ExplanationIrRecord,
  LlmExplanationRecord,
  RunMode,
} from "./explanation-schema";

import { isExplanationIrRecord, normalizeRunMode } from "./explanation-schema";

import { generateExplanationFromIr } from "./explanation-generator";
import { writeLlmExplanationArtifacts } from "./artifact-writer";

/**
 * Batch I v1.0 - Batch Runner
 *
 * Responsibility:
 * Read Explanation IR JSONL -> call LLM explanation generator -> write artifacts.
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
      `Batch I v1.0 currently supports inputSource="precomputed_ir" only. Received: ${options.inputSource}`,
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

  const limited =
    typeof options.limit === "number" && options.limit > 0
      ? filtered.slice(0, options.limit)
      : filtered;

  const outputRecords: LlmExplanationRecord[] = [];

  for (let index = 0; index < limited.length; index++) {
    const irRecord = limited[index];

    console.log(
      `[Batch I v1.0] Generating ${index + 1}/${limited.length}: ${
        irRecord.ir_id
      }`,
    );

    const record = await generateExplanationFromIr(irRecord, {
      runMode: normalizeRunMode(irRecord.run_mode, options.runMode),
      batchId: options.batchId,
      inputSource: options.inputSource,
    });

    outputRecords.push(record);
  }

  const artifactPaths = await writeLlmExplanationArtifacts(outputRecords, {
    projectRoot,
    runMode: options.runMode,
    batchId: options.batchId,
    inputSource: options.inputSource,
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

  for (let index = 0; index < lines.length; index++) {
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
