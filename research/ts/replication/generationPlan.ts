import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { EvidencePackage, EvidenceLevel } from "../../../contracts/narrative";
import { buildPrompt, getModelConfig } from "../narrative/index";
import { loadEvidencePackages } from "../narrative/loaders";
import { sha256, stableStringify } from "../common/utils";
import {
  REPLICATION_PROTOCOL,
  assertReplicationProtocolMatchesCommonRuntime,
  replicationProtocolSha256,
} from "./protocol";

export type GenerationPlanJob = {
  schema_version: "replication_generation_job_v1";
  job_id: string;
  dataset_id: string;
  dataset_fingerprint: string;
  experiment_id: string;
  case_id: string;
  source_ir_id: string;
  stratum: string | null;
  evidence_level: EvidenceLevel;
  package_id: string;
  evidence_package_sha256: string;
  model_id: string;
  remote_model_id: string;
  repeat_id: 1;
  prompt_id: string;
  prompt_message_sha256: string;
  generation_config_sha256: string;
  protocol_sha256: string;
  status: "PLANNED";
};

export type PlannedPrompt = {
  schema_version: "replication_planned_prompt_v1";
  job_id: string;
  prompt_id: string;
  model_id: string;
  package_id: string;
  source_ir_id: string;
  evidence_level: EvidenceLevel;
  message_sha256: string;
  messages: Array<{ role: "system" | "user"; content: string }>;
};

export type GenerationPlanResult = {
  planDir: string;
  jobsPath: string;
  promptsPath: string;
  manifestPath: string;
  jobCount: number;
  caseCount: number;
  protocolSha256: string;
};

const EXPECTED_DATASET = "freddie_sflld_2024";
const HOME_CREDIT_LEAK_PATTERNS = [
  /home[ _-]?credit/iu,
  /home_credit_default_risk/iu,
  /SK_ID_CURR/u,
  /customer_id/iu,
  /AMT_INCOME_TOTAL/u,
  /EXT_SOURCE_[123]/u,
  /high_default_risk/iu,
  /low_default_risk/iu,
  /khách hàng sẽ gặp khó khăn trả nợ/iu,
];

export async function buildFreddieGenerationPlan(options: {
  workspace: string;
  evidencePath?: string;
  m16ReceiptPath?: string;
  outputDir?: string;
  experimentId?: string;
}): Promise<GenerationPlanResult> {
  assertReplicationProtocolMatchesCommonRuntime();
  const workspace = path.resolve(options.workspace);
  const evidencePath = path.resolve(options.evidencePath ?? path.join(
    workspace,
    "data/reports/evidence_exposure/evaluation_36/evidence_packages_36.jsonl",
  ));
  const m16ReceiptPath = path.resolve(options.m16ReceiptPath ?? path.join(
    workspace,
    "data/manifests/freddie_sflld_2024_m16_evaluation_cohort_receipt_v1.json",
  ));
  const outputDir = path.resolve(options.outputDir ?? path.join(
    workspace,
    "data/reports/llm_narratives/m17a_plan",
  ));
  const experimentId = options.experimentId ?? "freddie_sflld_2024_replication_v1";

  const receipt = JSON.parse(await readFile(m16ReceiptPath, "utf8")) as Record<string, unknown>;
  await assertM16Receipt(receipt, workspace, evidencePath);
  const packages = await loadEvidencePackages(evidencePath);
  const matrix = validateEvidenceMatrix(packages);
  const datasetFingerprint = matrix.datasetFingerprint;
  const protocolSha = replicationProtocolSha256();
  const generationConfigSha = sha256(stableStringify({
    decoding: REPLICATION_PROTOCOL.generation.decoding,
    execution: REPLICATION_PROTOCOL.generation.execution,
    repeat_ids: REPLICATION_PROTOCOL.generation.repeat_ids,
    prompt_version: REPLICATION_PROTOCOL.generation.prompt_version,
    output_schema_version: REPLICATION_PROTOCOL.generation.output_schema_version,
  }));

  const jobs: GenerationPlanJob[] = [];
  const prompts: PlannedPrompt[] = [];
  for (const modelSpec of REPLICATION_PROTOCOL.generation.models) {
    const model = getModelConfig(modelSpec.model_id);
    for (const packageItem of packages) {
      const prompt = buildPrompt(packageItem, model, REPLICATION_PROTOCOL.generation.prompt_version);
      assertPromptHasNoHomeCreditLeak(prompt.message_text, packageItem.package_id);
      const caseId = getCaseId(packageItem);
      const packageSha = sha256(stableStringify(packageItem));
      const jobId = `job_${sha256(stableStringify({
        dataset_fingerprint: datasetFingerprint,
        experiment_id: experimentId,
        case_id: caseId,
        evidence_package_sha256: packageSha,
        model_id: model.id,
        remote_model_id: model.remote_model_id,
        repeat_id: 1,
        prompt_message_sha256: prompt.message_sha256,
        generation_config_sha256: generationConfigSha,
        protocol_sha256: protocolSha,
      }))}`;
      jobs.push({
        schema_version: "replication_generation_job_v1",
        job_id: jobId,
        dataset_id: EXPECTED_DATASET,
        dataset_fingerprint: datasetFingerprint,
        experiment_id: experimentId,
        case_id: caseId,
        source_ir_id: packageItem.source_ir_id,
        stratum: getStratum(packageItem),
        evidence_level: packageItem.evidence_level,
        package_id: packageItem.package_id,
        evidence_package_sha256: packageSha,
        model_id: model.id,
        remote_model_id: model.remote_model_id,
        repeat_id: 1,
        prompt_id: prompt.prompt_id,
        prompt_message_sha256: prompt.message_sha256,
        generation_config_sha256: generationConfigSha,
        protocol_sha256: protocolSha,
        status: "PLANNED",
      });
      prompts.push({
        schema_version: "replication_planned_prompt_v1",
        job_id: jobId,
        prompt_id: prompt.prompt_id,
        model_id: model.id,
        package_id: packageItem.package_id,
        source_ir_id: packageItem.source_ir_id,
        evidence_level: packageItem.evidence_level,
        message_sha256: prompt.message_sha256,
        messages: prompt.messages,
      });
    }
  }

  assertUnique(jobs.map((item) => item.job_id), "job_id");
  assertUnique(jobs.map((item) => `${item.model_id}::${item.source_ir_id}::${item.evidence_level}`), "canonical generation cell");
  if (jobs.length !== REPLICATION_PROTOCOL.generation.matrix.planned_generations) {
    throw new Error(`Expected 648 planned jobs, found ${jobs.length}.`);
  }

  await mkdir(outputDir, { recursive: true });
  const jobsPath = path.join(outputDir, "generation_jobs_v1.jsonl");
  const promptsPath = path.join(outputDir, "prompt_instances_planned_v1.jsonl");
  const manifestPath = path.join(outputDir, "generation_plan_manifest_v1.json");
  await writeJsonlAtomic(jobsPath, jobs);
  await writeJsonlAtomic(promptsPath, prompts);
  const manifest = {
    schema_version: "replication_generation_plan_manifest_v1",
    dataset_id: EXPECTED_DATASET,
    dataset_fingerprint: datasetFingerprint,
    experiment_id: experimentId,
    protocol_id: REPLICATION_PROTOCOL.protocol_id,
    protocol_sha256: protocolSha,
    m16_receipt_path: m16ReceiptPath,
    m16_receipt_sha256: await sha256File(m16ReceiptPath),
    evidence_path: evidencePath,
    evidence_sha256: await sha256File(evidencePath),
    matrix: {
      cases: matrix.caseCount,
      evidence_packages: packages.length,
      evidence_levels: REPLICATION_PROTOCOL.generation.evidence_levels,
      models: REPLICATION_PROTOCOL.generation.models.map((item) => item.model_id),
      repeats: REPLICATION_PROTOCOL.generation.repeat_ids,
      planned_generations: jobs.length,
    },
    prompt_leakage_count: 0,
    generation_config_sha256: generationConfigSha,
    jobs: { path: jobsPath, sha256: await sha256File(jobsPath), record_count: jobs.length },
    prompts: { path: promptsPath, sha256: await sha256File(promptsPath), record_count: prompts.length },
    status: "PASS",
  };
  await writeJsonAtomic(manifestPath, manifest);
  return { planDir: outputDir, jobsPath, promptsPath, manifestPath, jobCount: jobs.length, caseCount: matrix.caseCount, protocolSha256: protocolSha };
}

function validateEvidenceMatrix(packages: EvidencePackage[]): { caseCount: number; datasetFingerprint: string } {
  if (packages.length !== 216) throw new Error(`M16 evidence subset must contain 216 packages, found ${packages.length}.`);
  const expectedLevels = REPLICATION_PROTOCOL.generation.evidence_levels;
  const byCase = new Map<string, Set<string>>();
  let datasetFingerprint: string | null = null;
  for (const item of packages) {
    const dataset = item.dataset;
    if (dataset?.dataset_id !== EXPECTED_DATASET) throw new Error(`Unexpected dataset_id in ${item.package_id}: ${String(dataset?.dataset_id)}.`);
    const fingerprint = typeof dataset.dataset_fingerprint === "string" ? dataset.dataset_fingerprint : null;
    if (!fingerprint) throw new Error(`Missing dataset_fingerprint in ${item.package_id}.`);
    if (datasetFingerprint !== null && fingerprint !== datasetFingerprint) throw new Error("Mixed dataset fingerprints in M16 evidence subset.");
    datasetFingerprint = fingerprint;
    const caseId = getCaseId(item);
    const levels = byCase.get(caseId) ?? new Set<string>();
    if (levels.has(item.evidence_level)) throw new Error(`Duplicate ${caseId}/${item.evidence_level}.`);
    levels.add(item.evidence_level);
    byCase.set(caseId, levels);
  }
  if (byCase.size !== 36) throw new Error(`Expected 36 cases, found ${byCase.size}.`);
  const stratumCounts = new Map<string, number>();
  for (const item of packages.filter((value) => value.evidence_level === "S0")) {
    const stratum = getStratum(item);
    if (!stratum) throw new Error(`Missing stratum in ${item.package_id}.`);
    stratumCounts.set(stratum, (stratumCounts.get(stratum) ?? 0) + 1);
  }
  const expectedStrata = [
    "top_high_risk", "low_risk", "true_positive",
    "false_positive", "false_negative", "near_threshold",
  ];
  for (const stratum of expectedStrata) {
    if (stratumCounts.get(stratum) !== 6) {
      throw new Error(`Expected 6 cases in stratum ${stratum}, found ${stratumCounts.get(stratum) ?? 0}.`);
    }
  }
  if (stratumCounts.size !== expectedStrata.length) {
    throw new Error(`Unexpected M16 strata: ${[...stratumCounts.keys()].sort().join(", ")}.`);
  }
  for (const [caseId, levels] of byCase) {
    if (levels.size !== 6 || expectedLevels.some((level) => !levels.has(level))) {
      throw new Error(`Case ${caseId} does not contain exact S0-S5 matrix.`);
    }
  }
  return { caseCount: byCase.size, datasetFingerprint: datasetFingerprint as string };
}

async function assertM16Receipt(receipt: Record<string, unknown>, workspace: string, evidencePath: string): Promise<void> {
  if (receipt.stage !== "freddie_evaluation_cohort_m16" || receipt.status !== "PASS") throw new Error("M16 receipt is not certified PASS.");
  if (receipt.dataset_id !== EXPECTED_DATASET) throw new Error(`M16 receipt dataset mismatch: ${String(receipt.dataset_id)}.`);
  const invariants = asObject(receipt.invariants);
  if (Object.values(invariants).some((value) => value !== "PASS")) throw new Error("M16 receipt contains failed invariants.");
  const outputs = asObject(receipt.output_fingerprints);
  const relative = path.relative(workspace, evidencePath);
  const expected = outputs[relative];
  if (typeof expected !== "string") throw new Error(`M16 receipt does not fingerprint ${relative}.`);
  const actual = await sha256File(evidencePath);
  if (actual !== expected) throw new Error(`M16 evidence hash mismatch for ${relative}.`);
}

function getCaseId(item: EvidencePackage): string {
  const top = asObject(item.case);
  const internal = asObject(item.internal_metadata);
  const internalCase = asObject(internal.case);
  const legacy = asObject(internal.customer);
  const value = top.case_id ?? top.source_entity_id ?? internalCase.case_id ?? internalCase.source_entity_id ?? legacy.SK_ID_CURR ?? legacy.customer_id ?? item.source_ir_id;
  if (typeof value !== "string" && typeof value !== "number") throw new Error(`Missing case identity in ${item.package_id}.`);
  return String(value);
}

function getStratum(item: EvidencePackage): string | null {
  const top = asObject(item.case);
  const internal = asObject(item.internal_metadata);
  const internalCase = asObject(internal.case);
  const legacy = asObject(internal.customer);
  const value = top.case_type ?? internalCase.case_type ?? legacy.case_type;
  return typeof value === "string" ? value : null;
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function assertPromptHasNoHomeCreditLeak(text: string, packageId: string): void {
  for (const pattern of HOME_CREDIT_LEAK_PATTERNS) {
    if (pattern.test(text)) throw new Error(`Home Credit prompt leakage in ${packageId}: ${pattern}.`);
  }
}

function assertUnique(values: string[], label: string): void {
  if (new Set(values).size !== values.length) throw new Error(`Duplicate ${label} detected.`);
}

async function sha256File(filePath: string): Promise<string> {
  const content = await readFile(filePath);
  return createHash("sha256").update(content).digest("hex");
}

async function writeJsonlAtomic(filePath: string, records: unknown[]): Promise<void> {
  const temp = `${filePath}.tmp`;
  await writeFile(temp, `${records.map((item) => JSON.stringify(item)).join("\n")}\n`, "utf8");
  await import("node:fs/promises").then(({ rename }) => rename(temp, filePath));
}

async function writeJsonAtomic(filePath: string, value: unknown): Promise<void> {
  const temp = `${filePath}.tmp`;
  await writeFile(temp, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await import("node:fs/promises").then(({ rename }) => rename(temp, filePath));
}
