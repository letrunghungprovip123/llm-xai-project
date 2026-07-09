// src/server/llm/artifact-writer.ts

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import type {
  InputSource,
  LlmExplanationRecord,
  RunMode,
} from "./explanation-schema";

/**
 * Batch I v1.2 - Artifact Writer
 *
 * Important artifact-lineage rule:
 * - Normal/base generation writes to llm_api/base/
 * - Regeneration writes to llm_api/regeneration_attempt_<n>/
 *
 * This prevents controlled regeneration from overwriting the base Batch I output.
 */

export type LlmArtifactWriteOptions = {
  projectRoot?: string;
  runMode: RunMode;
  batchId: string;
  inputSource: InputSource;

  /**
   * Examples:
   * - base
   * - regeneration_attempt_1
   */
  artifactSubdir?: string;
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
  const artifactSubdir = sanitizeFileName(options.artifactSubdir ?? "base");

  const baseOutputDir =
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
          sanitizeFileName(options.batchId),
          "llm_api",
        );

  const outputDir = path.join(baseOutputDir, artifactSubdir);

  const manifestName =
    options.runMode === "evaluation"
      ? `llm_explanation_manifest_evaluation_llm_api_${artifactSubdir}.json`
      : `llm_explanation_manifest_inference_${sanitizeFileName(
          options.batchId,
        )}_llm_api_${artifactSubdir}.json`;

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
    "prompt_version",
    "generation_attempt",
    "has_regeneration_feedback",
    "feedback_id",
    "parent_explanation_id",
    "is_parseable_json",
    "has_required_sections",
    "section_count",
    "character_count",
    "has_referenced_terms",
    "has_evidence_items_used",
    "has_evidence_groups_used",
    "contains_forbidden_wording",
    "contains_raw_technical_name",
    "error_count",
    "warning_count",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
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

    const usage = record.raw_response?.usage ?? {};

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
      record.generator.prompt_version ?? "",
      String(record.metadata.generation_attempt ?? 0),
      String(Boolean(record.metadata.has_regeneration_feedback)),
      record.metadata.feedback_id ?? "",
      record.metadata.parent_explanation_id ?? "",
      String(record.quality.is_parseable_json),
      String(record.quality.has_required_sections),
      String(record.quality.section_count),
      String(record.quality.character_count),
      String(record.quality.has_referenced_terms),
      String(record.quality.has_evidence_items_used),
      String(record.quality.has_evidence_groups_used),
      String(record.quality.contains_forbidden_wording),
      String(record.quality.contains_raw_technical_name),
      String(record.quality.errors.length),
      String(record.quality.warnings.length),
      String(usage.prompt_tokens ?? ""),
      String(usage.completion_tokens ?? ""),
      String(usage.total_tokens ?? ""),
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
  const artifactSubdir = sanitizeFileName(options.artifactSubdir ?? "base");

  const parseableCount = records.filter(
    (record) => record.quality.is_parseable_json,
  ).length;

  const requiredSectionsCount = records.filter(
    (record) => record.quality.has_required_sections,
  ).length;

  const referencedTermsCount = records.filter(
    (record) => record.quality.has_referenced_terms,
  ).length;

  const evidenceItemsCount = records.filter(
    (record) => record.quality.has_evidence_items_used,
  ).length;

  const evidenceGroupsCount = records.filter(
    (record) => record.quality.has_evidence_groups_used,
  ).length;

  const forbiddenCount = records.filter(
    (record) => record.quality.contains_forbidden_wording,
  ).length;

  const rawTechnicalCount = records.filter(
    (record) => record.quality.contains_raw_technical_name,
  ).length;

  const recordsWithErrors = records.filter(
    (record) => record.quality.errors.length > 0,
  );

  const recordsWithWarnings = records.filter(
    (record) => record.quality.warnings.length > 0,
  );

  const recordsWithFeedback = records.filter(
    (record) => record.metadata.has_regeneration_feedback,
  );

  const totalCharacters = records.reduce(
    (sum, record) => sum + record.quality.character_count,
    0,
  );

  const totalTokens = records.reduce(
    (sum, record) =>
      sum + Number(record.raw_response?.usage?.total_tokens ?? 0),
    0,
  );

  return {
    report_name: "Batch I v1.2 LLM API Explanation Quality Report",
    created_at: new Date().toISOString(),
    run_mode: options.runMode,
    batch_id: options.batchId,
    input_source: options.inputSource,
    generator_type: "llm_api",
    artifact_subdir: artifactSubdir,
    total_records: total,
    parseable_json_count: parseableCount,
    parseable_json_rate: safeRate(parseableCount, total),
    required_sections_count: requiredSectionsCount,
    required_sections_rate: safeRate(requiredSectionsCount, total),
    referenced_terms_count: referencedTermsCount,
    referenced_terms_rate: safeRate(referencedTermsCount, total),
    evidence_items_used_count: evidenceItemsCount,
    evidence_items_used_rate: safeRate(evidenceItemsCount, total),
    evidence_groups_used_count: evidenceGroupsCount,
    evidence_groups_used_rate: safeRate(evidenceGroupsCount, total),
    records_with_forbidden_wording_count: forbiddenCount,
    records_with_raw_technical_name_count: rawTechnicalCount,
    records_with_errors_count: recordsWithErrors.length,
    records_with_warnings_count: recordsWithWarnings.length,
    records_with_regeneration_feedback_count: recordsWithFeedback.length,
    text_stats: {
      total_characters: totalCharacters,
      average_characters_per_record: total > 0 ? totalCharacters / total : 0,
    },
    usage: {
      total_tokens: totalTokens,
    },
    failed_records: recordsWithErrors.map((record) => ({
      explanation_id: record.explanation_id,
      source_ir_id: record.source_ir_id,
      generation_attempt: record.metadata.generation_attempt ?? 0,
      feedback_id: record.metadata.feedback_id,
      errors: record.quality.errors,
    })),
    warning_records: recordsWithWarnings.slice(0, 100).map((record) => ({
      explanation_id: record.explanation_id,
      source_ir_id: record.source_ir_id,
      generation_attempt: record.metadata.generation_attempt ?? 0,
      feedback_id: record.metadata.feedback_id,
      warnings: record.quality.warnings,
    })),
  };
}

function buildManifest(
  records: LlmExplanationRecord[],
  options: LlmArtifactWriteOptions,
  paths: LlmArtifactPaths,
) {
  const artifactSubdir = sanitizeFileName(options.artifactSubdir ?? "base");

  const providers = Array.from(
    new Set(records.map((record) => record.generator.provider).filter(Boolean)),
  );

  const models = Array.from(
    new Set(
      records.map((record) => record.generator.model_name).filter(Boolean),
    ),
  );

  const promptVersions = Array.from(
    new Set(
      records.map((record) => record.generator.prompt_version).filter(Boolean),
    ),
  );

  const generationAttempts = Array.from(
    new Set(
      records.map((record) => Number(record.metadata.generation_attempt ?? 0)),
    ),
  ).sort((a, b) => a - b);

  return {
    manifest_name: "Batch I v1.2 LLM API Explanation Manifest",
    created_at: new Date().toISOString(),
    batch: "Batch I",
    batch_version: "v1.2",
    generator_type: "llm_api",
    run_mode: options.runMode,
    batch_id: options.batchId,
    input_source: options.inputSource,
    artifact_subdir: artifactSubdir,
    record_count: records.length,
    generation_attempts: generationAttempts,
    records_with_regeneration_feedback_count: records.filter(
      (record) => record.metadata.has_regeneration_feedback,
    ).length,
    providers,
    models,
    prompt_versions: promptVersions,
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
  const trimmed = value.trim();

  if (!trimmed) {
    return "base";
  }

  return trimmed.replace(/[^a-zA-Z0-9_-]+/g, "_");
}
