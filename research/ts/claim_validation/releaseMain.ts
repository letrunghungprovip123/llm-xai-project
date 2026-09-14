import path from "node:path";

import { verifyValidationRelease } from "./releaseVerifier";

const args = parseArgs(process.argv.slice(2));
const validationDirectory = required(args, "validation-dir");
verifyValidationRelease({
  validationDirectory,
  regressionReportPath: required(args, "regression-report"),
  coverageSummaryPath: required(args, "coverage-summary"),
  mutationReportPath: required(args, "mutation-report"),
  deterministicComparisonPath: required(args, "determinism-report"),
  calibrationReportPath:
    args.get("calibration-report") ??
    path.join(validationDirectory, "human_calibration", "calibration_report.json"),
  outputPath:
    args.get("output") ??
    path.join(validationDirectory, "claim_validation_release.json"),
})
  .then((report) => console.log(JSON.stringify(report, null, 2)))
  .catch((error: unknown) => {
    console.error(error instanceof Error ? error.stack : String(error));
    process.exitCode = 1;
  });

function parseArgs(values: string[]): Map<string, string> {
  const result = new Map<string, string>();
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!key?.startsWith("--") || !value || value.startsWith("--")) {
      throw new Error(`Invalid argument near ${key ?? "end"}.`);
    }
    result.set(key.slice(2), value);
  }
  return result;
}

function required(args: Map<string, string>, key: string): string {
  const value = args.get(key);
  if (!value) throw new Error(`--${key} is required.`);
  return value;
}
