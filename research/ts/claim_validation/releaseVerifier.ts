import { createHash } from "node:crypto";
import { access, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { assertClaimValidationResult } from "./schema";
import type { ClaimValidationResult } from "./types";
import { readJsonl } from "./calibration/io";

type JsonRecord = Record<string, unknown>;

export type ReleaseVerifierOptions = {
  validationDirectory: string;
  regressionReportPath: string;
  coverageSummaryPath: string;
  mutationReportPath: string;
  deterministicComparisonPath: string;
  calibrationReportPath: string;
  outputPath: string;
};

export async function verifyValidationRelease(
  options: ReleaseVerifierOptions,
): Promise<Record<string, unknown>> {
  const validationDirectory = path.resolve(options.validationDirectory);
  const [
    manifest,
    summary,
    results,
    generationSummary,
    regression,
    coverage,
    mutation,
    comparison,
  ] = await Promise.all([
    readJson(path.join(validationDirectory, "claim_validation_manifest.json")),
    readJson(path.join(validationDirectory, "claim_validation_summary.json")),
    readJsonl<ClaimValidationResult>(
      path.join(validationDirectory, "claim_validation_results.jsonl"),
    ),
    readJsonl<JsonRecord>(
      path.join(validationDirectory, "generation_validation_summary.jsonl"),
    ),
    readJson(options.regressionReportPath),
    readJson(options.coverageSummaryPath),
    readJson(options.mutationReportPath),
    readJson(options.deterministicComparisonPath),
  ]);
  const calibration = (await exists(options.calibrationReportPath))
    ? await readJson(options.calibrationReportPath)
    : null;
  const schemaFailures: string[] = [];
  for (const result of results) {
    try {
      assertClaimValidationResult(result);
    } catch (error) {
      schemaFailures.push(
        `${result.claim_id}:${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }
  const hiddenClaimTypes = new Set([
    "feature_presence",
    "feature_direction",
    "concept_presence",
    "concept_direction",
    "ranking",
    "magnitude",
  ]);
  const s0SupportedCounts = Object.fromEntries(
    [...hiddenClaimTypes].map((claimType) => [
      claimType,
      results.filter(
        (result) =>
          result.evidence_level === "S0" &&
          result.claim_type === claimType &&
          result.evidence_status === "SUPPORTED",
      ).length,
    ]),
  );
  const executionErrors = results.filter(
    (result) => result.execution_status === "ERROR",
  ).length;
  const outputHashesValid = await verifyManifestOutputHashes(
    validationDirectory,
    manifest,
  );
  const gates = {
    C1: gate(
      manifest.validation_schema_version === "claim_validation_v4" &&
        manifest.run_mode === "FULL" &&
        manifest.determinism instanceof Object &&
        (manifest.determinism as JsonRecord).provider_calls === false &&
        results.length === Number((manifest.cohort as JsonRecord)?.selected_claim_count) &&
        generationSummary.length === 648 &&
        Number((manifest.cohort as JsonRecord)?.usable_generations) === 638 &&
        Number((manifest.cohort as JsonRecord)?.unusable_generations) === 10,
      "Experimental integrity and frozen cohort",
    ),
    C2: gate(
      regression.pass === true &&
        regression.corpus_count === 260 &&
        regression.measurement_bug_count === 257 &&
        regression.preserved_experimental_contradiction_count === 3,
      "Reviewed claim-measurement regression",
    ),
    C3: gate(
      Object.values(s0SupportedCounts).every((count) => count === 0) &&
        results.every(
          (result) =>
            !(
              result.evidence_status === "CONTRADICTED" &&
              result.observed.exposure_status === "SOURCE_MISSING"
            ),
        ),
      "Evidence exposure and semantic invariants",
    ),
    C4: gate(
      schemaFailures.length === 0 &&
        executionErrors === 0 &&
        results.every(
          (result) =>
            result.execution_status === "ERROR"
              ? result.validation_status === null
              : result.validation_status !== null,
        ),
      "V4 result schema and fact consistency",
    ),
    C5: gate(
      coverage.pass === true &&
        mutation.pass === true &&
        mutation.survived_count === 0 &&
        comparison.match === true,
      "Coverage, mutation and deterministic A/B proof",
    ),
    C6: gate(
      calibration?.c6_pass === true,
      calibration
        ? "Real human calibration thresholds"
        : "Real human calibration report is missing",
    ),
    C7: gate(
      outputHashesValid &&
        manifest.schema_version === "claim_validation_manifest_v3" &&
        summary.schema_version === "claim_validation_summary_v3",
      "Release interface and artifact hashes",
    ),
  };
  const completionScore = Object.values(gates).reduce(
    (product, item) => product * (item.pass ? 1 : 0),
    1,
  );
  const report = {
    schema_version: "claim_validation_release_v1",
    generated_at: new Date().toISOString(),
    inputs: {
      validation_directory: validationDirectory,
      regression_report: path.resolve(options.regressionReportPath),
      coverage_summary: path.resolve(options.coverageSummaryPath),
      mutation_report: path.resolve(options.mutationReportPath),
      deterministic_comparison: path.resolve(options.deterministicComparisonPath),
      human_calibration_report: calibration
        ? path.resolve(options.calibrationReportPath)
        : null,
    },
    machine_derived: true,
    result_count: results.length,
    generation_summary_count: generationSummary.length,
    execution_error_count: executionErrors,
    s0_supported_counts: s0SupportedCounts,
    schema_failure_count: schemaFailures.length,
    schema_failure_examples: schemaFailures.slice(0, 20),
    output_hashes_valid: outputHashesValid,
    gates,
    CLAIM_VALIDATION_BATCH_COMPLETION_SCORE: completionScore.toFixed(3),
    completion_score: completionScore,
    metric_ready: completionScore === 1,
    verdict: completionScore === 1 ? "APPROVED" : "REJECTED",
  };
  await writeFile(options.outputPath, `${JSON.stringify(report, null, 2)}\n`);
  return report;
}

function gate(pass: boolean, evidence: string): { pass: boolean; evidence: string } {
  return { pass, evidence };
}

async function verifyManifestOutputHashes(
  directory: string,
  manifest: JsonRecord,
): Promise<boolean> {
  const outputs = manifest.outputs;
  if (!outputs || typeof outputs !== "object" || Array.isArray(outputs)) return false;
  for (const descriptor of Object.values(outputs)) {
    if (!descriptor || typeof descriptor !== "object" || Array.isArray(descriptor)) {
      return false;
    }
    const record = descriptor as JsonRecord;
    if (typeof record.path !== "string" || typeof record.sha256 !== "string") {
      return false;
    }
    const content = await readFile(path.join(directory, record.path));
    const digest = createHash("sha256").update(content).digest("hex");
    if (digest !== record.sha256) return false;
  }
  return true;
}

async function readJson(filePath: string): Promise<JsonRecord> {
  const value: unknown = JSON.parse(await readFile(filePath, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Expected JSON object: ${filePath}.`);
  }
  return value as JsonRecord;
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}
