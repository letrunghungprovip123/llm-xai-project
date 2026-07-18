import path from "node:path";

import type { GenerationContractMetrics } from "../../../contracts/generation-contract";
import type {
  CanonicalGenerationRow,
  EvidencePackageRecord,
  JsonObject,
} from "../../../contracts/llm-validation";
import {
  isPlainObject,
  readJsonlStrict,
  writeJsonlAtomic,
} from "../canonicalization/io";
import {
  REQUIRED_OUTPUT_FIELDS,
  calculateDuplicateSentenceRate,
  collectNarrativeText,
  findDuplicates,
  findMissingRequiredSections,
  getConstraints,
  getSkeleton,
  getSkeletonFeatureIds,
  hasHeavyEnglishProse,
  hasVietnameseSignal,
  matchesSkeletonOrder,
  readFactors,
  unique,
} from "./rules";

export const GENERATION_CONTRACT_VALIDATOR_VERSION =
  "generation_contract_validator_v1.0.0";

export type GenerationContractRunOptions = {
  generationIndexPath: string;
  evidencePackagesPath: string;
  outputPath: string;
};

export type GenerationContractRunSummary = {
  output_path: string;
  total_records: number;
  contract_passed: number;
  contract_failed: number;
};

// Chạy validator theo thứ tự canonical để luôn tạo đúng một record cho mỗi ô thí nghiệm.
export async function runGenerationContractValidation(
  options: GenerationContractRunOptions,
): Promise<GenerationContractRunSummary> {
  const generationInput = await readJsonlStrict<JsonObject>(
    options.generationIndexPath,
  );
  const evidenceInput = await readJsonlStrict<JsonObject>(
    options.evidencePackagesPath,
  );

  const evidenceByPackageId = new Map<string, EvidencePackageRecord>();
  for (const item of evidenceInput.records) {
    const packageId = asNonEmptyString(item.value.package_id);
    if (!packageId) {
      throw new Error(
        `Evidence package at line ${item.line} is missing package_id.`,
      );
    }
    if (evidenceByPackageId.has(packageId)) {
      throw new Error(`Duplicate evidence package_id: ${packageId}`);
    }
    evidenceByPackageId.set(
      packageId,
      item.value as unknown as EvidencePackageRecord,
    );
  }

  const results: GenerationContractMetrics[] = [];
  for (const item of generationInput.records) {
    const row = item.value as unknown as CanonicalGenerationRow;
    assertCanonicalIdentity(row, item.line);
    const evidence = evidenceByPackageId.get(row.package_id);
    if (!evidence) {
      throw new Error(
        `No evidence package for generation ${row.generation_id}: ${row.package_id}`,
      );
    }
    results.push(validateGenerationContract(row, evidence));
  }

  await writeJsonlAtomic(options.outputPath, results);
  const passed = results.filter((record) => record.contract_pass).length;

  return {
    output_path: path.resolve(options.outputPath),
    total_records: results.length,
    contract_passed: passed,
    contract_failed: results.length - passed,
  };
}

// Hàm thuần này gom các kiểm tra runtime, cấu trúc và policy surface của một generation.
export function validateGenerationContract(
  row: CanonicalGenerationRow,
  evidence: EvidencePackageRecord,
): GenerationContractMetrics {
  const generation = row.generation_record;
  const runtime = asObject(generation.runtime_metrics);
  const schema = asObject(generation.schema_metrics);
  const content = asObject(generation.content_metrics);
  const mentions = asObject(generation.evidence_mention_metrics);
  const parsedOutput = asObjectOrNull(generation.parsed_output);
  const factors = readFactors(parsedOutput?.factors);

  const missingRequiredSections = findMissingRequiredSections(parsedOutput);
  const duplicateFactorIds = findDuplicates(
    factors.map((factor) => factor.factor_id).filter(Boolean),
  );

  const constraints = getConstraints(evidence);
  const allowedFeatureIds = new Set(asStringArray(constraints.allowed_feature_ids));
  const allowedConceptIds = new Set(asStringArray(constraints.allowed_concept_ids));
  const declaredFeatureIds = factors.flatMap(
    (factor) => factor.declared_feature_ids,
  );
  const declaredConceptIds = factors.flatMap(
    (factor) => factor.declared_concept_ids,
  );
  const invalidFeatureIds = unique(
    declaredFeatureIds.filter((id) => !allowedFeatureIds.has(id)),
  );
  const invalidConceptIds = unique(
    declaredConceptIds.filter((id) => !allowedConceptIds.has(id)),
  );

  const skeleton = getSkeleton(evidence);
  const expectedSkeletonIds = getSkeletonFeatureIds(skeleton);
  const factorCountExpected =
    row.evidence_level === "S0"
      ? 0
      : row.evidence_level === "S5"
        ? expectedSkeletonIds.length
        : null;
  const factorCountActual = parsedOutput ? factors.length : null;
  const factorCountAccuracy =
    factorCountExpected === null || factorCountActual === null
      ? null
      : factorCountActual === factorCountExpected;
  const hasSkeletonContract = expectedSkeletonIds.length > 0;
  const factorOrderAccuracy =
    row.evidence_level === "S5" && parsedOutput
      ? hasSkeletonContract && matchesSkeletonOrder(factors, expectedSkeletonIds)
      : null;
  const factorRoleAccuracy =
    row.evidence_level === "S5" && parsedOutput
      ? factors.every((factor) => factor.role === "main")
      : null;
  const skeletonCompliance =
    row.evidence_level === "S5"
      ? Boolean(
          hasSkeletonContract &&
            factorCountAccuracy &&
            factorOrderAccuracy &&
            factorRoleAccuracy &&
            invalidFeatureIds.length === 0,
        )
      : null;

  const outputText = collectNarrativeText(parsedOutput);
  const languageCompliance = outputText ? hasVietnameseSignal(outputText) : null;
  const mixedLanguageFlag = outputText ? hasHeavyEnglishProse(outputText) : null;
  const redundancyIndicator = outputText
    ? calculateDuplicateSentenceRate(outputText)
    : null;
  const emptySectionCount = parsedOutput
    ? REQUIRED_OUTPUT_FIELDS.filter((field) => {
        if (field === "factors") return factors.length === 0;
        return asString(parsedOutput[field]).trim().length === 0;
      }).length
    : null;

  const issueCodes: string[] = [];
  if (runtime.status !== "SUCCESS") issueCodes.push("REQUEST_FAILED");
  if (!row.usable) issueCodes.push("OUTPUT_UNUSABLE");
  if (missingRequiredSections.length > 0) {
    issueCodes.push("MISSING_REQUIRED_SECTIONS");
  }
  if (duplicateFactorIds.length > 0) issueCodes.push("DUPLICATE_FACTOR_ID");
  if (factorCountAccuracy === false) issueCodes.push("FACTOR_COUNT_MISMATCH");
  if (factorOrderAccuracy === false) issueCodes.push("FACTOR_ORDER_MISMATCH");
  if (factorRoleAccuracy === false) issueCodes.push("FACTOR_ROLE_MISMATCH");
  if (invalidFeatureIds.length > 0) issueCodes.push("FEATURE_OUTSIDE_CONTRACT");
  if (invalidConceptIds.length > 0) issueCodes.push("CONCEPT_OUTSIDE_CONTRACT");
  if (languageCompliance === false || mixedLanguageFlag === true) {
    issueCodes.push("LANGUAGE_SURFACE_WARNING");
  }

  const structuralPass =
    missingRequiredSections.length === 0 &&
    duplicateFactorIds.length === 0 &&
    factorCountAccuracy !== false &&
    factorOrderAccuracy !== false &&
    factorRoleAccuracy !== false &&
    invalidFeatureIds.length === 0 &&
    invalidConceptIds.length === 0;

  return {
    contract_schema_version: "generation_contract_metrics_v1",
    contract_validator_version: GENERATION_CONTRACT_VALIDATOR_VERSION,
    generation_id: row.generation_id,
    canonical_key: row.canonical_key,
    model_id: row.model_id,
    case_id: row.case_id,
    source_ir_id: row.source_ir_id,
    evidence_level: row.evidence_level,
    repeat_id: row.repeat_id,
    package_id: row.package_id,
    raw_metrics: {
      request_attempted: true,
      request_success: runtime.status === "SUCCESS",
      runtime_status: asNullableString(runtime.status),
      finish_reason: asNullableString(runtime.finish_reason),
      retry_count: asNullableNumber(runtime.retry_count),
      empty_response: runtime.empty_response === true,
      truncated: row.truncated_response,
      max_token_hit:
        row.truncated_response || asNullableString(runtime.finish_reason) === "length",
      raw_json_parse_success: row.raw_json_parse_success,
      json_parse_success: schema.json_parse_success === true,
      schema_valid: row.schema_valid,
      usable_output: row.usable,
    },
    structural_metrics: {
      required_sections_present: missingRequiredSections.length === 0,
      missing_required_sections: missingRequiredSections,
      factor_id_unique:
        row.evidence_level === "S0"
          ? null
          : parsedOutput
            ? duplicateFactorIds.length === 0
            : null,
      duplicate_factor_ids: duplicateFactorIds,
      factor_count_actual: factorCountActual,
      factor_count_expected: factorCountExpected,
      factor_count_accuracy: factorCountAccuracy,
      factor_order_accuracy: factorOrderAccuracy,
      factor_role_accuracy: factorRoleAccuracy,
      skeleton_compliance: skeletonCompliance,
      allowed_feature_compliance: parsedOutput
        ? invalidFeatureIds.length === 0
        : false,
      invalid_feature_ids: invalidFeatureIds,
      allowed_concept_compliance: parsedOutput
        ? invalidConceptIds.length === 0
        : false,
      invalid_concept_ids: invalidConceptIds,
    },
    surface_metrics: {
      language_compliance: languageCompliance,
      mixed_language_flag: mixedLanguageFlag,
      too_short: asNullableBoolean(content.too_short),
      too_long: asNullableBoolean(content.too_long),
      redundancy_indicator: redundancyIndicator,
      empty_section_count: emptySectionCount,
    },
    evidence_reference_metrics: {
      selected_evidence_mention_rate: asNullableNumber(
        mentions.selected_feature_mention_rate,
      ),
      top1_mention: asNullableNumber(mentions.top1_mention_rate),
      top3_mention: asNullableNumber(mentions.top3_mention_rate),
      top5_mention: asNullableNumber(mentions.top5_mention_rate),
      concept_group_coverage: asNullableNumber(mentions.concept_mention_rate),
      direction_surface_match: null,
    },
    contract_pass: row.usable && row.schema_valid && structuralPass,
    issue_codes: unique(issueCodes),
  };
}

function assertCanonicalIdentity(row: CanonicalGenerationRow, line: number): void {
  if (!row || typeof row !== "object") {
    throw new Error(`Generation index line ${line} is not an object.`);
  }
  if (!asNonEmptyString(row.generation_id)) {
    throw new Error(`Generation index line ${line} is missing generation_id.`);
  }
  if (!asNonEmptyString(row.canonical_key)) {
    throw new Error(`Generation index line ${line} is missing canonical_key.`);
  }
  if (!asNonEmptyString(row.package_id)) {
    throw new Error(`Generation index line ${line} is missing package_id.`);
  }
}

function asObject(value: unknown): JsonObject {
  return isPlainObject(value) ? value : {};
}

function asObjectOrNull(value: unknown): JsonObject | null {
  return isPlainObject(value) ? value : null;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is string => typeof item === "string" && item.length > 0,
  );
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asNullableBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}
