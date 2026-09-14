import { access } from "node:fs/promises";
import path from "node:path";

import type {
  CanonicalGenerationRow,
  JsonObject,
} from "../../../contracts/llm-validation";
import type {
  AtomicClaimRecord,
  StoredClaimExtractionAttemptRecord,
  StoredClaimExtractionFailure,
} from "../../../contracts/validation-claims";
import {
  isPlainObject,
  readJsonlStrict,
  writeJsonlAtomic,
} from "../canonicalization/io";

type RunnerStateOptions = {
  generationIndexPath: string;
  claimsOutputPath: string;
  failuresOutputPath: string;
  limit: number | null;
  checkpointEvery: number;
};

export async function readExistingRecords<T>(filePath: string): Promise<T[]> {
  try {
    await access(filePath);
  } catch {
    return [];
  }
  const loaded = await readJsonlStrict<JsonObject>(filePath);
  return loaded.records.map((item) => item.value as unknown as T);
}

export function groupClaims(
  claims: AtomicClaimRecord[],
): Map<string, AtomicClaimRecord[]> {
  const result = new Map<string, AtomicClaimRecord[]>();
  for (const claim of claims) {
    if (!isPlainObject(claim) || typeof claim.generation_id !== "string") {
      throw new Error("Existing claims output contains an invalid record.");
    }
    const group = result.get(claim.generation_id) ?? [];
    group.push(claim);
    result.set(claim.generation_id, group);
  }
  return result;
}

export function buildNextAttemptNumbers(
  attempts: StoredClaimExtractionAttemptRecord[],
): Map<string, number> {
  const result = new Map<string, number>();
  for (const attempt of attempts) {
    const current = result.get(attempt.generation_id) ?? 1;
    result.set(
      attempt.generation_id,
      Math.max(current, attempt.attempt_number + 1),
    );
  }
  return result;
}

export async function writeCheckpoint(
  rows: CanonicalGenerationRow[],
  claimsByGeneration: Map<string, AtomicClaimRecord[]>,
  failureByGeneration: Map<string, StoredClaimExtractionFailure>,
  attempts: StoredClaimExtractionAttemptRecord[],
  options: Pick<
    RunnerStateOptions,
    "claimsOutputPath" | "failuresOutputPath"
  >,
  attemptsOutputPath: string,
): Promise<void> {
  const claims = rows.flatMap((row) =>
    (claimsByGeneration.get(row.generation_id) ?? []).sort(
      (left, right) => left.local_claim_index - right.local_claim_index,
    ),
  );
  const failures = rows
    .map((row) => failureByGeneration.get(row.generation_id))
    .filter((value): value is StoredClaimExtractionFailure => Boolean(value));

  // Ghi audit attempt trước để crash giữa checkpoint không làm mất dấu API call.
  await writeJsonlAtomic(attemptsOutputPath, attempts);
  await writeJsonlAtomic(options.claimsOutputPath, claims);
  await writeJsonlAtomic(options.failuresOutputPath, failures);
}

export function assertUniqueGenerationIds(
  rows: CanonicalGenerationRow[],
): void {
  const seen = new Set<string>();
  for (const row of rows) {
    if (!row.generation_id) {
      throw new Error("Canonical row is missing generation_id.");
    }
    if (seen.has(row.generation_id)) {
      throw new Error(
        `Duplicate canonical generation_id: ${row.generation_id}`,
      );
    }
    seen.add(row.generation_id);
  }
}

export function assertUniqueAttemptIds(
  attempts: StoredClaimExtractionAttemptRecord[],
): void {
  const seen = new Set<string>();
  for (const attempt of attempts) {
    if (
      !attempt.attempt_id ||
      !attempt.generation_id ||
      !Number.isInteger(attempt.attempt_number) ||
      attempt.attempt_number < 1
    ) {
      throw new Error(
        "Existing claim attempt output contains an invalid record.",
      );
    }
    if (seen.has(attempt.attempt_id)) {
      throw new Error(
        `Duplicate claim extraction attempt_id: ${attempt.attempt_id}`,
      );
    }
    seen.add(attempt.attempt_id);
  }
}

export function defaultAttemptsOutputPath(
  failuresOutputPath: string,
): string {
  return path.join(
    path.dirname(failuresOutputPath),
    "claim_extraction_attempts.jsonl",
  );
}

export function validateRunnerOptions(options: RunnerStateOptions): void {
  if (
    options.limit !== null &&
    (!Number.isInteger(options.limit) || options.limit < 1)
  ) {
    throw new Error("limit must be null or a positive integer.");
  }
  if (
    !Number.isInteger(options.checkpointEvery) ||
    options.checkpointEvery < 1
  ) {
    throw new Error("checkpointEvery must be a positive integer.");
  }
}

export function validateOutputPaths(
  options: RunnerStateOptions,
  attemptsOutputPath: string,
): void {
  const generationInput = path.resolve(options.generationIndexPath);
  const outputs = [
    path.resolve(options.claimsOutputPath),
    path.resolve(options.failuresOutputPath),
    path.resolve(attemptsOutputPath),
  ];

  if (new Set(outputs).size !== outputs.length) {
    throw new Error(
      "Claims, failures and attempts outputs must use different paths.",
    );
  }
  if (outputs.includes(generationInput)) {
    throw new Error(
      "An extraction output path must not overwrite generation-index.",
    );
  }
}
