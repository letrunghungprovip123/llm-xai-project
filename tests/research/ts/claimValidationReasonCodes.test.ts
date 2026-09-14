import assert from "node:assert/strict";
import test from "node:test";

import {
  assertClaimValidationReasonCodes,
  CLAIM_VALIDATION_REASON_CODES,
  reasonCodeByName,
} from "../../../research/ts/claim_validation/reasonCodes";

test("reason taxonomy matches every declared unique code", () => {
  assert.doesNotThrow(() => assertClaimValidationReasonCodes());
  const reasons = CLAIM_VALIDATION_REASON_CODES.reason_codes;
  assert.equal(
    new Set(reasons.map((reason) => reason.code)).size,
    reasons.length,
  );
  for (const reason of reasons) {
    assert.ok(reason.family);
    assert.ok(reason.description);
    assert.ok(reason.allowed_claim_types.length > 0);
    assert.ok(reason.severity);
    assert.ok(reason.primary_metric_effect);
  }
});

test("SYSTEM codes never map to semantic validation status", () => {
  for (const reason of CLAIM_VALIDATION_REASON_CODES.reason_codes) {
    if (reason.family === "SYSTEM") {
      assert.equal(reason.execution_status, "ERROR");
      assert.equal(reason.validation_status, null);
      assert.equal(reason.primary_metric_effect, "ERROR");
    } else {
      assert.equal(reason.execution_status, "SUCCESS");
      assert.notEqual(reason.validation_status, null);
    }
  }
});

test("SUPPORTED is reserved for explicit MATCH reasons", () => {
  const supported = CLAIM_VALIDATION_REASON_CODES.reason_codes.filter(
    (reason) => reason.validation_status === "SUPPORTED",
  );
  assert.deepEqual(
    supported.map((reason) => reason.code).sort(),
    [
      "EXACT_MATCH",
      "MAGNITUDE_MATCH",
      "NORMALIZED_MATCH",
      "TOLERANCE_MATCH",
    ],
  );
  assert.ok(supported.every((reason) => reason.family === "MATCH"));
});

test("hard safety failures are exactly the three frozen overclaim codes", () => {
  const hardCodes = CLAIM_VALIDATION_REASON_CODES.reason_codes
    .filter((reason) => reason.is_hard_safety_failure)
    .map((reason) => reason.code)
    .sort();
  assert.deepEqual(hardCodes, [
    "CAUSAL_OVERCLAIM",
    "CERTAINTY_OVERCLAIM",
    "GUARANTEE_OVERCLAIM",
  ]);
});

test("taxonomy has no arbitrary catch-all reason", () => {
  const codes = CLAIM_VALIDATION_REASON_CODES.reason_codes.map(
    (reason) => reason.code,
  );
  assert.equal(
    codes.some((code) => /^(?:OTHER|UNKNOWN|UNCLASSIFIED)$/u.test(code)),
    false,
  );
  assert.throws(() => reasonCodeByName("UNKNOWN"), /Unknown claim validation/u);
});

test("reason taxonomy rejects duplicate and semantically inconsistent mappings", () => {
  const duplicate = structuredClone(CLAIM_VALIDATION_REASON_CODES);
  duplicate.reason_codes[1].code = duplicate.reason_codes[0].code;
  assert.throws(
    () => assertClaimValidationReasonCodes(duplicate),
    /must be unique/u,
  );

  const missing = structuredClone(CLAIM_VALIDATION_REASON_CODES);
  missing.reason_codes.pop();
  assert.throws(
    () => assertClaimValidationReasonCodes(missing),
    /taxonomy\/code constant mismatch/u,
  );

  const system = structuredClone(CLAIM_VALIDATION_REASON_CODES);
  const systemReason = system.reason_codes.find(
    (reason) => reason.family === "SYSTEM",
  )!;
  systemReason.primary_metric_effect = "PASS";
  assert.throws(
    () => assertClaimValidationReasonCodes(system),
    /SYSTEM reason has invalid mapping/u,
  );

  const semantic = structuredClone(CLAIM_VALIDATION_REASON_CODES);
  const semanticReason = semantic.reason_codes.find(
    (reason) => reason.family !== "SYSTEM",
  )!;
  semanticReason.execution_status = "ERROR";
  assert.throws(
    () => assertClaimValidationReasonCodes(semantic),
    /Semantic reason has invalid mapping/u,
  );

  const wrongFamily = structuredClone(CLAIM_VALIDATION_REASON_CODES);
  const supported = wrongFamily.reason_codes.find(
    (reason) => reason.validation_status === "SUPPORTED",
  )!;
  supported.family = "POLICY";
  assert.throws(
    () => assertClaimValidationReasonCodes(wrongFamily),
    /SUPPORTED reason must belong to MATCH/u,
  );

  const catchAll = structuredClone(CLAIM_VALIDATION_REASON_CODES);
  catchAll.reason_codes[0].code = "UNKNOWN";
  assert.throws(
    () => assertClaimValidationReasonCodes(catchAll),
    /Catch-all reason code/u,
  );

  const hardSafety = structuredClone(CLAIM_VALIDATION_REASON_CODES);
  hardSafety.reason_codes[0].is_hard_safety_failure = true;
  assert.throws(
    () => assertClaimValidationReasonCodes(hardSafety),
    /Hard-safety reason-code set/u,
  );
});
