import type { ClaimValidationGenerationRow } from "./runtimeTypes";
import {
  requireBoolean,
  requireEvidenceLevel,
  requireObject,
  requirePositiveInteger,
  requireString,
  requireStringArray,
} from "./parseHelpers";

/** Parses only the canonical-generation fields used by claim validation. */
export function parseClaimValidationGeneration(
  value: unknown,
  context: string,
): ClaimValidationGenerationRow {
  const row = requireObject(value, context);
  if (row.canonical_schema_version !== "generation_index_v1") {
    throw new Error(`${context}.canonical_schema_version must be generation_index_v1.`);
  }
  const identity = parseOuterIdentity(row, context);
  const generationRecord = parseGenerationRecord(
    row.generation_record,
    `${context}.generation_record`,
  );
  assertNestedIdentity(
    identity,
    generationRecord,
    context,
  );
  const state = parseGenerationState(row, context);
  assertUsabilityMetadata(state, context);
  return {
    canonical_schema_version: "generation_index_v1",
    generation_id: identity.generationId,
    package_id: identity.packageId,
    source_evidence_id: identity.sourceEvidenceId,
    source_ir_id: identity.sourceIrId,
    model_id: identity.modelId,
    case_id: identity.caseId,
    repeat_id: identity.repeatId,
    evidence_level: identity.evidenceLevel,
    usable: state.usable,
    runtime_status: state.runtimeStatus,
    finish_reason: state.finishReason,
    truncated_response: state.truncatedResponse,
    raw_json_parse_success: state.rawJsonParseSuccess,
    schema_valid: state.schemaValid,
    usability_reason_codes: state.usabilityReasonCodes,
    generation_record: generationRecord,
  };
}

function parseOuterIdentity(
  row: Record<string, unknown>,
  context: string,
): {
  generationId: string;
  packageId: string;
  sourceEvidenceId: string;
  sourceIrId: string;
  modelId: string;
  caseId: string;
  repeatId: number;
  evidenceLevel: ClaimValidationGenerationRow["evidence_level"];
} {
  return {
    generationId: requireString(row.generation_id, `${context}.generation_id`),
    packageId: requireString(row.package_id, `${context}.package_id`),
    sourceEvidenceId: requireString(
      row.source_evidence_id,
      `${context}.source_evidence_id`,
    ),
    sourceIrId: requireString(row.source_ir_id, `${context}.source_ir_id`),
    modelId: requireString(row.model_id, `${context}.model_id`),
    caseId: requireString(row.case_id, `${context}.case_id`),
    repeatId: requirePositiveInteger(row.repeat_id, `${context}.repeat_id`),
    evidenceLevel: requireEvidenceLevel(
      row.evidence_level,
      `${context}.evidence_level`,
    ),
  };
}

function parseGenerationState(
  row: Record<string, unknown>,
  context: string,
): {
  usable: boolean;
  runtimeStatus: string;
  finishReason: string;
  truncatedResponse: boolean;
  rawJsonParseSuccess: boolean;
  schemaValid: boolean;
  usabilityReasonCodes: string[];
} {
  return {
    usable: requireBoolean(row.usable, `${context}.usable`),
    runtimeStatus: requireString(row.runtime_status, `${context}.runtime_status`),
    finishReason: requireString(row.finish_reason, `${context}.finish_reason`),
    truncatedResponse: requireBoolean(
      row.truncated_response,
      `${context}.truncated_response`,
    ),
    rawJsonParseSuccess: requireBoolean(
      row.raw_json_parse_success,
      `${context}.raw_json_parse_success`,
    ),
    schemaValid: requireBoolean(row.schema_valid, `${context}.schema_valid`),
    usabilityReasonCodes: requireStringArray(
      row.usability_reason_codes,
      `${context}.usability_reason_codes`,
    ),
  };
}

function parseGenerationRecord(
  value: unknown,
  context: string,
): ClaimValidationGenerationRow["generation_record"] {
  const record = requireObject(value, context);
  return {
    generation_id: requireString(record.generation_id, `${context}.generation_id`),
    package_id: requireString(record.package_id, `${context}.package_id`),
    source_ir_id: requireString(record.source_ir_id, `${context}.source_ir_id`),
    source_evidence_id: requireString(
      record.source_evidence_id,
      `${context}.source_evidence_id`,
    ),
    evidence_level: requireEvidenceLevel(
      record.evidence_level,
      `${context}.evidence_level`,
    ),
    model_id: requireString(record.model_id, `${context}.model_id`),
    repeat_id: requirePositiveInteger(record.repeat_id, `${context}.repeat_id`),
  };
}

function assertNestedIdentity(
  outer: {
    generationId: string;
    packageId: string;
    sourceEvidenceId: string;
    sourceIrId: string;
    modelId: string;
    caseId: string;
    repeatId: number;
    evidenceLevel: string;
  },
  nested: ClaimValidationGenerationRow["generation_record"],
  context: string,
): void {
  const comparisons: Array<[string, string | number, string | number]> = [
    ["generation_id", outer.generationId, nested.generation_id],
    ["package_id", outer.packageId, nested.package_id],
    ["source_evidence_id", outer.sourceEvidenceId, nested.source_evidence_id],
    ["source_ir_id", outer.sourceIrId, nested.source_ir_id],
    ["model_id", outer.modelId, nested.model_id],
    ["repeat_id", outer.repeatId, nested.repeat_id],
    ["evidence_level", outer.evidenceLevel, nested.evidence_level],
  ];
  const mismatch = comparisons.find(([, left, right]) => left !== right);
  if (mismatch) {
    throw new Error(`${context}.${mismatch[0]} conflicts with generation_record.`);
  }
}

function assertUsabilityMetadata(
  state: {
    usable: boolean;
    truncatedResponse: boolean;
    rawJsonParseSuccess: boolean;
    schemaValid: boolean;
    usabilityReasonCodes: string[];
  },
  context: string,
): void {
  if (state.usable && state.usabilityReasonCodes.length > 0) {
    throw new Error(`${context} usable row cannot contain usability failures.`);
  }
  if (!state.usable && state.usabilityReasonCodes.length === 0) {
    throw new Error(`${context} unusable row requires usability failure metadata.`);
  }
  if (state.usable && (!state.rawJsonParseSuccess || !state.schemaValid)) {
    throw new Error(`${context} usable row must be parsed and schema-valid.`);
  }
  if (!state.usable && !state.truncatedResponse && state.rawJsonParseSuccess && state.schemaValid) {
    throw new Error(`${context} unusable row metadata does not explain failure.`);
  }
}
