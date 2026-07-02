// src/server/llm/artifact-writer.ts

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import type {
  InputSource,
  LlmExplanationRecord,
  RunMode,
} from "./explanation-schema";

/**
 * Batch I v1.0 - Artifact Writer
 *
 * Responsibility:
 * Save LLM explanation artifacts:
 * - llm_explanations.jsonl
 * - llm_explanation_summary.csv
 * - llm_explanation_quality_report.json
 * - manifest json
 */

export type LlmArtifactWriteOptions = {
  projectRoot?: string;
  runMode: RunMode;
  batchId: string;
  inputSource: InputSource;
};

export type LlmArtifactPaths = {
  outputDir: string;
  explanationsJsonl: string;
  summaryCsv: string;
  qualityReportJson: string;
  manifestJson: string;
};

export async function writeLlmExplanationArtifacts(
  records: LlmExplanationRecord[],
  options: LlmArtifactWriteOptions,
): Promise<LlmArtifactPaths> {
  const paths = buildLlmArtifactPaths(options);

  await mkdir(paths.outputDir, { recursive: true });
  await mkdir(path.dirname(paths.manifestJson), { recursive: true });

  await writeJsonl(paths.explanationsJsonl, records);
  await writeFile(paths.summaryCsv, buildSummaryCsv(records), "utf-8");
  await writeFile(
    paths.qualityReportJson,
    JSON.stringify(buildQualityReport(records, options), null, 2),
    "utf-8",
  );
  await writeFile(
    paths.manifestJson,
    JSON.stringify(buildManifest(records, options, paths), null, 2),
    "utf-8",
  );

  return paths;
}

export function buildLlmArtifactPaths(
  options: LlmArtifactWriteOptions,
): LlmArtifactPaths {
  const projectRoot = options.projectRoot ?? process.cwd();

  const outputDir =
    options.runMode === "evaluation"
      ? path.join(
          projectRoot,
          "data",
          "reports",
          "llm_explanations",
          "evaluation",
          "llm_api",
        )
      : path.join(
          projectRoot,
          "data",
          "reports",
          "llm_explanations",
          "inference",
          options.batchId,
          "llm_api",
        );

  const manifestName =
    options.runMode === "evaluation"
      ? "llm_explanation_manifest_evaluation_llm_api.json"
      : `llm_explanation_manifest_inference_${sanitizeFileName(
          options.batchId,
        )}_llm_api.json`;

  return {
    outputDir,
    explanationsJsonl: path.join(outputDir, "llm_explanations.jsonl"),
    summaryCsv: path.join(outputDir, "llm_explanation_summary.csv"),
    qualityReportJson: path.join(
      outputDir,
      "llm_explanation_quality_report.json",
    ),
    manifestJson: path.join(projectRoot, "data", "manifests", manifestName),
  };
}

async function writeJsonl(
  filePath: string,
  records: LlmExplanationRecord[],
): Promise<void> {
  const content = records.map((record) => JSON.stringify(record)).join("\n");
  await writeFile(
    filePath,
    content + (records.length > 0 ? "\n" : ""),
    "utf-8",
  );
}

function buildSummaryCsv(records: LlmExplanationRecord[]): string {
  const header = [
    "explanation_id",
    "source_ir_id",
    "source_evidence_id",
    "trace_id",
    "run_mode",
    "has_ground_truth",
    "customer_id",
    "predicted_label",
    "probability",
    "threshold",
    "generator_type",
    "provider",
    "model_name",
    "is_parseable_json",
    "has_required_sections",
    "section_count",
    "character_count",
    "error_count",
    "warning_count",
  ];

  const rows = records.map((record) => {
    const prediction = record.prediction_summary as
      | Record<string, unknown>
      | undefined;

    const predictedLabel =
      prediction?.predicted_label ?? prediction?.predictedLabel ?? "";

    const probability =
      prediction?.probability ??
      prediction?.predicted_probability ??
      prediction?.predictedProbability ??
      "";

    const threshold = prediction?.threshold ?? "";

    const customerId =
      record.customer.SK_ID_CURR ?? record.customer.sk_id_curr ?? "";

    return [
      record.explanation_id,
      record.source_ir_id,
      record.source_evidence_id ?? "",
      record.trace_id ?? "",
      record.run_mode,
      String(record.has_ground_truth),
      String(customerId),
      String(predictedLabel),
      String(probability),
      String(threshold),
      record.generator.generator_type,
      record.generator.provider ?? "",
      record.generator.model_name ?? "",
      String(record.quality.is_parseable_json),
      String(record.quality.has_required_sections),
      String(record.quality.section_count),
      String(record.quality.character_count),
      String(record.quality.errors.length),
      String(record.quality.warnings.length),
    ].map(csvEscape);
  });

  return [header.map(csvEscape), ...rows]
    .map((row) => row.join(","))
    .join("\n");
}

function buildQualityReport(
  records: LlmExplanationRecord[],
  options: LlmArtifactWriteOptions,
) {
  const total = records.length;
  const parseableCount = records.filter(
    (record) => record.quality.is_parseable_json,
  ).length;

  const requiredSectionsCount = records.filter(
    (record) => record.quality.has_required_sections,
  ).length;

  const recordsWithErrors = records.filter(
    (record) => record.quality.errors.length > 0,
  );

  const recordsWithWarnings = records.filter(
    (record) => record.quality.warnings.length > 0,
  );

  return {
    report_name: "Batch I v1.0 LLM API Explanation Quality Report",
    created_at: new Date().toISOString(),
    run_mode: options.runMode,
    batch_id: options.batchId,
    input_source: options.inputSource,
    generator_type: "llm_api",
    total_records: total,
    parseable_json_count: parseableCount,
    parseable_json_rate: safeRate(parseableCount, total),
    required_sections_count: requiredSectionsCount,
    required_sections_rate: safeRate(requiredSectionsCount, total),
    records_with_errors_count: recordsWithErrors.length,
    records_with_warnings_count: recordsWithWarnings.length,
    failed_records: recordsWithErrors.map((record) => ({
      explanation_id: record.explanation_id,
      source_ir_id: record.source_ir_id,
      errors: record.quality.errors,
    })),
  };
}

function buildManifest(
  records: LlmExplanationRecord[],
  options: LlmArtifactWriteOptions,
  paths: LlmArtifactPaths,
) {
  const providers = Array.from(
    new Set(records.map((record) => record.generator.provider).filter(Boolean)),
  );

  const models = Array.from(
    new Set(
      records.map((record) => record.generator.model_name).filter(Boolean),
    ),
  );

  return {
    manifest_name: "Batch I v1.0 LLM API Explanation Manifest",
    created_at: new Date().toISOString(),
    batch: "Batch I",
    batch_version: "v1.0",
    generator_type: "llm_api",
    run_mode: options.runMode,
    batch_id: options.batchId,
    input_source: options.inputSource,
    record_count: records.length,
    providers,
    models,
    artifacts: {
      llm_explanations_jsonl: paths.explanationsJsonl,
      llm_explanation_summary_csv: paths.summaryCsv,
      llm_explanation_quality_report_json: paths.qualityReportJson,
      manifest_json: paths.manifestJson,
    },
    next_batch: {
      name: "Batch J - Faithfulness Validator",
      expected_inputs: [
        "data/reports/explanation_ir/.../explanation_ir.jsonl",
        paths.explanationsJsonl,
      ],
    },
  };
}

function csvEscape(value: string): string {
  const escaped = value.replace(/"/g, '""');
  return `"${escaped}"`;
}

function safeRate(count: number, total: number): number {
  if (total === 0) return 0;
  return Number((count / total).toFixed(6));
}

function sanitizeFileName(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]+/g, "_");
}
