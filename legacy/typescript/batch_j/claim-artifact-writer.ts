// src/server/validator/claim-artifact-writer.ts

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import type { ClaimExtractionArtifactRecord } from "./claim-schema";
import type { BedrockClaimExtractorConfig } from "./bedrock-claim-extractor";

export type ClaimExtractionWriteInput = {
  outputDir: string;
  records: ClaimExtractionArtifactRecord[];
  generatorType: string;
  runMode: string;
  explanationsPath: string;
  extractorConfig: BedrockClaimExtractorConfig;
};

export async function writeClaimExtractionArtifacts(
  input: ClaimExtractionWriteInput,
): Promise<void> {
  await mkdir(input.outputDir, { recursive: true });

  const jsonlPath = path.join(input.outputDir, "claim_extraction.jsonl");
  const csvPath = path.join(input.outputDir, "claim_extraction_summary.csv");
  const reportPath = path.join(
    input.outputDir,
    "claim_extraction_quality_report.json",
  );
  const manifestPath = path.join(
    input.outputDir,
    "claim_extraction_manifest.json",
  );

  await writeJsonl(jsonlPath, input.records);
  await writeFile(csvPath, toCsv(buildCsvRows(input.records)), "utf8");
  await writeJson(reportPath, buildQualityReport(input.records, input));
  await writeJson(
    manifestPath,
    buildManifest(input, {
      jsonlPath,
      csvPath,
      reportPath,
      manifestPath,
    }),
  );
}

async function writeJsonl(filePath: string, records: unknown[]): Promise<void> {
  const content =
    records.map((record) => JSON.stringify(record)).join("\n") + "\n";

  await writeFile(filePath, content, "utf8");
}

async function writeJson(filePath: string, payload: unknown): Promise<void> {
  await writeFile(filePath, JSON.stringify(payload, null, 2), "utf8");
}

function buildCsvRows(records: ClaimExtractionArtifactRecord[]) {
  return records.map((record) => ({
    claim_extraction_id: record.claim_extraction_id,
    ir_id: record.ir_id,
    explanation_id: record.explanation_id,
    customer_id: record.customer_id ?? "",
    generator_type: record.generator_type,
    run_mode: record.run_mode,
    extractor_type: record.extractor_type,
    model_id: record.bedrock.model_id,
    parseable_json: String(record.quality.parseable_json),
    schema_valid: String(record.quality.schema_valid),
    claim_count: String(record.claim_extraction.claim_count),
    error: record.quality.error ?? "",
    warning: record.quality.warning ?? "",
    created_at: record.created_at,
  }));
}

function buildQualityReport(
  records: ClaimExtractionArtifactRecord[],
  input: ClaimExtractionWriteInput,
) {
  const total = records.length;
  const parseableJsonCount = records.filter(
    (r) => r.quality.parseable_json,
  ).length;
  const schemaValidCount = records.filter((r) => r.quality.schema_valid).length;
  const errorCount = records.filter((r) => r.quality.error).length;
  const totalClaims = records.reduce(
    (sum, r) => sum + r.claim_extraction.claim_count,
    0,
  );

  return {
    report_name: "Batch J.1 Bedrock Structured Claim Extraction Quality Report",
    created_at: utcNow(),
    batch: "Batch J",
    stage: "J.1 Claim Extraction",
    stage_version: input.extractorConfig.extractorVersion,
    run_mode: input.runMode,
    generator_type: input.generatorType,
    extractor_type: "bedrock_structured_outputs",
    model_id: input.extractorConfig.modelId,
    total_records: total,
    parseable_json_count: parseableJsonCount,
    parseable_json_rate: total ? parseableJsonCount / total : 0,
    schema_valid_count: schemaValidCount,
    schema_valid_rate: total ? schemaValidCount / total : 0,
    error_count: errorCount,
    total_claims: totalClaims,
    average_claims_per_record: total ? totalClaims / total : 0,
    failed_records: records
      .filter((r) => r.quality.error)
      .map((r) => ({
        claim_extraction_id: r.claim_extraction_id,
        ir_id: r.ir_id,
        explanation_id: r.explanation_id,
        error: r.quality.error,
      })),
  };
}

function buildManifest(
  input: ClaimExtractionWriteInput,
  paths: {
    jsonlPath: string;
    csvPath: string;
    reportPath: string;
    manifestPath: string;
  },
) {
  return {
    manifest_name: "Batch J.1 Bedrock Structured Claim Extraction Manifest",
    created_at: utcNow(),
    batch: "Batch J",
    stage: "J.1 Claim Extraction",
    stage_version: input.extractorConfig.extractorVersion,
    run_mode: input.runMode,
    generator_type: input.generatorType,
    extractor: {
      type: "bedrock_structured_outputs",
      provider: "amazon_bedrock",
      endpoint: "bedrock-runtime",
      region_name: input.extractorConfig.regionName,
      model_id: input.extractorConfig.modelId,
      structured_output: true,
      max_tokens: input.extractorConfig.maxTokens,
      temperature: input.extractorConfig.temperature,
    },
    input_source: {
      explanations_path: input.explanationsPath,
    },
    record_count: input.records.length,
    outputs: {
      claim_extraction_jsonl: paths.jsonlPath,
      claim_extraction_summary_csv: paths.csvPath,
      claim_extraction_quality_report_json: paths.reportPath,
      claim_extraction_manifest_json: paths.manifestPath,
    },
    next_stage: {
      name: "Batch J.2 - Faithfulness Validation",
      expected_inputs: [
        "data/reports/explanation_ir/evaluation/explanation_ir.jsonl",
        paths.jsonlPath,
      ],
    },
  };
}

function toCsv(rows: Record<string, string>[]): string {
  if (rows.length === 0) return "";

  const headers = Object.keys(rows[0]);

  const lines = [
    headers.join(","),
    ...rows.map((row) =>
      headers.map((header) => csvEscape(row[header] ?? "")).join(","),
    ),
  ];

  return lines.join("\n") + "\n";
}

function csvEscape(value: string): string {
  const mustQuote = /[",\n\r]/.test(value);
  const escaped = value.replace(/"/g, '""');
  return mustQuote ? `"${escaped}"` : escaped;
}

export function utcNow(): string {
  return new Date().toISOString();
}
