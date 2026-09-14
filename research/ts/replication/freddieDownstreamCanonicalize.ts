import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";

import { buildGenerationIndex } from "../canonicalization/buildGenerationIndex";
import type { ModelSource } from "../../../contracts/llm-validation";

type SourceConfig = {
  model_id: "qwen3_8b" | "deepseek_v4_flash" | "phi4_mini_instruct";
  run_id: string;
  aws_job_id?: string;
  source_uri: string;
  model_revision: string;
  expected_records: number;
  expected_usable: number;
  generations_file: string;
  prompts_file: string;
  source_manifest_file: string;
};

type FreddieDownstreamConfig = {
  schema_version: "freddie_downstream_replication_v1";
  dataset_id: "freddie_sflld_2024";
  experiment_id: string;
  protocol_id: string;
  protocol_sha256: string;
  evidence_sha256: string;
  evidence_path: string;
  frozen_source_root: string;
  canonical_output_dir: string;
  contract_output: string;
  claim_root: string;
  finalization_root: string;
  expected: {
    cases: number;
    evidence_packages: number;
    models: number;
    evidence_levels: string[];
    planned_generations: number;
    runtime_success: number;
    usable_generations: number;
    unusable_generations: number;
  };
  sources: SourceConfig[];
};

type CanonicalRow = {
  canonical_key: string;
  generation_id: string;
  model_id: string;
  model_revision: string | null;
  case_id: string | null;
  source_ir_id: string;
  evidence_level: string;
  repeat_id: number;
  usable: boolean;
  runtime_status: string | null;
  input_package_hash_verified: boolean;
  prompt_hash_verified: boolean;
};

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(readOptional(args, "repo-root") ?? process.cwd());
  const configPath = resolveRepo(repoRoot, required(args, "config"));
  const configRaw = await fs.readFile(configPath, "utf8");
  const config = parseConfig(JSON.parse(configRaw) as unknown);

  const evidencePath = resolveRepo(repoRoot, config.evidence_path);
  const evidenceHash = sha256Bytes(await fs.readFile(evidencePath));
  requireEqual(evidenceHash, config.evidence_sha256, "frozen evidence SHA-256");

  const outputDir = resolveRepo(repoRoot, config.canonical_output_dir);
  await assertFreshOutputDirectory(outputDir);

  const frozenRoot = resolveRepo(repoRoot, config.frozen_source_root);
  const mainSources: ModelSource[] = config.sources.map((source) => ({
    model_id: source.model_id,
    generations_path: path.resolve(frozenRoot, source.generations_file),
    prompts_path: path.resolve(frozenRoot, source.prompts_file),
    manifest_path: path.resolve(frozenRoot, source.source_manifest_file),
    is_baseline: false,
    eligible_for_selection: true,
  }));

  await buildGenerationIndex({
    evidence_path: evidencePath,
    main_sources: mainSources,
    output_dir: outputDir,
    strict_official_counts: false,
  });

  const generationIndex = path.join(outputDir, "generation_index.jsonl");
  const evidenceCopy = path.join(outputDir, "evidence_packages_36.jsonl");
  const rows = await readJsonl<CanonicalRow>(generationIndex);
  const evidenceRows = await readJsonl<Record<string, unknown>>(evidenceCopy);

  const acceptance = buildAcceptance(rows, evidenceRows, config, configPath, configRaw);
  const acceptancePath = path.join(outputDir, "freddie_downstream_acceptance.json");
  await fs.writeFile(acceptancePath, `${JSON.stringify(acceptance, null, 2)}\n`, "utf8");

  console.log("FREDDIE_CANONICALIZATION=PASS");
  console.log(`CANONICAL_ROWS=${rows.length}`);
  console.log(`USABLE=${rows.filter((row) => row.usable).length}`);
  console.log(`UNUSABLE=${rows.filter((row) => !row.usable).length}`);
  console.log(`EVIDENCE_PACKAGES=${evidenceRows.length}`);
  console.log(`OUTPUT_DIR=${outputDir}`);
  console.log(`ACCEPTANCE=${acceptancePath}`);
}

function buildAcceptance(
  rows: CanonicalRow[],
  evidenceRows: Record<string, unknown>[],
  config: FreddieDownstreamConfig,
  configPath: string,
  configRaw: string,
): Record<string, unknown> {
  requireEqual(rows.length, config.expected.planned_generations, "canonical row count");
  requireEqual(evidenceRows.length, config.expected.evidence_packages, "evidence package count");

  const uniqueKeys = new Set(rows.map((row) => row.canonical_key));
  const uniqueGenerationIds = new Set(rows.map((row) => row.generation_id));
  const uniqueSourceIrIds = new Set(rows.map((row) => row.source_ir_id));
  const uniqueCaseIds = new Set(rows.map((row) => row.case_id).filter((value): value is string => Boolean(value)));

  requireEqual(uniqueKeys.size, config.expected.planned_generations, "unique canonical keys");
  requireEqual(uniqueGenerationIds.size, config.expected.planned_generations, "unique generation ids");
  requireEqual(uniqueSourceIrIds.size, config.expected.cases, "distinct source_ir_id");
  requireEqual(uniqueCaseIds.size, config.expected.cases, "distinct case_id");

  const usable = rows.filter((row) => row.usable).length;
  const unusable = rows.length - usable;
  const runtimeSuccess = rows.filter((row) => row.runtime_status === "SUCCESS").length;
  requireEqual(usable, config.expected.usable_generations, "usable generations");
  requireEqual(unusable, config.expected.unusable_generations, "unusable generations");
  requireEqual(runtimeSuccess, config.expected.runtime_success, "runtime success count");

  const packageHashMismatch = rows.filter((row) => !row.input_package_hash_verified).length;
  const promptHashMismatch = rows.filter((row) => !row.prompt_hash_verified).length;
  requireEqual(packageHashMismatch, 0, "input package hash mismatches");
  requireEqual(promptHashMismatch, 0, "prompt hash mismatches");

  const byModel: Record<string, unknown> = {};
  for (const source of config.sources) {
    const modelRows = rows.filter((row) => row.model_id === source.model_id);
    requireEqual(modelRows.length, source.expected_records, `${source.model_id} records`);
    requireEqual(modelRows.filter((row) => row.usable).length, source.expected_usable, `${source.model_id} usable`);

    const revisions = [...new Set(modelRows.map((row) => row.model_revision))];
    requireEqual(revisions.length, 1, `${source.model_id} revision cardinality`);
    requireEqual(revisions[0], source.model_revision, `${source.model_id} revision`);

    const levelCounts = Object.fromEntries(
      config.expected.evidence_levels.map((level) => [
        level,
        modelRows.filter((row) => row.evidence_level === level).length,
      ]),
    );
    for (const level of config.expected.evidence_levels) {
      requireEqual(levelCounts[level], config.expected.cases, `${source.model_id}/${level} rows`);
    }
    byModel[source.model_id] = {
      actual: modelRows.length,
      usable: modelRows.filter((row) => row.usable).length,
      unusable: modelRows.filter((row) => !row.usable).length,
      revision: revisions[0],
      levels: levelCounts,
    };
  }

  const expectedModels = new Set(config.sources.map((source) => source.model_id));
  const observedModels = new Set(rows.map((row) => row.model_id));
  requireSetEqual(observedModels, expectedModels, "model set");

  const overallLevels = Object.fromEntries(
    config.expected.evidence_levels.map((level) => [
      level,
      rows.filter((row) => row.evidence_level === level).length,
    ]),
  );
  for (const level of config.expected.evidence_levels) {
    requireEqual(overallLevels[level], config.expected.cases * config.expected.models, `overall ${level} rows`);
  }

  return {
    schema_version: "freddie_downstream_acceptance_v1",
    status: "PASS",
    dataset_id: config.dataset_id,
    experiment_id: config.experiment_id,
    protocol_id: config.protocol_id,
    protocol_sha256: config.protocol_sha256,
    config_path: configPath,
    config_sha256: sha256(configRaw),
    observed: {
      canonical_rows: rows.length,
      unique_canonical_keys: uniqueKeys.size,
      unique_generation_ids: uniqueGenerationIds.size,
      distinct_source_ir_ids: uniqueSourceIrIds.size,
      distinct_case_ids: uniqueCaseIds.size,
      runtime_success: runtimeSuccess,
      usable,
      unusable,
      evidence_packages: evidenceRows.length,
      evidence_sha256: config.evidence_sha256,
      input_package_hash_mismatch: packageHashMismatch,
      prompt_hash_mismatch: promptHashMismatch,
      levels: overallLevels,
      by_model: byModel,
    },
    policy: {
      strict_official_counts: false,
      historical_home_credit_usability_counts_enforced: false,
      structural_matrix_counts_enforced: true,
      unusable_rows_preserved: true,
    },
  };
}

function parseConfig(value: unknown): FreddieDownstreamConfig {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Freddie downstream config must be an object.");
  }
  const config = value as Partial<FreddieDownstreamConfig>;
  if (config.schema_version !== "freddie_downstream_replication_v1") {
    throw new Error(`Unexpected config schema: ${String(config.schema_version)}`);
  }
  if (config.dataset_id !== "freddie_sflld_2024") {
    throw new Error(`Unexpected dataset_id: ${String(config.dataset_id)}`);
  }
  if (!Array.isArray(config.sources) || config.sources.length !== 3) {
    throw new Error("Exactly three Freddie main-model sources are required.");
  }
  const modelIds = config.sources.map((source) => source.model_id);
  const expectedOrder = ["qwen3_8b", "deepseek_v4_flash", "phi4_mini_instruct"];
  if (modelIds.join("|") !== expectedOrder.join("|")) {
    throw new Error(`Unexpected model source order: ${modelIds.join(",")}`);
  }
  if (!config.expected || config.expected.planned_generations !== 648) {
    throw new Error("Freddie replication config must preserve the 648-cell main matrix.");
  }
  return config as FreddieDownstreamConfig;
}

async function readJsonl<T>(filePath: string): Promise<T[]> {
  const text = await fs.readFile(filePath, "utf8");
  return text.split(/\r?\n/u).map((line) => line.trim()).filter(Boolean).map((line, index) => {
    try {
      return JSON.parse(line) as T;
    } catch (error) {
      throw new Error(`Invalid JSONL at ${filePath}:${index + 1}: ${error instanceof Error ? error.message : String(error)}`);
    }
  });
}

async function assertFreshOutputDirectory(outputDir: string): Promise<void> {
  try {
    const entries = await fs.readdir(outputDir);
    if (entries.length > 0) {
      throw new Error(`Refusing to overwrite non-empty canonical output directory: ${outputDir}`);
    }
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error
      ? String((error as { code?: unknown }).code)
      : "";
    if (code !== "ENOENT") throw error;
  }
}

function requireEqual(actual: unknown, expected: unknown, label: string): void {
  if (actual !== expected) throw new Error(`${label}: expected ${String(expected)}, got ${String(actual)}.`);
}

function requireSetEqual(actual: Set<string>, expected: Set<string>, label: string): void {
  const left = [...actual].sort();
  const right = [...expected].sort();
  if (left.join("|") !== right.join("|")) {
    throw new Error(`${label}: expected [${right.join(",")}], got [${left.join(",")}].`);
  }
}

function resolveRepo(repoRoot: string, value: string): string {
  return path.isAbsolute(value) ? value : path.resolve(repoRoot, value);
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

function readOptional(args: Map<string, string>, key: string): string | undefined {
  const value = args.get(key)?.trim();
  return value || undefined;
}

function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function sha256Bytes(value: Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
});
