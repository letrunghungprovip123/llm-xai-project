import path from "node:path";

import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../contracts/validation-claims";
import { EXECUTION_STATUS } from "./constants";
import { loadValidationInputs } from "./input";
import { buildValidationIndexes } from "./indexes";
import { assertNumericTolerancePolicy } from "./numericPolicy";
import { writeValidationOutput } from "./outputArtifacts";
import { assertClaimValidationPolicy } from "./policy";
import {
  assertResultReconciliation,
} from "./reconciliation";
import { assertClaimValidationReasonCodes } from "./reasonCodes";
import type { ResultProvenance } from "./result";
import type {
  ClaimValidationOptions,
  ClaimValidationRunSummary,
} from "./runTypes";
import { assertClaimValidationResult } from "./schema";
import {
  compareClaims,
  selectBalancedSmokeClaims,
} from "./selection";
import {
  buildClaimValidationSummary,
  buildGenerationValidationSummary,
  countBy,
} from "./summary";
import { validateSelectedClaims } from "./validationExecution";

export { assertResultReconciliation } from "./reconciliation";
export { selectBalancedSmokeClaims } from "./selection";
export type {
  ClaimValidationOptions,
  ClaimValidationRunSummary,
} from "./runTypes";

/**
 * Runs the visible load → verify → index → select → validate → reconcile →
 * summarize → write deterministic pipeline.
 */
export async function runClaimValidation(
  options: ClaimValidationOptions,
): Promise<ClaimValidationRunSummary> {
  validateOptions(options);
  verifyFrozenConfiguration();
  const startedAt = new Date().toISOString();
  const inputs = await loadValidationInputs({
    repositoryRoot: options.repositoryRoot,
    claimsInputPath: options.claimsInputPath,
    generationIndexPath: options.generationIndexPath,
    evidencePackagesPath: options.evidencePackagesPath,
  });
  const indexes = buildValidationIndexes(inputs);
  const selectedClaims = selectClaims(inputs.claims, options);
  const provenance = resultProvenance(inputs.artifacts);
  const results = validateSelectedClaims(selectedClaims, indexes, provenance);
  for (const result of results) assertClaimValidationResult(result);
  assertResultReconciliation(selectedClaims, results);
  const claimSummary = buildClaimValidationSummary(selectedClaims, results);
  const generationSummary = buildGenerationValidationSummary(
    inputs.generations,
    results,
  );
  assertGenerationCount(
    generationSummary.length,
    inputs.generations.length,
  );
  const resultsSha256 = await writeValidationOutput({
    inputs,
    selectedClaims,
    results,
    claimSummary,
    generationSummary,
    options,
    startedAt,
    endedAt: new Date().toISOString(),
  });
  return runSummary(options, inputs.claims.length, results, generationSummary.length, resultsSha256);
}

function validateOptions(options: ClaimValidationOptions): void {
  if (options.mode !== "deterministic") {
    throw new Error("Only --mode deterministic is supported.");
  }
  if (!Number.isInteger(options.smokeLimit) || options.smokeLimit < 1) {
    throw new Error("--smoke-limit must be a positive integer.");
  }
  const output = path.resolve(options.outputDirectory);
  const inputs = [
    options.claimsInputPath,
    options.generationIndexPath,
    options.evidencePackagesPath,
  ].map((input) => path.resolve(options.repositoryRoot ?? process.cwd(), input));
  if (inputs.includes(output)) {
    throw new Error("Validation output directory must not overwrite an input.");
  }
}

function verifyFrozenConfiguration(): void {
  assertClaimValidationPolicy();
  assertClaimValidationReasonCodes();
  assertNumericTolerancePolicy();
}

function selectClaims(
  claims: readonly AtomicClaimRecord[],
  options: ClaimValidationOptions,
): AtomicClaimRecord[] {
  if (options.smoke) {
    return selectBalancedSmokeClaims(claims, options.smokeLimit);
  }
  return [...claims].sort(compareClaims);
}

function resultProvenance(
  artifacts: {
    finalized_claims: { path: string; sha256: string };
    canonical_generation_index: { path: string; sha256: string };
    canonical_evidence_packages: { path: string; sha256: string };
  },
): ResultProvenance {
  return {
    claimsInputPath: artifacts.finalized_claims.path,
    claimsInputSha256: artifacts.finalized_claims.sha256,
    generationIndexPath: artifacts.canonical_generation_index.path,
    generationIndexSha256: artifacts.canonical_generation_index.sha256,
    evidencePackagesPath: artifacts.canonical_evidence_packages.path,
    evidencePackagesSha256: artifacts.canonical_evidence_packages.sha256,
  };
}

function assertGenerationCount(actual: number, expected: number): void {
  if (actual !== expected) {
    throw new Error(`Generation summary count mismatch: ${actual}.`);
  }
}

function runSummary(
  options: ClaimValidationOptions,
  inputClaimCount: number,
  results: ReturnType<typeof validateSelectedClaims>,
  generationSummaryCount: number,
  resultsSha256: string,
): ClaimValidationRunSummary {
  const executionErrors = results.filter(
    (result) => result.execution_status === EXECUTION_STATUS.ERROR,
  );
  return {
    mode: options.smoke ? "SMOKE" : "FULL",
    inputClaimCount,
    selectedClaimCount: results.length,
    outputResultCount: results.length,
    executionErrorCount: executionErrors.length,
    statusCounts: countBy(
      results,
      (result) => result.validation_status ?? "null",
    ),
    reasonCodeCounts: countBy(results, (result) => result.reason_code),
    outputDirectory: path.resolve(options.outputDirectory),
    resultsSha256,
    generationSummaryCount,
  };
}
