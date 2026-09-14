import assert from "node:assert/strict";
import test from "node:test";

import type { JsonObject } from "../../../contracts/llm-validation";
import type { AtomicClaimRecordV3 } from "../../../contracts/validation-claims";
import { readJsonlStrict } from "../../../research/ts/canonicalization/io";
import { REASON_CODE } from "../../../research/ts/claim_validation/constants";
import { loadValidationInputs } from "../../../research/ts/claim_validation/input";
import { reasonCodeByName } from "../../../research/ts/claim_validation/reasonCodes";
import { buildSuccessResult } from "../../../research/ts/claim_validation/result";
import type {
  ClaimValidationEvidencePackage,
  ClaimValidationGenerationRow,
} from "../../../research/ts/claim_validation/runtimeTypes";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";

const corpusPath =
  "tests/fixtures/claim_validation_v4_regression_cases.jsonl";

test("reviewed 260-case corpus repairs 257 measurement bugs and preserves 3 errors", async () => {
  const inputs = await loadValidationInputs({});
  const cases = await loadRegressionCases();
  assert.equal(cases.length, 260);
  assert.equal(
    cases.filter((item) => item.sourceClassification === "MEASUREMENT_BUG")
      .length,
    257,
  );
  assert.equal(
    cases.filter(
      (item) => item.sourceClassification === "VALID_EXPERIMENTAL_ERROR",
    ).length,
    3,
  );

  const claimsByParent = groupByParent(inputs.claims);
  const generationById = new Map(
    inputs.generations.map((generation) => [
      generation.generation_id,
      generation,
    ]),
  );
  const evidenceByPackageId = new Map(
    inputs.evidencePackages.map((evidence) => [evidence.package_id, evidence]),
  );
  const counts = new Map<string, number>();

  for (const regressionCase of cases) {
    increment(counts, regressionCase.expectedOutcome);
    const descendants = claimsByParent.get(regressionCase.historicalClaimId) ??
      [];
    if (regressionCase.expectedOutcome === "DROPPED") {
      assert.equal(descendants.length, 0, regressionCase.regressionCaseId);
      continue;
    }
    const expectedDescendants = regressionCase.expectedSplitCount || 1;
    assert.equal(
      descendants.length,
      expectedDescendants,
      regressionCase.regressionCaseId,
    );
    if (regressionCase.expectedOutcome === "NON_PREDICTION_ROUTE") {
      assert.ok(
        descendants.every((claim) => claim.claim_type !== "prediction"),
        regressionCase.regressionCaseId,
      );
    }
    if (regressionCase.expectedOutcome === "CORRECTED_DIRECTION") {
      assert.ok(regressionCase.correctedDirection);
      assert.ok(
        descendants.every(
          (claim) => claim.direction === regressionCase.correctedDirection,
        ),
        regressionCase.regressionCaseId,
      );
    }

    for (const claim of descendants) {
      const joined = join(
        claim,
        generationById,
        evidenceByPackageId,
      );
      const semantic = validateClaimDeterministically(
        claim,
        joined.evidence,
      );
      const result = buildSuccessResult({
        claim,
        generation: joined.generation,
        evidence: joined.evidence,
        decision: semantic,
        provenance: {
          claimsInputPath: inputs.artifacts.finalized_claims.path,
          claimsInputSha256: inputs.artifacts.finalized_claims.sha256,
          generationIndexPath:
            inputs.artifacts.canonical_generation_index.path,
          generationIndexSha256:
            inputs.artifacts.canonical_generation_index.sha256,
          evidencePackagesPath:
            inputs.artifacts.canonical_evidence_packages.path,
          evidencePackagesSha256:
            inputs.artifacts.canonical_evidence_packages.sha256,
        },
      });

      if (regressionCase.expectedOutcome === "AGGREGATE_MIXED") {
        assert.equal(
          semantic.reasonCode,
          REASON_CODE.DIRECTION_MIXED_OR_UNKNOWN,
          regressionCase.regressionCaseId,
        );
        assert.equal(semantic.observed.direction, "mixed");
      }
      if (regressionCase.expectedOutcome === "FACT_CONSISTENT_UNCERTAINTY") {
        if (semantic.reasonCode === REASON_CODE.EXACT_MATCH) {
          assertComparedExpectedFactsEqual(semantic.expected, semantic.observed);
        }
        assert.equal(result.claim_type, "uncertainty");
      }
      if (regressionCase.expectedOutcome === "PRESERVED_CONTRADICTION") {
        assert.equal(
          reasonCodeByName(semantic.reasonCode).validation_status,
          "CONTRADICTED",
          regressionCase.regressionCaseId,
        );
        assert.equal(
          semantic.reasonCode,
          REASON_CODE.PREDICTION_LABEL_MISMATCH,
        );
      }
    }
  }

  assert.deepEqual(Object.fromEntries(counts), {
    FACT_CONSISTENT_UNCERTAINTY: 63,
    AGGREGATE_MIXED: 161,
    NON_PREDICTION_ROUTE: 14,
    PRESERVED_CONTRADICTION: 3,
    DROPPED: 15,
    CORRECTED_DIRECTION: 4,
  });
});

type RegressionCase = {
  regressionCaseId: string;
  historicalClaimId: string;
  sourceClassification: string;
  correctedDirection: AtomicClaimRecordV3["direction"] | null;
  expectedOutcome: string;
  expectedSplitCount: number;
};

async function loadRegressionCases(): Promise<RegressionCase[]> {
  const input = await readJsonlStrict<JsonObject>(corpusPath);
  return input.records.map(({ value, line }) => ({
    regressionCaseId: stringField(value, "regression_case_id", line),
    historicalClaimId: stringField(value, "historical_claim_id", line),
    sourceClassification: stringField(value, "source_classification", line),
    correctedDirection: nullableDirection(value.corrected_direction, line),
    expectedOutcome: stringField(value, "expected_outcome", line),
    expectedSplitCount: numberField(value, "expected_split_count", line),
  }));
}

function groupByParent(
  claims: readonly AtomicClaimRecordV3[],
): Map<string, AtomicClaimRecordV3[]> {
  const groups = new Map<string, AtomicClaimRecordV3[]>();
  for (const claim of claims) {
    if (!claim.parent_claim_id) continue;
    const group = groups.get(claim.parent_claim_id) ?? [];
    group.push(claim);
    groups.set(claim.parent_claim_id, group);
  }
  return groups;
}

function join(
  claim: AtomicClaimRecordV3,
  generationById: ReadonlyMap<string, ClaimValidationGenerationRow>,
  evidenceByPackageId: ReadonlyMap<string, ClaimValidationEvidencePackage>,
): {
  generation: ClaimValidationGenerationRow;
  evidence: ClaimValidationEvidencePackage;
} {
  const generation = generationById.get(claim.generation_id);
  assert.ok(generation, `${claim.claim_id}: generation`);
  const evidence = evidenceByPackageId.get(generation.package_id);
  assert.ok(evidence, `${claim.claim_id}: evidence`);
  return { generation, evidence };
}

function assertComparedExpectedFactsEqual(
  expected: Record<string, unknown>,
  observed: Record<string, unknown>,
): void {
  for (const [key, expectedValue] of Object.entries(expected)) {
    if (expectedValue !== null) {
      assert.equal(observed[key], expectedValue, key);
    }
  }
}

function stringField(
  value: JsonObject,
  key: string,
  line: number,
): string {
  const field = value[key];
  if (typeof field !== "string") {
    throw new Error(`${corpusPath}:${line}.${key}`);
  }
  return field;
}

function numberField(
  value: JsonObject,
  key: string,
  line: number,
): number {
  const field = value[key];
  if (typeof field !== "number") {
    throw new Error(`${corpusPath}:${line}.${key}`);
  }
  return field;
}

function nullableDirection(
  value: unknown,
  line: number,
): AtomicClaimRecordV3["direction"] | null {
  if (value === null) return null;
  if (
    value === "increase_risk" ||
    value === "decrease_risk" ||
    value === "mixed" ||
    value === "neutral" ||
    value === "unknown"
  ) {
    return value;
  }
  throw new Error(`${corpusPath}:${line}.corrected_direction`);
}

function increment(counts: Map<string, number>, key: string): void {
  counts.set(key, (counts.get(key) ?? 0) + 1);
}
