import assert from "node:assert/strict";
import test from "node:test";

import metricDictionary from "../../../config/research/ts-validation/metric_dictionary.json";
import historicalValidatorPrompt from "../../../config/research/ts-validation/validator_prompt_v1.json";
import { CLAIM_TYPES } from "../../../contracts/validation-claims";
import {
  assertNumericTolerancePolicy,
  NUMERIC_TOLERANCE_POLICY,
} from "../../../research/ts/claim_validation/numericPolicy";
import {
  assertClaimValidationPolicy,
  CLAIM_VALIDATION_POLICY,
  normalizeDirection,
} from "../../../research/ts/claim_validation/policy";
import {
  assertClaimValidationReasonCodes,
  CLAIM_VALIDATION_REASON_CODES,
} from "../../../research/ts/claim_validation/reasonCodes";

test("claim validation policy v1 is strict and covers every claims_v2 type", () => {
  assert.doesNotThrow(() => assertClaimValidationPolicy());
  const routes = CLAIM_VALIDATION_POLICY.claim_type_routing;
  assert.equal(routes.length, CLAIM_TYPES.length);
  assert.deepEqual(
    [...new Set(routes.map((route) => route.claim_type))].sort(),
    [...CLAIM_TYPES].sort(),
  );
  assert.ok(routes.some((route) => route.claim_type === "causal"));
});

test("policy versions reference the frozen reason and numeric policies", () => {
  assert.doesNotThrow(() => assertClaimValidationReasonCodes());
  assert.doesNotThrow(() => assertNumericTolerancePolicy());
  assert.equal(
    CLAIM_VALIDATION_POLICY.reason_code_taxonomy_version,
    CLAIM_VALIDATION_REASON_CODES.taxonomy_version,
  );
  assert.equal(
    CLAIM_VALIDATION_POLICY.numeric_policy_version,
    NUMERIC_TOLERANCE_POLICY.numeric_policy_version,
  );
});

test("every semantic reason is compatible with each allowed claim route", () => {
  const routes = new Map(
    CLAIM_VALIDATION_POLICY.claim_type_routing.map((route) => [
      route.claim_type,
      route,
    ]),
  );
  for (const reason of CLAIM_VALIDATION_REASON_CODES.reason_codes) {
    if (reason.family === "SYSTEM" || reason.validation_status === null) continue;
    for (const claimType of reason.allowed_claim_types) {
      const route = routes.get(claimType);
      assert.ok(route, `Missing route for ${claimType}`);
      assert.ok(
        route.allowed_reason_families.includes(reason.family),
        `${reason.code} family is not allowed by ${claimType}`,
      );
      assert.ok(
        route.allowed_statuses.includes(reason.validation_status),
        `${reason.code} status is not allowed by ${claimType}`,
      );
    }
  }
});

test("S0 prohibits hidden IR and does not expose feature semantics", () => {
  const boundary = CLAIM_VALIDATION_POLICY.evidence_exposure_boundary;
  assert.equal(boundary.validation_source, "canonical_evidence_package");
  assert.equal(boundary.hidden_IR_prohibited, true);
  assert.deepEqual(boundary.s0.exposed_claim_families, ["PREDICTION"]);
  for (const family of [
    "FEATURE",
    "CONCEPT",
    "DIRECTION",
    "MAGNITUDE",
  ] as const) {
    assert.ok(boundary.s0.unexposed_claim_families.includes(family));
  }

  const s0ExposureCodes = [
    "FEATURE_NOT_EXPOSED",
    "CONCEPT_NOT_EXPOSED",
    "DIRECTION_NOT_EXPOSED",
    "MAGNITUDE_NOT_EXPOSED",
  ];
  for (const code of s0ExposureCodes) {
    const reason = CLAIM_VALIDATION_REASON_CODES.reason_codes.find(
      (candidate) => candidate.code === code,
    );
    assert.equal(reason?.validation_status, "UNSUPPORTED");
  }
});

test("direction normalization and near-zero epsilon match active source", () => {
  assert.equal(normalizeDirection("increase_risk"), "increase_risk");
  assert.equal(normalizeDirection("increases_risk"), "increase_risk");
  assert.equal(normalizeDirection("decrease_risk"), "decrease_risk");
  assert.equal(normalizeDirection("decreases_risk"), "decrease_risk");
  assert.equal(CLAIM_VALIDATION_POLICY.near_zero_shap_epsilon, 1e-12);
});

test("unsupported claim types and unresolved joins fail closed", () => {
  assert.equal(CLAIM_VALIDATION_POLICY.one_result_per_claim, true);
  assert.equal(CLAIM_VALIDATION_POLICY.unresolved_join_behavior, "ERROR");
  assert.equal(
    CLAIM_VALIDATION_POLICY.unsupported_claim_type_behavior,
    "ERROR",
  );
});

test("policy rejects invalid shapes, duplicate routes and status flag drift", () => {
  assert.throws(
    () => assertClaimValidationPolicy({}),
    /Invalid claim validation policy/u,
  );
  const duplicateRoute = structuredClone(CLAIM_VALIDATION_POLICY);
  duplicateRoute.claim_type_routing[
    duplicateRoute.claim_type_routing.length - 1
  ] = structuredClone(duplicateRoute.claim_type_routing[0]);
  assert.throws(
    () => assertClaimValidationPolicy(duplicateRoute),
    /one route per claim type/u,
  );
  const flagMismatch = structuredClone(CLAIM_VALIDATION_POLICY);
  const route = flagMismatch.claim_type_routing.find(
    (candidate) => candidate.allowed_statuses.includes("NOT_APPLICABLE"),
  )!;
  route.not_applicable_allowed = false;
  assert.throws(
    () => assertClaimValidationPolicy(flagMismatch),
    /flag\/status mismatch/u,
  );
  assert.throws(
    () => normalizeDirection("not-a-frozen-direction"),
    /Unsupported direction/u,
  );
});

test("active metric lineage uses v2 status and old validator prompt is historical", () => {
  const serializedMetrics = JSON.stringify(metricDictionary);
  assert.equal(metricDictionary.dictionary_version, "metric_dictionary_v2");
  assert.doesNotMatch(serializedMetrics, /PARTIALLY_SUPPORTED|partially_supported/u);
  assert.doesNotMatch(serializedMetrics, /validation_label/u);
  assert.match(serializedMetrics, /validation_status/u);

  assert.equal(
    historicalValidatorPrompt.status,
    "HISTORICAL_SCAFFOLD_NOT_ACTIVE",
  );
  assert.equal(
    historicalValidatorPrompt.superseded_by,
    "config/research/ts-validation/claim_validation_policy_v1.json",
  );
});
