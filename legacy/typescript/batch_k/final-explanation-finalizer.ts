// src/server/finalization/final-explanation-finalizer.ts

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

type AnyRecord = Record<string, unknown>;

type FinalizationStatus = "FINALIZED" | "FINALIZED_WITH_WARNINGS" | "BLOCKED";

type RunKOptions = {
  runMode?: string;
  generatorType?: string;
  runSlot?: string;

  llmExplanationsPath?: string;
  finalizationCandidatesPath?: string;
  validationDecisionsPath?: string;
  faithfulnessValidationPath?: string;
  outputDir?: string;
};

type FinalExplanationRecord = {
  final_explanation_id: string;
  created_at: string;

  ir_id: string;
  explanation_id: string;
  validation_id: string | null;
  decision_id: string | null;
  customer_id: string | null;

  run_mode: string;
  generator_type: string;
  run_slot: string;

  status: FinalizationStatus;
  can_show_to_user: boolean;

  final_text: string;
  sections: Record<string, string>;

  customer: unknown | null;
  model: unknown | null;
  prediction_summary: unknown | null;

  generator: unknown | null;

  decision: {
    decision_status: string;
    next_action: string;
    recommended_fallback: string | null;
    notes: string[];
  };

  faithfulness: {
    status: string | null;
    summary: unknown | null;
    validator_version: string | null;
    failed_claims: number | null;
    warning_claims: number | null;
  };

  source_explanation_quality: unknown | null;

  lineage: {
    source_batch: "Batch K";
    source_ir_id: string;
    source_explanation_id: string;
    source_validation_id: string | null;
    source_decision_id: string | null;
    llm_explanations_path: string;
    finalization_candidates_path: string;
    validation_decisions_path: string;
    faithfulness_validation_path: string;
  };

  quality: {
    source_explanation_found: boolean;
    validation_found: boolean;
    decision_found: boolean;
    has_final_text: boolean;
    has_required_sections: boolean;
    errors: string[];
    warnings: string[];
  };
};

type KSummary = {
  report_name: string;
  created_at: string;
  batch: "Batch K";
  batch_version: "v1.0";
  mode: "final_explanation_finalization";
  run_mode: string;
  generator_type: string;
  run_slot: string;
  input_paths: {
    llm_explanations_path: string;
    finalization_candidates_path: string;
    validation_decisions_path: string;
    faithfulness_validation_path: string;
  };
  output_paths: {
    final_explanations_jsonl_path: string;
    final_explanation_summary_json_path: string;
    final_explanation_summary_csv_path: string;
    final_explanation_manifest_json_path: string;
    final_explanation_report_md_path: string;
  };
  counts: {
    llm_explanation_records: number;
    finalization_candidate_records: number;
    validation_decision_records: number;
    faithfulness_validation_records: number;
    finalized_records: number;
    finalized_with_warnings_records: number;
    blocked_records: number;
    records_with_errors: number;
    records_with_warnings: number;
    records_can_show_to_user: number;
  };
  policy: {
    calls_llm: false;
    calls_bedrock: false;
    only_finalize_can_show_to_user: true;
  };
};

type RunKResult = {
  paths: {
    outputDir: string;
    finalExplanationsJsonlPath: string;
    finalExplanationSummaryJsonPath: string;
    finalExplanationSummaryCsvPath: string;
    finalExplanationManifestJsonPath: string;
    finalExplanationReportMdPath: string;
  };
  records: FinalExplanationRecord[];
  summary: KSummary;
};

const REQUIRED_SECTIONS = [
  "prediction",
  "contribution_overview",
  "main_risk_drivers",
  "supporting_evidence_groups",
  "risk_reducing_factors",
  "limitations",
];

export async function runFinalExplanationFinalizer(
  options: RunKOptions = {},
): Promise<RunKResult> {
  const resolved = resolveOptions(options);

  await mkdir(resolved.outputDir, { recursive: true });

  const finalExplanationsJsonlPath = path.join(
    resolved.outputDir,
    "final_explanations.jsonl",
  );
  const finalExplanationSummaryJsonPath = path.join(
    resolved.outputDir,
    "final_explanation_summary.json",
  );
  const finalExplanationSummaryCsvPath = path.join(
    resolved.outputDir,
    "final_explanation_summary.csv",
  );
  const finalExplanationManifestJsonPath = path.join(
    resolved.outputDir,
    "final_explanation_manifest.json",
  );
  const finalExplanationReportMdPath = path.join(
    resolved.outputDir,
    "final_explanation_report.md",
  );

  console.log("Running Batch K Final Explanation Finalizer...");
  console.log("LLM explanations:", resolved.llmExplanationsPath);
  console.log("Finalization candidates:", resolved.finalizationCandidatesPath);
  console.log("Validation decisions:", resolved.validationDecisionsPath);
  console.log("Faithfulness validation:", resolved.faithfulnessValidationPath);
  console.log("Output dir:", resolved.outputDir);
  console.log("Calls LLM: false");
  console.log("Calls Bedrock: false");

  const llmExplanations = await readJsonl<AnyRecord>(
    resolved.llmExplanationsPath,
  );
  const candidates = await readJsonl<AnyRecord>(
    resolved.finalizationCandidatesPath,
  );
  const decisions = await readJsonl<AnyRecord>(
    resolved.validationDecisionsPath,
  );
  const validations = await readJsonl<AnyRecord>(
    resolved.faithfulnessValidationPath,
  );

  const explanationsById = new Map<string, AnyRecord>();
  for (const record of llmExplanations) {
    const explanationId = getString(record.explanation_id);
    if (explanationId) explanationsById.set(explanationId, record);
  }

  const decisionsByExplanationId = new Map<string, AnyRecord>();
  const decisionsByDecisionId = new Map<string, AnyRecord>();

  for (const decision of decisions) {
    const explanationId = getString(decision.explanation_id);
    const decisionId = getString(decision.decision_id);

    if (explanationId) decisionsByExplanationId.set(explanationId, decision);
    if (decisionId) decisionsByDecisionId.set(decisionId, decision);
  }

  const validationsByExplanationId = new Map<string, AnyRecord>();
  const validationsByValidationId = new Map<string, AnyRecord>();

  for (const validation of validations) {
    const explanationId = getString(validation.explanation_id);
    const validationId = getString(validation.validation_id);

    if (explanationId)
      validationsByExplanationId.set(explanationId, validation);
    if (validationId) validationsByValidationId.set(validationId, validation);
  }

  const createdAt = new Date().toISOString();

  const finalRecords = candidates.map((candidate, index) =>
    buildFinalExplanationRecord({
      candidate,
      index,
      createdAt,
      resolved,
      sourceExplanation:
        explanationsById.get(getString(candidate.explanation_id)) ?? null,
      decision:
        decisionsByDecisionId.get(getString(candidate.decision_id)) ??
        decisionsByExplanationId.get(getString(candidate.explanation_id)) ??
        null,
      validation:
        validationsByValidationId.get(getString(candidate.validation_id)) ??
        validationsByExplanationId.get(getString(candidate.explanation_id)) ??
        null,
    }),
  );

  const summary = buildSummary({
    resolved,
    paths: {
      finalExplanationsJsonlPath,
      finalExplanationSummaryJsonPath,
      finalExplanationSummaryCsvPath,
      finalExplanationManifestJsonPath,
      finalExplanationReportMdPath,
    },
    llmExplanations,
    candidates,
    decisions,
    validations,
    finalRecords,
  });

  await writeJsonl(finalExplanationsJsonlPath, finalRecords);
  await writeFile(
    finalExplanationSummaryJsonPath,
    JSON.stringify(summary, null, 2),
    "utf8",
  );
  await writeFile(
    finalExplanationSummaryCsvPath,
    toCsv(buildCsvRows(finalRecords)),
    "utf8",
  );
  await writeFile(
    finalExplanationManifestJsonPath,
    JSON.stringify(buildManifest(summary), null, 2),
    "utf8",
  );
  await writeFile(
    finalExplanationReportMdPath,
    buildMarkdownReport(summary, finalRecords),
    "utf8",
  );

  console.log("\nBatch K finished.");
  console.log(JSON.stringify(summary, null, 2));

  if (
    summary.counts.blocked_records > 0 ||
    summary.counts.records_with_errors > 0
  ) {
    process.exitCode = 1;
  }

  return {
    paths: {
      outputDir: resolved.outputDir,
      finalExplanationsJsonlPath,
      finalExplanationSummaryJsonPath,
      finalExplanationSummaryCsvPath,
      finalExplanationManifestJsonPath,
      finalExplanationReportMdPath,
    },
    records: finalRecords,
    summary,
  };
}

function buildFinalExplanationRecord(input: {
  candidate: AnyRecord;
  index: number;
  createdAt: string;
  resolved: Required<RunKOptions>;
  sourceExplanation: AnyRecord | null;
  decision: AnyRecord | null;
  validation: AnyRecord | null;
}): FinalExplanationRecord {
  const {
    candidate,
    index,
    createdAt,
    resolved,
    sourceExplanation,
    decision,
    validation,
  } = input;

  const explanationId = getString(candidate.explanation_id);
  const irId =
    getString(candidate.ir_id) ||
    getString(sourceExplanation?.source_ir_id) ||
    getString(sourceExplanation?.ir_id);
  const validationId =
    getString(candidate.validation_id) ||
    getString(validation?.validation_id) ||
    null;
  const decisionId =
    getString(candidate.decision_id) ||
    getString(decision?.decision_id) ||
    null;
  const customerId =
    getNullableString(candidate.customer_id) ||
    getNullableString(sourceExplanation?.customer_id) ||
    getCustomerIdFromCustomer(sourceExplanation?.customer) ||
    null;

  const sections = getExplanationSections(sourceExplanation);
  const fullText = getExplanationFullText(sourceExplanation, sections);
  const canShowToUser = getBoolean(candidate.can_show_to_user);

  const decisionStatus =
    getString(candidate.decision_status) ||
    getString(decision?.decision_status) ||
    "UNKNOWN";

  const nextAction =
    getString(candidate.next_action) ||
    getString(decision?.next_action) ||
    "UNKNOWN";

  const validationStatus = getString(validation?.status) || null;
  const validationSummary = isPlainObject(validation?.summary)
    ? validation?.summary
    : null;

  const failedClaims = getDeepNumber(validation, ["summary", "fail_claims"]);
  const warningClaims = getDeepNumber(validation, ["summary", "warn_claims"]);

  const errors: string[] = [];
  const warnings: string[] = [];

  if (!sourceExplanation) {
    errors.push("Source LLM explanation record was not found.");
  }

  if (!decision) {
    warnings.push(
      "Validation decision record was not found. Candidate data was used.",
    );
  }

  if (!validation) {
    warnings.push("Faithfulness validation record was not found.");
  }

  if (!canShowToUser) {
    errors.push("Finalization candidate is not marked as can_show_to_user.");
  }

  if (!fullText.trim()) {
    errors.push("Final explanation text is empty.");
  }

  const hasRequiredSections = REQUIRED_SECTIONS.every((sectionName) => {
    const value = sections[sectionName];
    return typeof value === "string" && value.trim().length > 0;
  });

  if (!hasRequiredSections) {
    errors.push("Final explanation does not contain all required sections.");
  }

  const status: FinalizationStatus =
    errors.length > 0
      ? "BLOCKED"
      : decisionStatus === "ACCEPTED"
        ? "FINALIZED"
        : "FINALIZED_WITH_WARNINGS";

  return {
    final_explanation_id: buildFinalExplanationId(explanationId, index),
    created_at: createdAt,

    ir_id: irId,
    explanation_id: explanationId,
    validation_id: validationId,
    decision_id: decisionId,
    customer_id: customerId,

    run_mode: resolved.runMode,
    generator_type: resolved.generatorType,
    run_slot: resolved.runSlot,

    status,
    can_show_to_user: canShowToUser && errors.length === 0,

    final_text: fullText,
    sections,

    customer: sourceExplanation?.customer ?? null,
    model: sourceExplanation?.model ?? null,
    prediction_summary: sourceExplanation?.prediction_summary ?? null,

    generator: sourceExplanation?.generator ?? null,

    decision: {
      decision_status: decisionStatus,
      next_action: nextAction,
      recommended_fallback:
        getNullableString(decision?.recommended_fallback) ?? null,
      notes: getStringArray(candidate.notes) || getStringArray(decision?.notes),
    },

    faithfulness: {
      status: validationStatus,
      summary: validationSummary,
      validator_version:
        getDeepString(validation, ["validation_rules", "validator_version"]) ||
        null,
      failed_claims: failedClaims,
      warning_claims: warningClaims,
    },

    source_explanation_quality: sourceExplanation?.quality ?? null,

    lineage: {
      source_batch: "Batch K",
      source_ir_id: irId,
      source_explanation_id: explanationId,
      source_validation_id: validationId,
      source_decision_id: decisionId,
      llm_explanations_path: resolved.llmExplanationsPath,
      finalization_candidates_path: resolved.finalizationCandidatesPath,
      validation_decisions_path: resolved.validationDecisionsPath,
      faithfulness_validation_path: resolved.faithfulnessValidationPath,
    },

    quality: {
      source_explanation_found: Boolean(sourceExplanation),
      validation_found: Boolean(validation),
      decision_found: Boolean(decision),
      has_final_text: fullText.trim().length > 0,
      has_required_sections: hasRequiredSections,
      errors,
      warnings,
    },
  };
}

function resolveOptions(options: RunKOptions): Required<RunKOptions> {
  const runMode = options.runMode ?? "evaluation";
  const generatorType = options.generatorType ?? "llm_api";
  const runSlot = options.runSlot ?? "base";

  const llmExplanationsPath =
    options.llmExplanationsPath ??
    path.join(
      "data",
      "reports",
      "llm_explanations",
      runMode,
      generatorType,
      runSlot,
      "llm_explanations.jsonl",
    );

  const validationRoot = path.join(
    "data",
    "reports",
    "faithfulness_validation",
    runMode,
    generatorType,
    runSlot,
  );

  const finalizationCandidatesPath =
    options.finalizationCandidatesPath ??
    path.join(validationRoot, "finalization_candidates.jsonl");

  const validationDecisionsPath =
    options.validationDecisionsPath ??
    path.join(validationRoot, "validation_decisions.jsonl");

  const faithfulnessValidationPath =
    options.faithfulnessValidationPath ??
    path.join(validationRoot, "faithfulness_validation.jsonl");

  const outputDir =
    options.outputDir ??
    path.join(
      "data",
      "reports",
      "final_explanations",
      runMode,
      generatorType,
      runSlot,
    );

  return {
    runMode,
    generatorType,
    runSlot,
    llmExplanationsPath,
    finalizationCandidatesPath,
    validationDecisionsPath,
    faithfulnessValidationPath,
    outputDir,
  };
}

function getExplanationSections(
  record: AnyRecord | null,
): Record<string, string> {
  if (!record) return {};

  const explanation = record.explanation;

  if (isPlainObject(explanation) && isPlainObject(explanation.sections)) {
    return stringifyRecordValues(explanation.sections);
  }

  if (isPlainObject(record.sections)) {
    return stringifyRecordValues(record.sections);
  }

  return {};
}

function getExplanationFullText(
  record: AnyRecord | null,
  sections: Record<string, string>,
): string {
  if (!record) return "";

  const explanation = record.explanation;

  if (isPlainObject(explanation)) {
    const fullText = getString(explanation.full_text);
    if (fullText) return fullText;
  }

  const direct = getString(record.full_text);
  if (direct) return direct;

  return REQUIRED_SECTIONS.map((sectionName) => sections[sectionName])
    .filter((value) => typeof value === "string" && value.trim())
    .join("\n\n");
}

function buildSummary(input: {
  resolved: Required<RunKOptions>;
  paths: {
    finalExplanationsJsonlPath: string;
    finalExplanationSummaryJsonPath: string;
    finalExplanationSummaryCsvPath: string;
    finalExplanationManifestJsonPath: string;
    finalExplanationReportMdPath: string;
  };
  llmExplanations: AnyRecord[];
  candidates: AnyRecord[];
  decisions: AnyRecord[];
  validations: AnyRecord[];
  finalRecords: FinalExplanationRecord[];
}): KSummary {
  const {
    resolved,
    paths,
    llmExplanations,
    candidates,
    decisions,
    validations,
    finalRecords,
  } = input;

  return {
    report_name: "Batch K Final Explanation Summary",
    created_at: new Date().toISOString(),
    batch: "Batch K",
    batch_version: "v1.0",
    mode: "final_explanation_finalization",
    run_mode: resolved.runMode,
    generator_type: resolved.generatorType,
    run_slot: resolved.runSlot,
    input_paths: {
      llm_explanations_path: resolved.llmExplanationsPath,
      finalization_candidates_path: resolved.finalizationCandidatesPath,
      validation_decisions_path: resolved.validationDecisionsPath,
      faithfulness_validation_path: resolved.faithfulnessValidationPath,
    },
    output_paths: {
      final_explanations_jsonl_path: paths.finalExplanationsJsonlPath,
      final_explanation_summary_json_path:
        paths.finalExplanationSummaryJsonPath,
      final_explanation_summary_csv_path: paths.finalExplanationSummaryCsvPath,
      final_explanation_manifest_json_path:
        paths.finalExplanationManifestJsonPath,
      final_explanation_report_md_path: paths.finalExplanationReportMdPath,
    },
    counts: {
      llm_explanation_records: llmExplanations.length,
      finalization_candidate_records: candidates.length,
      validation_decision_records: decisions.length,
      faithfulness_validation_records: validations.length,
      finalized_records: finalRecords.filter((r) => r.status === "FINALIZED")
        .length,
      finalized_with_warnings_records: finalRecords.filter(
        (r) => r.status === "FINALIZED_WITH_WARNINGS",
      ).length,
      blocked_records: finalRecords.filter((r) => r.status === "BLOCKED")
        .length,
      records_with_errors: finalRecords.filter(
        (r) => r.quality.errors.length > 0,
      ).length,
      records_with_warnings: finalRecords.filter(
        (r) => r.quality.warnings.length > 0,
      ).length,
      records_can_show_to_user: finalRecords.filter((r) => r.can_show_to_user)
        .length,
    },
    policy: {
      calls_llm: false,
      calls_bedrock: false,
      only_finalize_can_show_to_user: true,
    },
  };
}

function buildCsvRows(
  records: FinalExplanationRecord[],
): Record<string, string>[] {
  return records.map((record) => ({
    final_explanation_id: record.final_explanation_id,
    ir_id: record.ir_id,
    explanation_id: record.explanation_id,
    validation_id: record.validation_id ?? "",
    decision_id: record.decision_id ?? "",
    customer_id: record.customer_id ?? "",
    run_mode: record.run_mode,
    generator_type: record.generator_type,
    run_slot: record.run_slot,
    status: record.status,
    can_show_to_user: String(record.can_show_to_user),
    decision_status: record.decision.decision_status,
    next_action: record.decision.next_action,
    faithfulness_status: record.faithfulness.status ?? "",
    failed_claims: String(record.faithfulness.failed_claims ?? ""),
    warning_claims: String(record.faithfulness.warning_claims ?? ""),
    has_final_text: String(record.quality.has_final_text),
    has_required_sections: String(record.quality.has_required_sections),
    source_explanation_found: String(record.quality.source_explanation_found),
    validation_found: String(record.quality.validation_found),
    decision_found: String(record.quality.decision_found),
    error_count: String(record.quality.errors.length),
    warning_count: String(record.quality.warnings.length),
  }));
}

function buildManifest(summary: KSummary): AnyRecord {
  return {
    manifest_name: "Batch K Final Explanation Manifest",
    created_at: new Date().toISOString(),
    batch: summary.batch,
    batch_version: summary.batch_version,
    mode: summary.mode,
    run_mode: summary.run_mode,
    generator_type: summary.generator_type,
    run_slot: summary.run_slot,
    input_paths: summary.input_paths,
    output_paths: summary.output_paths,
    counts: summary.counts,
    policy: summary.policy,
    next_batch: "UI / Human Evaluation / API Consumption",
  };
}

function buildMarkdownReport(
  summary: KSummary,
  records: FinalExplanationRecord[],
): string {
  const lines: string[] = [];

  lines.push("# Batch K Final Explanation Report");
  lines.push("");
  lines.push(`Created at: ${summary.created_at}`);
  lines.push(
    `Status: **${summary.counts.blocked_records > 0 ? "FAIL" : "PASS"}**`,
  );
  lines.push("");
  lines.push("## Summary");
  lines.push("");
  lines.push(
    `- Finalization candidates: ${summary.counts.finalization_candidate_records}`,
  );
  lines.push(`- Finalized records: ${summary.counts.finalized_records}`);
  lines.push(
    `- Finalized with warnings records: ${summary.counts.finalized_with_warnings_records}`,
  );
  lines.push(`- Blocked records: ${summary.counts.blocked_records}`);
  lines.push(
    `- Records can show to user: ${summary.counts.records_can_show_to_user}`,
  );
  lines.push(`- Records with errors: ${summary.counts.records_with_errors}`);
  lines.push(
    `- Records with warnings: ${summary.counts.records_with_warnings}`,
  );
  lines.push("");
  lines.push("## Policy");
  lines.push("");
  lines.push("- Calls LLM: `false`");
  lines.push("- Calls Bedrock: `false`");
  lines.push("- Only finalize `can_show_to_user=true`: `true`");
  lines.push("");
  lines.push("## Per-record finalization");
  lines.push("");
  lines.push(
    "| # | Status | Can show | IR ID | Explanation ID | Faithfulness | Errors | Warnings |",
  );
  lines.push("|---:|---|---|---|---|---|---:|---:|");

  records.forEach((record, index) => {
    lines.push(
      `| ${index + 1} | ${record.status} | ${record.can_show_to_user} | \`${record.ir_id}\` | \`${record.explanation_id}\` | ${record.faithfulness.status ?? ""} | ${record.quality.errors.length} | ${record.quality.warnings.length} |`,
    );
  });

  lines.push("");
  lines.push("## Output artifacts");
  lines.push("");
  lines.push(
    `- Final explanations: \`${summary.output_paths.final_explanations_jsonl_path}\``,
  );
  lines.push(
    `- Summary JSON: \`${summary.output_paths.final_explanation_summary_json_path}\``,
  );
  lines.push(
    `- Summary CSV: \`${summary.output_paths.final_explanation_summary_csv_path}\``,
  );
  lines.push(
    `- Manifest: \`${summary.output_paths.final_explanation_manifest_json_path}\``,
  );
  lines.push("");

  return lines.join("\n");
}

async function readJsonl<T>(filePath: string): Promise<T[]> {
  const raw = await readFile(filePath, "utf8");

  return raw
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

async function writeJsonl(filePath: string, records: unknown[]): Promise<void> {
  const content = records.map((record) => JSON.stringify(record)).join("\n");
  await writeFile(filePath, content + (content ? "\n" : ""), "utf8");
}

function toCsv(rows: Record<string, string>[]): string {
  if (rows.length === 0) return "";

  const headers = Object.keys(rows[0]);

  return [
    headers.join(","),
    ...rows.map((row) =>
      headers.map((header) => csvEscape(row[header] ?? "")).join(","),
    ),
  ].join("\n");
}

function csvEscape(value: string): string {
  if (!/[",\n\r]/.test(value)) return value;
  return `"${value.replace(/"/g, '""')}"`;
}

function buildFinalExplanationId(explanationId: string, index: number): string {
  const base = explanationId || `row_${String(index + 1).padStart(4, "0")}`;
  return `final_${safeId(base)}`;
}

function safeId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 160);
}

function stringifyRecordValues(record: AnyRecord): Record<string, string> {
  const output: Record<string, string> = {};

  for (const [key, value] of Object.entries(record)) {
    output[key] = typeof value === "string" ? value : JSON.stringify(value);
  }

  return output;
}

function getCustomerIdFromCustomer(value: unknown): string | null {
  if (!isPlainObject(value)) return null;

  for (const key of ["SK_ID_CURR", "customer_id", "sk_id_curr", "id"]) {
    const candidate = value[key];

    if (candidate !== undefined && candidate !== null) {
      return String(candidate);
    }
  }

  return null;
}

function getStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];

  return value.map((item) => String(item ?? "").trim()).filter(Boolean);
}

function getDeepString(value: unknown, pathParts: string[]): string {
  const result = getDeepValue(value, pathParts);
  return getString(result);
}

function getDeepNumber(value: unknown, pathParts: string[]): number | null {
  const result = getDeepValue(value, pathParts);
  return getNumber(result);
}

function getDeepValue(value: unknown, pathParts: string[]): unknown {
  let current = value;

  for (const part of pathParts) {
    if (!isPlainObject(current)) return undefined;
    current = current[part];
  }

  return current;
}

function getString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function getNullableString(value: unknown): string | null {
  const result = getString(value);
  return result || null;
}

function getBoolean(value: unknown): boolean {
  return value === true || value === "true" || value === 1 || value === "1";
}

function getNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;

  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }

  return null;
}

function isPlainObject(value: unknown): value is AnyRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
