import { sha256, stableStringify } from "../common/utils";

import { isPlainObject } from "./io";
import {
  EVIDENCE_LEVELS,
  type EvidenceLevel,
  type EvidencePackageRecord,
  type GenerationRecordLike,
  type JsonObject,
  type PromptRecordLike,
  type UsabilityResult,
} from "../../../contracts/llm-validation";

const LEVEL_SET = new Set<string>(EVIDENCE_LEVELS);

export function parseEvidencePackage(
  value: JsonObject,
  context: string,
): EvidencePackageRecord {
  const packageId = requireString(value, "package_id", context);
  const sourceIrId = requireString(value, "source_ir_id", context);
  const sourceEvidenceId = requireString(value, "source_evidence_id", context);
  const evidenceLevel = requireEvidenceLevel(value, context);

  return {
    ...value,
    package_id: packageId,
    source_ir_id: sourceIrId,
    source_evidence_id: sourceEvidenceId,
    evidence_level: evidenceLevel,
  };
}

export function parseGenerationRecord(
  value: JsonObject,
  context: string,
): GenerationRecordLike {
  const modelRevision = value.model_revision;
  if (modelRevision !== null && typeof modelRevision !== "string") {
    throw new Error(`${context}: model_revision must be a string or null.`);
  }

  const repeatId = requireInteger(value, "repeat_id", context);

  return {
    ...value,
    generation_id: requireString(value, "generation_id", context),
    run_id: requireString(value, "run_id", context),
    experiment_stage: requireString(value, "experiment_stage", context),
    package_id: requireString(value, "package_id", context),
    source_ir_id: requireString(value, "source_ir_id", context),
    source_evidence_id: requireString(value, "source_evidence_id", context),
    evidence_level: requireEvidenceLevel(value, context),
    model_id: requireString(value, "model_id", context),
    model_revision: modelRevision,
    prompt_version: requireString(value, "prompt_version", context),
    output_schema_version: requireString(value, "output_schema_version", context),
    repeat_id: repeatId,
    input_package_sha256: requireHash(value, "input_package_sha256", context),
    prompt_id: requireString(value, "prompt_id", context),
    prompt_message_sha256: requireHash(value, "prompt_message_sha256", context),
  };
}

export function parsePromptRecord(
  value: JsonObject,
  context: string,
): PromptRecordLike {
  const modelRevision = value.model_revision;
  if (modelRevision !== null && typeof modelRevision !== "string") {
    throw new Error(`${context}: model_revision must be a string or null.`);
  }

  const messages = value.messages;
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new Error(`${context}: messages must be a non-empty array.`);
  }

  return {
    ...value,
    prompt_id: requireString(value, "prompt_id", context),
    prompt_version: requireString(value, "prompt_version", context),
    output_schema_version: requireString(value, "output_schema_version", context),
    package_id: requireString(value, "package_id", context),
    source_ir_id: requireString(value, "source_ir_id", context),
    evidence_level: requireEvidenceLevel(value, context),
    model_id: requireString(value, "model_id", context),
    model_revision: modelRevision,
    message_sha256: requireHash(value, "message_sha256", context),
  };
}

export function cohortKey(record: {
  source_ir_id: string;
  evidence_level: EvidenceLevel;
}): string {
  return `${record.source_ir_id}::${record.evidence_level}`;
}

export function matrixKey(record: {
  model_id: string;
  repeat_id: number;
  source_ir_id: string;
  evidence_level: EvidenceLevel;
}): string {
  return [
    record.model_id,
    `r${record.repeat_id}`,
    record.source_ir_id,
    record.evidence_level,
  ].join("::");
}

export function evidencePackageHash(record: EvidencePackageRecord): string {
  return sha256(stableStringify(record));
}

export function getUsability(record: GenerationRecordLike): UsabilityResult {
  const reasons: string[] = [];
  const runtime = isPlainObject(record.runtime_metrics)
    ? record.runtime_metrics
    : {};
  const schema = isPlainObject(record.schema_metrics) ? record.schema_metrics : {};

  if (runtime.status !== "SUCCESS") reasons.push("runtime_status_not_success");
  if (runtime.empty_response === true) reasons.push("empty_response");
  if (runtime.truncated_response === true) reasons.push("truncated_response");
  if (runtime.finish_reason === "length") reasons.push("finish_reason_length");
  if (schema.raw_json_parse_success !== true) reasons.push("raw_json_parse_failed");
  if (schema.schema_valid !== true) reasons.push("schema_invalid");
  if (asFiniteNumber(schema.missing_required_field_count) !== 0) {
    reasons.push("missing_required_fields");
  }
  if (asFiniteNumber(schema.validation_error_count) !== 0) {
    reasons.push("schema_validation_errors");
  }
  if (record.parsed_output === null || record.parsed_output === undefined) {
    reasons.push("parsed_output_missing");
  }

  return { usable: reasons.length === 0, reason_codes: reasons };
}

export function extractCaseId(record: GenerationRecordLike): string | null {
  const metadata = isPlainObject(record.case_metadata) ? record.case_metadata : {};
  const value = metadata.customer_id;
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

export function verifyGenerationAgainstEvidence(input: {
  generation: GenerationRecordLike;
  evidence: EvidencePackageRecord;
  prompt: PromptRecordLike;
  expectedModelId: string;
  context: string;
}): void {
  const { generation, evidence, prompt, expectedModelId, context } = input;

  assertEqual(generation.model_id, expectedModelId, `${context}: model_id`);
  assertEqual(generation.package_id, evidence.package_id, `${context}: package_id`);
  assertEqual(
    generation.source_ir_id,
    evidence.source_ir_id,
    `${context}: source_ir_id`,
  );
  assertEqual(
    generation.source_evidence_id,
    evidence.source_evidence_id,
    `${context}: source_evidence_id`,
  );
  assertEqual(
    generation.evidence_level,
    evidence.evidence_level,
    `${context}: evidence_level`,
  );
  assertEqual(
    generation.input_package_sha256,
    evidencePackageHash(evidence),
    `${context}: input_package_sha256`,
  );

  assertEqual(prompt.prompt_id, generation.prompt_id, `${context}: prompt_id`);
  assertEqual(prompt.model_id, expectedModelId, `${context}: prompt model_id`);
  assertEqual(prompt.package_id, evidence.package_id, `${context}: prompt package_id`);
  assertEqual(
    prompt.source_ir_id,
    evidence.source_ir_id,
    `${context}: prompt source_ir_id`,
  );
  assertEqual(
    prompt.evidence_level,
    evidence.evidence_level,
    `${context}: prompt evidence_level`,
  );
  assertEqual(
    prompt.message_sha256,
    generation.prompt_message_sha256,
    `${context}: prompt message hash`,
  );
  assertEqual(
    prompt.prompt_version,
    generation.prompt_version,
    `${context}: prompt_version`,
  );
  assertEqual(
    prompt.output_schema_version,
    generation.output_schema_version,
    `${context}: output_schema_version`,
  );
}

export function getRuntimeString(
  record: GenerationRecordLike,
  key: string,
): string | null {
  const runtime = isPlainObject(record.runtime_metrics) ? record.runtime_metrics : {};
  const value = runtime[key];
  return typeof value === "string" ? value : null;
}

export function getRuntimeBoolean(
  record: GenerationRecordLike,
  key: string,
): boolean {
  const runtime = isPlainObject(record.runtime_metrics) ? record.runtime_metrics : {};
  return runtime[key] === true;
}

export function getSchemaBoolean(
  record: GenerationRecordLike,
  key: string,
): boolean {
  const schema = isPlainObject(record.schema_metrics) ? record.schema_metrics : {};
  return schema[key] === true;
}

function requireString(
  value: JsonObject,
  key: string,
  context: string,
): string {
  const result = value[key];
  if (typeof result !== "string" || !result.trim()) {
    throw new Error(`${context}: ${key} must be a non-empty string.`);
  }
  return result;
}

function requireHash(value: JsonObject, key: string, context: string): string {
  const result = requireString(value, key, context);
  if (!/^[a-f0-9]{64}$/i.test(result)) {
    throw new Error(`${context}: ${key} must be a SHA-256 hex digest.`);
  }
  return result.toLowerCase();
}

function requireInteger(
  value: JsonObject,
  key: string,
  context: string,
): number {
  const result = value[key];
  if (typeof result !== "number" || !Number.isInteger(result) || result < 1) {
    throw new Error(`${context}: ${key} must be a positive integer.`);
  }
  return result;
}

function requireEvidenceLevel(
  value: JsonObject,
  context: string,
): EvidenceLevel {
  const result = requireString(value, "evidence_level", context);
  if (!LEVEL_SET.has(result)) {
    throw new Error(`${context}: invalid evidence_level ${result}.`);
  }
  return result as EvidenceLevel;
}

function assertEqual(left: unknown, right: unknown, context: string): void {
  if (left !== right) {
    throw new Error(
      `${context} mismatch: expected ${JSON.stringify(right)}, found ${JSON.stringify(left)}.`,
    );
  }
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
