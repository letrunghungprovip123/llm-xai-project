import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import Ajv2020 from "ajv/dist/2020";

import type {
  AtomicClaimRecordV3,
} from "../../../contracts/validation-claims";
import {
  readJsonlStrict,
} from "../../../research/ts/canonicalization/io";
import {
  runSemanticClaimFinalization,
} from "../../../research/ts/claim_finalization/semanticClaimFinalizer";
import type {
  ClaimSemanticCorrection,
} from "../../../research/ts/claim_finalization/generateSemanticCorrections";

const root = process.cwd();
const generationIndex = path.join(
  root,
  "data/reports/llm_validation/validation_v1/canonicalization/generation_index.jsonl",
);
const historicalClaims = path.join(
  root,
  "data/reports/llm_validation/validation_v1/claim_finalization_v1/claims_final.jsonl",
);
const correctionsPath = path.join(
  root,
  "config/research/ts-validation/claim_semantic_corrections_v1.jsonl",
);

test("semantic finalization rebuilds claims_v3 with reviewed lineage", async () => {
  const outputDir = await mkdtemp(path.join(os.tmpdir(), "claims-v3-test-"));
  const summary = await runSemanticClaimFinalization(options(outputDir));
  assert.equal(summary.claims_v2_count, 14680);
  assert.equal(summary.claims_v3_count, 14667);
  assert.deepEqual(summary.change_counts, {
    ADD: 2,
    UPDATE: 14665,
    DROP: 15,
    SPLIT: 2,
  });
  assert.deepEqual(summary.source_span_reconstruction, {
    audited_claim_count: 14667,
    exact_match_count: 14667,
    mismatch_count: 0,
  });

  const claims = (
    await readJsonlStrict<AtomicClaimRecordV3>(
      path.join(outputDir, "claims_final.jsonl"),
    )
  ).records.map((record) => record.value);
  const corrections = (
    await readJsonlStrict<ClaimSemanticCorrection>(correctionsPath)
  ).records.map((record) => record.value);
  assert.equal(claims.length, 14667);
  assert.ok(claims.every((claim) => claim.claim_schema_version === "claims_v3"));
  assert.ok(claims.every((claim) => claim.parent_claim_id));
  assert.ok(claims.every((claim) => claim.proposition_status === "COMPLETE"));
  const schema = JSON.parse(await readFile(
    path.join(root, "contracts/llm-validation/claims.schema.json"),
    "utf8",
  ));
  const validateClaim = new Ajv2020({ allErrors: true, strict: false })
    .compile(schema);
  for (const claim of claims) {
    assert.equal(
      validateClaim(claim),
      true,
      JSON.stringify(validateClaim.errors),
    );
  }

  const byParent = groupBy(claims, (claim) => claim.parent_claim_id);
  const fragments = corrections.filter(
    (correction) => correction.operation === "DROP_FRAGMENT",
  );
  assert.equal(fragments.length, 15);
  assert.ok(
    fragments.every(
      (correction) => !byParent.has(correction.historical_claim_id),
    ),
  );

  const mistyped = corrections.filter(
    (correction) =>
      correction.semantic_case_name
      === "FACTOR_STATEMENT_MISCLASSIFIED_AS_PREDICTION",
  );
  assert.equal(mistyped.length, 14);
  assert.ok(mistyped.every((correction) =>
    (byParent.get(correction.historical_claim_id) ?? [])
      .every((claim) => claim.claim_type !== "prediction")
  ));

  const directions = corrections.filter(
    (correction) => correction.operation === "UPDATE_DIRECTION",
  );
  assert.equal(directions.length, 4);
  assert.ok(directions.every((correction) => {
    const migrated = byParent.get(correction.historical_claim_id) ?? [];
    return migrated.length === 1
      && migrated[0]?.claim_subtype === "OVERALL_LABEL"
      && migrated[0]?.direction === "decrease_risk"
      && migrated[0]?.claim_id !== correction.historical_claim_id;
  }));

  const contradictions = corrections.filter(
    (correction) => correction.operation === "PRESERVE_EXPERIMENTAL_ERROR",
  );
  assert.equal(contradictions.length, 3);
  assert.ok(contradictions.every((correction) => {
    const migrated = byParent.get(correction.historical_claim_id) ?? [];
    return migrated.length === 1
      && migrated[0]?.claim_type === "prediction"
      && migrated[0]?.claim_subtype === "OVERALL_LABEL"
      && migrated[0]?.direction === "decrease_risk";
  }));
});

function options(outputDir: string) {
  return {
    generationIndexPath: generationIndex,
    historicalClaimsPath: historicalClaims,
    correctionsPath,
    claimsOutputPath: path.join(outputDir, "claims_final.jsonl"),
    changesOutputPath: path.join(outputDir, "claim_finalization_changes.jsonl"),
    summaryOutputPath: path.join(outputDir, "claim_finalization_summary.json"),
    manifestOutputPath: path.join(outputDir, "claim_finalization_manifest.json"),
  };
}

function groupBy<T>(
  values: readonly T[],
  key: (value: T) => string | null,
): Map<string, T[]> {
  const result = new Map<string, T[]>();
  for (const value of values) {
    const itemKey = key(value);
    if (!itemKey) continue;
    const group = result.get(itemKey) ?? [];
    group.push(value);
    result.set(itemKey, group);
  }
  return result;
}
