import assert from "node:assert/strict";
import test from "node:test";

import {
  cohortKey,
  evidencePackageHash,
  getUsability,
  matrixKey,
} from "../../research/llm/canonicalization/index";
import type {
  EvidencePackageRecord,
  GenerationRecordLike,
} from "../../contracts/llm-validation";

function generation(overrides: Record<string, unknown> = {}): GenerationRecordLike {
  return {
    generation_id: "generation_1",
    run_id: "run_1",
    experiment_stage: "evaluation",
    package_id: "pkg_S4_case_1",
    source_ir_id: "case_1",
    source_evidence_id: "evidence_1",
    evidence_level: "S4",
    model_id: "model_1",
    model_revision: "revision_1",
    prompt_version: "prompt_v1",
    output_schema_version: "1.0",
    repeat_id: 1,
    input_package_sha256: "a".repeat(64),
    prompt_id: "prompt_1",
    prompt_message_sha256: "b".repeat(64),
    runtime_metrics: {
      status: "SUCCESS",
      empty_response: false,
      truncated_response: false,
      finish_reason: "stop",
    },
    schema_metrics: {
      raw_json_parse_success: true,
      schema_valid: true,
      missing_required_field_count: 0,
      validation_error_count: 0,
    },
    parsed_output: { prediction_summary: "ok", factors: [] },
    ...overrides,
  };
}

test("canonical cohort and matrix keys are deterministic", () => {
  const record = generation();
  assert.equal(cohortKey(record), "case_1::S4");
  assert.equal(matrixKey(record), "model_1::r1::case_1::S4");
});

test("usable generation requires runtime and schema success", () => {
  assert.deepEqual(getUsability(generation()), {
    usable: true,
    reason_codes: [],
  });
});

test("length-truncated generation remains present but is unusable", () => {
  const record = generation({
    runtime_metrics: {
      status: "SUCCESS",
      empty_response: false,
      truncated_response: true,
      finish_reason: "length",
    },
    schema_metrics: {
      raw_json_parse_success: false,
      schema_valid: false,
      missing_required_field_count: 5,
      validation_error_count: 1,
    },
    parsed_output: null,
  });
  const result = getUsability(record);
  assert.equal(result.usable, false);
  assert.deepEqual(result.reason_codes, [
    "truncated_response",
    "finish_reason_length",
    "raw_json_parse_failed",
    "schema_invalid",
    "missing_required_fields",
    "schema_validation_errors",
    "parsed_output_missing",
  ]);
});

test("evidence package hashing ignores object key order", () => {
  const left = {
    package_id: "pkg_S0_case_1",
    source_ir_id: "case_1",
    source_evidence_id: "evidence_1",
    evidence_level: "S0",
    nested: { beta: 2, alpha: 1 },
  } as EvidencePackageRecord;
  const right = {
    nested: { alpha: 1, beta: 2 },
    evidence_level: "S0",
    source_evidence_id: "evidence_1",
    source_ir_id: "case_1",
    package_id: "pkg_S0_case_1",
  } as EvidencePackageRecord;
  assert.equal(evidencePackageHash(left), evidencePackageHash(right));
});
