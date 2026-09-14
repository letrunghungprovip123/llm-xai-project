import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { EvidenceLevel, RunOptions } from "../../../contracts/narrative";
import {
  buildPrompt,
  getModelConfig,
  runNarrativePipeline,
} from "../narrative/index";
import { loadEvidencePackages } from "../narrative/loaders";
import {
  REPLICATION_PROTOCOL,
  assertReplicationProtocolMatchesCommonRuntime,
  replicationProtocolSha256,
} from "./protocol";
import type { GenerationPlanJob, PlannedPrompt } from "./generationPlan";

export type FreddieGenerationPreflight = {
  workspace: string;
  planDir: string;
  outputDir: string;
  evidencePath: string;
  modelId: string;
  plannedCells: number;
  promptParityCells: number;
};

/**
 * Refuse provider execution when the frozen M17A plan has drifted from the
 * current common prompt/runtime code.  This runs before any LLM call.
 */
export async function preflightFreddieGenerationModel(options: {
  workspace: string;
  modelId: string;
  outputDir?: string;
  planDir?: string;
}): Promise<FreddieGenerationPreflight> {
  assertReplicationProtocolMatchesCommonRuntime();
  const workspace = path.resolve(options.workspace);
  const planDir = ensureInsideWorkspace(
    workspace,
    path.resolve(
      options.planDir
        ?? path.join(workspace, "data/reports/llm_narratives/m17a_plan"),
    ),
    "planDir",
  );
  const outputDir = ensureInsideWorkspace(
    workspace,
    path.resolve(
      options.outputDir
        ?? path.join(workspace, "data/reports/llm_narratives/m17a_generations"),
    ),
    "outputDir",
  );

  const modelSpec = REPLICATION_PROTOCOL.generation.models.find(
    (item) => item.model_id === options.modelId,
  );
  if (!modelSpec) {
    throw new Error(`Model ${options.modelId} is outside frozen replication protocol.`);
  }
  const model = getModelConfig(modelSpec.model_id);

  const manifestPath = path.join(planDir, "generation_plan_manifest_v1.json");
  const jobsPath = path.join(planDir, "generation_jobs_v1.jsonl");
  const promptsPath = path.join(planDir, "prompt_instances_planned_v1.jsonl");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as Record<string, unknown>;
  if (
    manifest.status !== "PASS"
    || Number((manifest.matrix as Record<string, unknown>)?.planned_generations) !== 648
  ) {
    throw new Error("M17A generation plan is not certified PASS.");
  }
  if (String(manifest.protocol_sha256 ?? "") !== replicationProtocolSha256()) {
    throw new Error("M17A generation plan protocol hash differs from current frozen protocol.");
  }

  await assertDescriptorHash(manifest.jobs, jobsPath, "generation_jobs_v1");
  await assertDescriptorHash(manifest.prompts, promptsPath, "prompt_instances_planned_v1");

  const evidencePath = path.resolve(String(manifest.evidence_path ?? ""));
  if (!evidencePath) throw new Error("Generation plan is missing evidence_path.");
  const expectedEvidenceHash = String(manifest.evidence_sha256 ?? "");
  if (await sha256File(evidencePath) !== expectedEvidenceHash) {
    throw new Error("M16 evidence hash changed after generation plan freeze.");
  }

  const packages = await loadEvidencePackages(evidencePath);
  const jobs = await readJsonl<GenerationPlanJob>(jobsPath);
  const plannedPrompts = await readJsonl<PlannedPrompt>(promptsPath);
  const modelJobs = jobs.filter((item) => item.model_id === options.modelId);
  const modelPrompts = plannedPrompts.filter((item) => item.model_id === options.modelId);
  if (modelJobs.length !== 216 || modelPrompts.length !== 216) {
    throw new Error(
      `${options.modelId} frozen plan must contain 216 jobs/prompts; found ${modelJobs.length}/${modelPrompts.length}.`,
    );
  }

  const promptByPackage = new Map(
    modelPrompts.map((item) => [item.package_id, item]),
  );
  const jobByPackage = new Map(modelJobs.map((item) => [item.package_id, item]));
  if (promptByPackage.size !== 216 || jobByPackage.size !== 216) {
    throw new Error(`${options.modelId} frozen plan contains duplicate package cells.`);
  }

  let promptParityCells = 0;
  for (const packageItem of packages) {
    const planned = promptByPackage.get(packageItem.package_id);
    const job = jobByPackage.get(packageItem.package_id);
    if (!planned || !job) {
      throw new Error(`${options.modelId} frozen plan is missing ${packageItem.package_id}.`);
    }
    const rebuilt = buildPrompt(
      packageItem,
      model,
      REPLICATION_PROTOCOL.generation.prompt_version,
    );
    if (
      rebuilt.prompt_id !== planned.prompt_id
      || rebuilt.message_sha256 !== planned.message_sha256
      || rebuilt.message_sha256 !== job.prompt_message_sha256
    ) {
      throw new Error(
        `Prompt drift detected before provider execution for ${options.modelId}/${packageItem.package_id}.`,
      );
    }
    promptParityCells += 1;
  }
  if (promptParityCells !== 216) {
    throw new Error(`Expected 216 prompt parity cells for ${options.modelId}, found ${promptParityCells}.`);
  }

  return {
    workspace,
    planDir,
    outputDir,
    evidencePath,
    modelId: options.modelId,
    plannedCells: modelJobs.length,
    promptParityCells,
  };
}

export async function runFreddieGenerationModel(options: {
  workspace: string;
  modelId: string;
  outputDir?: string;
  planDir?: string;
  runId?: string;
  concurrency?: number;
  resume?: boolean;
}): Promise<Awaited<ReturnType<typeof runNarrativePipeline>>> {
  const preflight = await preflightFreddieGenerationModel(options);
  const runOptions: RunOptions = {
    input_path: preflight.evidencePath,
    output_dir: preflight.outputDir,
    run_id: options.runId ?? `freddie_m17a_${options.modelId}_v1`,
    model_ids: [options.modelId],
    levels: [...REPLICATION_PROTOCOL.generation.evidence_levels] as EvidenceLevel[],
    repeat_ids: [1],
    decoding: { ...REPLICATION_PROTOCOL.generation.decoding },
    prompt_version: REPLICATION_PROTOCOL.generation.prompt_version,
    output_schema_version: REPLICATION_PROTOCOL.generation.output_schema_version,
    experiment_stage: "evaluation",
    chunk_start: 0,
    concurrency:
      options.concurrency
      ?? REPLICATION_PROTOCOL.generation.execution.default_concurrency,
    checkpoint_every:
      REPLICATION_PROTOCOL.generation.execution.checkpoint_every,
    timeout_ms: REPLICATION_PROTOCOL.generation.execution.timeout_ms,
    max_retries: REPLICATION_PROTOCOL.generation.execution.max_retries,
    retry_delay_ms: REPLICATION_PROTOCOL.generation.execution.retry_delay_ms,
    base_seed: REPLICATION_PROTOCOL.generation.execution.base_seed,
    resume: options.resume ?? true,
  };
  return runNarrativePipeline(runOptions);
}

function ensureInsideWorkspace(
  workspace: string,
  candidate: string,
  label: string,
): string {
  const relative = path.relative(workspace, candidate);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    if (candidate === workspace) {
      throw new Error(`${label} must be a child directory of the Freddie workspace.`);
    }
    throw new Error(`${label} must remain inside the Freddie workspace: ${candidate}`);
  }
  return candidate;
}

async function assertDescriptorHash(
  value: unknown,
  expectedPath: string,
  label: string,
): Promise<void> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Generation plan is missing ${label} descriptor.`);
  }
  const descriptor = value as Record<string, unknown>;
  if (path.resolve(String(descriptor.path ?? "")) !== path.resolve(expectedPath)) {
    throw new Error(`${label} path differs from frozen generation plan.`);
  }
  if (String(descriptor.sha256 ?? "") !== await sha256File(expectedPath)) {
    throw new Error(`${label} hash differs from frozen generation plan.`);
  }
}

async function readJsonl<T>(filePath: string): Promise<T[]> {
  const text = await readFile(filePath, "utf8");
  return text
    .split(/\r?\n/u)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as T);
}

async function sha256File(filePath: string): Promise<string> {
  const content = await readFile(filePath);
  return createHash("sha256").update(content).digest("hex");
}
