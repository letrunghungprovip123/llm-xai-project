import assert from "node:assert/strict";
import test from "node:test";

import type { JsonObject } from "../../../contracts/llm-validation";
import { readJsonlStrict } from "../../../research/ts/canonicalization/io";
import { parseClaimValidationEvidence } from "../../../research/ts/claim_validation/evidenceParser";
import type {
  ClaimValidationEvidencePackage,
} from "../../../research/ts/claim_validation/runtimeTypes";
import { REASON_CODE } from "../../../research/ts/claim_validation/constants";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";
import {
  buildEvidenceView,
  claimExposureState,
  conceptExposureState,
  featureExposureState,
  findConcept,
  findFeature,
} from "../../../research/ts/claim_validation/validators/shared";
import {
  testClaim,
  testEvidence,
} from "./claimValidationTestFixtures";

const evidencePath =
  "data/reports/llm_validation/validation_v1/canonicalization/evidence_packages_36.jsonl";

test("EvidenceView retains exposed identities independently of allowlists", () => {
  const evidence = testEvidence();
  evidence.prompt_payload.constraints.allowed_feature_ids = ["feature_a"];
  evidence.prompt_payload.constraints.allowed_concept_ids = [];
  const evidenceSnapshot = structuredClone(evidence);
  const view = buildEvidenceView(evidence);

  assert.notEqual(
    view.exposed_features,
    evidence.prompt_payload.selected_evidence,
  );
  assert.notEqual(
    view.allowed_feature_ids,
    evidence.prompt_payload.constraints.allowed_feature_ids,
  );
  assert.deepEqual(
    view.exposed_features.map((feature) => feature.feature_id),
    ["feature_a", "feature_b"],
  );
  assert.deepEqual(view.allowed_feature_ids, ["feature_a"]);
  assert.deepEqual(
    view.exposed_concept_instances.map((concept) => concept.concept),
    ["concept_a"],
  );
  assert.deepEqual(view.allowed_concept_ids, []);

  assert.equal(featureExposureState(view, "feature_a"), "EXPOSED_ALLOWED");
  assert.equal(featureExposureState(view, "feature_b"), "EXPOSED_FORBIDDEN");
  assert.equal(featureExposureState(view, "feature_missing"), "NOT_EXPOSED");
  assert.equal(featureExposureState(view, null), "SOURCE_MISSING");
  assert.equal(conceptExposureState(view, "concept_a"), "EXPOSED_FORBIDDEN");
  assert.equal(conceptExposureState(view, "concept_missing"), "NOT_EXPOSED");
  assert.equal(conceptExposureState(view, null), "SOURCE_MISSING");

  assert.equal(findFeature(view, "feature_b")?.feature_id, "feature_b");
  assert.equal(findConcept(view, "concept_a")?.concept_id, "concept_a");
  assert.equal(
    claimExposureState(testClaim({ claim_type: "prediction" }), view),
    "NOT_APPLICABLE",
  );
  assert.deepEqual(evidence, evidenceSnapshot);
});

test("canonical S0-S4 exposure matches exact prompt evidence", async () => {
  const packages = await loadCanonicalEvidence();
  const expected = {
    S0: { packages: 36, features: 0, concepts: 0 },
    S1: { packages: 36, features: 360, concepts: 0 },
    S2: { packages: 36, features: 360, concepts: 0 },
    S3: { packages: 36, features: 345, concepts: 0 },
    S4: { packages: 36, features: 620, concepts: 318 },
  } as const;

  for (const [level, counts] of Object.entries(expected)) {
    const levelPackages = packages.filter(
      (packageItem) => packageItem.evidence_level === level,
    );
    assert.equal(levelPackages.length, counts.packages);
    assert.equal(
      sum(levelPackages, (packageItem) =>
        buildEvidenceView(packageItem).exposed_features.length
      ),
      counts.features,
    );
    assert.equal(
      sum(levelPackages, (packageItem) =>
        buildEvidenceView(packageItem).exposed_concept_instances.length
      ),
      counts.concepts,
    );
    for (const packageItem of levelPackages) {
      const view = buildEvidenceView(packageItem);
      for (const feature of view.exposed_features) {
        assert.equal(
          featureExposureState(view, feature.feature_id),
          "EXPOSED_ALLOWED",
        );
      }
      for (const concept of view.exposed_concept_instances) {
        assert.equal(
          conceptExposureState(view, concept.concept),
          "EXPOSED_ALLOWED",
        );
      }
    }
  }
});

test("all 36 S5 packages distinguish exposed-forbidden from absent", async () => {
  const s5Packages = (await loadCanonicalEvidence()).filter(
    (packageItem) => packageItem.evidence_level === "S5",
  );
  assert.equal(s5Packages.length, 36);

  let exposedFeatures = 0;
  let allowedFeatures = 0;
  let forbiddenFeatures = 0;
  let exposedConcepts = 0;
  let allowedConcepts = 0;
  let forbiddenConcepts = 0;

  for (const packageItem of s5Packages) {
    const view = buildEvidenceView(packageItem);
    const allowedFeature = view.exposed_features.find(
      (feature) =>
        featureExposureState(view, feature.feature_id) === "EXPOSED_ALLOWED",
    );
    const forbiddenFeature = view.exposed_features.find(
      (feature) =>
        featureExposureState(view, feature.feature_id) === "EXPOSED_FORBIDDEN",
    );
    const allowedConcept = view.exposed_concept_instances.find(
      (concept) =>
        conceptExposureState(view, concept.concept) === "EXPOSED_ALLOWED",
    );
    const forbiddenConcept = view.exposed_concept_instances.find(
      (concept) =>
        conceptExposureState(view, concept.concept) === "EXPOSED_FORBIDDEN",
    );
    assert.ok(allowedFeature, `${packageItem.package_id}: allowed feature`);
    assert.ok(forbiddenFeature, `${packageItem.package_id}: forbidden feature`);
    assert.ok(allowedConcept, `${packageItem.package_id}: allowed concept`);
    assert.ok(forbiddenConcept, `${packageItem.package_id}: forbidden concept`);

    exposedFeatures += view.exposed_features.length;
    allowedFeatures += view.exposed_features.filter(
      (feature) =>
        featureExposureState(view, feature.feature_id) === "EXPOSED_ALLOWED",
    ).length;
    forbiddenFeatures += view.exposed_features.filter(
      (feature) =>
        featureExposureState(view, feature.feature_id) === "EXPOSED_FORBIDDEN",
    ).length;
    exposedConcepts += view.exposed_concept_instances.length;
    allowedConcepts += view.exposed_concept_instances.filter(
      (concept) =>
        conceptExposureState(view, concept.concept) === "EXPOSED_ALLOWED",
    ).length;
    forbiddenConcepts += view.exposed_concept_instances.filter(
      (concept) =>
        conceptExposureState(view, concept.concept) === "EXPOSED_FORBIDDEN",
    ).length;

    const forbiddenDecision = validateClaimDeterministically(
      testClaim({
        claim_type: "feature_presence",
        subject_type: "feature",
        feature_id: forbiddenFeature.feature_id,
        evidence_level: "S5",
      }),
      packageItem,
    );
    assert.equal(forbiddenDecision.reasonCode, REASON_CODE.EXACT_MATCH);
    assert.equal(forbiddenDecision.observed.exposure_status, "EXPOSED");
  }

  assert.deepEqual({
    exposedFeatures,
    allowedFeatures,
    forbiddenFeatures,
    exposedConcepts,
    allowedConcepts,
    forbiddenConcepts,
  }, {
    exposedFeatures: 620,
    allowedFeatures: 180,
    forbiddenFeatures: 440,
    exposedConcepts: 318,
    allowedConcepts: 211,
    forbiddenConcepts: 107,
  });
});

async function loadCanonicalEvidence(): Promise<
  ClaimValidationEvidencePackage[]
> {
  const input = await readJsonlStrict<JsonObject>(evidencePath);
  return input.records.map(({ value, line }) =>
    parseClaimValidationEvidence(value, `canonical evidence line ${line}`)
  );
}

function sum<T>(
  values: readonly T[],
  select: (value: T) => number,
): number {
  return values.reduce((total, value) => total + select(value), 0);
}
