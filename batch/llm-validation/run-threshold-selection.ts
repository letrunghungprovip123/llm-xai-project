import type { JsonObject } from "../../src/types/llm-validation";
import type {
  ConfigurationCandidate,
  PairedQualityObservation,
} from "../../src/types/validation-selection";
import {
  readJsonlStrict,
  writeJsonAtomic,
} from "../../src/server/llmValidation/canonicalization/io";
import { assertFrozenSelectionPolicy } from "../../src/server/llmValidation/selection/selectionPolicy";
import { runThresholdSelection } from "../../src/server/llmValidation/selection/thresholdSelection";

// CLI này chỉ chạy khi Phase 7-8 đã tạo candidate và paired observations đầy đủ.
async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  assertFrozenSelectionPolicy();
  const candidateInput = await readJsonlStrict<JsonObject>(
    required(args, "candidates"),
  );
  const observationInput = await readJsonlStrict<JsonObject>(
    required(args, "observations"),
  );
  const candidates = candidateInput.records.map(
    (item) => item.value as unknown as ConfigurationCandidate,
  );
  const observations = observationInput.records.map(
    (item) => item.value as unknown as PairedQualityObservation,
  );
  const result = runThresholdSelection(candidates, observations);
  const output = required(args, "output");
  await writeJsonAtomic(output, result);

  console.log("Threshold selection completed.");
  console.log(`Status: ${result.decision.status}`);
  console.log(`Selected: ${result.decision.selected_candidate_id ?? "none"}`);
  console.log(`S5 fallback: ${result.decision.s5_fallback_candidate_id ?? "none"}`);
  console.log(`Output: ${output}`);
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

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});

