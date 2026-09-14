import { createHash } from "node:crypto";
import path from "node:path";

import type { CanonicalGenerationRow, JsonObject } from "../../../contracts/llm-validation";
import type {
  AtomicClaimRecord,
  ClaimExtractionAttemptRecord,
} from "../../../contracts/validation-claims";
import {
  ATOMIC_CLAIM_EXTRACTOR_VERSION,
  ATOMIC_CLAIM_PROMPT_VERSION,
  validateAndNormalizeClaimPayload,
} from "../claim_extraction/atomicClaimSchema";
import { buildGenerationTextDocument } from "../claim_extraction/generationTextAdapter";
import {
  readJsonlStrict,
  writeJsonAtomic,
  writeJsonlAtomic,
} from "../canonicalization/io";

const EXPECTED_CANONICAL = 648;
const EXPECTED_USABLE = 645;
const EXPECTED_UNUSABLE = 3;
const EXPECTED_EXISTING_SUCCESS = 198;
const EXPECTED_OFFLINE = 447;
const EXPECTED_EXTRACTOR_MODEL = "deepseek-v4-flash";
const EXPECTED_PROMPT_SHA256 = "6c571dbe10b12e2f1b933fca366ae5f8b900520a330a9a36111ff9c477fb2553";
const DETERMINISTIC_TIME = "1970-01-01T00:00:00.000Z";

type FrozenOfflineResponse = JsonObject & {
  generation_id: string;
  source_input_sha256: string;
  batch_id: string;
  batch_sequence: number;
  response_payload_sha256: string;
  provider_response: JsonObject;
};

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const generationIndex = await readJsonlStrict<JsonObject>(required(args, "generation-index"));
  const historicalClaims = await readJsonlStrict<JsonObject>(required(args, "historical-claims"));
  const historicalAttempts = await readJsonlStrict<JsonObject>(required(args, "historical-attempts"));
  const historicalFailures = await readJsonlStrict<JsonObject>(required(args, "historical-failures"));
  const offlineInput = await readJsonlStrict<JsonObject>(required(args, "offline-responses"));

  const rows = generationIndex.records.map((record) => record.value as unknown as CanonicalGenerationRow);
  assertCohort(rows);
  const rowById = uniqueMap(rows, (row) => row.generation_id, "canonical generation");
  const historicalClaimRows = historicalClaims.records.map((record) => record.value);
  const existingSuccessIds = new Set(historicalClaimRows.map((claim) => requireString(claim.generation_id, "historical claim generation_id")));
  if (existingSuccessIds.size !== EXPECTED_EXISTING_SUCCESS) throw new Error(`Expected ${EXPECTED_EXISTING_SUCCESS} historical claim generations; found ${existingSuccessIds.size}.`);

  const unusableIds = new Set(rows.filter((row) => !row.usable).map((row) => row.generation_id));
  const providerFailureIds = new Set<string>();
  const retainedFailures: JsonObject[] = [];
  for (const record of historicalFailures.records) {
    const failure = record.value;
    const id = requireString(failure.generation_id, "failure.generation_id");
    const code = requireString(failure.failure_code, "failure.failure_code");
    if (failure.attempted === true && code === "PROVIDER_CALL_FAILED") providerFailureIds.add(id);
    if (failure.attempted === false && code === "GENERATION_UNUSABLE") retainedFailures.push(failure);
  }
  if (providerFailureIds.size !== EXPECTED_OFFLINE) throw new Error(`Expected ${EXPECTED_OFFLINE} provider failures; found ${providerFailureIds.size}.`);
  if (retainedFailures.length !== EXPECTED_UNUSABLE) throw new Error(`Expected ${EXPECTED_UNUSABLE} retained unusable failures; found ${retainedFailures.length}.`);

  const offlineRows = offlineInput.records.map((record) => parseFrozen(record.value));
  const offlineById = uniqueMap(offlineRows, (row) => row.generation_id, "offline response");
  if (offlineById.size !== EXPECTED_OFFLINE) throw new Error(`Expected ${EXPECTED_OFFLINE} offline responses; found ${offlineById.size}.`);
  for (const id of providerFailureIds) if (!offlineById.has(id)) throw new Error(`Missing offline response for provider failure: ${id}`);
  for (const id of offlineById.keys()) {
    if (!providerFailureIds.has(id)) throw new Error(`Offline response is outside official provider-failure cohort: ${id}`);
    if (existingSuccessIds.has(id)) throw new Error(`Offline response overlaps historical success: ${id}`);
    if (unusableIds.has(id)) throw new Error(`Offline response targets canonical unusable generation: ${id}`);
  }

  const historicalAttemptRows = historicalAttempts.records.map((record) => record.value);
  const maxAttemptByGeneration = new Map<string, number>();
  for (const attempt of historicalAttemptRows) {
    const id = requireString(attempt.generation_id, "attempt.generation_id");
    const number = Number(attempt.attempt_number);
    if (Number.isInteger(number)) maxAttemptByGeneration.set(id, Math.max(maxAttemptByGeneration.get(id) ?? 0, number));
  }

  const replayClaims: AtomicClaimRecord[] = [];
  const replayAttempts: ClaimExtractionAttemptRecord[] = [];
  const events: JsonObject[] = [];
  for (const row of rows) {
    const frozen = offlineById.get(row.generation_id);
    if (!frozen) continue;
    const document = buildGenerationTextDocument(row);
    if (document.source_input_sha256 !== frozen.source_input_sha256) throw new Error(`Offline source hash drift: ${row.generation_id}`);
    const payload = validateAndNormalizeClaimPayload(frozen.provider_response, document);
    const claims = payload.claims.map((draft): AtomicClaimRecord => ({
      ...draft,
      claim_schema_version: "claims_v2",
      claim_id: buildClaimId(row.generation_id, draft.semantic_signature, draft.source_span_start),
      generation_id: row.generation_id,
      model_id: row.model_id,
      source_ir_id: row.source_ir_id,
      case_id: row.case_id,
      evidence_level: row.evidence_level,
      repeat_id: row.repeat_id,
      source_input_sha256: document.source_input_sha256,
      source_text_sha256: sha256(draft.source_text),
      extractor_provider: "deepseek",
      extractor_model_id: EXPECTED_EXTRACTOR_MODEL,
      extractor_version: ATOMIC_CLAIM_EXTRACTOR_VERSION,
      extractor_prompt_version: ATOMIC_CLAIM_PROMPT_VERSION,
      extractor_prompt_sha256: EXPECTED_PROMPT_SHA256,
      extractor_status: "SUCCESS",
    }));
    if (claims.length === 0) throw new Error(`Offline replay produced zero final claims: ${row.generation_id}`);
    replayClaims.push(...claims);

    const rawText = JSON.stringify(frozen.provider_response);
    const rawSha = sha256(rawText);
    const attemptNumber = (maxAttemptByGeneration.get(row.generation_id) ?? 0) + 1;
    const attemptId = `offline_replay_attempt_${sha256(`${row.generation_id}|${rawSha}`).slice(0, 32)}`;
    const attempt: ClaimExtractionAttemptRecord = {
      attempt_schema_version: "claim_extraction_attempt_v2",
      attempt_id: attemptId,
      generation_id: row.generation_id,
      canonical_key: row.canonical_key,
      source_ir_id: row.source_ir_id,
      case_id: row.case_id,
      evidence_level: row.evidence_level,
      repeat_id: row.repeat_id,
      attempt_number: attemptNumber,
      started_at: DETERMINISTIC_TIME,
      completed_at: DETERMINISTIC_TIME,
      duration_ms: 0,
      status: "SUCCESS",
      failure_code: null,
      failure_message: null,
      result_claim_count: claims.length,
      source_input_sha256: document.source_input_sha256,
      extractor_provider: "deepseek",
      extractor_model_id: EXPECTED_EXTRACTOR_MODEL,
      extractor_version: ATOMIC_CLAIM_EXTRACTOR_VERSION,
      extractor_prompt_version: ATOMIC_CLAIM_PROMPT_VERSION,
      extractor_prompt_sha256: EXPECTED_PROMPT_SHA256,
      response_received: true,
      raw_response_sha256: rawSha,
      raw_response_text: rawText,
      stop_reason: "offline_frozen_response",
      usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
      provider_request_id: null,
      provider_returned_model_id: null,
      retry_count: 0,
      http_status: null,
      postprocess_metrics: payload.postprocess_metrics,
    };
    replayAttempts.push(attempt);
    events.push({
      schema_version: "freddie_offline_claim_replay_event_v1",
      generation_id: row.generation_id,
      historical_provider_failure_preserved: true,
      response_origin: "chatgpt_work_offline_frozen_response",
      batch_id: frozen.batch_id,
      batch_sequence: frozen.batch_sequence,
      response_payload_sha256: frozen.response_payload_sha256,
      synthetic_success_attempt_id: attemptId,
      synthetic_attempt_number: attemptNumber,
      raw_response_sha256: rawSha,
      normalized_claim_count: claims.length,
      postprocess_metrics: payload.postprocess_metrics as unknown as JsonObject,
      provider_calls_made: 0,
    });
  }

  if (new Set(replayClaims.map((claim) => claim.generation_id)).size !== EXPECTED_OFFLINE) throw new Error("Offline replay did not cover all 447 generations.");
  const replayClaimRows = replayClaims.map((claim) => claim as unknown as JsonObject);
  const mergedClaims: JsonObject[] = [...historicalClaimRows, ...replayClaimRows];
  assertUniqueClaimIds(mergedClaims);
  const claimGenerationIds = new Set(mergedClaims.map((claim) => requireString(claim.generation_id, "merged claim generation_id")));
  if (claimGenerationIds.size !== EXPECTED_USABLE) throw new Error(`Effective claims cover ${claimGenerationIds.size}/${EXPECTED_USABLE} usable generations.`);
  for (const row of rows) {
    if (row.usable !== claimGenerationIds.has(row.generation_id)) throw new Error(`Claim coverage does not match canonical usability: ${row.generation_id}`);
  }

  const replayAttemptRows = replayAttempts.map((attempt) => attempt as unknown as JsonObject);
  const attemptsOutput: JsonObject[] = [...historicalAttemptRows, ...replayAttemptRows];
  const claimsDescriptor = await writeJsonlAtomic(required(args, "claims-output"), mergedClaims);
  const attemptsDescriptor = await writeJsonlAtomic(required(args, "attempts-output"), attemptsOutput);
  const failuresDescriptor = await writeJsonlAtomic(required(args, "failures-output"), retainedFailures);
  const eventsDescriptor = await writeJsonlAtomic(required(args, "events-output"), events);
  const manifest = {
    schema_version: "freddie_effective_claim_extraction_manifest_v1",
    deterministic: true,
    provider_calls_made: 0,
    historical_attempt_log_preserved_as_input: true,
    historical_provider_failure_history_rewritten: false,
    cohort: {
      canonical_generations: EXPECTED_CANONICAL,
      usable_generations: EXPECTED_USABLE,
      unusable_generations: EXPECTED_UNUSABLE,
      historical_api_success_generations: EXPECTED_EXISTING_SUCCESS,
      offline_replayed_generations: EXPECTED_OFFLINE,
      effective_claim_generations: claimGenerationIds.size,
      unresolved_usable_generations: 0,
    },
    lineage: {
      extractor_provider_contract_value: "deepseek",
      extractor_model_id: EXPECTED_EXTRACTOR_MODEL,
      extractor_version: ATOMIC_CLAIM_EXTRACTOR_VERSION,
      extractor_prompt_version: ATOMIC_CLAIM_PROMPT_VERSION,
      extractor_prompt_sha256: EXPECTED_PROMPT_SHA256,
      offline_response_origin_is_recorded_separately: true,
    },
    inputs: {
      generation_index: descriptor(generationIndex),
      historical_claims: descriptor(historicalClaims),
      historical_attempts: descriptor(historicalAttempts),
      historical_failures: descriptor(historicalFailures),
      offline_responses: descriptor(offlineInput),
    },
    outputs: {
      claims: claimsDescriptor,
      attempts: attemptsDescriptor,
      failures: failuresDescriptor,
      replay_events: eventsDescriptor,
    },
  };
  await writeJsonAtomic(required(args, "manifest-output"), manifest);
  console.log(`FREDDIE_M18B_OFFLINE_REPLAY=PASS claim_generations=${claimGenerationIds.size} replayed=${replayAttempts.length}`);
}

function descriptor(input: { path: string; sha256: string; byte_count: number; records: unknown[] }): JsonObject {
  return { path: path.resolve(input.path), sha256: input.sha256, byte_count: input.byte_count, record_count: input.records.length };
}

function parseFrozen(value: JsonObject): FrozenOfflineResponse {
  if (value.schema_version !== "freddie_offline_claim_response_v1") throw new Error("Unexpected offline response schema_version.");
  const provider = value.provider_response;
  if (!provider || typeof provider !== "object" || Array.isArray(provider)) throw new Error("offline provider_response must be an object.");
  return {
    ...value,
    generation_id: requireString(value.generation_id, "offline.generation_id"),
    source_input_sha256: requireString(value.source_input_sha256, "offline.source_input_sha256"),
    batch_id: requireString(value.batch_id, "offline.batch_id"),
    batch_sequence: Number(value.batch_sequence),
    response_payload_sha256: requireString(value.response_payload_sha256, "offline.response_payload_sha256"),
    provider_response: provider as JsonObject,
  } as FrozenOfflineResponse;
}

function assertCohort(rows: CanonicalGenerationRow[]): void {
  if (rows.length !== EXPECTED_CANONICAL) throw new Error(`Expected ${EXPECTED_CANONICAL} canonical rows; found ${rows.length}.`);
  const usable = rows.filter((row) => row.usable).length;
  if (usable !== EXPECTED_USABLE || rows.length - usable !== EXPECTED_UNUSABLE) throw new Error(`Expected ${EXPECTED_USABLE}/${EXPECTED_UNUSABLE} usable/unusable; found ${usable}/${rows.length - usable}.`);
}

function assertUniqueClaimIds(claims: JsonObject[]): void {
  const seen = new Set<string>();
  for (const claim of claims) {
    const id = requireString(claim.claim_id, "claim.claim_id");
    if (seen.has(id)) throw new Error(`Duplicate effective claim_id: ${id}`);
    seen.add(id);
  }
}

function uniqueMap<T>(values: readonly T[], key: (value: T) => string, label: string): Map<string, T> {
  const result = new Map<string, T>();
  for (const value of values) {
    const id = key(value);
    if (result.has(id)) throw new Error(`Duplicate ${label}: ${id}`);
    result.set(id, value);
  }
  return result;
}

function buildClaimId(generationId: string, semanticSignature: string, sourceSpanStart: number): string {
  return `claim_${sha256(`${generationId}|${semanticSignature}|${sourceSpanStart}`).slice(0, 32)}`;
}

function sha256(value: string): string { return createHash("sha256").update(value).digest("hex"); }
function requireString(value: unknown, context: string): string { if (typeof value !== "string" || !value.trim()) throw new Error(`${context} must be non-empty.`); return value; }
function parseArgs(values: string[]): Map<string, string> { const result = new Map<string, string>(); for (let index = 0; index < values.length; index += 2) { const key = values[index]; const value = values[index + 1]; if (!key?.startsWith("--") || value === undefined || value.startsWith("--")) throw new Error(`Invalid CLI arguments near: ${key ?? "end"}`); const normalized = key.slice(2); if (result.has(normalized)) throw new Error(`Duplicate argument: --${normalized}`); result.set(normalized, value); } return result; }
function required(args: ReadonlyMap<string, string>, key: string): string { const value = args.get(key)?.trim(); if (!value) throw new Error(`Missing required argument: --${key}`); return value; }

main().catch((error: unknown) => { console.error(error instanceof Error ? error.stack ?? error.message : String(error)); process.exitCode = 1; });
