import { createHash } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import type { GenerationRecord, PromptInstanceRecord } from "../../../contracts/narrative";
import { isGenerationUsable } from "../narrative/index";
import { listFilesRecursive } from "../narrative/artifacts";
import { REPLICATION_PROTOCOL, replicationProtocolSha256 } from "./protocol";
import type { GenerationPlanJob, PlannedPrompt } from "./generationPlan";

export type M17AGenerationSummary = {
  schema_version: "freddie_m17a_generation_summary_v1";
  dataset_id: "freddie_sflld_2024";
  stage: "freddie_llm_generation_m17a";
  protocol_sha256: string;
  planned: 648;
  attempted_terminal: number;
  provider_success: number;
  raw_output_valid: number;
  usable: number;
  unusable: number;
  per_model: Record<string, {
    planned: 216;
    provider_success: number;
    raw_output_valid: number;
    usable: number;
    unusable: number;
  }>;
  historical_home_credit_reference: {
    planned: number;
    usable: number;
    unusable: number;
    note: string;
  };
  status: "PASS";
};

export async function certifyFreddieM17A(options: {
  workspace: string;
  planDir?: string;
  generationDir?: string;
}): Promise<{ receiptPath: string; summaryPath: string; planned: number; providerSuccess: number; usable: number; unusable: number }> {
  const workspace = path.resolve(options.workspace);
  const planDir = path.resolve(options.planDir ?? path.join(workspace, "data/reports/llm_narratives/m17a_plan"));
  const generationDir = path.resolve(options.generationDir ?? path.join(workspace, "data/reports/llm_narratives/m17a_generations"));
  const jobsPath = path.join(planDir, "generation_jobs_v1.jsonl");
  const plannedPromptsPath = path.join(planDir, "prompt_instances_planned_v1.jsonl");
  const planManifestPath = path.join(planDir, "generation_plan_manifest_v1.json");
  const jobs = await readJsonl<GenerationPlanJob>(jobsPath);
  const plannedPrompts = await readJsonl<PlannedPrompt>(plannedPromptsPath);
  if (jobs.length !== 648 || plannedPrompts.length !== 648) throw new Error("M17A plan must contain exact 648 jobs/prompts.");
  if (new Set(jobs.map((job) => job.protocol_sha256)).size !== 1 || jobs[0]?.protocol_sha256 !== replicationProtocolSha256()) {
    throw new Error("Frozen generation plan protocol hash differs from current replication protocol.");
  }
  const jobByCell = new Map(jobs.map((job) => [cellKey(job.model_id, job.source_ir_id, job.evidence_level), job]));
  const promptByCell = new Map(plannedPrompts.map((item) => [cellKey(item.model_id, item.source_ir_id, item.evidence_level), item]));

  const generationFiles = (await listFilesRecursive(generationDir, "generations.jsonl")).sort();
  const promptFiles = (await listFilesRecursive(generationDir, "prompt_instances.jsonl")).sort();
  const generations = (await Promise.all(generationFiles.map(readJsonl<GenerationRecord>))).flat();
  const prompts = (await Promise.all(promptFiles.map(readJsonl<PromptInstanceRecord>))).flat();
  if (generations.length !== 648) throw new Error(`Expected 648 terminal generation records, found ${generations.length}. Resume execution before certification.`);
  if (prompts.length !== 648) throw new Error(`Expected 648 prompt records, found ${prompts.length}.`);

  const seenGenerationIds = new Set<string>();
  const seenCells = new Set<string>();
  for (const generation of generations) {
    if (seenGenerationIds.has(generation.generation_id)) throw new Error(`Duplicate generation_id ${generation.generation_id}.`);
    seenGenerationIds.add(generation.generation_id);
    const key = cellKey(generation.model_id, generation.source_ir_id, generation.evidence_level);
    if (seenCells.has(key)) throw new Error(`Duplicate generation cell ${key}.`);
    seenCells.add(key);
    const job = jobByCell.get(key);
    if (!job) throw new Error(`Generated cell outside frozen plan: ${key}.`);
    if (generation.package_id !== job.package_id) throw new Error(`Package mismatch at ${key}.`);
    if (generation.input_package_sha256 !== job.evidence_package_sha256) throw new Error(`Evidence hash mismatch at ${key}.`);
    if (generation.prompt_message_sha256 !== job.prompt_message_sha256) throw new Error(`Prompt hash mismatch at ${key}.`);
    if (generation.repeat_id !== 1) throw new Error(`Unexpected repeat_id at ${key}.`);
    if (generation.experiment_stage !== "evaluation") throw new Error(`Unexpected experiment_stage at ${key}.`);
  }

  const seenPromptCells = new Set<string>();
  for (const prompt of prompts) {
    const key = cellKey(prompt.model_id, prompt.source_ir_id, prompt.evidence_level);
    if (seenPromptCells.has(key)) throw new Error(`Duplicate prompt cell ${key}.`);
    seenPromptCells.add(key);
    const planned = promptByCell.get(key);
    if (!planned || prompt.message_sha256 !== planned.message_sha256 || prompt.prompt_id !== planned.prompt_id) throw new Error(`Executed prompt differs from frozen plan at ${key}.`);
  }
  if (seenCells.size !== jobByCell.size || seenPromptCells.size !== promptByCell.size) throw new Error("Executed matrix does not cover frozen 648-cell plan.");

  const providerSuccess = generations.filter((item) => item.runtime_metrics.status === "SUCCESS").length;
  const rawOutputValid = generations.filter((item) => item.schema_metrics.raw_json_parse_success && item.schema_metrics.schema_valid).length;
  const usable = generations.filter(isGenerationUsable).length;
  const unusable = generations.length - usable;
  const perModel = Object.fromEntries(REPLICATION_PROTOCOL.generation.models.map((model) => {
    const rows = generations.filter((row) => row.model_id === model.model_id);
    if (rows.length !== 216) throw new Error(`${model.model_id} must have 216 generation rows; found ${rows.length}.`);
    return [model.model_id, {
      planned: 216 as const,
      provider_success: rows.filter((row) => row.runtime_metrics.status === "SUCCESS").length,
      raw_output_valid: rows.filter((row) => row.schema_metrics.raw_json_parse_success && row.schema_metrics.schema_valid).length,
      usable: rows.filter(isGenerationUsable).length,
      unusable: rows.filter((row) => !isGenerationUsable(row)).length,
    }];
  }));

  const summary: M17AGenerationSummary = {
    schema_version: "freddie_m17a_generation_summary_v1",
    dataset_id: "freddie_sflld_2024",
    stage: "freddie_llm_generation_m17a",
    protocol_sha256: replicationProtocolSha256(),
    planned: 648,
    attempted_terminal: generations.length,
    provider_success: providerSuccess,
    raw_output_valid: rawOutputValid,
    usable,
    unusable,
    per_model: perModel,
    historical_home_credit_reference: {
      planned: REPLICATION_PROTOCOL.source_experiment.historical_planned_generations,
      usable: REPLICATION_PROTOCOL.source_experiment.historical_usable_generations,
      unusable: REPLICATION_PROTOCOL.source_experiment.historical_unusable_generations,
      note: "Reference evidence only. Freddie usable counts are observed and are never forced to Home Credit counts.",
    },
    status: "PASS",
  };

  const manifestDir = path.join(workspace, "data/manifests");
  const summaryPath = path.join(manifestDir, "freddie_sflld_2024_m17a_generation_summary_v1.json");
  await mkdir(manifestDir, { recursive: true });
  await writeJsonAtomic(summaryPath, summary);

  const outputFingerprints: Record<string, string> = {
    [relativeToWorkspace(workspace, summaryPath)]: await sha256File(summaryPath),
  };
  for (const filePath of generationFiles) outputFingerprints[relativeToWorkspace(workspace, filePath)] = await sha256File(filePath);
  for (const filePath of promptFiles) outputFingerprints[relativeToWorkspace(workspace, filePath)] = await sha256File(filePath);

  const receipt = {
    schema_version: "stage_receipt_v1",
    stage: "freddie_llm_generation_m17a",
    stage_version: "v1",
    dataset_id: "freddie_sflld_2024",
    patch_id: "0012",
    input_fingerprints: {
      [relativeToWorkspace(workspace, jobsPath)]: await sha256File(jobsPath),
      [relativeToWorkspace(workspace, plannedPromptsPath)]: await sha256File(plannedPromptsPath),
      [relativeToWorkspace(workspace, planManifestPath)]: await sha256File(planManifestPath),
    },
    config_fingerprints: {
      llm_replication_protocol_v1: replicationProtocolSha256(),
    },
    output_fingerprints: outputFingerprints,
    invariants: {
      exact_648_cells: "PASS",
      exact_36x6x3_matrix: "PASS",
      prompt_plan_parity: "PASS",
      evidence_hash_parity: "PASS",
      unique_generation_ids: "PASS",
      terminal_state_for_every_planned_cell: "PASS",
      home_credit_usable_count_not_enforced_on_freddie: "PASS",
    },
    status: "PASS",
  };
  const receiptPath = path.join(manifestDir, "freddie_sflld_2024_m17a_generation_receipt_v1.json");
  await writeJsonAtomic(receiptPath, receipt);
  return { receiptPath, summaryPath, planned: 648, providerSuccess, usable, unusable };
}

function cellKey(modelId: string, sourceIrId: string, level: string): string {
  return `${modelId}::${sourceIrId}::${level}`;
}

function relativeToWorkspace(workspace: string, filePath: string): string {
  const relative = path.relative(workspace, filePath);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error(`Artifact must remain inside workspace: ${filePath}`);
  return relative.split(path.sep).join("/");
}

async function readJsonl<T>(filePath: string): Promise<T[]> {
  const text = await readFile(filePath, "utf8");
  return text.split(/\r?\n/u).filter((line) => line.trim()).map((line) => JSON.parse(line) as T);
}

async function sha256File(filePath: string): Promise<string> {
  const content = await readFile(filePath);
  return createHash("sha256").update(content).digest("hex");
}

async function writeJsonAtomic(filePath: string, value: unknown): Promise<void> {
  const temp = `${filePath}.tmp`;
  await writeFile(temp, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(temp, filePath);
}
