import { runAtomicClaimExtraction } from "../../src/server/llmValidation/claimExtraction/claimExtractionRunner";

// CLI hỗ trợ limit để smoke test và tự resume bằng source hash khi chạy lại toàn cohort.
async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const summary = await runAtomicClaimExtraction({
    generationIndexPath: required(args, "generation-index"),
    claimsOutputPath: required(args, "claims-output"),
    failuresOutputPath: required(args, "failures-output"),
    attemptsOutputPath: optionalString(args, "attempts-output"),
    limit: optionalInteger(args, "limit"),
    force: optionalBoolean(args, "force", false),
    checkpointEvery: optionalInteger(args, "checkpoint-every") ?? 5,
    storeRawResponses: optionalBoolean(args, "store-raw-responses", false),
  });

  console.log("Atomic claim extraction completed.");
  console.log(`Canonical generations: ${summary.total_canonical_generations}`);
  console.log(`Successful generations: ${summary.successful_generations}`);
  console.log(`Failure/unusable records: ${summary.failed_or_unusable_generations}`);
  console.log(`Claims: ${summary.total_claims}`);
  console.log(`Reused successes: ${summary.reused_successes}`);
  console.log(`New DeepSeek calls: ${summary.new_provider_calls}`);
  console.log(`New attempt records: ${summary.new_attempt_records}`);
  console.log(`Pending generations: ${summary.pending_generations}`);
  console.log(
    `Usage for new calls: ${summary.usage_for_new_calls.input_tokens} input + ` +
      `${summary.usage_for_new_calls.output_tokens} output = ` +
      `${summary.usage_for_new_calls.total_tokens} total tokens`,
  );
  if (summary.estimated_cost_for_new_calls_usd !== null) {
    console.log(
      `Estimated API cost for new calls: $${summary.estimated_cost_for_new_calls_usd.toFixed(6)}`,
    );
  }
  const postprocess = summary.postprocess_for_new_successes;
  console.log(
    `Postprocess: ${postprocess.llm_claims_received} LLM claims + ` +
      `${postprocess.deterministic_claims_added} deterministic + ` +
      `${postprocess.derived_numeric_claims_added} derived numeric; ` +
      `${postprocess.causal_overclaims_demoted} causal overclaims demoted; ` +
      `${postprocess.semantic_duplicates_removed} semantic duplicates removed`,
  );
  console.log(
    `Source coverage: ${postprocess.source_slots_covered}/` +
      `${postprocess.source_slots_total} slots; ` +
      `${postprocess.unclaimed_source_slots} unclaimed`,
  );
  console.log(`Claims output: ${summary.claims_output_path}`);
  console.log(`Failures output: ${summary.failures_output_path}`);
  console.log(`Attempts output: ${summary.attempts_output_path}`);
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
    if (result.has(normalized)) throw new Error(`Duplicate argument: --${normalized}`);
    result.set(normalized, value);
  }
  return result;
}

function required(args: Map<string, string>, key: string): string {
  const value = args.get(key)?.trim();
  if (!value) throw new Error(`Missing required argument: --${key}`);
  return value;
}

function optionalInteger(args: Map<string, string>, key: string): number | null {
  const value = args.get(key);
  if (value === undefined) return null;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`--${key} must be a positive integer.`);
  }
  return parsed;
}

function optionalString(
  args: Map<string, string>,
  key: string,
): string | undefined {
  const value = args.get(key)?.trim();
  return value || undefined;
}

function optionalBoolean(
  args: Map<string, string>,
  key: string,
  fallback: boolean,
): boolean {
  const value = args.get(key);
  if (value === undefined) return fallback;
  if (["true", "1", "yes"].includes(value.toLowerCase())) return true;
  if (["false", "0", "no"].includes(value.toLowerCase())) return false;
  throw new Error(`--${key} must be true or false.`);
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});
