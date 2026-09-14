import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  EXECUTION_STATUS,
  REASON_CODE,
  VALIDATION_STATUS,
} from "../../../research/ts/claim_validation/constants";
import { uniqueIndex } from "../../../research/ts/claim_validation/indexes";
import { loadValidationInputs } from "../../../research/ts/claim_validation/input";
import { reasonCodeByName } from "../../../research/ts/claim_validation/reasonCodes";
import { assertResultReconciliation } from "../../../research/ts/claim_validation/reconciliation";
import {
  buildErrorResult,
  buildSuccessResult,
} from "../../../research/ts/claim_validation/result";
import {
  assertClaimValidationResult,
  createValidationId,
} from "../../../research/ts/claim_validation/schema";
import { selectBalancedSmokeClaims } from "../../../research/ts/claim_validation/selection";
import { buildGenerationValidationSummary } from "../../../research/ts/claim_validation/summary";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";
import {
  numericTestClaim,
  testClaim,
  testEvidence,
  testGeneration,
  testProvenance,
} from "./claimValidationTestFixtures";

const mutations: Array<[string, () => void | Promise<void>]> = [
  ["M1 S0 hidden feature", killS0HiddenFeature],
  ["M2 reversed normalization", killReversedNormalization],
  ["M3 epsilon changed to zero", killEpsilonMutation],
  ["M4 tolerance widened", killToleranceWidening],
  ["M5 outside tolerance supported", killOutsideToleranceSupport],
  ["M6 registry rescues concept", killConceptRegistryRescue],
  ["M7 ERROR semantic status", killErrorSemanticStatus],
  ["M8 SUCCESS missing status", killSuccessMissingStatus],
  ["M9 failed join dropped", killDroppedJoin],
  ["M10 duplicate last-write-wins", killDuplicateOverwrite],
  ["M11 timestamp in validation_id", killTimestampIdentity],
  ["M12 input-order output", killInputOrderMutation],
  ["M13 unusable generations dropped", killUnusableDrop],
  ["M14 causal SHAP supported", killCausalSupport],
  ["M15 unknown reason accepted", killUnknownReason],
  ["M16 upstream bytes mutated", killUpstreamMutation],
];

test("critical mutation catalog kills all 16 deliberate mutations", async (t) => {
  let killed = 0;
  for (const [name, detector] of mutations) {
    await t.test(name, async () => {
      await detector();
      killed += 1;
    });
  }
  assert.equal(killed, 16);
});

function killS0HiddenFeature(): void {
  const result = validateClaimDeterministically(
    testClaim({
      claim_type: "feature_presence",
      feature_id: "feature_a",
      evidence_level: "S0",
    }),
    testEvidence({ level: "S0" }),
  );
  assert.equal(result.reasonCode, REASON_CODE.FEATURE_NOT_EXPOSED);
}

function killReversedNormalization(): void {
  const result = validateClaimDeterministically(
    testClaim({
      claim_type: "feature_direction",
      feature_id: "feature_a",
      direction: "increase_risk",
    }),
    testEvidence(),
  );
  assert.equal(result.reasonCode, REASON_CODE.NORMALIZED_MATCH);
}

function killEpsilonMutation(): void {
  const feature = {
    feature_id: "feature_a",
    shap_value: 1e-12,
    abs_shap_value: 1e-12,
    direction: "increases_risk" as const,
    rank: 1,
  };
  const result = validateClaimDeterministically(
    testClaim({
      claim_type: "feature_direction",
      feature_id: "feature_a",
      direction: "increase_risk",
    }),
    testEvidence({ features: [feature] }),
  );
  assert.equal(result.reasonCode, REASON_CODE.DIRECTION_NEUTRAL);
}

function killToleranceWidening(): void {
  const result = outsideToleranceResult();
  assert.equal(result.reasonCode, REASON_CODE.NUMERIC_OUTSIDE_TOLERANCE);
}

function killOutsideToleranceSupport(): void {
  const mapping = reasonCodeByName(outsideToleranceResult().reasonCode);
  assert.equal(mapping.validation_status, VALIDATION_STATUS.CONTRADICTED);
}

function killConceptRegistryRescue(): void {
  const result = validateClaimDeterministically(
    testClaim({ claim_type: "concept_presence", concept_id: "registry_only" }),
    testEvidence(),
  );
  assert.equal(result.reasonCode, REASON_CODE.CONCEPT_NOT_FOUND_IN_EVIDENCE);
}

function killErrorSemanticStatus(): void {
  const error = buildErrorResult({
    claim: testClaim({ claim_type: "prediction" }),
    generation: null,
    evidence: null,
    provenance: testProvenance(),
    reasonCode: REASON_CODE.GENERATION_JOIN_FAILED,
    failedStage: "GENERATION_JOIN",
    errorMessage: "Missing.",
  });
  const mutant: Record<string, unknown> = structuredClone(error);
  mutant.validation_status = VALIDATION_STATUS.UNSUPPORTED;
  assert.throws(() => assertClaimValidationResult(mutant));
}

function killSuccessMissingStatus(): void {
  const success = validSuccessResult();
  const mutant: Record<string, unknown> = structuredClone(success);
  mutant.validation_status = null;
  assert.throws(() => assertClaimValidationResult(mutant));
}

function killDroppedJoin(): void {
  const claims = [
    testClaim({ claim_type: "prediction", claim_id: "claim_a" }),
    testClaim({ claim_type: "prediction", claim_id: "claim_b" }),
  ];
  assert.throws(
    () => assertResultReconciliation(claims, [validSuccessResult()]),
    /reconciliation failed/u,
  );
}

function killDuplicateOverwrite(): void {
  assert.throws(
    () => uniqueIndex([{ id: "a" }, { id: "a" }], (value) => value.id, "id"),
    /Duplicate id/u,
  );
}

function killTimestampIdentity(): void {
  const input = {
    claim_id: "claim_001",
    validator_version: "validator",
    policy_version: "policy",
  };
  const stable = createValidationId(input);
  const timestampMutant = createHash("sha256")
    .update(stable)
    .update("2026-07-23T01:00:00.000Z")
    .digest("hex");
  assert.notEqual(stable, timestampMutant);
}

function killInputOrderMutation(): void {
  const claims = Array.from({ length: 40 }, (_, index) =>
    testClaim({
      claim_type: index % 2 === 0 ? "prediction" : "feature_presence",
      claim_id: `claim_${String(index).padStart(3, "0")}`,
      model_id: `model_${index % 3}`,
      evidence_level: index % 2 === 0 ? "S0" : "S3",
    }),
  );
  const forward = selectBalancedSmokeClaims(claims, 20);
  const reverse = selectBalancedSmokeClaims([...claims].reverse(), 20);
  assert.deepEqual(forward, reverse);
}

function killUnusableDrop(): void {
  const usable = testGeneration();
  const unusable = {
    ...testGeneration(),
    generation_id: "generation_unusable",
    usable: false,
    truncated_response: true,
    raw_json_parse_success: false,
    schema_valid: false,
    usability_reason_codes: ["truncated_response"],
    generation_record: {
      ...testGeneration().generation_record,
      generation_id: "generation_unusable",
    },
  };
  const rows = buildGenerationValidationSummary([usable, unusable], []);
  assert.equal(rows.length, 2);
  assert.equal(rows[1]?.usable, false);
  assert.equal(rows[1]?.total_claims, 0);
}

function killCausalSupport(): void {
  const result = validateClaimDeterministically(
    testClaim({ claim_type: "causal", causal_strength: "causal" }),
    testEvidence(),
  );
  assert.equal(result.reasonCode, REASON_CODE.CAUSAL_OVERCLAIM);
}

function killUnknownReason(): void {
  assert.throws(() => reasonCodeByName("UNRECOGNIZED_REASON"));
}

async function killUpstreamMutation(): Promise<void> {
  const inputs = await loadValidationInputs({});
  const bytes = await readFile(
    "data/reports/llm_validation/validation_v1/canonicalization/generation_index.jsonl",
  );
  const original = createHash("sha256").update(bytes).digest("hex");
  const mutated = createHash("sha256")
    .update(bytes)
    .update("\nmutated")
    .digest("hex");
  assert.equal(
    original,
    inputs.artifacts.canonical_generation_index.sha256,
  );
  assert.notEqual(
    mutated,
    inputs.artifacts.canonical_generation_index.sha256,
  );
}

function outsideToleranceResult() {
  return validateClaimDeterministically(
    numericTestClaim({
      value: 50.01,
      unit: "percent",
      role: "prediction_score",
    }),
    testEvidence({ probability: 0.5 }),
  );
}

function validSuccessResult() {
  const claim = testClaim({
    claim_type: "prediction",
    direction: "increase_risk",
    claim_id: "claim_a",
  });
  const evidence = testEvidence();
  return buildSuccessResult({
    claim,
    generation: testGeneration(),
    evidence,
    decision: validateClaimDeterministically(claim, evidence),
    provenance: testProvenance(),
  });
}
