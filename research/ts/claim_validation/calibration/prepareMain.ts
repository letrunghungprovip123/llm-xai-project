import { prepareCalibrationPackage } from "./prepare";

const args = parseArgs(process.argv.slice(2));
prepareCalibrationPackage({
  resultsPath: required(args, "results"),
  claimsPath: required(args, "claims"),
  outputDirectory: args.get("output-dir") ?? "human_calibration",
  sampleSize: Number(args.get("sample-size") ?? "600"),
})
  .then((manifest) => console.log(JSON.stringify(manifest, null, 2)))
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
