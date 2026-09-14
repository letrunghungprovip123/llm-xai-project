import { runSemanticClaimFinalization } from "./semanticClaimFinalizer";

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const summary = await runSemanticClaimFinalization({
    generationIndexPath: required(args, "generation-index"),
    historicalClaimsPath: required(args, "historical-claims"),
    correctionsPath: required(args, "corrections"),
    claimsOutputPath: required(args, "claims-output"),
    changesOutputPath: required(args, "changes-output"),
    summaryOutputPath: required(args, "summary-output"),
    manifestOutputPath: required(args, "manifest-output"),
  });
  console.log(JSON.stringify(summary, null, 2));
}

function parseArgs(values: string[]): Map<string, string> {
  const result = new Map<string, string>();
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!key?.startsWith("--") || !value || value.startsWith("--")) {
      throw new Error(`Invalid CLI argument near ${key ?? "end"}.`);
    }
    result.set(key.slice(2), value);
  }
  return result;
}

function required(args: ReadonlyMap<string, string>, key: string): string {
  const value = args.get(key)?.trim();
  if (!value) throw new Error(`Missing required argument: --${key}.`);
  return value;
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});
