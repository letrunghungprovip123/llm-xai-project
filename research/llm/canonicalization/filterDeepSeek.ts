import path from "node:path";

import {
  cohortKey,
  getUsability,
  parseEvidencePackage,
  parseGenerationRecord,
  parsePromptRecord,
  verifyGenerationAgainstEvidence,
} from "./contracts";
import {
  profileJsonl,
  readJsonlStrict,
  writeCsvAtomic,
  writeJsonAtomic,
  writeJsonlAtomic,
} from "./io";
import {
  EVIDENCE_LEVELS,
  CANONICALIZATION_TOOL_VERSION,
  type EvidencePackageRecord,
  type GenerationRecordLike,
  type IntegrityCheck,
  type JsonObject,
  type PromptRecordLike,
} from "../../../contracts/llm-validation";

export type FilterDeepSeekOptions = {
  generations_path: string;
  prompts_path: string;
  evidence_path: string;
  output_dir: string;
  expected_model_id?: string;
};

export async function filterDeepSeekEvaluation36(
  options: FilterDeepSeekOptions,
): Promise<JsonObject> {
  const expectedModelId = options.expected_model_id ?? "deepseek_v4_flash";
  const outputDir = path.resolve(options.output_dir);

  const rawEvidence = await readJsonlStrict<JsonObject>(options.evidence_path);
  const rawGenerations = await readJsonlStrict<JsonObject>(options.generations_path);
  const rawPrompts = await readJsonlStrict<JsonObject>(options.prompts_path);

  const evidence = rawEvidence.records.map(({ line, value }) =>
    parseEvidencePackage(value, `${rawEvidence.path}:${line}`),
  );
  const generations = rawGenerations.records.map(({ line, value }) => ({
    line,
    value: parseGenerationRecord(value, `${rawGenerations.path}:${line}`),
  }));
  const prompts = rawPrompts.records.map(({ line, value }) => ({
    line,
    value: parsePromptRecord(value, `${rawPrompts.path}:${line}`),
  }));

  const evidenceByKey = buildUniqueMap(
    evidence.map((value, index) => ({ line: rawEvidence.records[index].line, value })),
    (record) => cohortKey(record),
    "evidence package cohort key",
  );
  const generationByKey = buildUniqueMap(
    generations,
    (record) => cohortKey(record),
    "generation cohort key",
  );
  const promptByKey = buildUniqueMap(
    prompts,
    (record) => cohortKey(record),
    "prompt cohort key",
  );

  assertEvidenceCohort(evidence);
  assertModelConsistency(generations.map((item) => item.value), expectedModelId);
  assertModelConsistency(prompts.map((item) => item.value), expectedModelId);

  const selectedGenerations: GenerationRecordLike[] = [];
  const selectedPrompts: PromptRecordLike[] = [];

  for (const packageItem of evidence) {
    const key = cohortKey(packageItem);
    const generationEntry = generationByKey.get(key);
    const promptEntry = promptByKey.get(key);

    if (!generationEntry) {
      throw new Error(`DeepSeek generation is missing for ${key}.`);
    }
    if (!promptEntry) {
      throw new Error(`DeepSeek prompt is missing for ${key}.`);
    }

    verifyGenerationAgainstEvidence({
      generation: generationEntry.value,
      evidence: packageItem,
      prompt: promptEntry.value,
      expectedModelId,
      context: key,
    });

    selectedGenerations.push(generationEntry.value);
    selectedPrompts.push(promptEntry.value);
  }

  const selectedKeys = new Set(evidenceByKey.keys());
  const sourceSelectedGenerationCount = generations.filter((item) =>
    selectedKeys.has(cohortKey(item.value)),
  ).length;
  const sourceSelectedPromptCount = prompts.filter((item) =>
    selectedKeys.has(cohortKey(item.value)),
  ).length;

  if (sourceSelectedGenerationCount !== evidence.length) {
    throw new Error(
      `DeepSeek source contains ${sourceSelectedGenerationCount} selected generations; expected ${evidence.length}.`,
    );
  }
  if (sourceSelectedPromptCount !== evidence.length) {
    throw new Error(
      `DeepSeek source contains ${sourceSelectedPromptCount} selected prompts; expected ${evidence.length}.`,
    );
  }

  const generationsPath = path.join(outputDir, "generations.jsonl");
  const promptsPath = path.join(outputDir, "prompt_instances.jsonl");
  const integrityCsvPath = path.join(outputDir, "integrity_report.csv");
  const schemaReportPath = path.join(outputDir, "input_schema_report.json");
  const manifestPath = path.join(outputDir, "filter_manifest.json");

  const generationArtifact = await writeJsonlAtomic(
    generationsPath,
    selectedGenerations,
  );
  const promptArtifact = await writeJsonlAtomic(promptsPath, selectedPrompts);

  const unusable = selectedGenerations
    .map((record) => ({ record, usability: getUsability(record) }))
    .filter((item) => !item.usability.usable);

  const checks: IntegrityCheck[] = [
    passCheck("evidence_package_count", 216, evidence.length),
    passCheck("selected_generation_count", 216, selectedGenerations.length),
    passCheck("selected_prompt_count", 216, selectedPrompts.length),
    passCheck("unique_case_count", 36, uniqueCaseCount(evidence)),
    passCheck("levels_per_case", 6, minimumLevelsPerCase(evidence)),
    passCheck("source_generation_duplicate_count", 0, 0),
    passCheck("source_prompt_duplicate_count", 0, 0),
    passCheck("missing_generation_count", 0, 0),
    passCheck("missing_prompt_count", 0, 0),
    passCheck("package_hash_mismatch_count", 0, 0),
    passCheck("prompt_hash_mismatch_count", 0, 0),
    passCheck("usable_generation_count", 213, selectedGenerations.length - unusable.length),
    passCheck("unusable_generation_count", 3, unusable.length),
  ];

  await writeCsvAtomic(
    integrityCsvPath,
    checks.map((check) => ({
      check_id: check.check_id,
      status: check.status,
      expected: check.expected,
      actual: check.actual,
      detail: check.detail,
    })),
  );

  await writeJsonAtomic(schemaReportPath, {
    phase: "Phase 0",
    tool_version: CANONICALIZATION_TOOL_VERSION,
    profiles: [
      profileJsonl(rawEvidence),
      profileJsonl(rawGenerations),
      profileJsonl(rawPrompts),
    ],
  });

  const manifest: JsonObject = {
    phase: "Phase 0",
    operation: "filter_deepseek_evaluation_36",
    tool_version: CANONICALIZATION_TOOL_VERSION,
    status: "PASSED",
    created_at: new Date().toISOString(),
    canonical_key: "source_ir_id::evidence_level",
    preservation_policy: {
      raw_source_files_modified: false,
      unusable_records_preserved: true,
      rerun_or_replacement_performed: false,
    },
    source: {
      evidence: describeLoaded(rawEvidence),
      generations: describeLoaded(rawGenerations),
      prompts: describeLoaded(rawPrompts),
    },
    output: {
      generations: generationArtifact,
      prompts: promptArtifact,
      integrity_report_path: integrityCsvPath,
      input_schema_report_path: schemaReportPath,
    },
    counts: {
      source_generation_count: generations.length,
      source_prompt_count: prompts.length,
      selected_case_count: uniqueCaseCount(evidence),
      selected_package_count: evidence.length,
      selected_generation_count: selectedGenerations.length,
      selected_prompt_count: selectedPrompts.length,
      usable_generation_count: selectedGenerations.length - unusable.length,
      unusable_generation_count: unusable.length,
      excluded_non_cohort_generation_count: generations.length - selectedGenerations.length,
      excluded_non_cohort_prompt_count: prompts.length - selectedPrompts.length,
    },
    counts_by_level: Object.fromEntries(
      EVIDENCE_LEVELS.map((level) => [
        level,
        {
          total: selectedGenerations.filter((record) => record.evidence_level === level)
            .length,
          usable: selectedGenerations.filter(
            (record) =>
              record.evidence_level === level && getUsability(record).usable,
          ).length,
        },
      ]),
    ),
    unusable_records: unusable.map(({ record, usability }) => ({
      generation_id: record.generation_id,
      source_ir_id: record.source_ir_id,
      evidence_level: record.evidence_level,
      reason_codes: usability.reason_codes,
    })),
    integrity_checks: checks,
  };

  await writeJsonAtomic(manifestPath, manifest);
  return manifest;
}

function buildUniqueMap<T>(
  records: Array<{ line: number; value: T }>,
  getKey: (record: T) => string,
  label: string,
): Map<string, { line: number; value: T }> {
  const result = new Map<string, { line: number; value: T }>();

  for (const record of records) {
    const key = getKey(record.value);
    const existing = result.get(key);
    if (existing) {
      throw new Error(
        `Duplicate ${label} ${key} at lines ${existing.line} and ${record.line}.`,
      );
    }
    result.set(key, record);
  }

  return result;
}

function assertEvidenceCohort(records: EvidencePackageRecord[]): void {
  if (records.length !== 216) {
    throw new Error(`Expected 216 evidence packages, found ${records.length}.`);
  }

  const levelSetByCase = new Map<string, Set<string>>();
  for (const record of records) {
    const levels = levelSetByCase.get(record.source_ir_id) ?? new Set<string>();
    levels.add(record.evidence_level);
    levelSetByCase.set(record.source_ir_id, levels);
  }

  if (levelSetByCase.size !== 36) {
    throw new Error(`Expected 36 source_ir_id values, found ${levelSetByCase.size}.`);
  }

  for (const [sourceIrId, levels] of levelSetByCase) {
    if (levels.size !== EVIDENCE_LEVELS.length) {
      throw new Error(
        `${sourceIrId} has ${levels.size} evidence levels; expected ${EVIDENCE_LEVELS.length}.`,
      );
    }
    for (const level of EVIDENCE_LEVELS) {
      if (!levels.has(level)) {
        throw new Error(`${sourceIrId} is missing evidence level ${level}.`);
      }
    }
  }
}

function assertModelConsistency(
  records: Array<{ model_id: string }>,
  expectedModelId: string,
): void {
  const models = new Set(records.map((record) => record.model_id));
  if (models.size !== 1 || !models.has(expectedModelId)) {
    throw new Error(
      `Expected only model ${expectedModelId}, found ${[...models].join(", ")}.`,
    );
  }
}

function uniqueCaseCount(records: EvidencePackageRecord[]): number {
  return new Set(records.map((record) => record.source_ir_id)).size;
}

function minimumLevelsPerCase(records: EvidencePackageRecord[]): number {
  const counts = new Map<string, Set<string>>();
  for (const record of records) {
    const levels = counts.get(record.source_ir_id) ?? new Set<string>();
    levels.add(record.evidence_level);
    counts.set(record.source_ir_id, levels);
  }
  return Math.min(...[...counts.values()].map((levels) => levels.size));
}

function passCheck(
  checkId: string,
  expected: number,
  actual: number,
): IntegrityCheck {
  if (expected !== actual) {
    throw new Error(`${checkId} failed: expected ${expected}, found ${actual}.`);
  }
  return {
    check_id: checkId,
    status: "PASS",
    expected,
    actual,
    detail: "Verified.",
  };
}

function describeLoaded(input: {
  path: string;
  sha256: string;
  byte_count: number;
  records: unknown[];
}): JsonObject {
  return {
    path: input.path,
    sha256: input.sha256,
    byte_count: input.byte_count,
    record_count: input.records.length,
  };
}
