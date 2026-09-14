import assert from "node:assert/strict";
import test from "node:test";

import { loadValidationInputs } from "../../../research/ts/claim_validation/input";
import { buildGenerationValidationSummary } from "../../../research/ts/claim_validation/summary";

test("official generation aggregation preserves the frozen 648-row denominator", async () => {
  const inputs = await loadValidationInputs({});
  const summary = buildGenerationValidationSummary(inputs.generations, []);
  const usableRows = summary.filter((row) => row.usable === true);
  const unusableRows = summary.filter((row) => row.usable === false);

  assert.equal(summary.length, 648);
  assert.equal(usableRows.length, 638);
  assert.equal(unusableRows.length, 10);
  assert.equal(
    new Set(summary.map((row) => row.generation_id)).size,
    summary.length,
  );
  assert.ok(
    unusableRows.every(
      (row) =>
        row.total_claims === 0 &&
        typeof row.failure_reason === "string" &&
        row.failure_reason.length > 0 &&
        row.contract_usability_metadata !== undefined,
    ),
  );
  assert.ok(
    usableRows.every(
      (row) =>
        row.total_claims === 0 &&
        row.supported_count === 0 &&
        row.execution_error_count === 0,
    ),
  );
});
