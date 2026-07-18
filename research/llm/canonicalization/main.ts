import { buildGenerationIndex } from "./buildGenerationIndex";
import type { ModelSource } from "../../../contracts/llm-validation";

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));

  const mainSources: ModelSource[] = [
    source(args, "qwen", "qwen3_8b", false, true),
    source(args, "deepseek", "deepseek_v4_flash", false, true),
    source(args, "phi", "phi4_mini_instruct", false, true),
  ];

  const templateGenerations = optional(args, "template-generations");
  const templatePrompts = optional(args, "template-prompts");
  if (Boolean(templateGenerations) !== Boolean(templatePrompts)) {
    throw new Error(
      "--template-generations and --template-prompts must be supplied together.",
    );
  }

  const baselineSource: ModelSource | undefined =
    templateGenerations && templatePrompts
      ? {
          model_id: "template_baseline",
          generations_path: templateGenerations,
          prompts_path: templatePrompts,
          manifest_path: optional(args, "template-manifest"),
          is_baseline: true,
          eligible_for_selection: false,
        }
      : undefined;

  const manifest = await buildGenerationIndex({
    evidence_path: required(args, "evidence"),
    selected_cases_path: optional(args, "selected-cases"),
    selection_manifest_path: optional(args, "selection-manifest"),
    feature_registry_path: optional(args, "feature-registry"),
    main_sources: mainSources,
    baseline_source: baselineSource,
    output_dir: required(args, "out-dir"),
    strict_official_counts: parseBoolean(
      optional(args, "strict-official-counts") ?? "true",
    ),
  });

  const counts = manifest.counts as Record<string, unknown>;
  console.log("Canonical generation index completed.");
  console.log(`Status: ${manifest.status}`);
  console.log(`Main rows: ${counts.main_actual}`);
  console.log(`Main usable: ${counts.main_usable}`);
  console.log(`Main unusable: ${counts.main_unusable}`);
  console.log(`Template baseline rows: ${counts.template_baseline_actual}`);
}

function source(
  args: Map<string, string>,
  prefix: string,
  modelId: string,
  isBaseline: boolean,
  eligibleForSelection: boolean,
): ModelSource {
  return {
    model_id: modelId,
    generations_path: required(args, `${prefix}-generations`),
    prompts_path: required(args, `${prefix}-prompts`),
    manifest_path: optional(args, `${prefix}-manifest`),
    is_baseline: isBaseline,
    eligible_for_selection: eligibleForSelection,
  };
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
    if (result.has(key)) throw new Error(`Duplicate argument: --${key}.`);
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

function parseBoolean(value: string): boolean {
  if (["true", "1", "yes"].includes(value.toLowerCase())) return true;
  if (["false", "0", "no"].includes(value.toLowerCase())) return false;
  throw new Error(`Invalid boolean value: ${value}.`);
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});
