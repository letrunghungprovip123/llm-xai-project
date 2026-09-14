import {
  joinPath,
  listFilesRecursive,
  writeCsvFile,
  writeJsonFile,
  writeJsonlFile,
} from "./artifacts";
import { getOrderedCaseIds, loadEvidencePackages, readJsonl } from "./loaders";
import { parseExplanationOutput } from "./outputSchema";
import { buildSchemaMetrics } from "./metrics/schemaMetrics";
import type {
  EvidenceLevel,
  GenerationRecord,
  PromptInstanceRecord,
} from "../../../contracts/narrative";
import {
  average,
  getGitCommitHash,
  jaccard,
  percentile,
  standardDeviation,
} from "../common/utils";

export interface AggregateOptions {
  shards_dir: string;
  output_dir: string;
  run_id: string;
  experiment_stage: "development" | "evaluation";
  input_path?: string;
  model_ids?: string[];
  levels?: EvidenceLevel[];
  repeat_ids?: number[];
  chunk_start?: number;
  chunk_size?: number;
  limit_cases?: number;
}

export interface AggregateResult {
  status: "PASSED" | "PASSED_WITH_WARNINGS" | "FAILED";
  generation_count: number;
  duplicate_generation_count: number;
  missing_generation_count: number;
  output_path: string;
}

export async function aggregateNarrativeRun(
  options: AggregateOptions,
): Promise<AggregateResult> {
  const generationFiles = await listFilesRecursive(
    options.shards_dir,
    "generations.jsonl",
  );
  const promptFiles = await listFilesRecursive(
    options.shards_dir,
    "prompt_instances.jsonl",
  );

  if (generationFiles.length === 0) {
    throw new Error(
      `No generation shard files found under: ${options.shards_dir}`,
    );
  }

  const allGenerations: GenerationRecord[] = [];
  for (const filePath of generationFiles) {
    allGenerations.push(...(await readJsonl<GenerationRecord>(filePath)));
  }

  const allPrompts: PromptInstanceRecord[] = [];
  for (const filePath of promptFiles) {
    allPrompts.push(...(await readJsonl<PromptInstanceRecord>(filePath)));
  }

  const generationDedup = deduplicateGenerations(allGenerations);
  const promptDedup = deduplicatePrompts(allPrompts);
  const generations = generationDedup.records
    .map(refreshSchemaMetrics)
    .sort(compareGenerationRecords);
  const prompts = promptDedup.records.sort((left, right) => {
    return left.prompt_id.localeCompare(right.prompt_id);
  });

  const expectedIds = await buildExpectedGenerationIds(options, generations);
  const actualIds = new Set(generations.map((record) => record.generation_id));
  const missingIds = expectedIds.filter((id) => !actualIds.has(id));
  const unexpectedIds = generations
    .map((record) => record.generation_id)
    .filter((id) => expectedIds.length > 0 && !expectedIds.includes(id));

  const apiRows = generations.map(buildApiRow);
  const promptRows = generations.map(buildPromptRow);
  const schemaRows = generations.map(buildSchemaRow);
  const contentRows = generations.map(buildContentRow);
  const evidenceRows = generations.map(buildEvidenceRow);
  const stabilityRows = buildRepeatStabilityRows(generations);
  const summaryByLevelModel = buildSummaryRows(generations, [
    "evidence_level",
    "model_id",
  ]);
  const summaryByModel = buildSummaryRows(generations, ["model_id"]);
  const summaryByLevel = buildSummaryRows(generations, ["evidence_level"]);
  const cellRows = buildCellQualityRows(generations);

  const quality = buildQualityReport(
    options,
    generations,
    generationDedup.duplicateCount,
    expectedIds.length,
    missingIds,
    unexpectedIds,
    cellRows,
    generationFiles,
  );

  const mainOutput = joinPath(
    options.output_dir,
    "generated_explanations.jsonl",
  );
  const promptOutput = joinPath(options.output_dir, "prompt_instances.jsonl");

  await writeJsonlFile(mainOutput, generations);
  await writeJsonlFile(promptOutput, prompts);
  await writeCsvFile(
    joinPath(options.output_dir, "api_call_report.csv"),
    apiRows,
  );
  await writeCsvFile(
    joinPath(options.output_dir, "prompt_audit_report.csv"),
    promptRows,
  );
  await writeCsvFile(
    joinPath(options.output_dir, "schema_validation_report.csv"),
    schemaRows,
  );
  await writeCsvFile(
    joinPath(options.output_dir, "content_quality_report.csv"),
    contentRows,
  );
  await writeCsvFile(
    joinPath(options.output_dir, "evidence_mention_report.csv"),
    evidenceRows,
  );
  await writeCsvFile(
    joinPath(options.output_dir, "repeat_stability_report.csv"),
    stabilityRows,
  );
  await writeCsvFile(
    joinPath(options.output_dir, "summary_by_level_model.csv"),
    summaryByLevelModel,
  );
  await writeCsvFile(
    joinPath(options.output_dir, "summary_by_model.csv"),
    summaryByModel,
  );
  await writeCsvFile(
    joinPath(options.output_dir, "summary_by_level.csv"),
    summaryByLevel,
  );
  await writeCsvFile(
    joinPath(options.output_dir, "run_cell_quality_report.csv"),
    cellRows,
  );
  await writeCsvFile(
    joinPath(options.output_dir, "matrix_integrity_report.csv"),
    [
      {
        expected_generation_count: expectedIds.length || null,
        actual_generation_count: generations.length,
        duplicate_generation_count: generationDedup.duplicateCount,
        duplicate_prompt_count: promptDedup.duplicateCount,
        missing_generation_count: missingIds.length,
        unexpected_generation_count: unexpectedIds.length,
        missing_generation_ids: missingIds.join("|"),
        unexpected_generation_ids: unexpectedIds.join("|"),
      },
    ],
  );

  await writeJsonFile(
    joinPath(options.output_dir, "llm_narrative_generation_report.json"),
    quality,
  );

  await writeJsonFile(
    joinPath(
      options.output_dir,
      `llm_narrative_manifest_${options.experiment_stage}.json`,
    ),
    {
      batch: "Batch I - Multi-LLM Narrative Generation Layer",
      run_id: options.run_id,
      experiment_stage: options.experiment_stage,
      created_at: new Date().toISOString(),
      git_commit_hash: getGitCommitHash(),
      input_evidence_package_path: options.input_path || null,
      shards_dir: options.shards_dir,
      output_dir: options.output_dir,
      generation_shard_count: generationFiles.length,
      prompt_shard_count: promptFiles.length,
      generation_count: generations.length,
      prompt_instance_count: prompts.length,
      model_list: [...new Set(generations.map((record) => record.model_id))],
      prompt_versions: [
        ...new Set(generations.map((record) => record.prompt_version)),
      ],
      output_schema_versions: [
        ...new Set(generations.map((record) => record.output_schema_version)),
      ],
      repeat_ids: [
        ...new Set(generations.map((record) => record.repeat_id)),
      ].sort(),
      evidence_levels: [
        ...new Set(generations.map((record) => record.evidence_level)),
      ].sort(),
      quality_gate_status: quality.status,
      main_output: mainOutput,
      prompt_output: promptOutput,
      reports: {
        api_call_report: joinPath(options.output_dir, "api_call_report.csv"),
        prompt_audit_report: joinPath(
          options.output_dir,
          "prompt_audit_report.csv",
        ),
        schema_validation_report: joinPath(
          options.output_dir,
          "schema_validation_report.csv",
        ),
        content_quality_report: joinPath(
          options.output_dir,
          "content_quality_report.csv",
        ),
        evidence_mention_report: joinPath(
          options.output_dir,
          "evidence_mention_report.csv",
        ),
        repeat_stability_report: joinPath(
          options.output_dir,
          "repeat_stability_report.csv",
        ),
        summary_by_level_model: joinPath(
          options.output_dir,
          "summary_by_level_model.csv",
        ),
        summary_by_model: joinPath(options.output_dir, "summary_by_model.csv"),
        summary_by_level: joinPath(options.output_dir, "summary_by_level.csv"),
        matrix_integrity_report: joinPath(
          options.output_dir,
          "matrix_integrity_report.csv",
        ),
        run_cell_quality_report: joinPath(
          options.output_dir,
          "run_cell_quality_report.csv",
        ),
      },
    },
  );

  return {
    status: quality.status,
    generation_count: generations.length,
    duplicate_generation_count: generationDedup.duplicateCount,
    missing_generation_count: missingIds.length,
    output_path: mainOutput,
  };
}

function refreshSchemaMetrics(record: GenerationRecord): GenerationRecord {
  const parseResult = parseExplanationOutput(
    record.raw_output,
    record.evidence_level,
  );

  return {
    ...record,
    cleaned_output: parseResult.cleaned_output,
    parsed_output: parseResult.parsed_output,
    schema_metrics: buildSchemaMetrics(parseResult),
  };
}

function deduplicateGenerations(records: GenerationRecord[]): {
  records: GenerationRecord[];
  duplicateCount: number;
} {
  const map = new Map<string, GenerationRecord>();
  let duplicateCount = 0;

  for (const record of records) {
    const existing = map.get(record.generation_id);
    if (!existing) {
      map.set(record.generation_id, record);
      continue;
    }

    duplicateCount += 1;

    if (
      existing.runtime_metrics.status === "FAILED" &&
      record.runtime_metrics.status === "SUCCESS"
    ) {
      map.set(record.generation_id, record);
    }
  }

  return {
    records: [...map.values()],
    duplicateCount,
  };
}

function deduplicatePrompts(records: PromptInstanceRecord[]): {
  records: PromptInstanceRecord[];
  duplicateCount: number;
} {
  const map = new Map<string, PromptInstanceRecord>();
  let duplicateCount = 0;

  for (const record of records) {
    if (map.has(record.prompt_id)) {
      duplicateCount += 1;
      continue;
    }
    map.set(record.prompt_id, record);
  }

  return {
    records: [...map.values()],
    duplicateCount,
  };
}

async function buildExpectedGenerationIds(
  options: AggregateOptions,
  generations: GenerationRecord[],
): Promise<string[]> {
  if (!options.input_path) {
    return [];
  }

  const packages = await loadEvidencePackages(options.input_path);
  let caseIds = getOrderedCaseIds(packages);
  const chunkStart = options.chunk_start || 0;

  if (chunkStart > 0 || options.chunk_size !== undefined) {
    const end =
      options.chunk_size === undefined
        ? undefined
        : chunkStart + options.chunk_size;
    caseIds = caseIds.slice(chunkStart, end);
  }

  if (options.limit_cases !== undefined) {
    caseIds = caseIds.slice(0, options.limit_cases);
  }

  const caseSet = new Set(caseIds);
  const levels = options.levels || [
    ...new Set(generations.map((record) => record.evidence_level)),
  ];
  const levelSet = new Set(levels);
  const selectedPackages = packages.filter((packageItem) => {
    return (
      caseSet.has(packageItem.source_ir_id) &&
      levelSet.has(packageItem.evidence_level)
    );
  });

  const modelIds = options.model_ids || [
    ...new Set(generations.map((record) => record.model_id)),
  ];
  const repeatIds = options.repeat_ids || [
    ...new Set(generations.map((record) => record.repeat_id)),
  ];
  const result: string[] = [];

  for (const modelId of modelIds) {
    for (const repeatId of repeatIds) {
      for (const packageItem of selectedPackages) {
        result.push(
          [
            sanitizeId(options.run_id),
            sanitizeId(modelId),
            `r${repeatId}`,
            sanitizeId(packageItem.package_id),
          ].join("__"),
        );
      }
    }
  }

  return result;
}

function buildApiRow(record: GenerationRecord): Record<string, unknown> {
  return {
    generation_id: record.generation_id,
    run_id: record.run_id,
    package_id: record.package_id,
    source_ir_id: record.source_ir_id,
    evidence_level: record.evidence_level,
    model_id: record.model_id,
    remote_model_id: record.remote_model_id,
    model_revision: record.model_revision,
    repeat_id: record.repeat_id,
    status: record.runtime_metrics.status,
    error_type: record.runtime_metrics.error_type,
    error_message: record.runtime_metrics.error_message,
    retry_count: record.runtime_metrics.retry_count,
    finish_reason: record.runtime_metrics.finish_reason,
    latency_ms: record.runtime_metrics.latency_ms,
    input_token_count: record.runtime_metrics.input_token_count,
    output_token_count: record.runtime_metrics.output_token_count,
    total_token_count: record.runtime_metrics.total_token_count,
    empty_response: record.runtime_metrics.empty_response,
    truncated_response: record.runtime_metrics.truncated_response,
    provider_request_id: record.runtime_metrics.provider_request_id,
    provider_returned_model_id:
      record.runtime_metrics.provider_returned_model_id,
    provider_api_cost_usd: record.runtime_metrics.provider_api_cost_usd,
    infrastructure_cost_usd: record.runtime_metrics.infrastructure_cost_usd,
    total_cost_usd: record.runtime_metrics.total_cost_usd,
  };
}

function buildPromptRow(record: GenerationRecord): Record<string, unknown> {
  return {
    generation_id: record.generation_id,
    package_id: record.package_id,
    evidence_level: record.evidence_level,
    model_id: record.model_id,
    repeat_id: record.repeat_id,
    prompt_id: record.prompt_id,
    prompt_message_sha256: record.prompt_message_sha256,
    prompt_char_count: record.prompt_metrics.prompt_char_count,
    prompt_estimated_token_count:
      record.prompt_metrics.prompt_estimated_token_count,
    actual_input_token_count: record.runtime_metrics.input_token_count,
    has_prediction_section: record.prompt_metrics.has_prediction_section,
    has_evidence_section: record.prompt_metrics.has_evidence_section,
    has_constraints_section: record.prompt_metrics.has_constraints_section,
    has_output_schema_section: record.prompt_metrics.has_output_schema_section,
    has_entropy_policy_section:
      record.prompt_metrics.has_entropy_policy_section,
    has_concept_grouping_section:
      record.prompt_metrics.has_concept_grouping_section,
    has_backend_skeleton_section:
      record.prompt_metrics.has_backend_skeleton_section,
  };
}

function buildSchemaRow(record: GenerationRecord): Record<string, unknown> {
  return {
    generation_id: record.generation_id,
    package_id: record.package_id,
    evidence_level: record.evidence_level,
    model_id: record.model_id,
    repeat_id: record.repeat_id,
    raw_json_parse_success: record.schema_metrics.raw_json_parse_success,
    json_parse_success: record.schema_metrics.json_parse_success,
    schema_valid: record.schema_metrics.schema_valid,
    missing_required_field_count:
      record.schema_metrics.missing_required_field_count,
    validation_error_count: record.schema_metrics.validation_error_count,
    cleanup_type: record.schema_metrics.cleanup_type,
  };
}

function buildContentRow(record: GenerationRecord): Record<string, unknown> {
  return {
    generation_id: record.generation_id,
    package_id: record.package_id,
    evidence_level: record.evidence_level,
    model_id: record.model_id,
    repeat_id: record.repeat_id,
    ...record.content_metrics,
    ...record.policy_metrics,
  };
}

function buildEvidenceRow(record: GenerationRecord): Record<string, unknown> {
  return {
    generation_id: record.generation_id,
    package_id: record.package_id,
    source_ir_id: record.source_ir_id,
    evidence_level: record.evidence_level,
    model_id: record.model_id,
    repeat_id: record.repeat_id,
    coverage: record.input_snapshot.coverage,
    coverage_status: record.input_snapshot.coverage_status,
    entropy_level: record.input_snapshot.entropy_level,
    ...record.evidence_mention_metrics,
  };
}

function buildRepeatStabilityRows(
  generations: GenerationRecord[],
): Record<string, unknown>[] {
  const groups = new Map<string, GenerationRecord[]>();

  for (const record of generations) {
    const key = [
      record.source_ir_id,
      record.evidence_level,
      record.model_id,
    ].join("|");

    const current = groups.get(key) || [];
    current.push(record);
    groups.set(key, current);
  }

  const rows: Record<string, unknown>[] = [];

  for (const records of groups.values()) {
    const sorted = [...records].sort((a, b) => a.repeat_id - b.repeat_id);
    const valid = sorted.filter((record) => record.parsed_output !== null);
    const lengths = valid.map(
      (record) => record.content_metrics.output_word_count,
    );
    const factorCounts = valid.map(
      (record) => record.content_metrics.total_factor_count,
    );
    const featureJaccards: number[] = [];
    const conceptJaccards: number[] = [];

    for (let left = 0; left < valid.length; left += 1) {
      for (let right = left + 1; right < valid.length; right += 1) {
        featureJaccards.push(
          jaccard(
            collectDeclaredFeatureIds(valid[left]),
            collectDeclaredFeatureIds(valid[right]),
          ),
        );
        conceptJaccards.push(
          jaccard(
            collectDeclaredConceptIds(valid[left]),
            collectDeclaredConceptIds(valid[right]),
          ),
        );
      }
    }

    rows.push({
      source_ir_id: sorted[0].source_ir_id,
      evidence_level: sorted[0].evidence_level,
      model_id: sorted[0].model_id,
      repeat_count: sorted.length,
      successful_repeat_count: valid.length,
      schema_stability_rate:
        sorted.length > 0
          ? sorted.filter((record) => record.schema_metrics.schema_valid)
              .length / sorted.length
          : null,
      output_length_std: standardDeviation(lengths),
      main_factor_count_std: standardDeviation(factorCounts),
      mentioned_feature_jaccard: average(featureJaccards),
      mentioned_concept_jaccard: average(conceptJaccards),
    });
  }

  return rows;
}

function buildSummaryRows(
  records: GenerationRecord[],
  groupFields: Array<"evidence_level" | "model_id">,
): Record<string, unknown>[] {
  const groups = new Map<string, GenerationRecord[]>();

  for (const record of records) {
    const key = groupFields.map((field) => String(record[field])).join("|");
    const current = groups.get(key) || [];
    current.push(record);
    groups.set(key, current);
  }

  const rows: Record<string, unknown>[] = [];

  for (const group of groups.values()) {
    const row: Record<string, unknown> = {};
    for (const field of groupFields) {
      row[field] = group[0][field];
    }

    const latencies = group
      .filter((record) => record.runtime_metrics.status === "SUCCESS")
      .map((record) => record.runtime_metrics.latency_ms);
    const inputTokens = collectNumbers(
      group.map((record) => record.runtime_metrics.input_token_count),
    );
    const outputTokens = collectNumbers(
      group.map((record) => record.runtime_metrics.output_token_count),
    );
    const totalTokens = collectNumbers(
      group.map((record) => record.runtime_metrics.total_token_count),
    );
    const costs = collectNumbers(
      group.map((record) => record.runtime_metrics.total_cost_usd),
    );

    Object.assign(row, {
      generation_count: group.length,
      runtime_success_rate: rate(
        group,
        (record) => record.runtime_metrics.status === "SUCCESS",
      ),
      json_parse_success_rate: rate(
        group,
        (record) => record.schema_metrics.json_parse_success,
      ),
      schema_validity_rate: rate(
        group,
        (record) => record.schema_metrics.schema_valid,
      ),
      empty_response_rate: rate(
        group,
        (record) => record.runtime_metrics.empty_response,
      ),
      truncated_response_rate: rate(
        group,
        (record) => record.runtime_metrics.truncated_response,
      ),
      uncertainty_compliance_rate: conditionalRate(
        group,
        (record) => record.policy_metrics.uncertainty_required,
        (record) => record.policy_metrics.uncertainty_compliant === true,
      ),
      distributed_note_compliance_rate: conditionalRate(
        group,
        (record) => record.policy_metrics.distributed_note_required,
        (record) => record.policy_metrics.distributed_note_compliant === true,
      ),
      single_cause_violation_rate: rate(
        group,
        (record) => record.policy_metrics.single_cause_violation,
      ),
      forbidden_phrase_violation_rate: rate(
        group,
        (record) => record.policy_metrics.forbidden_phrase_violation,
      ),
      average_latency_ms: average(latencies),
      p95_latency_ms: percentile(latencies, 95),
      p99_latency_ms: percentile(latencies, 99),
      average_input_tokens: average(inputTokens),
      average_output_tokens: average(outputTokens),
      average_total_tokens: average(totalTokens),
      average_total_cost_usd: average(costs),
      estimated_total_cost_usd:
        costs.length > 0 ? costs.reduce((sum, value) => sum + value, 0) : null,
      average_output_word_count: average(
        group.map((record) => record.content_metrics.output_word_count),
      ),
      average_factor_count: average(
        group.map((record) => record.content_metrics.total_factor_count),
      ),
      average_selected_feature_mention_rate: average(
        collectNumbers(
          group.map(
            (record) =>
              record.evidence_mention_metrics.selected_feature_mention_rate,
          ),
        ),
      ),
      average_concept_mention_rate: average(
        collectNumbers(
          group.map(
            (record) => record.evidence_mention_metrics.concept_mention_rate,
          ),
        ),
      ),
    });

    rows.push(row);
  }

  return rows.sort((left, right) =>
    JSON.stringify(left).localeCompare(JSON.stringify(right)),
  );
}

function buildCellQualityRows(
  records: GenerationRecord[],
): Record<string, unknown>[] {
  return buildSummaryRows(records, ["evidence_level", "model_id"]);
}

function buildQualityReport(
  options: AggregateOptions,
  records: GenerationRecord[],
  duplicateCount: number,
  expectedGenerationCount: number,
  missingIds: string[],
  unexpectedIds: string[],
  cellRows: Record<string, unknown>[],
  generationFiles: string[],
): {
  batch: string;
  run_id: string;
  status: "PASSED" | "PASSED_WITH_WARNINGS" | "FAILED";
  created_at: string;
  experiment_stage: string;
  generation_shard_count: number;
  expected_generation_count: number | null;
  actual_generation_count: number;
  completed_generation_count: number;
  failed_generation_count: number;
  duplicate_generation_count: number;
  missing_generation_count: number;
  unexpected_generation_count: number;
  generation_completion_rate: number | null;
  runtime_success_rate: number;
  json_parse_success_rate: number;
  schema_validity_rate: number;
  empty_output_rate: number;
  missing_prompt_section_count: number;
  errors: string[];
  warnings: string[];
} {
  const errors: string[] = [];
  const warnings: string[] = [];
  const expectedCount =
    expectedGenerationCount > 0 ? expectedGenerationCount : null;

  const completed = records.filter((record) => {
    return record.runtime_metrics.status === "SUCCESS";
  }).length;
  const runtimeSuccessRate =
    records.length > 0 ? completed / records.length : 0;
  const jsonParseRate = rate(
    records,
    (record) => record.schema_metrics.json_parse_success,
  );
  const schemaRate = rate(
    records,
    (record) => record.schema_metrics.schema_valid,
  );
  const emptyRate = rate(
    records,
    (record) => record.runtime_metrics.empty_response,
  );
  const missingPromptSectionCount = records.filter((record) => {
    const metrics = record.prompt_metrics;
    return (
      !metrics.has_prediction_section ||
      !metrics.has_evidence_section ||
      !metrics.has_constraints_section ||
      !metrics.has_output_schema_section
    );
  }).length;

  if (duplicateCount > 0) {
    errors.push("Duplicate generation IDs were found across shards.");
  }
  if (missingIds.length > 0) {
    errors.push("Some expected generation IDs are missing.");
  }
  if (unexpectedIds.length > 0) {
    warnings.push("Some generation IDs were not part of the expected matrix.");
  }
  if (missingPromptSectionCount > 0) {
    errors.push("Some prompts are missing required sections.");
  }
  if (emptyRate > 0) {
    errors.push("Some generation records have empty responses.");
  }

  if (options.experiment_stage === "evaluation") {
    if (runtimeSuccessRate < 0.95) {
      errors.push("Runtime success rate is below 0.95.");
    }
    if (jsonParseRate < 0.9) {
      errors.push("JSON parse success rate is below 0.90.");
    }
    if (schemaRate < 0.85) {
      errors.push("Schema validity rate is below 0.85.");
    }
  } else {
    if (runtimeSuccessRate < 0.95) {
      warnings.push("Development runtime success rate is below 0.95.");
    }
    if (jsonParseRate < 0.95) {
      warnings.push("Development JSON parse success rate is below 0.95.");
    }
    if (schemaRate < 0.95) {
      warnings.push("Development schema validity rate is below 0.95.");
    }
  }

  for (const cell of cellRows) {
    const cellRuntime = readRowNumber(cell.runtime_success_rate);
    const cellSchema = readRowNumber(cell.schema_validity_rate);

    if (cellRuntime !== null && cellRuntime < 0.9) {
      warnings.push(
        `Cell ${cell.model_id}/${cell.evidence_level} runtime success is below 0.90.`,
      );
    }

    if (cellSchema !== null && cellSchema < 0.8) {
      warnings.push(
        `Cell ${cell.model_id}/${cell.evidence_level} schema validity is below 0.80.`,
      );
    }
  }

  let status: "PASSED" | "PASSED_WITH_WARNINGS" | "FAILED" = "PASSED";
  if (warnings.length > 0) {
    status = "PASSED_WITH_WARNINGS";
  }
  if (errors.length > 0) {
    status = "FAILED";
  }

  return {
    batch: "Batch I - Multi-LLM Narrative Generation Layer",
    run_id: options.run_id,
    status,
    created_at: new Date().toISOString(),
    experiment_stage: options.experiment_stage,
    generation_shard_count: generationFiles.length,
    expected_generation_count: expectedCount,
    actual_generation_count: records.length,
    completed_generation_count: completed,
    failed_generation_count: records.length - completed,
    duplicate_generation_count: duplicateCount,
    missing_generation_count: missingIds.length,
    unexpected_generation_count: unexpectedIds.length,
    generation_completion_rate:
      expectedCount && expectedCount > 0
        ? records.length / expectedCount
        : null,
    runtime_success_rate: runtimeSuccessRate,
    json_parse_success_rate: jsonParseRate,
    schema_validity_rate: schemaRate,
    empty_output_rate: emptyRate,
    missing_prompt_section_count: missingPromptSectionCount,
    errors,
    warnings,
  };
}

function collectDeclaredFeatureIds(record: GenerationRecord): string[] {
  if (!record.parsed_output) {
    return [];
  }

  return [
    ...new Set(
      record.parsed_output.factors.flatMap((factor) => {
        return factor.declared_feature_ids;
      }),
    ),
  ];
}

function collectDeclaredConceptIds(record: GenerationRecord): string[] {
  if (!record.parsed_output) {
    return [];
  }

  return [
    ...new Set(
      record.parsed_output.factors.flatMap((factor) => {
        return factor.declared_concept_ids;
      }),
    ),
  ];
}

function rate<T>(items: T[], predicate: (item: T) => boolean): number {
  if (items.length === 0) {
    return 0;
  }

  return items.filter(predicate).length / items.length;
}

function conditionalRate<T>(
  items: T[],
  applies: (item: T) => boolean,
  passes: (item: T) => boolean,
): number | null {
  const applicable = items.filter(applies);
  if (applicable.length === 0) {
    return null;
  }

  return applicable.filter(passes).length / applicable.length;
}

function collectNumbers(values: Array<number | null>): number[] {
  return values.filter((value): value is number => {
    return typeof value === "number" && Number.isFinite(value);
  });
}

function compareGenerationRecords(
  left: GenerationRecord,
  right: GenerationRecord,
): number {
  const leftKey = [
    left.model_id,
    String(left.repeat_id).padStart(3, "0"),
    left.source_ir_id,
    left.evidence_level,
  ].join("|");
  const rightKey = [
    right.model_id,
    String(right.repeat_id).padStart(3, "0"),
    right.source_ir_id,
    right.evidence_level,
  ].join("|");

  return leftKey.localeCompare(rightKey);
}

function sanitizeId(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, "_");
}

function readRowNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
