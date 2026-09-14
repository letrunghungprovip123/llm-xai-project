import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../contracts/validation-claims";
import {
  writeCsvAtomic,
  writeJsonAtomic,
  writeJsonlAtomic,
} from "../canonicalization/io";
import {
  CLAIM_VALIDATION_MANIFEST_VERSION,
  CLAIM_VALIDATION_SCHEMA_VERSION,
  CLAIM_VALIDATOR_VERSION,
  EXECUTION_STATUS,
  VALIDATOR_MODE,
} from "./constants";
import type { ValidationInputs } from "./input";
import { NUMERIC_TOLERANCE_POLICY } from "./numericPolicy";
import { CLAIM_VALIDATION_POLICY } from "./policy";
import { CLAIM_VALIDATION_REASON_CODES } from "./reasonCodes";
import { reconciliation } from "./reconciliation";
import type { ClaimValidationOptions } from "./runTypes";
import {
  countBy,
  reasonCodeCsvRows,
} from "./summary";
import type { ClaimValidationResult } from "./types";
import { writeNewOutputDirectory } from "./writer";

type ArtifactDescriptor = {
  path: string;
  sha256: string;
  byte_count: number;
  record_count?: number;
};

export type ValidationOutputData = {
  inputs: ValidationInputs;
  selectedClaims: AtomicClaimRecord[];
  results: ClaimValidationResult[];
  claimSummary: Record<string, unknown>;
  generationSummary: Array<Record<string, unknown>>;
  options: ClaimValidationOptions;
  startedAt: string;
  endedAt: string;
};

/** Writes the complete v3 output set atomically into a new directory. */
export async function writeValidationOutput(
  data: ValidationOutputData,
): Promise<string> {
  let resultsSha256 = "";
  const sourceCommit = await currentCommit(data.inputs.repositoryRoot);
  await writeNewOutputDirectory({
    outputDirectory: data.options.outputDirectory,
    force: data.options.force,
    write: async (directory) => {
      const outputs = await writeOutputFiles(directory, data);
      resultsSha256 = outputs.claim_validation_results.sha256;
      const manifest = buildManifest(data, sourceCommit, directory, outputs);
      await writeJsonAtomic(
        path.join(directory, "claim_validation_manifest.json"),
        manifest,
      );
    },
  });
  return resultsSha256;
}

async function writeOutputFiles(
  directory: string,
  data: ValidationOutputData,
): Promise<Record<string, ArtifactDescriptor>> {
  const executionErrors = data.results.filter(
    (result) => result.execution_status === EXECUTION_STATUS.ERROR,
  );
  const results = await writeJsonlAtomic(
    path.join(directory, "claim_validation_results.jsonl"),
    data.results,
  );
  const errors = await writeJsonlAtomic(
    path.join(directory, "validation_execution_errors.jsonl"),
    executionErrors,
  );
  const summary = await writeJsonAtomic(
    path.join(directory, "claim_validation_summary.json"),
    data.claimSummary,
  );
  const reasons = await writeCsvAtomic(
    path.join(directory, "reason_code_counts.csv"),
    reasonCodeCsvRows(data.results),
    [
      "reason_code",
      "reason_family",
      "execution_status",
      "validation_status",
      "count",
      "hard_safety",
    ],
  );
  const generations = await writeJsonlAtomic(
    path.join(directory, "generation_validation_summary.jsonl"),
    data.generationSummary,
  );
  return {
    claim_validation_results: results,
    validation_execution_errors: errors,
    claim_validation_summary: summary,
    reason_code_counts: reasons,
    generation_validation_summary: generations,
  };
}

function buildManifest(
  data: ValidationOutputData,
  sourceCommit: string,
  directory: string,
  outputs: Record<string, ArtifactDescriptor>,
): Record<string, unknown> {
  const executionErrors = data.results.filter(
    (result) => result.execution_status === EXECUTION_STATUS.ERROR,
  );
  return {
    schema_version: CLAIM_VALIDATION_MANIFEST_VERSION,
    validation_schema_version: CLAIM_VALIDATION_SCHEMA_VERSION,
    validator_version: CLAIM_VALIDATOR_VERSION,
    policy_version: CLAIM_VALIDATION_POLICY.policy_version,
    reason_taxonomy_version: CLAIM_VALIDATION_REASON_CODES.taxonomy_version,
    numeric_policy_version: NUMERIC_TOLERANCE_POLICY.numeric_policy_version,
    source_commit: sourceCommit,
    run_mode: data.options.smoke ? "SMOKE" : "FULL",
    started_at: data.startedAt,
    ended_at: data.endedAt,
    determinism: determinismMetadata(data.options),
    inputs: inputMetadata(data.inputs),
    cohort: cohortMetadata(data),
    reconciliation: reconciliation(data.selectedClaims, data.results),
    status_counts: countBy(
      data.results,
      (result) => result.validation_status ?? "null",
    ),
    reason_code_counts: countBy(data.results, (result) => result.reason_code),
    execution_error_count: executionErrors.length,
    outputs: Object.fromEntries(
      Object.entries(outputs).map(([name, descriptor]) => [
        name,
        relativeDescriptor(directory, descriptor),
      ]),
    ),
  };
}

function determinismMetadata(
  options: ClaimValidationOptions,
): Record<string, unknown> {
  return {
    validator_mode: VALIDATOR_MODE.DETERMINISTIC,
    provider_calls: false,
    hidden_ir_used: false,
    result_timestamp_is_version_constant: true,
    stable_order: "claim_id_ascending",
    smoke_selector: options.smoke ? "balanced_strata_sha256_v2" : null,
  };
}

function inputMetadata(
  inputs: ValidationInputs,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(inputs.artifacts).map(([name, artifact]) => [
      name,
      {
        path: artifact.path,
        sha256: artifact.sha256,
        record_count: artifact.record_count,
      },
    ]),
  );
}

function cohortMetadata(data: ValidationOutputData): Record<string, unknown> {
  return {
    official_input_claim_count: data.inputs.claims.length,
    selected_claim_count: data.selectedClaims.length,
    selected_claim_ids: data.options.smoke
      ? data.selectedClaims.map((claim) => claim.claim_id)
      : null,
    smoke_limit: data.options.smoke ? data.options.smokeLimit : null,
    main_generations: data.inputs.generations.length,
    usable_generations: data.inputs.generations.filter(
      (generation) => generation.usable,
    ).length,
    unusable_generations: data.inputs.generations.filter(
      (generation) => !generation.usable,
    ).length,
    template_baseline_generations: null,
  };
}

function relativeDescriptor(
  directory: string,
  descriptor: ArtifactDescriptor,
): Record<string, unknown> {
  return {
    path: path.relative(directory, descriptor.path),
    sha256: descriptor.sha256,
    byte_count: descriptor.byte_count,
    record_count: descriptor.record_count ?? null,
  };
}

const execFileAsync = promisify(execFile);

async function currentCommit(repositoryRoot: string): Promise<string> {
  const { stdout } = await execFileAsync("git", ["rev-parse", "HEAD"], {
    cwd: repositoryRoot,
  });
  return stdout.trim();
}
