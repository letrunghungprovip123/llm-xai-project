import assert from "node:assert/strict";
import test from "node:test";

import type { JsonObject } from "../../../contracts/llm-validation";
import { readJsonlStrict } from "../../../research/ts/canonicalization/io";
import { loadValidationInputs } from "../../../research/ts/claim_validation/input";
import { REASON_CODE } from "../../../research/ts/claim_validation/constants";
import type {
  ClaimValidationConceptEvidence,
  ClaimValidationEvidencePackage,
} from "../../../research/ts/claim_validation/runtimeTypes";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";
import {
  aggregateConceptDirection,
  aggregateConceptInstances,
  buildEvidenceView,
} from "../../../research/ts/claim_validation/validators/shared";

const correctionPath =
  "config/research/ts-validation/claim_semantic_corrections_v1.jsonl";

test("concept aggregate direction covers every canonical branch", () => {
  assert.equal(aggregateConceptDirection(["increase_risk"]), "increase_risk");
  assert.equal(aggregateConceptDirection(["decrease_risk"]), "decrease_risk");
  assert.equal(
    aggregateConceptDirection(["increase_risk", "decrease_risk"]),
    "mixed",
  );
  assert.equal(aggregateConceptDirection(["neutral"]), "neutral");
  assert.equal(aggregateConceptDirection([]), "unknown");
  assert.equal(
    aggregateConceptDirection(["increase_risk", "neutral"]),
    "unknown",
  );
  assert.equal(aggregateConceptDirection(["unknown"]), "unknown");
});

test("all 81 allowed duplicate concept groups are permutation invariant", async () => {
  const { evidencePackages } = await loadValidationInputs({});
  const groups = allowedDuplicateGroups(evidencePackages);
  assert.equal(groups.length, 81);

  for (const group of groups) {
    const forward = aggregateConceptInstances(
      group.packageId,
      group.instances,
      [group.conceptId],
    ).get(group.conceptId);
    const reverse = aggregateConceptInstances(
      group.packageId,
      [...group.instances].reverse(),
      [group.conceptId],
    ).get(group.conceptId);
    const rotated = aggregateConceptInstances(
      group.packageId,
      rotate(group.instances),
      [group.conceptId],
    ).get(group.conceptId);

    assert.ok(forward, `${group.packageId}/${group.conceptId}: forward`);
    assert.deepEqual(reverse, forward, `${group.packageId}/${group.conceptId}: reverse`);
    assert.deepEqual(rotated, forward, `${group.packageId}/${group.conceptId}: rotate`);
    assert.equal(forward.direction, "mixed");
    assert.equal(forward.instance_count, group.instances.length);
    assert.equal(forward.exposure_state, "EXPOSED_ALLOWED");
    assert.deepEqual(
      [...forward.supporting_feature_ids],
      [...forward.supporting_feature_ids].sort(),
    );
    assert.deepEqual(
      [...forward.source_record_keys],
      [...forward.source_record_keys].sort((left, right) => {
        if (left.startsWith("concept:")) return -1;
        if (right.startsWith("concept:")) return 1;
        return left.localeCompare(right);
      }),
    );
  }
});

test("all 161 reviewed concept-direction claims use the aggregate", async () => {
  const inputs = await loadValidationInputs({});
  const reviewedHistoricalIds = await reviewedConceptClaimIds();
  assert.equal(reviewedHistoricalIds.size, 161);

  const affectedClaims = inputs.claims.filter(
    (claim) =>
      claim.claim_type === "concept_direction" &&
      (
        reviewedHistoricalIds.has(claim.claim_id) ||
        (
          "parent_claim_id" in claim &&
          typeof claim.parent_claim_id === "string" &&
          reviewedHistoricalIds.has(claim.parent_claim_id)
        )
      ),
  );
  assert.equal(affectedClaims.length, 161);

  const generationById = new Map(
    inputs.generations.map((generation) => [
      generation.generation_id,
      generation,
    ]),
  );
  const evidenceByPackageId = new Map(
    inputs.evidencePackages.map((evidence) => [evidence.package_id, evidence]),
  );

  for (const claim of affectedClaims) {
    const generation = generationById.get(claim.generation_id);
    assert.ok(generation, `${claim.claim_id}: generation`);
    const evidence = evidenceByPackageId.get(generation.package_id);
    assert.ok(evidence, `${claim.claim_id}: evidence`);
    const aggregate = buildEvidenceView(evidence).aggregated_concepts.get(
      claim.concept_id ?? "",
    );
    assert.ok(aggregate, `${claim.claim_id}: concept aggregate`);
    assert.equal(aggregate.direction, "mixed", claim.claim_id);
    assert.ok(aggregate.instance_count > 1, claim.claim_id);

    const decision = validateClaimDeterministically(claim, evidence);
    assert.equal(
      decision.reasonCode,
      REASON_CODE.DIRECTION_MIXED_OR_UNKNOWN,
      claim.claim_id,
    );
    assert.equal(decision.observed.direction, "mixed", claim.claim_id);

    const permutedEvidence = reverseConceptInstances(evidence);
    assert.deepEqual(
      validateClaimDeterministically(claim, permutedEvidence),
      decision,
      `${claim.claim_id}: validator permutation`,
    );
  }
});

type DuplicateConceptGroup = {
  packageId: string;
  conceptId: string;
  instances: ClaimValidationConceptEvidence[];
};

function allowedDuplicateGroups(
  packages: readonly ClaimValidationEvidencePackage[],
): DuplicateConceptGroup[] {
  const groups: DuplicateConceptGroup[] = [];
  for (const packageItem of packages) {
    const byConcept = new Map<string, ClaimValidationConceptEvidence[]>();
    for (const instance of packageItem.prompt_payload.concept_evidence) {
      const group = byConcept.get(instance.concept);
      if (group) {
        group.push(instance);
      } else {
        byConcept.set(instance.concept, [instance]);
      }
    }
    for (const [conceptId, instances] of byConcept) {
      if (
        instances.length > 1 &&
        packageItem.prompt_payload.constraints.allowed_concept_ids.includes(
          conceptId,
        )
      ) {
        groups.push({
          packageId: packageItem.package_id,
          conceptId,
          instances,
        });
      }
    }
  }
  return groups.sort((left, right) =>
    `${left.packageId}/${left.conceptId}`.localeCompare(
      `${right.packageId}/${right.conceptId}`,
    )
  );
}

async function reviewedConceptClaimIds(): Promise<Set<string>> {
  const corrections = await readJsonlStrict<JsonObject>(correctionPath);
  const ids = new Set<string>();
  for (const { value, line } of corrections.records) {
    if (
      value.semantic_case_name !==
        "CONCEPT_DIRECTION_FIRST_MATCH_AMBIGUITY"
    ) {
      continue;
    }
    if (typeof value.historical_claim_id !== "string") {
      throw new Error(`correction line ${line}: historical_claim_id`);
    }
    ids.add(value.historical_claim_id);
  }
  return ids;
}

function rotate<T>(values: readonly T[]): T[] {
  return values.length < 2
    ? [...values]
    : [...values.slice(1), values[0]];
}

function reverseConceptInstances(
  evidence: ClaimValidationEvidencePackage,
): ClaimValidationEvidencePackage {
  return {
    ...evidence,
    prompt_payload: {
      ...evidence.prompt_payload,
      concept_evidence: [...evidence.prompt_payload.concept_evidence].reverse(),
    },
  };
}
