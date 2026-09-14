import { filterDeepSeekEvaluation36 } from "./filterDeepSeek";

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const manifest = await filterDeepSeekEvaluation36({
    generations_path: required(args, "generations"),
    prompts_path: required(args, "prompts"),
    evidence_path: required(args, "evidence"),
    output_dir: required(args, "out-dir"),
    expected_model_id: optional(args, "model-id") ?? "deepseek_v4_flash",
  });

  const counts = manifest.counts as Record<string, unknown>;
  console.log("DeepSeek evaluation-cohort filtering completed.");
  console.log(`Selected generations: ${counts.selected_generation_count}`);
  console.log(`Usable generations: ${counts.usable_generation_count}`);
  console.log(`Unusable generations: ${counts.unusable_generation_count}`);
}

function parseArgs(values: string[]): Map<string, string> {
  const result = new Map<string, string>();
  for (let index = 0; index < values.length; index += 1) {
    const current = values[index];
    if (!current.startsWith("--")) {
      throw new Error(`Unexpected argument: ${current}`);
    }

    const key = current.slice(2);
    const value = values[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`Missing value for --${key}.`);
    }
    if (result.has(key)) {
      throw new Error(`Duplicate argument: --${key}.`);
    }
    result.set(key, value);
    index += 1;
  }
  return result;
}

function required(args: Map<string, string>, key: string): string {
  const value = args.get(key)?.trim();
  if (!value) throw new Error(`Missing required argument: --${key}.`);
  return value;
}

function optional(args: Map<string, string>, key: string): string | undefined {
  const value = args.get(key)?.trim();
  return value || undefined;
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});
