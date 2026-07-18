import assert from "node:assert/strict";
import test from "node:test";

import { validateGenerationContract } from "../../research/llm/contract_validation/index";
import { canonicalRow, defaultParsedOutput, evidencePackage } from "./fixtures";

test("S5 contract passes when factor count, order, role and IDs match", () => {
  const result = validateGenerationContract(canonicalRow(), evidencePackage());
  assert.equal(result.contract_pass, true);
  assert.equal(result.structural_metrics.skeleton_compliance, true);
  assert.deepEqual(result.issue_codes, []);
});

test("S5 order mismatch is reported without dropping the generation", () => {
  const output = defaultParsedOutput();
  output.factors = [...(output.factors as unknown[])].reverse();
  const result = validateGenerationContract(
    canonicalRow({ parsedOutput: output }),
    evidencePackage(),
  );
  assert.equal(result.contract_pass, false);
  assert.equal(result.structural_metrics.factor_order_accuracy, false);
  assert.ok(result.issue_codes.includes("FACTOR_ORDER_MISMATCH"));
});

test("unusable generation remains a contract record and fails", () => {
  const result = validateGenerationContract(
    canonicalRow({ usable: false, parsedOutput: null }),
    evidencePackage(),
  );
  assert.equal(result.raw_metrics.usable_output, false);
  assert.equal(result.contract_pass, false);
  assert.ok(result.issue_codes.includes("OUTPUT_UNUSABLE"));
});
