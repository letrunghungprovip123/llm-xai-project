// src/server/validator/claim-extraction-runner.ts

import "dotenv/config";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  CLAIM_EXTRACTION_JSON_SCHEMA,
  ClaimExtractionPayload,
} from "./claim-schema";

import {
  BedrockStructuredClaimExtractor,
  GeneratedExplanationRecord,
  getCustomerId,
  getExplanationId,
  getFullText,
  getGeneratorType,
  getIrId,
  getSections,
} from "./bedrock-claim-extractor";

const DEFAULT_TEMPLATE_EXPLANATIONS_PATH =
  "data/reports/llm_explanations/evaluation/template/llm_explanations.jsonl";

const DEFAULT_LLM_API_EXPLANATIONS_PATH =
  "data/reports/llm_explanations/evaluation/llm_api/base/llm_explanations.jsonl";

const DEFAULT_OUTPUT_ROOT = "data/reports/faithfulness_validation/evaluation";

const RUN_LLM_API = "llm_api";
const RUN_TEMPLATE_MATCHED_LLM_API_5 = "template_matched_llm_api_5";
const RUN_TEMPLATE_FULL = "template_full";

const CLAIM_EXTRACTION_PROMPT_VERSION = "batch_j_claim_extraction_prompt_v1.0";

const DEFAULT_INPUT_PRICE_PER_1K = 0.0011;
const DEFAULT_OUTPUT_PRICE_PER_1K = 0.0055;

export type J1RunnerOptions = {
  runName: string;
  inputPath: string;
  outputDir: string;
  limit: number | null;
  forceReextract: boolean;
  matchIrIdsFromPath: string | null;
};

type SelectedExplanationRecord = {
  record: GeneratedExplanationRecord;
  sourceRecordIndex: number;
  runIndex: number;
  ir_id: string;
};

type TokenUsage = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

type EstimatedCost = {
  input_cost_usd: number;
  output_cost_usd: number;
  total_cost_usd: number;
  input_price_per_1k: number;
  output_price_per_1k: number;
};

type ClaimExtractionArtifact = {
  claim_extraction_id: string;
  created_at: string;
  ir_id: string;
  explanation_id: string;
  customer_id: string | null;
  generator_type: string;
  source_record_index: number;
  run_record_index: number;
  source_input_hash: string;
  source: {
    llm_explanations_path: string;
    full_text_length: number;
    section_names: string[];
  };
  extractor: {
    provider: "amazon_bedrock";
    model_id: string;
    region_name: string;
    extractor_version: string;
    prompt_version: string;
    schema_hash: string;
  };
  claim_extraction: ClaimExtractionPayload;
  usage: TokenUsage;
  estimated_cost: EstimatedCost;
  cache: {
    status: "new" | "reused";
    force_reextract: boolean;
    reused_from_claim_extraction_id?: string;
  };
};

type J1FailureRecord = {
  record_index: number;
  run_record_index: number;
  ir_id: string;
  explanation_id: string;
  source_input_hash: string;
  error: string;
};

type J1Summary = {
  report_name: string;
  created_at: string;
  run_name: string;
  input_path: string;
  output_path: string;
  summary_path: string;
  failures_path: string;
  match_ir_ids_from_path: string | null;
  force_reextract: boolean;
  total_input_records: number;
  selected_records: number;
  newly_extracted: number;
  reused: number;
  failed: number;
  total_claims: number;
  token_usage_for_new_calls_only: TokenUsage;
  estimated_cost_for_new_calls_only: EstimatedCost;
  extractor: {
    provider: "amazon_bedrock";
    model_id: string;
    region_name: string;
    extractor_version: string;
    prompt_version: string;
    schema_hash: string;
  };
};

export async function runJ1BedrockClaimExtraction(
  overrides: Partial<J1RunnerOptions> = {},
): Promise<J1Summary> {
  const options = resolveRunnerOptions(overrides);

  await mkdir(options.outputDir, { recursive: true });

  const outputPath = path.join(options.outputDir, "claim_extractions.jsonl");
  const summaryPath = path.join(
    options.outputDir,
    "claim_extraction_summary.json",
  );
  const failuresPath = path.join(
    options.outputDir,
    "claim_extraction_failures.json",
  );

  const sourceRecords = await readJsonl(options.inputPath);
  const selectedRecords = await selectRecordsForRun({
    sourceRecords,
    options,
  });

  const extractor = new BedrockStructuredClaimExtractor();
  const config = extractor.getConfig();

  const schemaHash = sha256Stable(CLAIM_EXTRACTION_JSON_SCHEMA);

  const existingArtifacts = await readExistingArtifacts(outputPath);
  const cache = buildArtifactCache(existingArtifacts);

  const artifacts: ClaimExtractionArtifact[] = [];
  const failures: J1FailureRecord[] = [];

  let newlyExtracted = 0;
  let reused = 0;

  let totalNewInputTokens = 0;
  let totalNewOutputTokens = 0;
  let totalNewTotalTokens = 0;

  let totalNewInputCost = 0;
  let totalNewOutputCost = 0;
  let totalNewCost = 0;

  console.log("Running Batch J.1 Bedrock claim extraction...");
  console.log("Run name:", options.runName);
  console.log("Input:", options.inputPath);
  console.log("Output:", outputPath);
  console.log("Match ir_ids from:", options.matchIrIdsFromPath ?? "none");
  console.log("Force re-extract:", options.forceReextract);
  console.log("Total input records:", sourceRecords.length);
  console.log("Selected records:", selectedRecords.length);
  console.log("Selected ir_ids:");
  for (const selected of selectedRecords) {
    console.log(`- ${selected.ir_id}`);
  }
  console.log("Model:", config.modelId);

  for (let index = 0; index < selectedRecords.length; index += 1) {
    const selected = selectedRecords[index];

    const record = selected.record;
    const sourceRecordIndex = selected.sourceRecordIndex;
    const runIndex = selected.runIndex;

    const irId = getIrId(record, sourceRecordIndex + 1);
    const explanationId = getExplanationId(record, sourceRecordIndex + 1);
    const customerId = getCustomerId(record);
    const generatorType = getGeneratorType(record) || options.runName;

    const sections = getSections(record);
    const fullText = getFullText(record, sections);

    const sourceInputHash = buildSourceInputHash({
      record,
      index: sourceRecordIndex,
      config,
      schemaHash,
    });

    const cacheKey = buildCacheKey(explanationId, sourceInputHash);
    const cachedArtifact = cache.get(cacheKey);

    if (!options.forceReextract && cachedArtifact) {
      const reusedArtifact: ClaimExtractionArtifact = {
        ...cachedArtifact,
        created_at: new Date().toISOString(),
        run_record_index: runIndex,
        cache: {
          status: "reused",
          force_reextract: false,
          reused_from_claim_extraction_id: cachedArtifact.claim_extraction_id,
        },
      };

      artifacts.push(reusedArtifact);
      reused += 1;

      console.log(
        `[${index + 1}/${selectedRecords.length}] REUSED ${explanationId}`,
      );

      continue;
    }

    console.log(
      `[${index + 1}/${selectedRecords.length}] EXTRACT ${explanationId}`,
    );

    try {
      const result =
        await extractor.extractClaimsFromExplanationWithRaw(record);

      const usage = normalizeUsage(result.usage);
      const cost = estimateCost(usage);

      totalNewInputTokens += usage.input_tokens;
      totalNewOutputTokens += usage.output_tokens;
      totalNewTotalTokens += usage.total_tokens;

      totalNewInputCost += cost.input_cost_usd;
      totalNewOutputCost += cost.output_cost_usd;
      totalNewCost += cost.total_cost_usd;

      const artifact: ClaimExtractionArtifact = {
        claim_extraction_id: buildClaimExtractionId(
          explanationId,
          sourceInputHash,
        ),
        created_at: new Date().toISOString(),
        ir_id: irId,
        explanation_id: explanationId,
        customer_id: customerId,
        generator_type: generatorType,
        source_record_index: sourceRecordIndex,
        run_record_index: runIndex,
        source_input_hash: sourceInputHash,
        source: {
          llm_explanations_path: options.inputPath,
          full_text_length: fullText.length,
          section_names: Object.keys(sections),
        },
        extractor: {
          provider: "amazon_bedrock",
          model_id: config.modelId,
          region_name: config.regionName,
          extractor_version: config.extractorVersion,
          prompt_version: CLAIM_EXTRACTION_PROMPT_VERSION,
          schema_hash: schemaHash,
        },
        claim_extraction: result.payload,
        usage,
        estimated_cost: cost,
        cache: {
          status: "new",
          force_reextract: options.forceReextract,
        },
      };

      artifacts.push(artifact);
      newlyExtracted += 1;
    } catch (error) {
      failures.push({
        record_index: sourceRecordIndex,
        run_record_index: runIndex,
        ir_id: irId,
        explanation_id: explanationId,
        source_input_hash: sourceInputHash,
        error: error instanceof Error ? error.message : String(error),
      });

      console.error(
        `[${index + 1}/${selectedRecords.length}] FAILED ${explanationId}`,
      );
      console.error(error);
    }
  }

  await writeJsonl(outputPath, artifacts);
  await writeFile(failuresPath, JSON.stringify(failures, null, 2), "utf8");

  const totalClaims = artifacts.reduce(
    (sum, artifact) => sum + artifact.claim_extraction.claim_count,
    0,
  );

  const summary: J1Summary = {
    report_name: "Batch J.1 Bedrock Claim Extraction Summary",
    created_at: new Date().toISOString(),
    run_name: options.runName,
    input_path: options.inputPath,
    output_path: outputPath,
    summary_path: summaryPath,
    failures_path: failuresPath,
    match_ir_ids_from_path: options.matchIrIdsFromPath,
    force_reextract: options.forceReextract,
    total_input_records: sourceRecords.length,
    selected_records: selectedRecords.length,
    newly_extracted: newlyExtracted,
    reused,
    failed: failures.length,
    total_claims: totalClaims,
    token_usage_for_new_calls_only: {
      input_tokens: totalNewInputTokens,
      output_tokens: totalNewOutputTokens,
      total_tokens: totalNewTotalTokens,
    },
    estimated_cost_for_new_calls_only: {
      input_cost_usd: roundUsd(totalNewInputCost),
      output_cost_usd: roundUsd(totalNewOutputCost),
      total_cost_usd: roundUsd(totalNewCost),
      input_price_per_1k: getInputPricePer1k(),
      output_price_per_1k: getOutputPricePer1k(),
    },
    extractor: {
      provider: "amazon_bedrock",
      model_id: config.modelId,
      region_name: config.regionName,
      extractor_version: config.extractorVersion,
      prompt_version: CLAIM_EXTRACTION_PROMPT_VERSION,
      schema_hash: schemaHash,
    },
  };

  await writeFile(summaryPath, JSON.stringify(summary, null, 2), "utf8");

  console.log("\nBatch J.1 finished.");
  console.log(JSON.stringify(summary, null, 2));

  if (failures.length > 0) {
    process.exitCode = 1;
  }

  return summary;
}

function resolveRunnerOptions(
  overrides: Partial<J1RunnerOptions> = {},
): J1RunnerOptions {
  const envRunName = process.env.J1_RUN_NAME;
  const envInputPath = process.env.J1_INPUT_PATH;
  const envOutputDir = process.env.J1_OUTPUT_DIR;
  const envMatchIrIdsFromPath = process.env.J1_MATCH_IR_IDS_FROM;

  const rawRunName = overrides.runName ?? envRunName ?? RUN_LLM_API;
  const runName = sanitizePathPart(rawRunName);

  let inputPath: string;
  let outputDir: string;
  let matchIrIdsFromPath: string | null = null;

  if (overrides.inputPath) {
    inputPath = overrides.inputPath;
  } else if (envInputPath) {
    inputPath = envInputPath;
  } else if (runName === RUN_LLM_API) {
    inputPath = DEFAULT_LLM_API_EXPLANATIONS_PATH;
  } else if (
    runName === RUN_TEMPLATE_MATCHED_LLM_API_5 ||
    runName === RUN_TEMPLATE_FULL
  ) {
    inputPath = DEFAULT_TEMPLATE_EXPLANATIONS_PATH;
  } else {
    throw new Error(
      [
        `Unknown runName without explicit inputPath: ${rawRunName}`,
        "Provide --inputPath for custom runs such as regeneration_attempt_1.",
      ].join("\n"),
    );
  }

  if (overrides.outputDir) {
    outputDir = overrides.outputDir;
  } else if (envOutputDir) {
    outputDir = envOutputDir;
  } else if (runName === RUN_LLM_API) {
    outputDir = path.join(DEFAULT_OUTPUT_ROOT, RUN_LLM_API, "base");
  } else if (runName === RUN_TEMPLATE_MATCHED_LLM_API_5) {
    outputDir = path.join(DEFAULT_OUTPUT_ROOT, RUN_TEMPLATE_MATCHED_LLM_API_5);
  } else if (runName === RUN_TEMPLATE_FULL) {
    outputDir = path.join(DEFAULT_OUTPUT_ROOT, RUN_TEMPLATE_FULL);
  } else {
    outputDir = path.join(
      DEFAULT_OUTPUT_ROOT,
      RUN_LLM_API,
      sanitizePathPart(runName),
    );
  }

  if (overrides.matchIrIdsFromPath !== undefined) {
    matchIrIdsFromPath = overrides.matchIrIdsFromPath;
  } else if (envMatchIrIdsFromPath) {
    matchIrIdsFromPath = envMatchIrIdsFromPath;
  } else if (runName === RUN_TEMPLATE_MATCHED_LLM_API_5) {
    matchIrIdsFromPath = DEFAULT_LLM_API_EXPLANATIONS_PATH;
  }

  const rawLimit =
    overrides.limit !== undefined && overrides.limit !== null
      ? String(overrides.limit)
      : process.env.J1_LIMIT;

  const limit =
    rawLimit === undefined || rawLimit.trim() === "" ? null : Number(rawLimit);

  if (limit !== null && (!Number.isInteger(limit) || limit <= 0)) {
    throw new Error(
      `J1_LIMIT/--limit must be a positive integer. Received: ${rawLimit}`,
    );
  }

  const forceReextract =
    overrides.forceReextract ?? process.env.J1_FORCE_REEXTRACT === "1";

  return {
    runName,
    inputPath,
    outputDir,
    limit,
    forceReextract,
    matchIrIdsFromPath,
  };
}

async function selectRecordsForRun(input: {
  sourceRecords: GeneratedExplanationRecord[];
  options: J1RunnerOptions;
}): Promise<SelectedExplanationRecord[]> {
  const { sourceRecords, options } = input;

  if (options.matchIrIdsFromPath) {
    return selectRecordsByMatchedIrIds({
      sourceRecords,
      matchIrIdsFromPath: options.matchIrIdsFromPath,
      limit: options.limit,
    });
  }

  const limited =
    options.limit === null
      ? sourceRecords
      : sourceRecords.slice(0, options.limit);

  return limited.map((record, index) => ({
    record,
    sourceRecordIndex: index,
    runIndex: index,
    ir_id: getIrId(record, index + 1),
  }));
}

async function selectRecordsByMatchedIrIds(input: {
  sourceRecords: GeneratedExplanationRecord[];
  matchIrIdsFromPath: string;
  limit: number | null;
}): Promise<SelectedExplanationRecord[]> {
  const matchRows = await readJsonl(input.matchIrIdsFromPath);

  const targetIrIds = matchRows
    .map((record, index) => getIrId(record, index + 1))
    .filter((irId) => irId && !irId.startsWith("missing_ir_id"));

  const limitedTargetIrIds =
    input.limit === null ? targetIrIds : targetIrIds.slice(0, input.limit);

  const sourceByIrId = new Map<
    string,
    { record: GeneratedExplanationRecord; sourceRecordIndex: number }
  >();

  for (let index = 0; index < input.sourceRecords.length; index += 1) {
    const record = input.sourceRecords[index];
    const irId = getIrId(record, index + 1);

    sourceByIrId.set(irId, {
      record,
      sourceRecordIndex: index,
    });
  }

  const selected: SelectedExplanationRecord[] = [];
  const missing: string[] = [];

  for (let runIndex = 0; runIndex < limitedTargetIrIds.length; runIndex += 1) {
    const irId = limitedTargetIrIds[runIndex];
    const matched = sourceByIrId.get(irId);

    if (!matched) {
      missing.push(irId);
      continue;
    }

    selected.push({
      record: matched.record,
      sourceRecordIndex: matched.sourceRecordIndex,
      runIndex,
      ir_id: irId,
    });
  }

  if (missing.length > 0) {
    throw new Error(
      [
        `Could not match ${missing.length} ir_id values from ${input.matchIrIdsFromPath}.`,
        "Missing ir_id values:",
        ...missing.map((id) => `- ${id}`),
      ].join("\n"),
    );
  }

  return selected;
}

async function readJsonl(
  filePath: string,
): Promise<GeneratedExplanationRecord[]> {
  const raw = await readFile(filePath, "utf8");

  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      try {
        return JSON.parse(line) as GeneratedExplanationRecord;
      } catch (error) {
        throw new Error(
          `Invalid JSONL at ${filePath}, line ${index + 1}: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      }
    });
}

async function readExistingArtifacts(
  filePath: string,
): Promise<ClaimExtractionArtifact[]> {
  try {
    const raw = await readFile(filePath, "utf8");

    return raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as ClaimExtractionArtifact);
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;

    if (nodeError.code === "ENOENT") {
      return [];
    }

    throw error;
  }
}

function buildArtifactCache(
  artifacts: ClaimExtractionArtifact[],
): Map<string, ClaimExtractionArtifact> {
  const cache = new Map<string, ClaimExtractionArtifact>();

  for (const artifact of artifacts) {
    const key = buildCacheKey(
      artifact.explanation_id,
      artifact.source_input_hash,
    );

    cache.set(key, artifact);
  }

  return cache;
}

async function writeJsonl(filePath: string, records: unknown[]): Promise<void> {
  const content = records.map((record) => JSON.stringify(record)).join("\n");

  await writeFile(filePath, content + (content ? "\n" : ""), "utf8");
}

function buildSourceInputHash(input: {
  record: GeneratedExplanationRecord;
  index: number;
  config: {
    modelId: string;
    regionName: string;
    extractorVersion: string;
  };
  schemaHash: string;
}): string {
  const sections = getSections(input.record);
  const fullText = getFullText(input.record, sections);

  const hashInput = {
    ir_id: getIrId(input.record, input.index + 1),
    explanation_id: getExplanationId(input.record, input.index + 1),
    generator_type: getGeneratorType(input.record),
    sections,
    full_text: fullText,
    referenced_terms: getArrayField(input.record, "referenced_terms"),
    evidence_items_used: getArrayField(input.record, "evidence_items_used"),
    evidence_groups_used: getArrayField(input.record, "evidence_groups_used"),
    extractor: {
      provider: "amazon_bedrock",
      model_id: input.config.modelId,
      region_name: input.config.regionName,
      extractor_version: input.config.extractorVersion,
      prompt_version: CLAIM_EXTRACTION_PROMPT_VERSION,
      schema_hash: input.schemaHash,
    },
  };

  return sha256Stable(hashInput);
}

function buildCacheKey(explanationId: string, sourceInputHash: string): string {
  return `${explanationId}::${sourceInputHash}`;
}

function buildClaimExtractionId(
  explanationId: string,
  sourceInputHash: string,
): string {
  return `cexp_${safeId(explanationId)}_${sourceInputHash.slice(0, 12)}`;
}

function safeId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80);
}

function normalizeUsage(usage: unknown): TokenUsage {
  const obj = isPlainObject(usage) ? usage : {};

  const inputTokens = toNumber(
    obj.inputTokens ??
      obj.input_tokens ??
      obj.promptTokens ??
      obj.prompt_tokens,
  );

  const outputTokens = toNumber(
    obj.outputTokens ??
      obj.output_tokens ??
      obj.completionTokens ??
      obj.completion_tokens,
  );

  const totalTokens = toNumber(obj.totalTokens ?? obj.total_tokens);

  return {
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    total_tokens: totalTokens || inputTokens + outputTokens,
  };
}

function estimateCost(usage: TokenUsage): EstimatedCost {
  const inputPricePer1k = getInputPricePer1k();
  const outputPricePer1k = getOutputPricePer1k();

  const inputCost = (usage.input_tokens / 1000) * inputPricePer1k;
  const outputCost = (usage.output_tokens / 1000) * outputPricePer1k;

  return {
    input_cost_usd: roundUsd(inputCost),
    output_cost_usd: roundUsd(outputCost),
    total_cost_usd: roundUsd(inputCost + outputCost),
    input_price_per_1k: inputPricePer1k,
    output_price_per_1k: outputPricePer1k,
  };
}

function getInputPricePer1k(): number {
  return Number(
    process.env.BEDROCK_INPUT_PRICE_PER_1K ?? DEFAULT_INPUT_PRICE_PER_1K,
  );
}

function getOutputPricePer1k(): number {
  return Number(
    process.env.BEDROCK_OUTPUT_PRICE_PER_1K ?? DEFAULT_OUTPUT_PRICE_PER_1K,
  );
}

function roundUsd(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function sha256Stable(value: unknown): string {
  return createHash("sha256").update(stableStringify(value)).digest("hex");
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }

  if (isPlainObject(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }

  return JSON.stringify(value);
}

function getArrayField(
  record: Record<string, unknown>,
  key: string,
): unknown[] {
  const direct = record[key];

  if (Array.isArray(direct)) {
    return direct;
  }

  const explanation = record.explanation;

  if (isPlainObject(explanation) && Array.isArray(explanation[key])) {
    return explanation[key];
  }

  const llmOutput = record.llm_output;

  if (isPlainObject(llmOutput) && Array.isArray(llmOutput[key])) {
    return llmOutput[key];
  }

  return [];
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function sanitizePathPart(value: string): string {
  const trimmed = value.trim();

  if (!trimmed) {
    return "llm_api";
  }

  return trimmed.replace(/[^a-zA-Z0-9_-]+/g, "_");
}
