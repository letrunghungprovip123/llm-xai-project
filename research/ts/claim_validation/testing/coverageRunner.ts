import { execFile } from "node:child_process";
import { mkdir, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

import thresholds from "../../../../config/research/ts-validation/claim_validation_test_thresholds_v1.json";

const execFileAsync = promisify(execFile);

type CoverageMetric = {
  lines: number;
  branches: number;
  functions: number;
};

const CRITICAL_SEMANTIC_BRANCH_TESTS = [
  "concept aggregate direction covers every canonical branch",
  "all 81 allowed duplicate concept groups are permutation invariant",
  "all 161 reviewed concept-direction claims use the aggregate",
  "all 36 S5 packages distinguish exposed-forbidden from absent",
  "fact-consistency rejects inconsistent exact and normalized matches",
  "tolerance, contradiction and unresolved-fact invariants fail closed",
  "S5 exposed-forbidden evidence remains supported with policy violation",
  "prediction routing fails closed for missing, ambiguous and prohibited sources",
] as const;

async function main(): Promise<void> {
  const outputDirectory = path.resolve(
    argumentValue("--output-dir") ?? "coverage/claim-validation",
  );
  const tests = (await readdir("tests/research/ts"))
    .filter(
      (name) =>
        (
          name.startsWith("claimValidation") ||
          name === "numericTolerancePolicy.test.ts"
        ) &&
        name.endsWith(".test.ts"),
    )
    .sort()
    .map((name) => path.join("tests/research/ts", name));
  const args = [
    "--import",
    "tsx",
    "--test",
    "--experimental-test-coverage",
    `--test-coverage-include=${thresholds.coverage_scope.include[0]}`,
    ...thresholds.coverage_scope.exclude.map(
      (value) => `--test-coverage-exclude=${value}`,
    ),
    ...tests,
  ];
  const run = await execFileAsync(process.execPath, args, {
    cwd: process.cwd(),
    maxBuffer: 20 * 1024 * 1024,
  });
  const output = `${run.stdout}${run.stderr}`;
  const parsed = parseCoverageTable(output);
  const criticalSemanticMatrix = Object.fromEntries(
    CRITICAL_SEMANTIC_BRANCH_TESTS.map((name) => [name, output.includes(`✔ ${name}`)]),
  );
  const criticalCovered = Object.values(criticalSemanticMatrix).filter(Boolean).length;
  const criticalPercent =
    (criticalCovered / CRITICAL_SEMANTIC_BRANCH_TESTS.length) * 100;
  const gate = {
    lines: parsed.total.lines >= thresholds.coverage.lines,
    branches: parsed.total.branches >= thresholds.coverage.branches,
    functions: parsed.total.functions >= thresholds.coverage.functions,
    critical_semantic_branches:
      criticalPercent >= thresholds.coverage.critical_branch_percent,
  };
  const report = {
    schema_version: "claim_validation_coverage_v1",
    runner: "node_test_v8_coverage",
    generated_at: new Date().toISOString(),
    test_count: tests.length,
    scope: thresholds.coverage_scope,
    thresholds: thresholds.coverage,
    total: parsed.total,
    files: parsed.files,
    critical_semantic_branch_matrix: {
      required_count: CRITICAL_SEMANTIC_BRANCH_TESTS.length,
      covered_count: criticalCovered,
      percent: criticalPercent,
      tests: criticalSemanticMatrix,
    },
    gates: gate,
    pass: Object.values(gate).every(Boolean),
  };
  await mkdir(outputDirectory, { recursive: true });
  await Promise.all([
    writeFile(
      path.join(outputDirectory, "coverage-summary.json"),
      `${JSON.stringify(report, null, 2)}\n`,
      "utf8",
    ),
    writeFile(
      path.join(outputDirectory, "coverage-final.json"),
      `${JSON.stringify(parsed.files, null, 2)}\n`,
      "utf8",
    ),
    writeFile(
      path.join(outputDirectory, "coverage-run.log"),
      output,
      "utf8",
    ),
  ]);
  console.log(JSON.stringify(report, null, 2));
  if (!report.pass) process.exitCode = 1;
}

function parseCoverageTable(output: string): {
  total: CoverageMetric;
  files: Record<string, CoverageMetric & { uncovered_lines: string }>;
} {
  const files: Record<string, CoverageMetric & { uncovered_lines: string }> = {};
  let total: CoverageMetric | null = null;
  for (const rawLine of output.split(/\r?\n/u)) {
    const line = rawLine.replace(/^ℹ\s*/u, "");
    const match = line.match(
      /^\s*(.+?\.ts|all files)\s+\|\s+([\d.]+)\s+\|\s+([\d.]+)\s+\|\s+([\d.]+)\s+\|\s*(.*)$/u,
    );
    if (!match) continue;
    const metric = {
      lines: Number(match[2]),
      branches: Number(match[3]),
      functions: Number(match[4]),
    };
    if (match[1].trim() === "all files") {
      total = metric;
    } else {
      files[match[1].trim()] = {
        ...metric,
        uncovered_lines: match[5].trim(),
      };
    }
  }
  if (!total) throw new Error("Node coverage summary was not found.");
  return { total, files };
}

function argumentValue(name: string): string | null {
  const index = process.argv.indexOf(name);
  if (index < 0) return null;
  const value = process.argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`${name} requires a value.`);
  }
  return value;
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
