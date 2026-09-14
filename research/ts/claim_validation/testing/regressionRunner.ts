import { execFile } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

import { readJsonl } from "../calibration/io";

const execFileAsync = promisify(execFile);

type RegressionCase = {
  source_classification: "MEASUREMENT_BUG" | "VALID_EXPERIMENTAL_ERROR";
  expected_outcome: string;
};

async function main(): Promise<void> {
  const outputPath = path.resolve(
    argumentValue("--output") ?? "reports/claim-validation-regression.json",
  );
  const cases = await readJsonl<RegressionCase>(
    "tests/fixtures/claim_validation_v4_regression_cases.jsonl",
  );
  let testPassed = false;
  let testOutput = "";
  try {
    const run = await execFileAsync(
      process.execPath,
      [
        "--import",
        "tsx",
        "--test",
        "tests/research/ts/claimValidationReviewedRegression.test.ts",
      ],
      { maxBuffer: 10 * 1024 * 1024 },
    );
    testPassed = true;
    testOutput = `${run.stdout}${run.stderr}`;
  } catch (error) {
    const failure = error as { stdout?: string; stderr?: string };
    testOutput = `${failure.stdout ?? ""}${failure.stderr ?? ""}`;
  }
  const outcomeCounts = Object.fromEntries(
    [...new Set(cases.map((item) => item.expected_outcome))]
      .sort()
      .map((outcome) => [
        outcome,
        cases.filter((item) => item.expected_outcome === outcome).length,
      ]),
  );
  const report = {
    schema_version: "claim_validation_reviewed_regression_report_v1",
    generated_at: new Date().toISOString(),
    corpus_count: cases.length,
    measurement_bug_count: cases.filter(
      (item) => item.source_classification === "MEASUREMENT_BUG",
    ).length,
    preserved_experimental_contradiction_count: cases.filter(
      (item) => item.source_classification === "VALID_EXPERIMENTAL_ERROR",
    ).length,
    outcome_counts: outcomeCounts,
    test_passed: testPassed,
    pass:
      testPassed &&
      cases.length === 260 &&
      cases.filter((item) => item.source_classification === "MEASUREMENT_BUG")
        .length === 257 &&
      cases.filter(
        (item) => item.source_classification === "VALID_EXPERIMENTAL_ERROR",
      ).length === 3,
    test_output_tail: testOutput.slice(-4000),
  };
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
  if (!report.pass) process.exitCode = 1;
}

function argumentValue(name: string): string | null {
  const index = process.argv.indexOf(name);
  if (index < 0) return null;
  const value = process.argv[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`${name} requires a value.`);
  return value;
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
