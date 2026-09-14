import { runClaimFinalization } from "./claimFinalizer";

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const summary = await runClaimFinalization({
    generationIndexPath: required(args, "generation-index"),
    claimsInputPath: required(args, "claims-input"),
    attemptsInputPath: required(args, "attempts-input"),
    failuresInputPath: required(args, "failures-input"),
    claimsOutputPath: required(args, "claims-output"),
    changesOutputPath: required(args, "changes-output"),
    manifestOutputPath: required(args, "manifest-output"),
  });

  console.log("Claim finalization completed.");
  console.log(`Canonical generations: ${summary.canonical_generations}`);
  console.log(`Successful generations: ${summary.successful_generations}`);
  console.log(`Unusable generations: ${summary.unusable_generations}`);
  console.log(`Input claims: ${summary.input_claims}`);
  console.log(`Claims after stored-response replay: ${summary.replayed_claims}`);
  console.log(`Final claims: ${summary.final_claims}`);
  console.log(`Changed generations: ${summary.changed_generations}`);
  console.log(`Change records: ${summary.change_records}`);
  console.log(`Policy-absence slots: ${summary.policy_absence_slots}`);
  console.log(`Atomic count facts: ${summary.atomic_count_facts}`);
  console.log(`Final claims SHA-256: ${summary.claims_output_sha256}`);
  console.log(`Claims output: ${summary.claims_output_path}`);
  console.log(`Changes output: ${summary.changes_output_path}`);
  console.log(`Manifest output: ${summary.manifest_output_path}`);
}

function parseArgs(values: string[]): Map<string, string> {
  const result = new Map<string, string>();
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!key?.startsWith("--") || !value || value.startsWith("--")) {
      throw new Error(`Invalid CLI arguments near: ${key ?? "end"}`);
    }
    const normalized = key.slice(2);
    if (result.has(normalized)) {
      throw new Error(`Duplicate argument: --${normalized}`);
    }
    result.set(normalized, value);
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
