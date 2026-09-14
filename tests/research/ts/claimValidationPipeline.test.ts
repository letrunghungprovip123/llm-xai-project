import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  CLAIM_SUBTYPES_BY_TYPE,
  type AtomicClaimRecordV3 as AtomicClaimRecord,
} from "../../../contracts/validation-claims";
import {
  assertResultReconciliation,
  runClaimValidation,
  selectBalancedSmokeClaims,
} from "../../../research/ts/claim_validation/pipeline";
import {
  DEFAULT_CLAIMS_INPUT_PATH,
  DEFAULT_EVIDENCE_PACKAGES_PATH,
  DEFAULT_GENERATION_INDEX_PATH,
} from "../../../research/ts/claim_validation/input";
import { createValidationId } from "../../../research/ts/claim_validation/schema";
import { emptyClaimValidationFactValues } from "../../../research/ts/claim_validation/types";
import { uniqueIndex } from "../../../research/ts/claim_validation/indexes";
import { validateSelectedClaims } from "../../../research/ts/claim_validation/validationExecution";
import {
  testEvidence,
  testGeneration,
  testProvenance,
} from "./claimValidationTestFixtures";
import { writeNewOutputDirectory } from "../../../research/ts/claim_validation/writer";
import { writeJsonlAtomic } from "../../../research/ts/canonicalization/io";

test("duplicate input keys fail closed", () => {
  assert.throws(
    () => uniqueIndex([{ id: "a" }, { id: "a" }], (value) => value.id, "id"),
    /Duplicate id/u,
  );
  assert.throws(
    () => uniqueIndex([{ id: "" }], (value) => value.id, "id"),
    /Empty id/u,
  );
});

test("validation execution emits terminal records for every join failure", () => {
  const claim = {
    ...minimalClaim(1),
    generation_id: "generation_001",
    model_id: "model_001",
    case_id: "case_001",
    source_ir_id: "ir_001",
    evidence_level: "S3" as const,
  };
  const missingGeneration = validateSelectedClaims(
    [claim],
    {
      claimById: new Map([[claim.claim_id, claim]]),
      generationById: new Map(),
      evidenceByPackageId: new Map(),
    },
    testProvenance(),
  )[0];
  assert.equal(missingGeneration.reason_code, "GENERATION_JOIN_FAILED");

  const generation = testGeneration();
  const missingEvidence = validateSelectedClaims(
    [claim],
    {
      claimById: new Map([[claim.claim_id, claim]]),
      generationById: new Map([[generation.generation_id, generation]]),
      evidenceByPackageId: new Map(),
    },
    testProvenance(),
  )[0];
  assert.equal(missingEvidence.reason_code, "EVIDENCE_JOIN_FAILED");

  const evidence = testEvidence();
  evidence.source_ir_id = "conflicting_ir";
  const conflicting = validateSelectedClaims(
    [claim],
    {
      claimById: new Map([[claim.claim_id, claim]]),
      generationById: new Map([[generation.generation_id, generation]]),
      evidenceByPackageId: new Map([[evidence.package_id, evidence]]),
    },
    testProvenance(),
  )[0];
  assert.equal(conflicting.reason_code, "EVIDENCE_JOIN_FAILED");
  assert.match(conflicting.error?.error_message ?? "", /Conflicting join identity/u);
});

test("pipeline option validation fails before reading inputs", async () => {
  const base = {
    claimsInputPath: DEFAULT_CLAIMS_INPUT_PATH,
    generationIndexPath: DEFAULT_GENERATION_INDEX_PATH,
    evidencePackagesPath: DEFAULT_EVIDENCE_PACKAGES_PATH,
    outputDirectory: "/tmp/claim-validation-invalid-options",
    mode: "deterministic" as const,
    smoke: true,
    smokeLimit: 1,
    force: false,
  };
  await assert.rejects(
    runClaimValidation({ ...base, mode: "semantic" as "deterministic" }),
    /Only --mode deterministic/u,
  );
  await assert.rejects(
    runClaimValidation({ ...base, smokeLimit: 0 }),
    /positive integer/u,
  );
  await assert.rejects(
    runClaimValidation({
      ...base,
      outputDirectory: path.resolve(DEFAULT_CLAIMS_INPUT_PATH),
    }),
    /must not overwrite an input/u,
  );
});

test("balanced smoke selector and ordering are deterministic", () => {
  const claims = Array.from({ length: 120 }, (_, index) =>
    minimalClaim(index),
  );
  const first = selectBalancedSmokeClaims(claims, 50);
  const second = selectBalancedSmokeClaims([...claims].reverse(), 50);
  assert.deepEqual(
    first.map((claim) => claim.claim_id),
    second.map((claim) => claim.claim_id),
  );
  assert.equal(first.length, 50);
  assert.deepEqual(
    first.map((claim) => claim.claim_id),
    first.map((claim) => claim.claim_id).sort(),
  );
  assert.equal(new Set(first.map((claim) => claim.model_id)).size, 3);
  assert.equal(new Set(first.map((claim) => claim.evidence_level)).size, 6);
});

test("one-result-per-claim reconciliation detects missing and duplicate results", () => {
  const claims = [minimalClaim(1), minimalClaim(2)];
  const results = claims.map((claim) => minimalResult(claim));
  assert.doesNotThrow(() => assertResultReconciliation(claims, results));
  assert.throws(
    () => assertResultReconciliation(claims, results.slice(0, 1)),
    /reconciliation failed/u,
  );
  assert.throws(
    () => assertResultReconciliation(claims, [results[0], results[0]]),
    /reconciliation failed/u,
  );
});

test("atomic directory writer refuses overwrite by default and cleans staging", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "claim-validation-writer-"));
  const output = path.join(root, "output");
  try {
    await writeNewOutputDirectory({
      outputDirectory: output,
      force: false,
      write: async (staging) => {
        await writeJsonlAtomic(path.join(staging, "results.jsonl"), [{ ok: true }]);
      },
    });
    assert.equal(
      await readFile(path.join(output, "results.jsonl"), "utf8"),
      '{"ok":true}\n',
    );
    await assert.rejects(
      writeNewOutputDirectory({
        outputDirectory: output,
        force: false,
        write: async () => undefined,
      }),
      /already exists/u,
    );
    await assert.rejects(
      writeNewOutputDirectory({
        outputDirectory: output,
        force: true,
        write: async () => undefined,
      }),
      /only a prior claim-validation output/u,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("official smoke pipeline writes the complete V4 artifact set", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "claim-validation-v4-"));
  const outputDirectory = path.join(root, "smoke");
  try {
    const summary = await runClaimValidation({
      claimsInputPath: DEFAULT_CLAIMS_INPUT_PATH,
      generationIndexPath: DEFAULT_GENERATION_INDEX_PATH,
      evidencePackagesPath: DEFAULT_EVIDENCE_PACKAGES_PATH,
      outputDirectory,
      mode: "deterministic",
      smoke: true,
      smokeLimit: 100,
      force: false,
    });
    assert.equal(summary.mode, "SMOKE");
    assert.equal(summary.inputClaimCount, 14_667);
    assert.equal(summary.outputResultCount, 100);
    assert.equal(summary.generationSummaryCount, 648);
    for (const name of [
      "claim_validation_results.jsonl",
      "claim_validation_summary.json",
      "reason_code_counts.csv",
      "generation_validation_summary.jsonl",
      "claim_validation_manifest.json",
    ]) {
      assert.ok((await readFile(path.join(outputDirectory, name))).length > 0);
    }
    assert.equal(
      await readFile(
        path.join(outputDirectory, "validation_execution_errors.jsonl"),
        "utf8",
      ),
      "",
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("official full pipeline covers deterministic non-smoke selection", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "claim-validation-v4-full-"));
  const outputDirectory = path.join(root, "full");
  try {
    const summary = await runClaimValidation({
      claimsInputPath: DEFAULT_CLAIMS_INPUT_PATH,
      generationIndexPath: DEFAULT_GENERATION_INDEX_PATH,
      evidencePackagesPath: DEFAULT_EVIDENCE_PACKAGES_PATH,
      outputDirectory,
      mode: "deterministic",
      smoke: false,
      smokeLimit: 100,
      force: false,
    });
    assert.equal(summary.mode, "FULL");
    assert.equal(summary.outputResultCount, 14_667);
    assert.equal(summary.executionErrorCount, 0);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

function minimalClaim(index: number): AtomicClaimRecord {
  const modelIds = ["deepseek_v4_flash", "qwen3_8b", "phi_4_mini"];
  const levels = ["S0", "S1", "S2", "S3", "S4", "S5"] as const;
  const claimTypes = [
    "prediction",
    "feature_presence",
    "feature_direction",
    "concept_presence",
    "concept_direction",
    "numeric",
    "uncertainty",
    "distributed_evidence",
    "limitation",
    "recommendation",
    "ranking",
    "magnitude",
  ] as const;
  const claimType = claimTypes[index % claimTypes.length];
  return {
    local_claim_index: 1,
    source_section: "safe_summary",
    source_factor_id: null,
    source_text: "Synthetic.",
    source_span_start: 0,
    source_span_end: 10,
    claim_type: claimType,
    subject_type: "narrative",
    feature_id: null,
    concept_id: null,
    direction: "unknown",
    magnitude: null,
    certainty: "unknown",
    causal_strength: "none",
    numeric_value: null,
    numeric_unit: null,
    numeric_role: null,
    claim_origin:
      index % 3 === 0
        ? "llm"
        : index % 3 === 1
          ? "deterministic_metadata"
          : "derived_numeric",
    model_normalized_claim_key: null,
    semantic_signature: `synthetic-${index}`,
    normalized_claim_key: `synthetic-${index}`,
    claim_schema_version: "claims_v3",
    claim_id: `claim_${String(index).padStart(4, "0")}`,
    parent_claim_id: `claim_parent_${String(index).padStart(4, "0")}`,
    generation_id: `generation_${index}`,
    model_id: modelIds[index % modelIds.length],
    source_ir_id: `ir_${index}`,
    case_id: `case_${index}`,
    evidence_level: levels[index % levels.length],
    repeat_id: 1,
    source_input_sha256: "1".repeat(64),
    source_text_sha256: "2".repeat(64),
    extractor_provider: "deepseek",
    extractor_model_id: "deepseek-v4-flash",
    extractor_version: "atomic_claim_extractor_v2.1.0",
    extractor_prompt_version: "atomic_claim_extraction_prompt_v3",
    extractor_prompt_sha256: "3".repeat(64),
    extractor_status: "SUCCESS",
    claim_subtype: CLAIM_SUBTYPES_BY_TYPE[claimType][0],
    proposition_status: "COMPLETE",
    source_start: 0,
    source_end: 10,
    finalizer_version: "claim_finalizer_v2.0.0",
    finalization_policy_version: "claim_finalization_policy_v3",
  } as AtomicClaimRecord;
}

function minimalResult(claim: AtomicClaimRecord) {
  return {
    schema_version: "claim_validation_v4" as const,
    validation_id: createValidationId({
      claim_id: claim.claim_id,
      validator_version: "claim_validator_v1.0.0",
      policy_version: "claim_validation_policy_v1",
    }),
    claim_id: claim.claim_id,
    generation_id: claim.generation_id,
    case_id: claim.case_id ?? "case",
    model_id: claim.model_id,
    evidence_level: claim.evidence_level,
    repeat_id: claim.repeat_id,
    claim_type: claim.claim_type,
    claim_subtype: claim.claim_subtype,
    claim_schema_version: claim.claim_schema_version,
    parent_claim_id: claim.parent_claim_id,
    finalizer_version: claim.finalizer_version,
    finalization_policy_version: claim.finalization_policy_version,
    execution_status: "SUCCESS" as const,
    validation_status: "SUPPORTED" as const,
    evidence_status: "SUPPORTED" as const,
    policy_status: "NOT_APPLICABLE" as const,
    validation_coverage: "DETERMINISTIC" as const,
    reason_code: "EXACT_MATCH" as const,
    primary_reason_code: "EXACT_MATCH" as const,
    reason_codes: ["EXACT_MATCH" as const],
    validator_mode: "DETERMINISTIC" as const,
    validator_version: "claim_validator_v1.0.0",
    policy_version: "claim_validation_policy_v1",
    created_at: "2026-07-23T00:00:00.000Z",
    claims_input_path: "data/claims.jsonl",
    claims_input_sha256: "4".repeat(64),
    generation_index_path: "data/generations.jsonl",
    generation_index_sha256: "5".repeat(64),
    evidence_packages_path: "data/evidence.jsonl",
    evidence_packages_sha256: "6".repeat(64),
    source_evidence_id: "evidence",
    package_id: "package",
    source_ir_id: claim.source_ir_id,
    expected: emptyClaimValidationFactValues(),
    observed: emptyClaimValidationFactValues(),
    message: "Synthetic.",
    normalizations_applied: [],
    source_record_keys: [],
    unresolved_facts: [],
    numeric_comparison: null,
    feature_exposure_status: "NOT_APPLICABLE" as const,
    concept_exposure_status: "NOT_APPLICABLE" as const,
    error: null,
  };
}
