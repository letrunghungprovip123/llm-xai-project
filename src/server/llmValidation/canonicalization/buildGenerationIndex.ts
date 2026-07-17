import path from "node:path";

import {
  cohortKey,
  evidencePackageHash,
  extractCaseId,
  getRuntimeBoolean,
  getRuntimeString,
  getSchemaBoolean,
  getUsability,
  matrixKey,
  parseEvidencePackage,
  parseGenerationRecord,
  parsePromptRecord,
  verifyGenerationAgainstEvidence,
} from "./contracts";
import {
  copyFileVerified,
  profileCsv,
  profileJson,
  profileJsonl,
  readCsvStrict,
  readJsonStrict,
  readJsonlStrict,
  writeCsvAtomic,
  writeJsonAtomic,
  writeJsonlAtomic,
  writeTextArtifactAtomic,
  type LoadedJsonl,
} from "./io";
import {
  EVIDENCE_LEVELS,
  CANONICALIZATION_TOOL_VERSION,
  type CanonicalGenerationRow,
  type EvidencePackageRecord,
  type FileProfile,
  type GenerationRecordLike,
  type IntegrityCheck,
  type JsonObject,
  type ModelSource,
  type PromptRecordLike,
} from "../../../types/llm-validation";

export type BuildGenerationIndexOptions = {
  evidence_path: string;
  selected_cases_path?: string;
  selection_manifest_path?: string;
  feature_registry_path?: string;
  main_sources: ModelSource[];
  baseline_source?: ModelSource;
  output_dir: string;
  strict_official_counts?: boolean;
};

type LoadedSource = {
  config: ModelSource;
  generations: LoadedJsonl<JsonObject>;
  prompts: LoadedJsonl<JsonObject>;
  manifest?: Awaited<ReturnType<typeof readJsonStrict<JsonObject>>>;
  generation_entries: Array<{ line: number; value: GenerationRecordLike }>;
  prompt_entries: Array<{ line: number; value: PromptRecordLike }>;
};

const OFFICIAL_MAIN_MODELS = [
  "qwen3_8b",
  "deepseek_v4_flash",
  "phi4_mini_instruct",
] as const;

const OFFICIAL_USABLE_COUNTS: Record<string, number> = {
  qwen3_8b: 216,
  deepseek_v4_flash: 213,
  phi4_mini_instruct: 209,
};

export async function buildGenerationIndex(
  options: BuildGenerationIndexOptions,
): Promise<JsonObject> {
  const strictOfficialCounts = options.strict_official_counts ?? true;
  validateSourceConfiguration(options.main_sources, options.baseline_source);

  const outputDir = path.resolve(options.output_dir);
  const rawEvidence = await readJsonlStrict<JsonObject>(options.evidence_path);
  const evidence = rawEvidence.records.map(({ line, value }) =>
    parseEvidencePackage(value, `${rawEvidence.path}:${line}`),
  );
  assertEvidenceCohort(evidence);

  const profiles: FileProfile[] = [profileJsonl(rawEvidence)];
  const auditWarnings: JsonObject[] = [];
  const integrityChecks: IntegrityCheck[] = [];

  const selection = await loadAndValidateSelectionInputs({
    evidence,
    evidenceFileSha256: rawEvidence.sha256,
    selectedCasesPath: options.selected_cases_path,
    selectionManifestPath: options.selection_manifest_path,
    profiles,
    auditWarnings,
    checks: integrityChecks,
  });

  const orderedEvidence = orderEvidence(evidence, selection.case_order);
  const restrictedFeatures = options.feature_registry_path
    ? await loadRestrictedFeatureIds(options.feature_registry_path, profiles)
    : new Set<string>();

  const loadedMainSources: LoadedSource[] = [];
  for (const source of options.main_sources) {
    loadedMainSources.push(await loadSource(source, profiles));
  }

  const loadedBaseline = options.baseline_source
    ? await loadSource(options.baseline_source, profiles)
    : undefined;

  const mainRows: CanonicalGenerationRow[] = [];
  for (let modelIndex = 0; modelIndex < loadedMainSources.length; modelIndex += 1) {
    const rows = buildRowsForSource({
      source: loadedMainSources[modelIndex],
      evidence: orderedEvidence,
      modelOrder: modelIndex + 1,
      matrixRole: "main",
    });
    mainRows.push(...rows);
  }

  const baselineRows = loadedBaseline
    ? buildRowsForSource({
        source: loadedBaseline,
        evidence: orderedEvidence,
        modelOrder: 1,
        matrixRole: "baseline",
      })
    : [];

  assertUniqueRows(mainRows, "main generation index");
  assertUniqueRows(baselineRows, "baseline generation index");
  validatePromptFairness(mainRows, integrityChecks);
  validateMatrixCounts({
    mainRows,
    baselineRows,
    strictOfficialCounts,
    checks: integrityChecks,
  });

  const dataContractAudit = buildDataContractAudit({
    evidence: orderedEvidence,
    mainRows,
    baselineRows,
    restrictedFeatureIds: restrictedFeatures,
  });
  auditWarnings.push(...dataContractAudit.warnings);

  const evidenceOutputPath = path.join(outputDir, "evidence_packages_36.jsonl");
  const generationIndexPath = path.join(outputDir, "generation_index.jsonl");
  const generationIndexCsvPath = path.join(outputDir, "generation_index.csv");
  const baselineIndexPath = path.join(outputDir, "template_baseline_index.jsonl");
  const baselineIndexCsvPath = path.join(outputDir, "template_baseline_index.csv");
  const sourceMapPath = path.join(outputDir, "canonical_sources.json");
  const integrityReportPath = path.join(outputDir, "matrix_integrity_report.csv");
  const schemaReportPath = path.join(outputDir, "input_schema_report.json");
  const auditJsonPath = path.join(outputDir, "phase0_audit_report.json");
  const auditMarkdownPath = path.join(outputDir, "phase0_audit_report.md");
  const manifestPath = path.join(outputDir, "phase0_manifest.json");

  const evidenceArtifact = await copyFileVerified(rawEvidence.path, evidenceOutputPath);
  evidenceArtifact.record_count = evidence.length;
  const generationIndexArtifact = await writeJsonlAtomic(
    generationIndexPath,
    mainRows,
  );
  const generationIndexCsvArtifact = await writeCsvAtomic(
    generationIndexCsvPath,
    mainRows.map(toCompactCsvRow),
  );
  const baselineIndexArtifact = await writeJsonlAtomic(
    baselineIndexPath,
    baselineRows,
  );
  const baselineIndexCsvArtifact = await writeCsvAtomic(
    baselineIndexCsvPath,
    baselineRows.map(toCompactCsvRow),
  );

  const canonicalSources = buildCanonicalSourceMap({
    evidence: rawEvidence,
    selection,
    mainSources: loadedMainSources,
    baselineSource: loadedBaseline,
  });
  const sourceMapArtifact = await writeJsonAtomic(sourceMapPath, canonicalSources);

  const integrityRows = buildIntegrityRows(mainRows, baselineRows);
  const integrityReportArtifact = await writeCsvAtomic(
    integrityReportPath,
    integrityRows,
  );
  const schemaReportArtifact = await writeJsonAtomic(schemaReportPath, {
    phase: "Phase 0",
    tool_version: CANONICALIZATION_TOOL_VERSION,
    profile_count: profiles.length,
    profiles,
  });

  const auditReport: JsonObject = {
    phase: "Phase 0",
    tool_version: CANONICALIZATION_TOOL_VERSION,
    status: auditWarnings.length === 0 ? "PASSED" : "PASSED_WITH_WARNINGS",
    created_at: new Date().toISOString(),
    canonical_key: "model_id::repeat_id::source_ir_id::evidence_level",
    cohort_key: "source_ir_id::evidence_level",
    matrix_counts: summarizeMatrix(mainRows, baselineRows),
    integrity_checks: integrityChecks,
    data_contract_audit: dataContractAudit.summary,
    warnings: auditWarnings,
    scope_note:
      "Phase 0 validates syntax, identity, hashes, cohort completeness, prompt parity, and observed package-contract inconsistencies. It does not run the semantic validator.",
  };
  const auditJsonArtifact = await writeJsonAtomic(auditJsonPath, auditReport);
  const auditMarkdownArtifact = await writeTextArtifactAtomic(
    auditMarkdownPath,
    buildAuditMarkdown(auditReport, mainRows, baselineRows),
  );

  const manifest: JsonObject = {
    phase: "Phase 0",
    operation: "build_canonical_generation_index",
    tool_version: CANONICALIZATION_TOOL_VERSION,
    status: auditWarnings.length === 0 ? "PASSED" : "PASSED_WITH_WARNINGS",
    created_at: new Date().toISOString(),
    strict_official_counts: strictOfficialCounts,
    raw_official_artifacts_modified: false,
    main_model_order: options.main_sources.map((source) => source.model_id),
    outputs: {
      evidence_packages_36: evidenceArtifact,
      generation_index_jsonl: generationIndexArtifact,
      generation_index_csv: generationIndexCsvArtifact,
      template_baseline_index_jsonl: baselineIndexArtifact,
      template_baseline_index_csv: baselineIndexCsvArtifact,
      canonical_sources: sourceMapArtifact,
      matrix_integrity_report: integrityReportArtifact,
      input_schema_report: schemaReportArtifact,
      phase0_audit_report_json: auditJsonArtifact,
      phase0_audit_report_md: auditMarkdownArtifact,
    },
    counts: summarizeMatrix(mainRows, baselineRows),
    integrity_check_count: integrityChecks.length,
    warning_count: auditWarnings.length,
  };

  await writeJsonAtomic(manifestPath, manifest);
  return manifest;
}

async function loadSource(
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

  assertOnlyModel(generationEntries.map((entry) => entry.value.model_id), config.model_id);
  assertOnlyModel(promptEntries.map((entry) => entry.value.model_id), config.model_id);

  return {
    config,
    generations,
    prompts,
    manifest,
    generation_entries: generationEntries,
    prompt_entries: promptEntries,
  };
}

function buildRowsForSource(input: {
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
  for (let evidenceIndex = 0; evidenceIndex < input.evidence.length; evidenceIndex += 1) {
    const packageItem = input.evidence[evidenceIndex];
    const key = cohortKey(packageItem);
    const generationEntry = generationByKey.get(key);
    const promptEntry = promptByKey.get(key);
    if (!generationEntry) throw new Error(`${input.source.config.model_id} is missing ${key}.`);
    if (!promptEntry) throw new Error(`${input.source.config.model_id} prompt is missing ${key}.`);

    verifyGenerationAgainstEvidence({
      generation: generationEntry.value,
      evidence: packageItem,
      prompt: promptEntry.value,
      expectedModelId: input.source.config.model_id,
      context: `${input.source.config.model_id}:${key}`,
    });

    const generation = generationEntry.value;
    const usability = getUsability(generation);
    const evidenceLevelOrder = EVIDENCE_LEVELS.indexOf(generation.evidence_level);
    const caseOrder = Math.floor(evidenceIndex / EVIDENCE_LEVELS.length) + 1;

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
      raw_json_parse_success: getSchemaBoolean(generation, "raw_json_parse_success"),
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

async function loadAndValidateSelectionInputs(input: {
  evidence: EvidencePackageRecord[];
  evidenceFileSha256: string;
  selectedCasesPath?: string;
  selectionManifestPath?: string;
  profiles: FileProfile[];
  auditWarnings: JsonObject[];
  checks: IntegrityCheck[];
}): Promise<{
  case_order: string[];
  selected_cases?: Awaited<ReturnType<typeof readCsvStrict>>;
  selection_manifest?: Awaited<ReturnType<typeof readJsonStrict<JsonObject>>>;
}> {
  const evidenceCaseIds = [...new Set(input.evidence.map((item) => item.source_ir_id))];
  let selectedCases: Awaited<ReturnType<typeof readCsvStrict>> | undefined;
  let selectionManifest:
    | Awaited<ReturnType<typeof readJsonStrict<JsonObject>>>
    | undefined;

  if (input.selectedCasesPath) {
    selectedCases = await readCsvStrict(input.selectedCasesPath);
    input.profiles.push(profileCsv(selectedCases));
    if (!selectedCases.headers.includes("case_id")) {
      throw new Error(`${selectedCases.path} is missing the case_id column.`);
    }
    const selectedIds = selectedCases.rows.map((row) => row.case_id);
    assertNoDuplicateStrings(selectedIds, "selected case_id");
    assertSameStringSet(selectedIds, evidenceCaseIds, "selected cases vs evidence cases");
    input.checks.push(passCheck("selected_case_csv_count", 36, selectedIds.length));
  }

  if (input.selectionManifestPath) {
    selectionManifest = await readJsonStrict<JsonObject>(input.selectionManifestPath);
    input.profiles.push(profileJson(selectionManifest));
    assertManifestNumber(selectionManifest.value, "selected_case_count", 36);
    assertManifestNumber(selectionManifest.value, "selected_package_count", 216);
    assertManifestString(
      selectionManifest.value,
      "subset_sha256",
      input.evidenceFileSha256,
    );
    input.checks.push(passCheck("selection_manifest_case_count", 36, 36));
    input.checks.push(passCheck("selection_manifest_package_count", 216, 216));
    input.checks.push(
      passCheck("selection_manifest_subset_hash", input.evidenceFileSha256, input.evidenceFileSha256),
    );
    input.auditWarnings.push({
      warning_id: "selection_source_not_reproducible_from_uploaded_subset",
      severity: "provenance",
      detail:
        "The selection manifest references the full 120-case evidence source, which is not part of the Phase 0 input bundle. The supplied 36-case subset and selection CSV are internally consistent, but the original selection cannot be rerun from this bundle alone.",
    });
  }

  if (selectedCases && selectionManifest) {
    input.auditWarnings.push({
      warning_id: "selected_case_csv_hash_not_recorded_in_selection_manifest",
      severity: "provenance",
      detail:
        "The selection manifest names selected_case_ids_36.csv but does not store its SHA-256 hash.",
    });
  }

  return {
    case_order: selectedCases
      ? selectedCases.rows.map((row) => row.case_id)
      : evidenceCaseIds,
    selected_cases: selectedCases,
    selection_manifest: selectionManifest,
  };
}

async function loadRestrictedFeatureIds(
  featureRegistryPath: string,
  profiles: FileProfile[],
): Promise<Set<string>> {
  const registry = await readCsvStrict(featureRegistryPath);
  profiles.push(profileCsv(registry));
  for (const required of [
    "feature_name",
    "sensitive",
    "allowed_in_user_explanation",
  ]) {
    if (!registry.headers.includes(required)) {
      throw new Error(`${registry.path} is missing column ${required}.`);
    }
  }

  return new Set(
    registry.rows
      .filter(
        (row) =>
          row.sensitive.trim().toLowerCase() === "true" ||
          row.allowed_in_user_explanation.trim().toLowerCase() !== "true",
      )
      .map((row) => row.feature_name),
  );
}

function buildDataContractAudit(input: {
  evidence: EvidencePackageRecord[];
  mainRows: CanonicalGenerationRow[];
  baselineRows: CanonicalGenerationRow[];
  restrictedFeatureIds: Set<string>;
}): { summary: JsonObject; warnings: JsonObject[] } {
  const conceptPolicyContradictions: string[] = [];
  const s5ExposureMismatches: string[] = [];
  let restrictedPackageCount = 0;
  let restrictedDistinctFeatureOccurrences = 0;
  const restrictedCases = new Set<string>();
  const restrictedIds = new Set<string>();

  for (const packageItem of input.evidence) {
    const constraints = asObject(packageItem.constraints);
    const claimPolicy = asObject(constraints.claim_policy);
    const allowedConceptIds = stringArray(constraints.allowed_concept_ids);
    const selectedEvidence = objectArray(packageItem.selected_evidence);
    const selectedFeatureIds = new Set(
      selectedEvidence.map((item) => stringValue(item.feature_id)).filter(Boolean),
    );

    if (
      (packageItem.evidence_level === "S2" || packageItem.evidence_level === "S3") &&
      claimPolicy.allow_concept_claim === true &&
      allowedConceptIds.length === 0 &&
      selectedEvidence.some((item) => Boolean(stringValue(item.concept)))
    ) {
      conceptPolicyContradictions.push(packageItem.package_id);
    }

    if (packageItem.evidence_level === "S5") {
      const allowedFeatureIds = new Set(stringArray(constraints.allowed_feature_ids));
      const extraExposed = [...selectedFeatureIds].filter((id) => !allowedFeatureIds.has(id));
      if (extraExposed.length > 0) s5ExposureMismatches.push(packageItem.package_id);
    }

    if (input.restrictedFeatureIds.size > 0) {
      const exposedRestricted = [...selectedFeatureIds].filter((id) =>
        input.restrictedFeatureIds.has(id),
      );
      if (exposedRestricted.length > 0) {
        restrictedPackageCount += 1;
        restrictedDistinctFeatureOccurrences += exposedRestricted.length;
        restrictedCases.add(packageItem.source_ir_id);
        exposedRestricted.forEach((id) => restrictedIds.add(id));
      }
    }
  }

  const outputExposureByModel: Record<string, JsonObject> = {};
  for (const row of [...input.mainRows, ...input.baselineRows]) {
    const output = asObject(row.generation_record.parsed_output);
    const declared = objectArray(output.factors).flatMap((factor) =>
      stringArray(factor.declared_feature_ids),
    );
    const restrictedDeclared = declared.filter((id) => input.restrictedFeatureIds.has(id));
    const summary = (outputExposureByModel[row.model_id] ??= {
      generation_count: 0,
      affected_generation_count: 0,
      restricted_declaration_count: 0,
    });
    summary.generation_count = Number(summary.generation_count) + 1;
    if (restrictedDeclared.length > 0) {
      summary.affected_generation_count = Number(summary.affected_generation_count) + 1;
      summary.restricted_declaration_count =
        Number(summary.restricted_declaration_count) + restrictedDeclared.length;
    }
  }

  const warnings: JsonObject[] = [];
  if (conceptPolicyContradictions.length > 0) {
    warnings.push({
      warning_id: "concept_claim_policy_vs_allowlist_mismatch",
      severity: "contract",
      affected_package_count: conceptPolicyContradictions.length,
      evidence_levels: ["S2", "S3"],
      detail:
        "Concept claims are enabled and concept metadata is exposed, while allowed_concept_ids is empty.",
    });
  }
  if (s5ExposureMismatches.length > 0) {
    warnings.push({
      warning_id: "s5_exposed_features_outside_allowed_feature_ids",
      severity: "contract",
      affected_package_count: s5ExposureMismatches.length,
      detail:
        "S5 prompt payloads expose selected feature evidence that is not present in the S5 allowed_feature_ids list.",
    });
  }
  if (restrictedPackageCount > 0) {
    warnings.push({
      warning_id: "restricted_registry_features_exposed_to_prompts",
      severity: "privacy_contract",
      affected_package_count: restrictedPackageCount,
      affected_case_count: restrictedCases.size,
      unique_restricted_feature_count: restrictedIds.size,
      detail:
        "Features marked sensitive or limited in feature_registry.csv occur in selected evidence supplied to the narrative prompt.",
    });
  }

  return {
    summary: {
      concept_policy_contradiction_package_count: conceptPolicyContradictions.length,
      s5_exposure_mismatch_package_count: s5ExposureMismatches.length,
      restricted_registry_feature_count: input.restrictedFeatureIds.size,
      restricted_feature_affected_package_count: restrictedPackageCount,
      restricted_feature_affected_case_count: restrictedCases.size,
      restricted_feature_unique_exposed_count: restrictedIds.size,
      restricted_feature_distinct_occurrences_across_packages:
        restrictedDistinctFeatureOccurrences,
      restricted_feature_ids_exposed: [...restrictedIds].sort(),
      restricted_output_declarations_by_model: outputExposureByModel,
    },
    warnings,
  };
}

function validatePromptFairness(
  rows: CanonicalGenerationRow[],
  checks: IntegrityCheck[],
): void {
  const hashesByCohort = new Map<string, Set<string>>();
  for (const row of rows) {
    const hashes = hashesByCohort.get(row.cohort_key) ?? new Set<string>();
    hashes.add(row.prompt_message_sha256);
    hashesByCohort.set(row.cohort_key, hashes);
  }

  const mismatchCount = [...hashesByCohort.values()].filter(
    (hashes) => hashes.size !== 1,
  ).length;
  if (mismatchCount !== 0) {
    throw new Error(`${mismatchCount} cohort cells have model-dependent prompt hashes.`);
  }
  checks.push(passCheck("cross_model_prompt_hash_mismatch_count", 0, mismatchCount));
}

function validateMatrixCounts(input: {
  mainRows: CanonicalGenerationRow[];
  baselineRows: CanonicalGenerationRow[];
  strictOfficialCounts: boolean;
  checks: IntegrityCheck[];
}): void {
  input.checks.push(passCheck("main_matrix_row_count", 648, input.mainRows.length));
  input.checks.push(
    passCheck(
      "main_matrix_unique_key_count",
      648,
      new Set(input.mainRows.map((row) => row.canonical_key)).size,
    ),
  );

  const usableCount = input.mainRows.filter((row) => row.usable).length;
  input.checks.push(passCheck("main_matrix_usable_count", 638, usableCount));
  input.checks.push(
    passCheck("main_matrix_unusable_count", 10, input.mainRows.length - usableCount),
  );

  for (const modelId of OFFICIAL_MAIN_MODELS) {
    const rows = input.mainRows.filter((row) => row.model_id === modelId);
    input.checks.push(passCheck(`${modelId}_row_count`, 216, rows.length));
    if (input.strictOfficialCounts) {
      input.checks.push(
        passCheck(
          `${modelId}_usable_count`,
          OFFICIAL_USABLE_COUNTS[modelId],
          rows.filter((row) => row.usable).length,
        ),
      );
    }
    for (const level of EVIDENCE_LEVELS) {
      input.checks.push(
        passCheck(
          `${modelId}_${level}_row_count`,
          36,
          rows.filter((row) => row.evidence_level === level).length,
        ),
      );
    }
  }

  if (input.baselineRows.length > 0) {
    input.checks.push(
      passCheck("template_baseline_row_count", 216, input.baselineRows.length),
    );
    input.checks.push(
      passCheck(
        "template_baseline_usable_count",
        216,
        input.baselineRows.filter((row) => row.usable).length,
      ),
    );
  }

  input.checks.push(
    passCheck(
      "package_hash_mismatch_count",
      0,
      [...input.mainRows, ...input.baselineRows].filter(
        (row) => !row.input_package_hash_verified,
      ).length,
    ),
  );
  input.checks.push(
    passCheck(
      "prompt_hash_mismatch_count",
      0,
      [...input.mainRows, ...input.baselineRows].filter(
        (row) => !row.prompt_hash_verified,
      ).length,
    ),
  );
}

function buildIntegrityRows(
  mainRows: CanonicalGenerationRow[],
  baselineRows: CanonicalGenerationRow[],
): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = [];
  rows.push(integrityScopeRow("main", "all", mainRows, 648));
  for (const modelId of OFFICIAL_MAIN_MODELS) {
    const modelRows = mainRows.filter((row) => row.model_id === modelId);
    rows.push(integrityScopeRow("model", modelId, modelRows, 216));
    for (const level of EVIDENCE_LEVELS) {
      rows.push(
        integrityScopeRow(
          "model_level",
          `${modelId}:${level}`,
          modelRows.filter((row) => row.evidence_level === level),
          36,
        ),
      );
    }
  }
  if (baselineRows.length > 0) {
    rows.push(integrityScopeRow("baseline", "template_baseline", baselineRows, 216));
  }
  return rows;
}

function integrityScopeRow(
  scopeType: string,
  scopeId: string,
  rows: CanonicalGenerationRow[],
  planned: number,
): Record<string, unknown> {
  const actual = rows.length;
  const usable = rows.filter((row) => row.usable).length;
  const keyCount = new Set(rows.map((row) => row.canonical_key)).size;
  const duplicateCount = actual - keyCount;
  const missingCount = Math.max(0, planned - keyCount);
  const hashMismatchCount = rows.filter(
    (row) => !row.input_package_hash_verified || !row.prompt_hash_verified,
  ).length;
  return {
    scope_type: scopeType,
    scope_id: scopeId,
    planned_count: planned,
    actual_count: actual,
    unique_key_count: keyCount,
    usable_count: usable,
    unusable_count: actual - usable,
    duplicate_count: duplicateCount,
    missing_count: missingCount,
    hash_mismatch_count: hashMismatchCount,
    status:
      actual === planned && duplicateCount === 0 && missingCount === 0 && hashMismatchCount === 0
        ? "PASS"
        : "FAIL",
  };
}

function buildCanonicalSourceMap(input: {
  evidence: LoadedJsonl<JsonObject>;
  selection: {
    selected_cases?: Awaited<ReturnType<typeof readCsvStrict>>;
    selection_manifest?: Awaited<ReturnType<typeof readJsonStrict<JsonObject>>>;
  };
  mainSources: LoadedSource[];
  baselineSource?: LoadedSource;
}): JsonObject {
  return {
    schema_version: "canonical_sources_v1",
    created_at: new Date().toISOString(),
    evidence: describeLoaded(input.evidence),
    selected_cases: input.selection.selected_cases
      ? describeCsv(input.selection.selected_cases)
      : null,
    selection_manifest: input.selection.selection_manifest
      ? describeJson(input.selection.selection_manifest)
      : null,
    main_models: input.mainSources.map(describeModelSource),
    baseline: input.baselineSource ? describeModelSource(input.baselineSource) : null,
  };
}

function describeModelSource(source: LoadedSource): JsonObject {
  const firstGeneration = source.generation_entries[0]?.value;
  return {
    model_id: source.config.model_id,
    is_baseline: source.config.is_baseline,
    eligible_for_selection: source.config.eligible_for_selection,
    generation_artifact: describeLoaded(source.generations),
    prompt_artifact: describeLoaded(source.prompts),
    manifest_artifact: source.manifest ? describeJson(source.manifest) : null,
    observed: {
      run_ids: uniqueStrings(source.generation_entries.map((item) => item.value.run_id)),
      model_revisions: uniqueNullableStrings(
        source.generation_entries.map((item) => item.value.model_revision),
      ),
      prompt_versions: uniqueStrings(
        source.generation_entries.map((item) => item.value.prompt_version),
      ),
      output_schema_versions: uniqueStrings(
        source.generation_entries.map((item) => item.value.output_schema_version),
      ),
      repeat_ids: [...new Set(source.generation_entries.map((item) => item.value.repeat_id))],
      experiment_stages: uniqueStrings(
        source.generation_entries.map((item) => item.value.experiment_stage),
      ),
      usable_count: source.generation_entries.filter((item) => getUsability(item.value).usable)
        .length,
      unusable_count: source.generation_entries.filter(
        (item) => !getUsability(item.value).usable,
      ).length,
      first_generation_id: firstGeneration?.generation_id ?? null,
    },
  };
}

function summarizeMatrix(
  mainRows: CanonicalGenerationRow[],
  baselineRows: CanonicalGenerationRow[],
): JsonObject {
  return {
    main_planned: 648,
    main_actual: mainRows.length,
    main_usable: mainRows.filter((row) => row.usable).length,
    main_unusable: mainRows.filter((row) => !row.usable).length,
    by_model: Object.fromEntries(
      OFFICIAL_MAIN_MODELS.map((modelId) => {
        const rows = mainRows.filter((row) => row.model_id === modelId);
        return [
          modelId,
          {
            planned: 216,
            actual: rows.length,
            usable: rows.filter((row) => row.usable).length,
            unusable: rows.filter((row) => !row.usable).length,
          },
        ];
      }),
    ),
    template_baseline_actual: baselineRows.length,
    template_baseline_usable: baselineRows.filter((row) => row.usable).length,
    template_baseline_eligible_for_selection: false,
  };
}

function buildAuditMarkdown(
  audit: JsonObject,
  mainRows: CanonicalGenerationRow[],
  baselineRows: CanonicalGenerationRow[],
): string {
  const lines = [
    "# Phase 0 — Input Audit and Canonicalization",
    "",
    `Status: **${String(audit.status)}**`,
    "",
    "## Canonical matrix",
    "",
    "| Model | Planned | Actual | Usable | Unusable |",
    "|---|---:|---:|---:|---:|",
  ];

  for (const modelId of OFFICIAL_MAIN_MODELS) {
    const rows = mainRows.filter((row) => row.model_id === modelId);
    const usable = rows.filter((row) => row.usable).length;
    lines.push(`| ${modelId} | 216 | ${rows.length} | ${usable} | ${rows.length - usable} |`);
  }
  lines.push(
    `| **Main total** | **648** | **${mainRows.length}** | **${mainRows.filter((row) => row.usable).length}** | **${mainRows.filter((row) => !row.usable).length}** |`,
  );
  if (baselineRows.length > 0) {
    lines.push(
      `| template_baseline | 216 | ${baselineRows.length} | ${baselineRows.filter((row) => row.usable).length} | ${baselineRows.filter((row) => !row.usable).length} |`,
    );
  }

  lines.push("", "## Preserved unusable records", "");
  const unusable = mainRows.filter((row) => !row.usable);
  for (const row of unusable) {
    lines.push(
      `- \`${row.generation_id}\` — ${row.usability_reason_codes.join(", ")}`,
    );
  }

  const warnings = Array.isArray(audit.warnings)
    ? audit.warnings.map(asObject)
    : [];
  lines.push("", "## Audit warnings", "");
  for (const warning of warnings) {
    const affected =
      warning.affected_package_count === undefined
        ? ""
        : ` Affected packages: ${String(warning.affected_package_count)}.`;
    lines.push(
      `- **${String(warning.warning_id)}** (${String(warning.severity)}): ${String(warning.detail)}${affected}`,
    );
  }

  lines.push("", "## Phase 0 boundary", "");
  lines.push(
    "No semantic validator was run. Phase 0 only canonicalizes official records and checks syntax, identity, hashes, cohort completeness, prompt parity, and observed package-contract inconsistencies.",
  );
  lines.push("");
  return lines.join("\n");
}

function toCompactCsvRow(row: CanonicalGenerationRow): Record<string, unknown> {
  return {
    canonical_key: row.canonical_key,
    cohort_key: row.cohort_key,
    matrix_role: row.matrix_role,
    model_id: row.model_id,
    model_revision: row.model_revision,
    revision_status: row.revision_status,
    generation_id: row.generation_id,
    run_id: row.run_id,
    case_id: row.case_id,
    source_ir_id: row.source_ir_id,
    evidence_level: row.evidence_level,
    repeat_id: row.repeat_id,
    package_id: row.package_id,
    source_evidence_id: row.source_evidence_id,
    prompt_id: row.prompt_id,
    prompt_version: row.prompt_version,
    output_schema_version: row.output_schema_version,
    is_baseline: row.is_baseline,
    eligible_for_selection: row.eligible_for_selection,
    usable: row.usable,
    usability_reason_codes: row.usability_reason_codes.join("|"),
    runtime_status: row.runtime_status,
    finish_reason: row.finish_reason,
    truncated_response: row.truncated_response,
    raw_json_parse_success: row.raw_json_parse_success,
    schema_valid: row.schema_valid,
    input_package_hash_verified: row.input_package_hash_verified,
    prompt_hash_verified: row.prompt_hash_verified,
    source_generation_file_sha256: row.source_generation_file_sha256,
    source_generation_line: row.source_generation_line,
    source_prompt_file_sha256: row.source_prompt_file_sha256,
    source_prompt_line: row.source_prompt_line,
  };
}

function orderEvidence(
  evidence: EvidencePackageRecord[],
  caseOrder: string[],
): EvidencePackageRecord[] {
  const byKey = new Map(evidence.map((item) => [cohortKey(item), item]));
  const ordered: EvidencePackageRecord[] = [];
  for (const sourceIrId of caseOrder) {
    for (const level of EVIDENCE_LEVELS) {
      const item = byKey.get(`${sourceIrId}::${level}`);
      if (!item) throw new Error(`Evidence package missing for ${sourceIrId}::${level}.`);
      ordered.push(item);
    }
  }
  return ordered;
}

function assertEvidenceCohort(evidence: EvidencePackageRecord[]): void {
  if (evidence.length !== 216) {
    throw new Error(`Expected 216 evidence packages, found ${evidence.length}.`);
  }
  const byCase = new Map<string, Set<string>>();
  for (const item of evidence) {
    const levels = byCase.get(item.source_ir_id) ?? new Set<string>();
    if (levels.has(item.evidence_level)) {
      throw new Error(`Duplicate evidence cohort key ${cohortKey(item)}.`);
    }
    levels.add(item.evidence_level);
    byCase.set(item.source_ir_id, levels);
  }
  if (byCase.size !== 36) throw new Error(`Expected 36 cases, found ${byCase.size}.`);
  for (const [sourceIrId, levels] of byCase) {
    if (levels.size !== 6 || EVIDENCE_LEVELS.some((level) => !levels.has(level))) {
      throw new Error(`${sourceIrId} does not have exactly S0-S5.`);
    }
  }
}

function validateSourceConfiguration(
  mainSources: ModelSource[],
  baselineSource?: ModelSource,
): void {
  if (mainSources.length !== 3) {
    throw new Error(`Expected three main model sources, found ${mainSources.length}.`);
  }
  const modelIds = mainSources.map((source) => source.model_id);
  if (modelIds.join("|") !== OFFICIAL_MAIN_MODELS.join("|")) {
    throw new Error(
      `Main model order must be ${OFFICIAL_MAIN_MODELS.join(", ")}; found ${modelIds.join(", ")}.`,
    );
  }
  if (mainSources.some((source) => source.is_baseline || !source.eligible_for_selection)) {
    throw new Error("Main sources must be non-baseline and eligible for selection.");
  }
  if (
    baselineSource &&
    (!baselineSource.is_baseline || baselineSource.eligible_for_selection)
  ) {
    throw new Error("Baseline source must set is_baseline=true and eligible_for_selection=false.");
  }
}

function assertUniqueRows(rows: CanonicalGenerationRow[], label: string): void {
  const keys = new Set<string>();
  const generationIds = new Set<string>();
  for (const row of rows) {
    if (keys.has(row.canonical_key)) {
      throw new Error(`Duplicate canonical key in ${label}: ${row.canonical_key}.`);
    }
    if (generationIds.has(row.generation_id)) {
      throw new Error(`Duplicate generation_id in ${label}: ${row.generation_id}.`);
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
      throw new Error(`Duplicate ${label} ${key} at lines ${existing.line} and ${entry.line}.`);
    }
    result.set(key, entry);
  }
  return result;
}

function assertOnlyModel(values: string[], expected: string): void {
  const observed = new Set(values);
  if (observed.size !== 1 || !observed.has(expected)) {
    throw new Error(`Expected model ${expected}, found ${[...observed].join(", ")}.`);
  }
}

function assertNoDuplicateStrings(values: string[], label: string): void {
  const seen = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) throw new Error(`Duplicate ${label}: ${value}.`);
    seen.add(value);
  }
}

function assertSameStringSet(left: string[], right: string[], label: string): void {
  const leftSet = new Set(left);
  const rightSet = new Set(right);
  const missing = [...rightSet].filter((value) => !leftSet.has(value));
  const extra = [...leftSet].filter((value) => !rightSet.has(value));
  if (missing.length || extra.length) {
    throw new Error(
      `${label} mismatch. Missing: ${missing.join(", ") || "none"}; extra: ${extra.join(", ") || "none"}.`,
    );
  }
}

function assertManifestNumber(
  manifest: JsonObject,
  key: string,
  expected: number,
): void {
  if (manifest[key] !== expected) {
    throw new Error(`Selection manifest ${key}: expected ${expected}, found ${manifest[key]}.`);
  }
}

function assertManifestString(
  manifest: JsonObject,
  key: string,
  expected: string,
): void {
  if (manifest[key] !== expected) {
    throw new Error(`Selection manifest ${key} does not match the supplied artifact.`);
  }
}

function passCheck(
  checkId: string,
  expected: string | number | boolean,
  actual: string | number | boolean,
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

function describeLoaded(input: LoadedJsonl<JsonObject>): JsonObject {
  return {
    path: input.path,
    sha256: input.sha256,
    byte_count: input.byte_count,
    record_count: input.records.length,
  };
}

function describeCsv(input: Awaited<ReturnType<typeof readCsvStrict>>): JsonObject {
  return {
    path: input.path,
    sha256: input.sha256,
    byte_count: input.byte_count,
    record_count: input.rows.length,
  };
}

function describeJson(
  input: Awaited<ReturnType<typeof readJsonStrict<JsonObject>>>,
): JsonObject {
  return {
    path: input.path,
    sha256: input.sha256,
    byte_count: input.byte_count,
  };
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values)].sort();
}

function uniqueNullableStrings(values: Array<string | null>): Array<string | null> {
  return [...new Set(values)].sort((left, right) => String(left).localeCompare(String(right)));
}

function asObject(value: unknown): JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function objectArray(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.filter((item) => Object.keys(asObject(item)).length > 0).map(asObject) : [];
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item))
    : [];
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
