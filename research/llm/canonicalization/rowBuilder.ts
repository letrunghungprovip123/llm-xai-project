import {
  cohortKey,
  evidencePackageHash,
  extractCaseId,
  getRuntimeBoolean,
  getRuntimeString,
  getSchemaBoolean,
  getUsability,
  matrixKey,
  parseGenerationRecord,
  parsePromptRecord,
  verifyGenerationAgainstEvidence,
} from "./contracts";
import {
  profileJson,
  profileJsonl,
  readJsonStrict,
  readJsonlStrict,
  type LoadedJsonl,
} from "./io";
import {
  EVIDENCE_LEVELS,
  type CanonicalGenerationRow,
  type EvidencePackageRecord,
  type FileProfile,
  type GenerationRecordLike,
  type JsonObject,
  type ModelSource,
  type PromptRecordLike,
} from "../../../contracts/llm-validation";

export type LoadedSource = {
  config: ModelSource;
  generations: LoadedJsonl<JsonObject>;
  prompts: LoadedJsonl<JsonObject>;
  manifest?: Awaited<ReturnType<typeof readJsonStrict<JsonObject>>>;
  generation_entries: Array<{ line: number; value: GenerationRecordLike }>;
  prompt_entries: Array<{ line: number; value: PromptRecordLike }>;
};

export async function loadSource(
  config: ModelSource,
  profiles: FileProfile[],
): Promise<LoadedSource> {
  const generations = await readJsonlStrict<JsonObject>(config.generations_path);
  const prompts = await readJsonlStrict<JsonObject>(config.prompts_path);
  profiles.push(profileJsonl(generations), profileJsonl(prompts));

  const manifest = config.manifest_path
    ? await readJsonStrict<JsonObject>(config.manifest_path)
    : undefined;
  if (manifest) profiles.push(profileJson(manifest));

  const generationEntries = generations.records.map(({ line, value }) => ({
    line,
    value: parseGenerationRecord(value, `${generations.path}:${line}`),
  }));
  const promptEntries = prompts.records.map(({ line, value }) => ({
    line,
    value: parsePromptRecord(value, `${prompts.path}:${line}`),
  }));

  assertOnlyModel(
    generationEntries.map((entry) => entry.value.model_id),
    config.model_id,
  );
  assertOnlyModel(
    promptEntries.map((entry) => entry.value.model_id),
    config.model_id,
  );

  return {
    config,
    generations,
    prompts,
    manifest,
    generation_entries: generationEntries,
    prompt_entries: promptEntries,
  };
}

export function buildRowsForSource(input: {
  source: LoadedSource;
  evidence: EvidencePackageRecord[];
  modelOrder: number;
  matrixRole: "main" | "baseline";
}): CanonicalGenerationRow[] {
  const generationByKey = uniqueEntryMap(
    input.source.generation_entries,
    (record) => cohortKey(record),
    `${input.source.config.model_id} generation cohort key`,
  );
  const promptByKey = uniqueEntryMap(
    input.source.prompt_entries,
    (record) => cohortKey(record),
    `${input.source.config.model_id} prompt cohort key`,
  );
  uniqueEntryMap(
    input.source.generation_entries,
    (record) => record.generation_id,
    `${input.source.config.model_id} generation_id`,
  );
  uniqueEntryMap(
    input.source.prompt_entries,
    (record) => record.prompt_id,
    `${input.source.config.model_id} prompt_id`,
  );

  if (generationByKey.size !== input.evidence.length) {
    throw new Error(
      `${input.source.config.model_id} has ${generationByKey.size} generation cohort keys; expected ${input.evidence.length}.`,
    );
  }
  if (promptByKey.size !== input.evidence.length) {
    throw new Error(
      `${input.source.config.model_id} has ${promptByKey.size} prompt cohort keys; expected ${input.evidence.length}.`,
    );
  }

  const rows: CanonicalGenerationRow[] = [];
  for (
    let evidenceIndex = 0;
    evidenceIndex < input.evidence.length;
    evidenceIndex += 1
  ) {
    const packageItem = input.evidence[evidenceIndex];
    const key = cohortKey(packageItem);
    const generationEntry = generationByKey.get(key);
    const promptEntry = promptByKey.get(key);
    if (!generationEntry) {
      throw new Error(`${input.source.config.model_id} is missing ${key}.`);
    }
    if (!promptEntry) {
      throw new Error(
        `${input.source.config.model_id} prompt is missing ${key}.`,
      );
    }

    verifyGenerationAgainstEvidence({
      generation: generationEntry.value,
      evidence: packageItem,
      prompt: promptEntry.value,
      expectedModelId: input.source.config.model_id,
      context: `${input.source.config.model_id}:${key}`,
    });

    const generation = generationEntry.value;
    const usability = getUsability(generation);
    const evidenceLevelOrder = EVIDENCE_LEVELS.indexOf(
      generation.evidence_level,
    );
    const caseOrder =
      Math.floor(evidenceIndex / EVIDENCE_LEVELS.length) + 1;

    rows.push({
      canonical_schema_version: "generation_index_v1",
      canonical_key: matrixKey(generation),
      cohort_key: key,
      matrix_role: input.matrixRole,
      model_order: input.modelOrder,
      case_order: caseOrder,
      evidence_level_order: evidenceLevelOrder,
      is_baseline: input.source.config.is_baseline,
      eligible_for_selection: input.source.config.eligible_for_selection,
      generation_id: generation.generation_id,
      run_id: generation.run_id,
      experiment_stage: generation.experiment_stage,
      model_id: generation.model_id,
      model_revision: generation.model_revision,
      revision_status: generation.model_revision
        ? "pinned"
        : "provider_managed_or_unavailable",
      case_id: extractCaseId(generation),
      source_ir_id: generation.source_ir_id,
      evidence_level: generation.evidence_level,
      repeat_id: generation.repeat_id,
      package_id: generation.package_id,
      source_evidence_id: generation.source_evidence_id,
      prompt_id: generation.prompt_id,
      prompt_version: generation.prompt_version,
      output_schema_version: generation.output_schema_version,
      input_package_sha256: generation.input_package_sha256,
      input_package_hash_verified:
        generation.input_package_sha256 === evidencePackageHash(packageItem),
      prompt_message_sha256: generation.prompt_message_sha256,
      prompt_hash_verified:
        generation.prompt_message_sha256 === promptEntry.value.message_sha256,
      runtime_status: getRuntimeString(generation, "status"),
      finish_reason: getRuntimeString(generation, "finish_reason"),
      truncated_response: getRuntimeBoolean(generation, "truncated_response"),
      raw_json_parse_success: getSchemaBoolean(
        generation,
        "raw_json_parse_success",
      ),
      schema_valid: getSchemaBoolean(generation, "schema_valid"),
      usable: usability.usable,
      usability_reason_codes: usability.reason_codes,
      source_generation_path: input.source.generations.path,
      source_generation_file_sha256: input.source.generations.sha256,
      source_generation_line: generationEntry.line,
      source_prompt_path: input.source.prompts.path,
      source_prompt_file_sha256: input.source.prompts.sha256,
      source_prompt_line: promptEntry.line,
      generation_record: generation,
    });
  }

  return rows;
}

export function assertUniqueRows(
  rows: CanonicalGenerationRow[],
  label: string,
): void {
  const keys = new Set<string>();
  const generationIds = new Set<string>();
  for (const row of rows) {
    if (keys.has(row.canonical_key)) {
      throw new Error(
        `Duplicate canonical key in ${label}: ${row.canonical_key}.`,
      );
    }
    if (generationIds.has(row.generation_id)) {
      throw new Error(
        `Duplicate generation_id in ${label}: ${row.generation_id}.`,
      );
    }
    keys.add(row.canonical_key);
    generationIds.add(row.generation_id);
  }
}

function uniqueEntryMap<T>(
  entries: Array<{ line: number; value: T }>,
  getKey: (value: T) => string,
  label: string,
): Map<string, { line: number; value: T }> {
  const result = new Map<string, { line: number; value: T }>();
  for (const entry of entries) {
    const key = getKey(entry.value);
    const existing = result.get(key);
    if (existing) {
      throw new Error(
        `Duplicate ${label} ${key} at lines ${existing.line} and ${entry.line}.`,
      );
    }
    result.set(key, entry);
  }
  return result;
}

function assertOnlyModel(values: string[], expected: string): void {
  const observed = new Set(values);
  if (observed.size !== 1 || !observed.has(expected)) {
    throw new Error(
      `Expected model ${expected}, found ${[...observed].join(", ")}.`,
    );
  }
}
