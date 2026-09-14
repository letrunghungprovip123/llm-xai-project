import { createHash } from "node:crypto";
import path from "node:path";

import type { CanonicalGenerationRow, JsonObject } from "../../../contracts/llm-validation";
import {
  readJsonlStrict,
  writeJsonAtomic,
  writeJsonlAtomic,
} from "../canonicalization/io";
import { validateAndNormalizeClaimPayload } from "../claim_extraction/atomicClaimSchema";
import { buildGenerationTextDocument } from "../claim_extraction/generationTextAdapter";

const EXPECTED_CANONICAL = 648;
const EXPECTED_USABLE = 645;
const EXPECTED_UNUSABLE = 3;
const EXPECTED_EXISTING_SUCCESS = 198;
const EXPECTED_OFFLINE = 447;
const EXPECTED_BATCH_SIZES = [6, 50, 200, 191] as const;

type WorkInputRow = JsonObject & {
  batch_sequence: number;
  generation_id: string;
  source_input_sha256: string;
};

type WorkResponseRow = JsonObject & {
  batch_sequence: number;
  generation_id: string;
  provider_response: JsonObject;
};

type FrozenOfflineResponse = {
  schema_version: "freddie_offline_claim_response_v1";
  generation_id: string;
  source_input_sha256: string;
  response_origin: "chatgpt_work_offline_frozen_response";
  batch_id: string;
  batch_sequence: number;
  response_payload_sha256: string;
  provider_response: JsonObject;
  provider_claim_count: number;
  normalized_claim_count: number;
  postprocess_metrics: JsonObject;
};

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const generationIndexPath = required(args, "generation-index");
  const claimsPath = required(args, "existing-claims");
  const failuresPath = required(args, "existing-failures");
  const responsesOutputPath = required(args, "responses-output");
  const manifestOutputPath = required(args, "manifest-output");

  const generationInput = await readJsonlStrict<JsonObject>(generationIndexPath);
  const claimsInput = await readJsonlStrict<JsonObject>(claimsPath);
  const failuresInput = await readJsonlStrict<JsonObject>(failuresPath);
  const rows = generationInput.records.map((record) => record.value as unknown as CanonicalGenerationRow);
  assertCanonicalCohort(rows);

  const rowById = uniqueMap(rows, (row) => row.generation_id, "canonical generation");
  const existingClaimGenerationIds = new Set(
    claimsInput.records.map((record) => requireString(record.value.generation_id, "claim.generation_id")),
  );
  if (existingClaimGenerationIds.size !== EXPECTED_EXISTING_SUCCESS) {
    throw new Error(`Expected ${EXPECTED_EXISTING_SUCCESS} existing successful claim generations; found ${existingClaimGenerationIds.size}.`);
  }

  const providerFailureIds = new Set<string>();
  const unusableFailureIds = new Set<string>();
  for (const record of failuresInput.records) {
    const failure = record.value;
    const id = requireString(failure.generation_id, "failure.generation_id");
    const code = requireString(failure.failure_code, "failure.failure_code");
    const attempted = failure.attempted === true;
    if (attempted && code === "PROVIDER_CALL_FAILED") providerFailureIds.add(id);
    if (!attempted && code === "GENERATION_UNUSABLE") unusableFailureIds.add(id);
  }
  if (providerFailureIds.size !== EXPECTED_OFFLINE) {
    throw new Error(`Expected ${EXPECTED_OFFLINE} provider failures; found ${providerFailureIds.size}.`);
  }
  if (unusableFailureIds.size !== EXPECTED_UNUSABLE) {
    throw new Error(`Expected ${EXPECTED_UNUSABLE} canonical unusable failures; found ${unusableFailureIds.size}.`);
  }
  assertDisjoint(existingClaimGenerationIds, providerFailureIds, "existing successes", "provider failures");

  const frozenByGeneration = new Map<string, FrozenOfflineResponse>();
  const batchDescriptors: JsonObject[] = [];
  for (let batchNumber = 1; batchNumber <= 4; batchNumber += 1) {
    const inputPath = required(args, `batch${batchNumber}-input`);
    const responsePath = required(args, `batch${batchNumber}-response`);
    const batchId = `batch${String(batchNumber).padStart(2, "0")}`;
    const expectedCount = EXPECTED_BATCH_SIZES[batchNumber - 1];
    const input = await readJsonlStrict<JsonObject>(inputPath);
    const response = await readJsonlStrict<JsonObject>(responsePath);
    if (input.records.length !== expectedCount || response.records.length !== expectedCount) {
      throw new Error(`${batchId} expected ${expectedCount} input/response rows; found ${input.records.length}/${response.records.length}.`);
    }

    for (let index = 0; index < expectedCount; index += 1) {
      const inputRow = parseWorkInput(input.records[index].value, batchId, index + 1);
      const responseRow = parseWorkResponse(response.records[index].value, batchId, index + 1);
      if (inputRow.batch_sequence !== index + 1 || responseRow.batch_sequence !== index + 1) {
        throw new Error(`${batchId} batch_sequence must be contiguous 1..${expectedCount}.`);
      }
      if (inputRow.generation_id !== responseRow.generation_id) {
        throw new Error(`${batchId} generation mismatch at sequence ${index + 1}.`);
      }
      if (!providerFailureIds.has(inputRow.generation_id)) {
        throw new Error(`${batchId} contains a generation outside the official 447 provider-failure cohort: ${inputRow.generation_id}`);
      }
      if (existingClaimGenerationIds.has(inputRow.generation_id)) {
        throw new Error(`Offline response overlaps an existing successful generation: ${inputRow.generation_id}`);
      }
      if (frozenByGeneration.has(inputRow.generation_id)) {
        throw new Error(`Duplicate offline generation across batches: ${inputRow.generation_id}`);
      }
      const canonical = rowById.get(inputRow.generation_id);
      if (!canonical || !canonical.usable) {
        throw new Error(`Offline response does not resolve to a usable canonical generation: ${inputRow.generation_id}`);
      }
      const document = buildGenerationTextDocument(canonical);
      if (document.source_input_sha256 !== inputRow.source_input_sha256) {
        throw new Error(`source_input_sha256 mismatch for ${inputRow.generation_id}.`);
      }
      const normalized = validateAndNormalizeClaimPayload(responseRow.provider_response, document);
      if (normalized.postprocess_metrics.llm_claim_count === 0 || normalized.claims.length === 0) {
        throw new Error(`Offline response produced no claims after authoritative normalization: ${inputRow.generation_id}`);
      }
      frozenByGeneration.set(inputRow.generation_id, {
        schema_version: "freddie_offline_claim_response_v1",
        generation_id: inputRow.generation_id,
        source_input_sha256: document.source_input_sha256,
        response_origin: "chatgpt_work_offline_frozen_response",
        batch_id: batchId,
        batch_sequence: inputRow.batch_sequence,
        response_payload_sha256: sha256(stableStringify(responseRow.provider_response)),
        provider_response: responseRow.provider_response,
        provider_claim_count: Array.isArray(responseRow.provider_response.claims)
          ? responseRow.provider_response.claims.length
          : 0,
        normalized_claim_count: normalized.claims.length,
        postprocess_metrics: normalized.postprocess_metrics as unknown as JsonObject,
      });
    }
    batchDescriptors.push({
      batch_id: batchId,
      record_count: expectedCount,
      input_path: path.resolve(inputPath),
      input_sha256: input.sha256,
      response_path: path.resolve(responsePath),
      response_sha256: response.sha256,
    });
  }

  if (frozenByGeneration.size !== EXPECTED_OFFLINE) {
    throw new Error(`Offline union must contain ${EXPECTED_OFFLINE} generations; found ${frozenByGeneration.size}.`);
  }
  const missing = [...providerFailureIds].filter((id) => !frozenByGeneration.has(id));
  if (missing.length > 0) throw new Error(`Offline freeze is missing ${missing.length} official provider failures.`);

  const ordered = rows
    .filter((row) => frozenByGeneration.has(row.generation_id))
    .map((row) => frozenByGeneration.get(row.generation_id)!);
  const outputDescriptor = await writeJsonlAtomic(responsesOutputPath, ordered);
  const manifest = {
    schema_version: "freddie_offline_claim_response_manifest_v1",
    deterministic: true,
    provider_calls_made: 0,
    response_origin: "chatgpt_work_offline_frozen_response",
    cohort: {
      canonical_generations: EXPECTED_CANONICAL,
      usable_generations: EXPECTED_USABLE,
      unusable_generations: EXPECTED_UNUSABLE,
      existing_api_success_generations: existingClaimGenerationIds.size,
      offline_response_generations: ordered.length,
      total_claim_covered_generations: existingClaimGenerationIds.size + ordered.length,
    },
    audits: {
      missing_offline_generation_count: 0,
      extra_offline_generation_count: 0,
      duplicate_offline_generation_count: 0,
      overlap_with_existing_success_count: 0,
      source_input_sha256_mismatch_count: 0,
      authoritative_provider_schema_error_count: 0,
    },
    inputs: {
      generation_index: { path: path.resolve(generationIndexPath), sha256: generationInput.sha256, record_count: generationInput.records.length },
      existing_claims: { path: path.resolve(claimsPath), sha256: claimsInput.sha256, record_count: claimsInput.records.length },
      existing_failures: { path: path.resolve(failuresPath), sha256: failuresInput.sha256, record_count: failuresInput.records.length },
      work_batches: batchDescriptors,
    },
    outputs: {
      frozen_responses: outputDescriptor,
    },
  };
  await writeJsonAtomic(manifestOutputPath, manifest);
  console.log(`FREDDIE_M18A_OFFLINE_RESPONSE_FREEZE=PASS records=${ordered.length}`);
}

function assertCanonicalCohort(rows: CanonicalGenerationRow[]): void {
  if (rows.length !== EXPECTED_CANONICAL) throw new Error(`Expected ${EXPECTED_CANONICAL} canonical rows; found ${rows.length}.`);
  const usable = rows.filter((row) => row.usable).length;
  if (usable !== EXPECTED_USABLE || rows.length - usable !== EXPECTED_UNUSABLE) {
    throw new Error(`Expected usable/unusable ${EXPECTED_USABLE}/${EXPECTED_UNUSABLE}; found ${usable}/${rows.length - usable}.`);
  }
}

function parseWorkInput(value: JsonObject, batch: string, line: number): WorkInputRow {
  return {
    ...value,
    batch_sequence: requirePositiveInteger(value.batch_sequence, `${batch}[${line}].batch_sequence`),
    generation_id: requireString(value.generation_id, `${batch}[${line}].generation_id`),
    source_input_sha256: requireSha(value.source_input_sha256, `${batch}[${line}].source_input_sha256`),
  } as WorkInputRow;
}

function parseWorkResponse(value: JsonObject, batch: string, line: number): WorkResponseRow {
  const providerResponse = value.provider_response;
  if (!providerResponse || typeof providerResponse !== "object" || Array.isArray(providerResponse)) {
    throw new Error(`${batch}[${line}].provider_response must be an object.`);
  }
  return {
    ...value,
    batch_sequence: requirePositiveInteger(value.batch_sequence, `${batch}[${line}].batch_sequence`),
    generation_id: requireString(value.generation_id, `${batch}[${line}].generation_id`),
    provider_response: providerResponse as JsonObject,
  } as WorkResponseRow;
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

function assertDisjoint(left: ReadonlySet<string>, right: ReadonlySet<string>, leftLabel: string, rightLabel: string): void {
  const overlap = [...left].filter((value) => right.has(value));
  if (overlap.length > 0) throw new Error(`${leftLabel} and ${rightLabel} overlap by ${overlap.length} generations.`);
}

function parseArgs(values: string[]): Map<string, string> {
  const result = new Map<string, string>();
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!key?.startsWith("--") || value === undefined || value.startsWith("--")) throw new Error(`Invalid CLI arguments near: ${key ?? "end"}`);
    const normalized = key.slice(2);
    if (result.has(normalized)) throw new Error(`Duplicate argument: --${normalized}`);
    result.set(normalized, value);
  }
  return result;
}

function required(args: ReadonlyMap<string, string>, key: string): string {
  const value = args.get(key)?.trim();
  if (!value) throw new Error(`Missing required argument: --${key}`);
  return value;
}

function requireString(value: unknown, context: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${context} must be a non-empty string.`);
  return value;
}

function requirePositiveInteger(value: unknown, context: string): number {
  if (!Number.isInteger(value) || Number(value) < 1) throw new Error(`${context} must be a positive integer.`);
  return Number(value);
}

function requireSha(value: unknown, context: string): string {
  const text = requireString(value, context);
  if (!/^[0-9a-f]{64}$/u.test(text)) throw new Error(`${context} must be a lowercase SHA-256.`);
  return text;
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b));
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});
