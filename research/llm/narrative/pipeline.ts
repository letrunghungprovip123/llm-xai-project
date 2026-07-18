import { FORBIDDEN_PROMPT_KEYS } from "./config";
import {
  joinPath,
  pathExists,
  writeJsonFile,
  writeJsonlFile,
} from "./artifacts";
import { getModelConfig } from "./modelRegistry";
import { loadEvidencePackages, readJsonl } from "./loaders";
import { buildPrompt } from "./promptBuilder";
import { parseExplanationOutput } from "./outputSchema";
import {
  buildGenerationId,
  isGenerationUsable,
  selectPackages,
} from "./generation";
import { buildPromptMetrics } from "./metrics/promptMetrics";
import { buildSchemaMetrics } from "./metrics/schemaMetrics";
import { buildContentMetrics } from "./metrics/contentMetrics";
import { buildPolicyMetrics } from "./metrics/policyMetrics";
import { buildEvidenceMentionMetrics } from "./metrics/evidenceMentionMetrics";
import { runTemplate } from "./runners/templateRunner";
import { runDeepSeek } from "./runners/deepseekRunner";
import { runVllm } from "./runners/vllmRunner";
import type {
  CaseMetadata,
  EvidencePackage,
  GenerationRecord,
  InputSnapshot,
  ModelConfig,
  PipelineResult,
  PromptInstanceRecord,
  RunOptions,
  RunnerResult,
} from "../../../contracts/narrative";
import {
  getGitCommitHash,
  hashToPositiveInt,
  sanitizeFilePart,
  seededShuffle,
  sha256,
  stableStringify,
} from "../common/utils";

interface GenerationTask {
  package_item: EvidencePackage;
  request_order_index: number;
  generation_seed: number;
}

export async function runNarrativePipeline(
  options: RunOptions,
): Promise<PipelineResult> {
  validateRunOptions(options);

  const allPackages = await loadEvidencePackages(options.input_path);
  validatePromptPayloadSafety(allPackages);

  const selectedPackages = selectPackages(allPackages, options);
  if (selectedPackages.length === 0) {
    throw new Error(
      "No evidence packages matched the selected cases and levels.",
    );
  }

  const shardPaths: string[] = [];
  let plannedGenerationCount = 0;
  let completedGenerationCount = 0;
  let failedGenerationCount = 0;

  for (const requestedModelId of options.model_ids) {
    const model = getModelConfig(requestedModelId);
    validateModelForStage(model, options);

    for (const repeatId of options.repeat_ids) {
      const result = await runOneShard(
        selectedPackages,
        model,
        repeatId,
        options,
      );

      shardPaths.push(result.shard_path);
      plannedGenerationCount += result.planned_count;
      completedGenerationCount += result.completed_count;
      failedGenerationCount += result.failed_count;
    }
  }

  return {
    run_id: options.run_id,
    shard_count: shardPaths.length,
    planned_generation_count: plannedGenerationCount,
    completed_generation_count: completedGenerationCount,
    failed_generation_count: failedGenerationCount,
    shard_paths: shardPaths,
  };
}

async function runOneShard(
  packages: EvidencePackage[],
  model: ModelConfig,
  repeatId: number,
  options: RunOptions,
): Promise<{
  shard_path: string;
  planned_count: number;
  completed_count: number;
  failed_count: number;
}> {
  const levelSet = options.levels.join("-");
  const chunkLabel = options.chunk_size
    ? `${options.chunk_start}-${options.chunk_start + options.chunk_size - 1}`
    : `${options.chunk_start}-end`;

  const shardPath = joinPath(
    options.output_dir,
    "shards",
    `model=${sanitizeFilePart(model.id)}`,
    `repeat=${repeatId}`,
    `chunk=${chunkLabel}`,
    `levels=${levelSet}`,
  );

  const generationPath = joinPath(shardPath, "generations.jsonl");
  const promptPath = joinPath(shardPath, "prompt_instances.jsonl");
  const manifestPath = joinPath(shardPath, "shard_manifest.json");

  const existingRecords =
    options.resume && (await pathExists(generationPath))
      ? await readJsonl<GenerationRecord>(generationPath)
      : [];

  const generationMap = new Map<string, GenerationRecord>();
  for (const record of existingRecords) {
    generationMap.set(record.generation_id, record);
  }

  const promptMap = new Map<string, PromptInstanceRecord>();
  if (options.resume && (await pathExists(promptPath))) {
    const existingPrompts = await readJsonl<PromptInstanceRecord>(promptPath);
    for (const record of existingPrompts) {
      promptMap.set(record.prompt_id, record);
    }
  }

  const orderSeed = hashToPositiveInt(
    [
      options.base_seed,
      options.run_id,
      model.id,
      repeatId,
      options.chunk_start,
      levelSet,
    ].join("|"),
  );

  const orderedPackages = seededShuffle(packages, orderSeed);
  const tasks: GenerationTask[] = orderedPackages.map((packageItem, index) => ({
    package_item: packageItem,
    request_order_index: index,
    generation_seed: hashToPositiveInt(
      [
        options.base_seed,
        model.id,
        repeatId,
        packageItem.source_ir_id,
        packageItem.evidence_level,
      ].join("|"),
    ),
  }));

  let generatedSinceCheckpoint = 0;

  for (let start = 0; start < tasks.length; start += options.concurrency) {
    const batch = tasks.slice(start, start + options.concurrency);

    const results = await Promise.all(
      batch.map(async (task) => {
        const generationId = buildGenerationId(
          options.run_id,
          model.id,
          repeatId,
          task.package_item.package_id,
        );

        const existing = generationMap.get(generationId);
        if (options.resume && existing && isGenerationUsable(existing)) {
          return {
            record: existing,
            prompt: null,
            skipped: true,
          };
        }

        const generated = await generateOne(task, model, repeatId, options);

        return {
          record: generated.record,
          prompt: generated.prompt,
          skipped: false,
        };
      }),
    );

    for (const result of results) {
      generationMap.set(result.record.generation_id, result.record);

      if (result.prompt) {
        promptMap.set(result.prompt.prompt_id, result.prompt);
      }

      if (!result.skipped) {
        generatedSinceCheckpoint += 1;
      }
    }

    if (generatedSinceCheckpoint >= options.checkpoint_every) {
      await writeShardFiles(
        generationPath,
        promptPath,
        manifestPath,
        generationMap,
        promptMap,
        model,
        repeatId,
        orderSeed,
        options,
        tasks,
      );
      generatedSinceCheckpoint = 0;
    }
  }

  await writeShardFiles(
    generationPath,
    promptPath,
    manifestPath,
    generationMap,
    promptMap,
    model,
    repeatId,
    orderSeed,
    options,
    tasks,
  );

  const finalRecords = [...generationMap.values()];
  const completed = finalRecords.filter(isGenerationUsable).length;

  return {
    shard_path: shardPath,
    planned_count: tasks.length,
    completed_count: completed,
    failed_count: finalRecords.length - completed,
  };
}

async function generateOne(
  task: GenerationTask,
  model: ModelConfig,
  repeatId: number,
  options: RunOptions,
): Promise<{
  record: GenerationRecord;
  prompt: PromptInstanceRecord;
}> {
  const packageItem = task.package_item;
  const prompt = buildPrompt(packageItem, model, options.prompt_version);
  const promptMetrics = buildPromptMetrics(prompt);
  const runnerResult = await runModel(
    packageItem,
    model,
    prompt,
    task.generation_seed,
    options,
  );

  const parseResult = parseExplanationOutput(
    runnerResult.raw_output,
    packageItem.evidence_level,
  );

  const parsedOutput = parseResult.parsed_output;
  const schemaMetrics = buildSchemaMetrics(parseResult);
  const contentMetrics = buildContentMetrics(parsedOutput);
  const policyMetrics = buildPolicyMetrics(packageItem, parsedOutput);
  const evidenceMentionMetrics = buildEvidenceMentionMetrics(
    packageItem,
    parsedOutput,
  );
  const inputSnapshot = buildInputSnapshot(packageItem);
  const caseMetadata = buildCaseMetadata(packageItem);
  const generationId = buildGenerationId(
    options.run_id,
    model.id,
    repeatId,
    packageItem.package_id,
  );

  const infrastructureCost = readInfrastructureCostPerGeneration();
  const totalCost = calculateTotalCost(
    model,
    runnerResult.provider_api_cost_usd,
    infrastructureCost,
  );

  const record: GenerationRecord = {
    generation_id: generationId,
    run_id: options.run_id,
    experiment_stage: options.experiment_stage,
    package_id: packageItem.package_id,
    source_ir_id: packageItem.source_ir_id,
    source_evidence_id: packageItem.source_evidence_id || null,
    evidence_level: packageItem.evidence_level,
    case_metadata: caseMetadata,
    model_provider: model.provider,
    model_id: model.id,
    remote_model_id: model.remote_model_id,
    model_family: model.family,
    model_revision: model.revision,
    prompt_version: options.prompt_version,
    output_schema_version: options.output_schema_version,
    repeat_id: repeatId,
    generation_seed: model.runtime === "api" ? null : task.generation_seed,
    request_order_index: task.request_order_index,
    output_constraint_mode: model.output_constraint_mode,
    decoding_config: options.decoding,
    input_package_sha256: sha256(stableStringify(packageItem)),
    prompt_id: prompt.prompt_id,
    prompt_message_sha256: prompt.message_sha256,
    input_snapshot: inputSnapshot,
    prompt_metrics: promptMetrics,
    runtime_metrics: {
      ...runnerResult,
      empty_response: !runnerResult.raw_output?.trim(),
      truncated_response: runnerResult.finish_reason === "length",
      infrastructure_cost_usd: infrastructureCost,
      total_cost_usd: totalCost,
    },
    raw_output: runnerResult.raw_output,
    cleaned_output: parseResult.cleaned_output,
    parsed_output: parsedOutput,
    schema_metrics: schemaMetrics,
    content_metrics: contentMetrics,
    policy_metrics: policyMetrics,
    evidence_mention_metrics: evidenceMentionMetrics,
    created_at: new Date().toISOString(),
  };

  const promptRecord: PromptInstanceRecord = {
    prompt_id: prompt.prompt_id,
    prompt_version: options.prompt_version,
    output_schema_version: options.output_schema_version,
    package_id: packageItem.package_id,
    source_ir_id: packageItem.source_ir_id,
    evidence_level: packageItem.evidence_level,
    model_id: model.id,
    model_revision: model.revision,
    messages: prompt.messages,
    message_sha256: prompt.message_sha256,
    prompt_char_count: promptMetrics.prompt_char_count,
    prompt_estimated_token_count: promptMetrics.prompt_estimated_token_count,
    section_flags: prompt.section_flags,
    created_at: new Date().toISOString(),
  };

  return {
    record,
    prompt: promptRecord,
  };
}

async function runModel(
  packageItem: EvidencePackage,
  model: ModelConfig,
  prompt: ReturnType<typeof buildPrompt>,
  generationSeed: number,
  options: RunOptions,
): Promise<RunnerResult> {
  if (model.runtime === "template") {
    return runTemplate(packageItem);
  }

  if (model.runtime === "api") {
    return runDeepSeek(
      model,
      prompt,
      options.decoding,
      options.timeout_ms,
      options.max_retries,
      options.retry_delay_ms,
    );
  }

  return runVllm(
    model,
    prompt,
    options.decoding,
    generationSeed,
    options.timeout_ms,
    options.max_retries,
    options.retry_delay_ms,
  );
}

function validateRunOptions(options: RunOptions): void {
  if (!options.run_id.trim()) {
    throw new Error("run_id must not be empty.");
  }

  if (options.model_ids.length === 0) {
    throw new Error("At least one model id is required.");
  }

  if (options.levels.length === 0) {
    throw new Error("At least one evidence level is required.");
  }

  if (options.repeat_ids.length === 0) {
    throw new Error("At least one repeat id is required.");
  }

  if (options.concurrency < 1) {
    throw new Error("concurrency must be at least 1.");
  }

  if (options.checkpoint_every < 1) {
    throw new Error("checkpoint_every must be at least 1.");
  }
}

function validateModelForStage(model: ModelConfig, options: RunOptions): void {
  if (
    options.experiment_stage === "evaluation" &&
    model.runtime === "vllm" &&
    !model.revision
  ) {
    throw new Error(
      `Model ${model.id} must have a pinned revision for evaluation. Set its revision environment variable.`,
    );
  }
}

function validatePromptPayloadSafety(packages: EvidencePackage[]): void {
  const findings: string[] = [];

  for (const packageItem of packages) {
    findForbiddenKeys(
      packageItem.prompt_payload,
      `package:${packageItem.package_id}.prompt_payload`,
      findings,
    );
  }

  if (findings.length > 0) {
    throw new Error(
      ["Prompt payload leakage detected.", ...findings.slice(0, 20)].join("\n"),
    );
  }
}

function findForbiddenKeys(
  value: unknown,
  currentPath: string,
  findings: string[],
): void {
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      findForbiddenKeys(value[index], `${currentPath}[${index}]`, findings);
    }
    return;
  }

  if (!value || typeof value !== "object") {
    return;
  }

  const source = value as Record<string, unknown>;
  for (const [key, item] of Object.entries(source)) {
    const nextPath = `${currentPath}.${key}`;

    if (FORBIDDEN_PROMPT_KEYS.has(key)) {
      findings.push(nextPath);
    }

    findForbiddenKeys(item, nextPath, findings);
  }
}

function buildInputSnapshot(packageItem: EvidencePackage): InputSnapshot {
  const context = packageItem.prompt_payload.selection_context;

  return {
    selected_evidence_count:
      context.selected_evidence_count ??
      packageItem.prompt_payload.selected_evidence.length,
    coverage: readOptionalNumber(context.coverage),
    coverage_threshold: readOptionalNumber(context.coverage_threshold),
    coverage_status: context.coverage_status || null,
    adaptive_k: readOptionalNumber(context.adaptive_k),
    entropy_level: context.entropy_level || null,
    normalized_entropy: readOptionalNumber(context.normalized_entropy),
    concept_group_count:
      context.concept_group_count ??
      packageItem.prompt_payload.concept_evidence.length,
    mixed_concept_group_count: context.mixed_concept_group_count ?? 0,
    has_concept_evidence:
      packageItem.prompt_payload.concept_evidence.length > 0,
    has_constraints: Boolean(packageItem.prompt_payload.constraints),
    has_forbidden_rules: Boolean(
      packageItem.prompt_payload.constraints.forbidden_rule_ids?.length,
    ),
    has_narrative_policy: Boolean(packageItem.prompt_payload.narrative_policy),
  };
}

function buildCaseMetadata(packageItem: EvidencePackage): CaseMetadata {
  const internal = packageItem.internal_metadata || {};
  const customer = isObject(internal.customer) ? internal.customer : {};
  const groundTruth = isObject(internal.ground_truth)
    ? internal.ground_truth
    : {};

  const customerId = readStringOrNumber(
    customer.SK_ID_CURR ?? customer.customer_id,
  );
  const selectionStratum =
    typeof customer.case_type === "string" ? customer.case_type : null;
  const trueLabel = readOptionalNumber(groundTruth.true_label);
  const predictedClass = readOptionalNumber(
    packageItem.prompt_payload.prediction.predicted_class,
  );

  let predictionOutcome: CaseMetadata["prediction_outcome"] = null;
  if (trueLabel !== null && predictedClass !== null) {
    if (trueLabel === 1 && predictedClass === 1) {
      predictionOutcome = "TP";
    } else if (trueLabel === 0 && predictedClass === 0) {
      predictionOutcome = "TN";
    } else if (trueLabel === 0 && predictedClass === 1) {
      predictionOutcome = "FP";
    } else if (trueLabel === 1 && predictedClass === 0) {
      predictionOutcome = "FN";
    }
  }

  return {
    customer_id: customerId,
    selection_stratum: selectionStratum,
    prediction_outcome: predictionOutcome,
    true_label: trueLabel,
  };
}

async function writeShardFiles(
  generationPath: string,
  promptPath: string,
  manifestPath: string,
  generationMap: Map<string, GenerationRecord>,
  promptMap: Map<string, PromptInstanceRecord>,
  model: ModelConfig,
  repeatId: number,
  orderSeed: number,
  options: RunOptions,
  tasks: GenerationTask[],
): Promise<void> {
  const generations = [...generationMap.values()].sort((left, right) => {
    return left.request_order_index - right.request_order_index;
  });

  const prompts = [...promptMap.values()].sort((left, right) => {
    return left.prompt_id.localeCompare(right.prompt_id);
  });

  await writeJsonlFile(generationPath, generations);
  await writeJsonlFile(promptPath, prompts);

  await writeJsonFile(manifestPath, {
    run_id: options.run_id,
    experiment_stage: options.experiment_stage,
    created_at: new Date().toISOString(),
    git_commit_hash: getGitCommitHash(),
    input_path: options.input_path,
    model: model,
    repeat_id: repeatId,
    evidence_levels: options.levels,
    chunk_start: options.chunk_start,
    chunk_size: options.chunk_size ?? null,
    selected_case_count: new Set(
      tasks.map((task) => task.package_item.source_ir_id),
    ).size,
    planned_generation_count: tasks.length,
    written_generation_count: generations.length,
    success_count: generations.filter(isGenerationUsable).length,
    failed_count: generations.filter((record) => {
      return !isGenerationUsable(record);
    }).length,
    request_order_seed: orderSeed,
    concurrency: options.concurrency,
    decoding_config: options.decoding,
    prompt_version: options.prompt_version,
    output_schema_version: options.output_schema_version,
    generation_path: generationPath,
    prompt_path: promptPath,
  });
}

function readInfrastructureCostPerGeneration(): number | null {
  const value = process.env.INFRASTRUCTURE_COST_PER_GENERATION_USD;
  if (!value) {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function calculateTotalCost(
  model: ModelConfig,
  apiCost: number | null,
  infrastructureCost: number | null,
): number | null {
  if (model.runtime === "api") {
    if (apiCost === null && infrastructureCost === null) {
      return null;
    }
    return (apiCost || 0) + (infrastructureCost || 0);
  }

  if (infrastructureCost === null) {
    return null;
  }

  return infrastructureCost;
}

function readOptionalNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readStringOrNumber(value: unknown): string | number | null {
  if (typeof value === "string" || typeof value === "number") {
    return value;
  }

  return null;
}
