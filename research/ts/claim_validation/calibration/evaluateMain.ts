import path from "node:path";

import { evaluateCalibration } from "./evaluate";

const args = parseArgs(process.argv.slice(2));
const packageDirectory = args.get("package-dir") ?? "human_calibration";
evaluateCalibration({
  packageDirectory,
  raterAPath:
    args.get("rater-a") ??
    path.join(packageDirectory, "annotation_template_rater_a.csv"),
  raterBPath:
    args.get("rater-b") ??
    path.join(packageDirectory, "annotation_template_rater_b.csv"),
  adjudicationPath: args.get("adjudication"),
  outputPath:
    args.get("output") ?? path.join(packageDirectory, "calibration_report.json"),
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
