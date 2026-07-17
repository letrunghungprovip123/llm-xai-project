import { access } from "node:fs/promises";
import path from "node:path";

import { sha256 } from "../../../utils/llmNarrative/utils";
import type {
  CanonicalGenerationRow,
  JsonObject,
} from "../../../types/llm-validation";
import type {
  AtomicClaimRecord,
  ClaimExtractionAttemptRecord,
  ClaimExtractionFailure,
  ClaimExtractionFailureCode,
  ClaimExtractionPostprocessMetrics,
  ClaimExtractionPostprocessTotals,
  ClaimExtractionRawResponse,
  ClaimExtractionUsage,
  StoredClaimExtractionAttemptRecord,
  StoredClaimExtractionFailure,
} from "../../../types/validation-claims";
import {
  isPlainObject,
  readJsonlStrict,
  writeJsonlAtomic,
} from "../canonicalization/io";
import {
  ATOMIC_CLAIM_EXTRACTOR_VERSION,
  ATOMIC_CLAIM_PROMPT_VERSION,
  ClaimExtractionValidationError,
} from "./atomicClaimSchema";
import {
  ClaimProviderCallError,
  ClaimResponseJsonError,
  DEEPSEEK_EXTRACTOR_LINEAGE,
  DeepSeekAtomicClaimExtractor,
  parseClaimExtractionResponse,
} from "./deepseekAtomicClaimExtractor";
import {
  buildGenerationTextDocument,
  type GenerationTextDocument,
} from "./generationTextAdapter";

export type ClaimExtractionRunnerOptions = {
  generationIndexPath: string;
  claimsOutputPath: string;
  failuresOutputPath: string;
  attemptsOutputPath?: string;
  limit: number | null;
  force: boolean;
  checkpointEvery: number;
  storeRawResponses?: boolean;
};

export type ClaimExtractionRunnerSummary = {
  claims_output_path: string;
  failures_output_path: string;
  attempts_output_path: string;
  total_canonical_generations: number;
  successful_generations: number;
  failed_or_unusable_generations: number;
  total_claims: number;
  reused_successes: number;
  new_provider_calls: number;
  new_attempt_records: number;
  pending_generations: number;
  usage_for_new_calls: ClaimExtractionUsage;
  postprocess_for_new_successes: ClaimExtractionPostprocessTotals;
  estimated_cost_for_new_calls_usd: number | null;
};

type ExtractorLike = {
  extractRaw(document: GenerationTextDocument): Promise<ClaimExtractionRawResponse>;
  getConfig(): {
    modelId: string;
    inputCostPerMillion?: number | null;
    outputCostPerMillion?: number | null;
  };
};

type MappedFailure = {
  code: ClaimExtractionFailureCode;
  message: string;
};

// Runner ghi audit attempt trước kết quả để không mất usage khi parse hoặc validation fail.
export async function runAtomicClaimExtraction(
  options: ClaimExtractionRunnerOptions,
  extractor: ExtractorLike = new DeepSeekAtomicClaimExtractor(),
): Promise<ClaimExtractionRunnerSummary> {
  validateOptions(options);
  const attemptsOutputPath = options.attemptsOutputPath
    ?? defaultAttemptsOutputPath(options.failuresOutputPath);
  const storeRawResponses = options.storeRawResponses ?? false;
  validateOutputPaths(options, attemptsOutputPath);

  const canonicalInput = await readJsonlStrict<JsonObject>(
    options.generationIndexPath,
  );
  const rows = canonicalInput.records.map(
    (item) => item.value as unknown as CanonicalGenerationRow,
  );
  assertUniqueGenerationIds(rows);

  const existingClaims = await readExistingRecords<AtomicClaimRecord>(
    options.claimsOutputPath,
  );
  const existingFailures = await readExistingRecords<StoredClaimExtractionFailure>(
    options.failuresOutputPath,
  );
  const attempts = await readExistingRecords<StoredClaimExtractionAttemptRecord>(
    attemptsOutputPath,
  );
  assertUniqueAttemptIds(attempts);

  const claimsByGeneration = groupClaims(existingClaims);
  const failureByGeneration = new Map(
    existingFailures.map((failure) => [failure.generation_id, failure]),
  );
  const nextAttemptNumberByGeneration = buildNextAttemptNumbers(attempts);

  const config = extractor.getConfig();
  let reusedSuccesses = 0;
  let newProviderCalls = 0;
  let newAttemptRecords = 0;
  let pendingGenerations = 0;
  let changedSinceCheckpoint = 0;
  const totalUsage: ClaimExtractionUsage = {
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
  };
  const postprocessTotals = emptyPostprocessTotals();

  for (const row of rows) {
    const document = buildGenerationTextDocument(row);
    const cachedClaims = claimsByGeneration.get(row.generation_id) ?? [];
    const cacheIsCurrent = cachedClaims.length > 0 && cachedClaims.every(
      (claim) =>
        claim.claim_schema_version === "claims_v2" &&
        claim.extractor_provider === "deepseek" &&
        claim.source_input_sha256 === document.source_input_sha256 &&
        claim.extractor_model_id === config.modelId &&
        claim.extractor_version === ATOMIC_CLAIM_EXTRACTOR_VERSION &&
        claim.extractor_prompt_version === ATOMIC_CLAIM_PROMPT_VERSION &&
        claim.extractor_prompt_sha256 ===
          DEEPSEEK_EXTRACTOR_LINEAGE.promptSha256,
    );

    if (!options.force && cacheIsCurrent) {
      failureByGeneration.delete(row.generation_id);
      reusedSuccesses += 1;
      continue;
    }

    // Cache cũ bị xóa ngay vì không còn cùng source/model/version với lượt chạy này.
    if (cachedClaims.length > 0) {
      claimsByGeneration.delete(row.generation_id);
    }

    if (!row.usable) {
      failureByGeneration.set(
        row.generation_id,
        buildFailure(row, {
          attempted: false,
          failureCode: "GENERATION_UNUSABLE",
          failureMessage:
            row.usability_reason_codes.join(", ") || "Generation is unusable.",
          sourceInputSha256: null,
          extractorModelId: null,
        }),
      );
      changedSinceCheckpoint += 1;
      await checkpointWhenNeeded();
      continue;
    }

    if (!document.generation_text.trim()) {
      failureByGeneration.set(
        row.generation_id,
        buildFailure(row, {
          attempted: false,
          failureCode: "SOURCE_TEXT_EMPTY",
          failureMessage: "Usable generation produced an empty extraction document.",
          sourceInputSha256: document.source_input_sha256,
          extractorModelId: config.modelId,
        }),
      );
      changedSinceCheckpoint += 1;
      await checkpointWhenNeeded();
      continue;
    }

    if (options.limit !== null && newProviderCalls >= options.limit) {
      pendingGenerations += 1;
      continue;
    }

    // Chỉ bỏ failure hiện tại khi generation thật sự được retry trong lượt này.
    failureByGeneration.delete(row.generation_id);
    claimsByGeneration.delete(row.generation_id);
    newProviderCalls += 1;

    const attemptNumber = nextAttemptNumberByGeneration.get(row.generation_id) ?? 1;
    nextAttemptNumberByGeneration.set(row.generation_id, attemptNumber + 1);
    const startedAt = new Date();
    const startedMs = Date.now();
    let rawResponse: ClaimExtractionRawResponse | null = null;
    let attemptUsage = emptyUsage();
    let attemptStatus: ClaimExtractionAttemptRecord["status"] = "PROVIDER_FAILED";
    let attemptFailure: MappedFailure | null = null;
    let resultClaimCount = 0;
    let postprocessMetrics: ClaimExtractionPostprocessMetrics | null = null;

    try {
      rawResponse = await extractor.extractRaw(document);
      attemptUsage = normalizeUsage(rawResponse.usage);
      addUsage(totalUsage, attemptUsage);
      if (rawResponse.api_error_type) {
        throw new ClaimProviderCallError(
          rawResponse.api_error_type,
          rawResponse.api_error_message ?? "DeepSeek request failed.",
        );
      }

      const payload = parseClaimExtractionResponse(
        rawResponse.raw_text,
        document,
      );
      postprocessMetrics = payload.postprocess_metrics;
      resultClaimCount = payload.claims.length;

      if (payload.postprocess_metrics.llm_claim_count === 0) {
        attemptStatus = "VALIDATION_FAILED";
        resultClaimCount = 0;
        attemptFailure = {
          code: "NO_CLAIMS_EXTRACTED",
          message:
            "Extractor returned no LLM claims; deterministic metadata claims alone are not accepted as a successful extraction.",
        };
        failureByGeneration.set(
          row.generation_id,
          buildFailureFromMapped(
            row,
            attemptFailure,
            document.source_input_sha256,
            config.modelId,
          ),
        );
      } else {
        const claims = payload.claims.map((draft): AtomicClaimRecord => ({
          ...draft,
          claim_schema_version: "claims_v2",
          claim_id: buildClaimId(
            row.generation_id,
            draft.semantic_signature,
            draft.source_span_start,
          ),
          generation_id: row.generation_id,
          model_id: row.model_id,
          source_ir_id: row.source_ir_id,
          case_id: row.case_id,
          evidence_level: row.evidence_level,
          repeat_id: row.repeat_id,
          source_input_sha256: document.source_input_sha256,
          source_text_sha256: sha256(draft.source_text),
          extractor_provider: "deepseek",
          extractor_model_id: config.modelId,
          extractor_version: ATOMIC_CLAIM_EXTRACTOR_VERSION,
          extractor_prompt_version: ATOMIC_CLAIM_PROMPT_VERSION,
          extractor_prompt_sha256: DEEPSEEK_EXTRACTOR_LINEAGE.promptSha256,
          extractor_status: "SUCCESS",
        }));
        claimsByGeneration.set(row.generation_id, claims);
        failureByGeneration.delete(row.generation_id);
        attemptStatus = "SUCCESS";
        addPostprocessTotals(postprocessTotals, payload.postprocess_metrics);
      }
    } catch (error) {
      claimsByGeneration.delete(row.generation_id);
      attemptFailure = mapFailure(error);
      attemptStatus = error instanceof ClaimProviderCallError || !rawResponse
        ? "PROVIDER_FAILED"
        : "VALIDATION_FAILED";
      failureByGeneration.set(
        row.generation_id,
        buildFailureFromMapped(
          row,
          attemptFailure,
          document.source_input_sha256,
          config.modelId,
        ),
      );
    }

    const completedAt = new Date();
    attempts.push(
      buildAttemptRecord({
        row,
        attemptNumber,
        startedAt,
        completedAt,
        durationMs: Math.max(0, Date.now() - startedMs),
        status: attemptStatus,
        failure: attemptFailure,
        resultClaimCount,
        sourceInputSha256: document.source_input_sha256,
        extractorModelId: config.modelId,
        rawResponse,
        usage: attemptUsage,
        postprocessMetrics,
        storeRawResponses,
      }),
    );
    newAttemptRecords += 1;
    changedSinceCheckpoint += 1;
    await checkpointWhenNeeded();
  }

  await writeCheckpoint(
    rows,
    claimsByGeneration,
    failureByGeneration,
    attempts,
    options,
    attemptsOutputPath,
  );

  const successfulGenerations = rows.filter(
    (row) => (claimsByGeneration.get(row.generation_id)?.length ?? 0) > 0,
  ).length;
  const failedGenerations = rows.filter((row) =>
    failureByGeneration.has(row.generation_id),
  ).length;
  const allClaims = rows.flatMap(
    (row) => claimsByGeneration.get(row.generation_id) ?? [],
  );

  return {
    claims_output_path: path.resolve(options.claimsOutputPath),
    failures_output_path: path.resolve(options.failuresOutputPath),
    attempts_output_path: path.resolve(attemptsOutputPath),
    total_canonical_generations: rows.length,
    successful_generations: successfulGenerations,
    failed_or_unusable_generations: failedGenerations,
    total_claims: allClaims.length,
    reused_successes: reusedSuccesses,
    new_provider_calls: newProviderCalls,
    new_attempt_records: newAttemptRecords,
    pending_generations: Math.max(
      pendingGenerations,
      rows.length - successfulGenerations - failedGenerations,
    ),
    usage_for_new_calls: totalUsage,
    postprocess_for_new_successes: postprocessTotals,
    estimated_cost_for_new_calls_usd: estimateCost(
      totalUsage,
      config.inputCostPerMillion,
      config.outputCostPerMillion,
    ),
  };

  async function checkpointWhenNeeded(): Promise<void> {
    if (changedSinceCheckpoint < options.checkpointEvery) return;
    await writeCheckpoint(
      rows,
      claimsByGeneration,
      failureByGeneration,
      attempts,
      options,
      attemptsOutputPath,
    );
    changedSinceCheckpoint = 0;
  }
}

function buildClaimId(
  generationId: string,
  semanticSignature: string,
  sourceSpanStart: number,
): string {
  const digest = sha256(
    `${generationId}|${semanticSignature}|${sourceSpanStart}`,
  ).slice(0, 32);
  return `claim_${digest}`;
}

function buildFailureFromMapped(
  row: CanonicalGenerationRow,
  failure: MappedFailure,
  sourceInputSha256: string,
  extractorModelId: string,
): ClaimExtractionFailure {
  return buildFailure(row, {
    attempted: true,
    failureCode: failure.code,
    failureMessage: failure.message,
    sourceInputSha256,
    extractorModelId,
  });
}

function buildFailure(
  row: CanonicalGenerationRow,
  input: {
    attempted: boolean;
    failureCode: ClaimExtractionFailureCode;
    failureMessage: string;
    sourceInputSha256: string | null;
    extractorModelId: string | null;
  },
): ClaimExtractionFailure {
  return {
    failure_schema_version: "claim_extraction_failure_v2",
    generation_id: row.generation_id,
    canonical_key: row.canonical_key,
    source_ir_id: row.source_ir_id,
    case_id: row.case_id,
    evidence_level: row.evidence_level,
    repeat_id: row.repeat_id,
    attempted: input.attempted,
    failure_code: input.failureCode,
    failure_message: input.failureMessage.slice(0, 2000),
    source_input_sha256: input.sourceInputSha256,
    extractor_provider: input.extractorModelId ? "deepseek" : null,
    extractor_model_id: input.extractorModelId,
    extractor_version: ATOMIC_CLAIM_EXTRACTOR_VERSION,
    extractor_prompt_version: ATOMIC_CLAIM_PROMPT_VERSION,
    extractor_prompt_sha256: DEEPSEEK_EXTRACTOR_LINEAGE.promptSha256,
  };
}

function buildAttemptRecord(input: {
  row: CanonicalGenerationRow;
  attemptNumber: number;
  startedAt: Date;
  completedAt: Date;
  durationMs: number;
  status: ClaimExtractionAttemptRecord["status"];
  failure: MappedFailure | null;
  resultClaimCount: number;
  sourceInputSha256: string;
  extractorModelId: string;
  rawResponse: ClaimExtractionRawResponse | null;
  usage: ClaimExtractionUsage;
  postprocessMetrics: ClaimExtractionPostprocessMetrics | null;
  storeRawResponses: boolean;
}): ClaimExtractionAttemptRecord {
  const rawText = input.rawResponse?.raw_text ?? null;
  const attemptId = `claim_attempt_${sha256(
    [
      input.row.generation_id,
      input.sourceInputSha256,
      input.extractorModelId,
      ATOMIC_CLAIM_EXTRACTOR_VERSION,
      DEEPSEEK_EXTRACTOR_LINEAGE.promptSha256,
      input.attemptNumber,
    ].join("|"),
  ).slice(0, 32)}`;

  return {
    attempt_schema_version: "claim_extraction_attempt_v2",
    attempt_id: attemptId,
    generation_id: input.row.generation_id,
    canonical_key: input.row.canonical_key,
    source_ir_id: input.row.source_ir_id,
    case_id: input.row.case_id,
    evidence_level: input.row.evidence_level,
    repeat_id: input.row.repeat_id,
    attempt_number: input.attemptNumber,
    started_at: input.startedAt.toISOString(),
    completed_at: input.completedAt.toISOString(),
    duration_ms: input.durationMs,
    status: input.status,
    failure_code: input.failure?.code ?? null,
    failure_message: input.failure?.message.slice(0, 2000) ?? null,
    result_claim_count: input.resultClaimCount,
    source_input_sha256: input.sourceInputSha256,
    extractor_provider: "deepseek",
    extractor_model_id: input.extractorModelId,
    extractor_version: ATOMIC_CLAIM_EXTRACTOR_VERSION,
    extractor_prompt_version: ATOMIC_CLAIM_PROMPT_VERSION,
    extractor_prompt_sha256: DEEPSEEK_EXTRACTOR_LINEAGE.promptSha256,
    response_received: input.rawResponse?.response_received ?? false,
    raw_response_sha256: rawText === null ? null : sha256(rawText),
    raw_response_text: input.storeRawResponses ? rawText : null,
    stop_reason: input.rawResponse?.stop_reason ?? null,
    usage: input.usage,
    provider_request_id: input.rawResponse?.provider_request_id ?? null,
    provider_returned_model_id:
      input.rawResponse?.provider_returned_model_id ?? null,
    retry_count: input.rawResponse?.retry_count ?? 0,
    http_status: input.rawResponse?.http_status ?? null,
    postprocess_metrics: input.postprocessMetrics,
  };
}

function mapFailure(error: unknown): MappedFailure {
  const message = error instanceof Error ? error.message : String(error);
  if (error instanceof ClaimExtractionValidationError) {
    return { code: error.code, message };
  }
  if (error instanceof ClaimResponseJsonError) {
    return { code: "RESPONSE_NOT_JSON", message };
  }
  if (error instanceof ClaimProviderCallError) {
    return {
      code: "PROVIDER_CALL_FAILED",
      message: `${error.providerErrorType}: ${message}`,
    };
  }
  return { code: "PROVIDER_CALL_FAILED", message };
}

async function writeCheckpoint(
  rows: CanonicalGenerationRow[],
  claimsByGeneration: Map<string, AtomicClaimRecord[]>,
  failureByGeneration: Map<string, StoredClaimExtractionFailure>,
  attempts: StoredClaimExtractionAttemptRecord[],
  options: ClaimExtractionRunnerOptions,
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

  // Audit attempt được ghi trước; crash giữa checkpoint vẫn không làm mất dấu API call.
  await writeJsonlAtomic(attemptsOutputPath, attempts);
  await writeJsonlAtomic(options.claimsOutputPath, claims);
  await writeJsonlAtomic(options.failuresOutputPath, failures);
}

async function readExistingRecords<T>(filePath: string): Promise<T[]> {
  try {
    await access(filePath);
  } catch {
    return [];
  }
  const loaded = await readJsonlStrict<JsonObject>(filePath);
  return loaded.records.map((item) => item.value as unknown as T);
}

function groupClaims(
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

function buildNextAttemptNumbers(
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

function normalizeUsage(value: unknown): ClaimExtractionUsage {
  const usage = isPlainObject(value) ? value : {};
  const input = readCount(
    usage.prompt_tokens ?? usage.inputTokens ?? usage.input_tokens,
  );
  const output = readCount(
    usage.completion_tokens ?? usage.outputTokens ?? usage.output_tokens,
  );
  const total = readCount(usage.totalTokens ?? usage.total_tokens) || input + output;
  return { input_tokens: input, output_tokens: output, total_tokens: total };
}

function emptyUsage(): ClaimExtractionUsage {
  return { input_tokens: 0, output_tokens: 0, total_tokens: 0 };
}

function emptyPostprocessTotals(): ClaimExtractionPostprocessTotals {
  return {
    llm_claims_received: 0,
    deterministic_claims_added: 0,
    derived_numeric_claims_added: 0,
    causal_overclaims_demoted: 0,
    semantic_duplicates_removed: 0,
    final_claims_created: 0,
    source_slots_covered: 0,
    source_slots_total: 0,
    unclaimed_source_slots: 0,
  };
}

// Chỉ cộng metrics của extraction thành công để khớp với claims đã ghi ra file.
function addPostprocessTotals(
  totals: ClaimExtractionPostprocessTotals,
  metrics: ClaimExtractionPostprocessMetrics,
): void {
  totals.llm_claims_received += metrics.llm_claim_count;
  totals.deterministic_claims_added +=
    metrics.deterministic_claim_count_added;
  totals.derived_numeric_claims_added +=
    metrics.derived_numeric_claim_count_added;
  totals.causal_overclaims_demoted += metrics.causal_overclaim_count_demoted;
  totals.semantic_duplicates_removed +=
    metrics.semantic_duplicate_count_removed;
  totals.final_claims_created += metrics.final_claim_count;
  totals.source_slots_covered +=
    metrics.nonempty_source_slot_count - metrics.unclaimed_source_slots.length;
  totals.source_slots_total += metrics.nonempty_source_slot_count;
  totals.unclaimed_source_slots += metrics.unclaimed_source_slots.length;
}

function addUsage(
  total: ClaimExtractionUsage,
  current: ClaimExtractionUsage,
): void {
  total.input_tokens += current.input_tokens;
  total.output_tokens += current.output_tokens;
  total.total_tokens += current.total_tokens;
}

function estimateCost(
  usage: ClaimExtractionUsage,
  inputCostPerMillion: number | null | undefined,
  outputCostPerMillion: number | null | undefined,
): number | null {
  if (
    inputCostPerMillion === null ||
    inputCostPerMillion === undefined ||
    outputCostPerMillion === null ||
    outputCostPerMillion === undefined
  ) {
    return null;
  }

  return (
    (usage.input_tokens / 1_000_000) * inputCostPerMillion +
    (usage.output_tokens / 1_000_000) * outputCostPerMillion
  );
}

function readCount(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : 0;
}

function assertUniqueGenerationIds(rows: CanonicalGenerationRow[]): void {
  const seen = new Set<string>();
  for (const row of rows) {
    if (!row.generation_id) throw new Error("Canonical row is missing generation_id.");
    if (seen.has(row.generation_id)) {
      throw new Error(`Duplicate canonical generation_id: ${row.generation_id}`);
    }
    seen.add(row.generation_id);
  }
}

function assertUniqueAttemptIds(
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
      throw new Error("Existing claim attempt output contains an invalid record.");
    }
    if (seen.has(attempt.attempt_id)) {
      throw new Error(`Duplicate claim extraction attempt_id: ${attempt.attempt_id}`);
    }
    seen.add(attempt.attempt_id);
  }
}

function defaultAttemptsOutputPath(failuresOutputPath: string): string {
  return path.join(
    path.dirname(failuresOutputPath),
    "claim_extraction_attempts.jsonl",
  );
}

function validateOptions(options: ClaimExtractionRunnerOptions): void {
  if (options.limit !== null && (!Number.isInteger(options.limit) || options.limit < 1)) {
    throw new Error("limit must be null or a positive integer.");
  }
  if (!Number.isInteger(options.checkpointEvery) || options.checkpointEvery < 1) {
    throw new Error("checkpointEvery must be a positive integer.");
  }
}

function validateOutputPaths(
  options: ClaimExtractionRunnerOptions,
  attemptsOutputPath: string,
): void {
  const generationInput = path.resolve(options.generationIndexPath);
  const outputs = [
    path.resolve(options.claimsOutputPath),
    path.resolve(options.failuresOutputPath),
    path.resolve(attemptsOutputPath),
  ];

  if (new Set(outputs).size !== outputs.length) {
    throw new Error("Claims, failures and attempts outputs must use different paths.");
  }
  if (outputs.includes(generationInput)) {
    throw new Error("An extraction output path must not overwrite generation-index.");
  }
}
