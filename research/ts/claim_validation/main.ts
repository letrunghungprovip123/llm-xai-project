import { runClaimValidation } from "./pipeline";
import {
  DEFAULT_CLAIMS_INPUT_PATH,
  DEFAULT_EVIDENCE_PACKAGES_PATH,
  DEFAULT_GENERATION_INDEX_PATH,
} from "./input";

const DEFAULT_OUTPUT_DIRECTORY =
  "data/reports/llm_validation/validation_v1/claim_validation_v4";

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const mode = args.get("mode")?.trim() ?? "deterministic";
  if (mode !== "deterministic") {
    throw new Error("--mode must be deterministic.");
  }
  const summary = await runClaimValidation({
    claimsInputPath:
      args.get("claims-input")?.trim() ?? DEFAULT_CLAIMS_INPUT_PATH,
    generationIndexPath:
      args.get("generation-index")?.trim() ?? DEFAULT_GENERATION_INDEX_PATH,
    evidencePackagesPath:
      args.get("evidence-packages")?.trim() ?? DEFAULT_EVIDENCE_PACKAGES_PATH,
    outputDirectory:
      args.get("output-dir")?.trim() ?? DEFAULT_OUTPUT_DIRECTORY,
    mode,
    smoke: booleanValue(args.get("smoke") ?? "false", "smoke"),
    smokeLimit: integerValue(args.get("smoke-limit") ?? "100", "smoke-limit"),
    force: booleanValue(args.get("force") ?? "false", "force"),
  });
  console.log("Deterministic claim validation completed.");
  console.log(`Run mode: ${summary.mode}`);
  console.log(`Official input claims: ${summary.inputClaimCount}`);
  console.log(`Selected claims: ${summary.selectedClaimCount}`);
  console.log(`Output results: ${summary.outputResultCount}`);
  console.log(`Execution errors: ${summary.executionErrorCount}`);
  console.log(`Generation summaries: ${summary.generationSummaryCount}`);
  console.log(`Results SHA-256: ${summary.resultsSha256}`);
  console.log(`Output directory: ${summary.outputDirectory}`);
}

function parseArgs(values: string[]): Map<string, string> {
  const allowed = new Set([
    "claims-input",
    "generation-index",
    "evidence-packages",
    "output-dir",
    "mode",
    "smoke",
    "smoke-limit",
    "force",
  ]);
  const result = new Map<string, string>();
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!key?.startsWith("--") || value === undefined || value.startsWith("--")) {
      throw new Error(`Invalid CLI arguments near: ${key ?? "end"}`);
    }
    const normalized = key.slice(2);
    if (!allowed.has(normalized)) throw new Error(`Unknown argument: --${normalized}`);
    if (result.has(normalized)) {
      throw new Error(`Duplicate argument: --${normalized}`);
    }
    result.set(normalized, value);
  }
  return result;
}

function booleanValue(value: string, key: string): boolean {
  if (value === "true") return true;
  if (value === "false") return false;
  throw new Error(`--${key} must be true or false.`);
}

function integerValue(value: string, key: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`--${key} must be a positive integer.`);
  }
  return parsed;
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});
