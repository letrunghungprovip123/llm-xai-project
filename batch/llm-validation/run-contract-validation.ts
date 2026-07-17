import { runGenerationContractValidation } from "../../src/server/llmValidation/contractValidation/generationContractValidator";

// CLI giữ tham số tường minh để người chạy không vô tình trỏ nhầm canonical cohort.
async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const summary = await runGenerationContractValidation({
    generationIndexPath: required(args, "generation-index"),
    evidencePackagesPath: required(args, "evidence"),
    outputPath: required(args, "output"),
  });

  console.log("Generation contract validation completed.");
  console.log(`Total records: ${summary.total_records}`);
  console.log(`Contract passed: ${summary.contract_passed}`);
  console.log(`Contract failed: ${summary.contract_failed}`);
  console.log(`Output: ${summary.output_path}`);
}

function parseArgs(values: string[]): Map<string, string> {
  const result = new Map<string, string>();
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!key?.startsWith("--") || !value || value.startsWith("--")) {
      throw new Error(`Invalid CLI arguments near: ${key ?? "end"}`);
    }
    const normalizedKey = key.slice(2);
    if (result.has(normalizedKey)) {
      throw new Error(`Duplicate argument: --${normalizedKey}`);
    }
    result.set(normalizedKey, value);
  }
  return result;
}

function required(args: Map<string, string>, key: string): string {
  const value = args.get(key)?.trim();
  if (!value) throw new Error(`Missing required argument: --${key}`);
  return value;
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});

