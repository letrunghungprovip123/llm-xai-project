import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const DETERMINISTIC_ARTIFACTS = [
  "claim_validation_results.jsonl",
  "validation_execution_errors.jsonl",
  "claim_validation_summary.json",
  "reason_code_counts.csv",
  "generation_validation_summary.jsonl",
] as const;

async function main(): Promise<void> {
  const directoryA = path.resolve(required("--a"));
  const directoryB = path.resolve(required("--b"));
  const outputPath = path.resolve(required("--output"));
  const artifacts = [];
  for (const name of DETERMINISTIC_ARTIFACTS) {
    const [contentA, contentB] = await Promise.all([
      readFile(path.join(directoryA, name)),
      readFile(path.join(directoryB, name)),
    ]);
    artifacts.push({
      name,
      sha256_a: sha256(contentA),
      sha256_b: sha256(contentB),
      byte_identical: contentA.equals(contentB),
    });
  }
  const report = {
    schema_version: "claim_validation_determinism_report_v1",
    compared_artifacts: artifacts,
    match: artifacts.every((artifact) => artifact.byte_identical),
  };
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
  if (!report.match) process.exitCode = 1;
}

function required(name: string): string {
  const index = process.argv.indexOf(name);
  const value = process.argv[index + 1];
  if (index < 0 || !value || value.startsWith("--")) {
    throw new Error(`${name} is required.`);
  }
  return value;
}

function sha256(content: Buffer): string {
  return createHash("sha256").update(content).digest("hex");
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
