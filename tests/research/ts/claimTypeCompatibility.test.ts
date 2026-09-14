import assert from "node:assert/strict";
import test from "node:test";

import {
  CLAIM_SUBTYPES_BY_TYPE,
  CLAIM_TYPES,
} from "../../../contracts/validation-claims";
import {
  loadClaimTypeCompatibility,
} from "../../../research/ts/claim_finalization/claimTypeCompatibility";

test("frozen compatibility matrix covers every claim type and subtype", () => {
  const config = loadClaimTypeCompatibility();
  assert.equal(config.schema_version, "claim_type_compatibility_v1");
  assert.equal(config.status, "FROZEN");

  const expected = CLAIM_TYPES.flatMap((claimType) =>
    CLAIM_SUBTYPES_BY_TYPE[claimType].map(
      (subtype) => `${claimType}/${subtype}`,
    )
  ).sort();
  const actual = config.rules.map(
    (rule) => `${rule.claim_type}/${rule.claim_subtype}`,
  ).sort();
  assert.deepEqual(actual, expected);
  assert.equal(new Set(actual).size, actual.length);
});

test("compatibility rules freeze all semantic routing fields", () => {
  for (const rule of loadClaimTypeCompatibility().rules) {
    assert.ok(rule.allowed_source_sections.length > 0);
    assert.ok(rule.required_fields.includes("claim_subtype"));
    assert.ok(rule.allowed_subject_types.length > 0);
    assert.equal(rule.complete_proposition_required, true);
    assert.ok(rule.deterministic_validator.length > 0);
    assert.equal(rule.semantic_fallback_allowed, false);
    assert.ok(rule.policy_relevance.length > 0);
  }
});
