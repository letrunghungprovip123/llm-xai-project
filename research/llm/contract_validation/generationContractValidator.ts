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

export const GENERATION_CONTRACT_VALIDATOR_VERSION =
  "generation_contract_validator_v1.0.0";

const REQUIRED_OUTPUT_FIELDS = [
  "prediction_summary",
  "factors",
  "uncertainty_note",
  "distributed_evidence_note",
  "safe_summary",
] as const;

type ExplanationFactor = {
  factor_id: string;
  role: string;
  declared_feature_ids: string[];
  declared_concept_ids: string[];
};

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

function findMissingRequiredSections(output: JsonObject | null): string[] {
  if (!output) return [...REQUIRED_OUTPUT_FIELDS];
  const missing: string[] = [];
  for (const field of REQUIRED_OUTPUT_FIELDS) {
    if (field === "factors") {
      if (!Array.isArray(output[field])) missing.push(field);
    } else if (typeof output[field] !== "string") {
      missing.push(field);
    }
  }
  return missing;
}

function readFactors(value: unknown): ExplanationFactor[] {
  if (!Array.isArray(value)) return [];
  const factors: ExplanationFactor[] = [];
  for (const item of value) {
    if (!isPlainObject(item)) continue;
    factors.push({
      factor_id: asString(item.factor_id),
      role: asString(item.role),
      declared_feature_ids: asStringArray(item.declared_feature_ids),
      declared_concept_ids: asStringArray(item.declared_concept_ids),
    });
  }
  return factors;
}

function getConstraints(evidence: EvidencePackageRecord): JsonObject {
  if (isPlainObject(evidence.constraints)) return evidence.constraints;
  const promptPayload = asObject(evidence.prompt_payload);
  return asObject(promptPayload.constraints);
}

function getSkeleton(evidence: EvidencePackageRecord): JsonObject {
  const promptPayload = asObject(evidence.prompt_payload);
  return asObject(promptPayload.backend_explanation_skeleton);
}

function getSkeletonFeatureIds(skeleton: JsonObject): string[] {
  const slots = skeleton.main_factor_slots;
  if (!Array.isArray(slots)) return [];
  return slots
    .map((slot) => (isPlainObject(slot) ? asString(slot.feature_id) : ""))
    .filter(Boolean);
}

function matchesSkeletonOrder(
  factors: ExplanationFactor[],
  expectedFeatureIds: string[],
): boolean {
  if (factors.length !== expectedFeatureIds.length) return false;
  return expectedFeatureIds.every((featureId, index) => {
    const factor = factors[index];
    return factor?.declared_feature_ids[0] === featureId;
  });
}

function collectNarrativeText(output: JsonObject | null): string {
  if (!output) return "";
  const originalFactors = Array.isArray(output.factors) ? output.factors : [];
  const factorText = originalFactors.flatMap((factor) => {
    if (!isPlainObject(factor)) return [];
    return [asString(factor.factor_name), asString(factor.explanation)];
  });

  return [
    asString(output.prediction_summary),
    ...factorText,
    asString(output.uncertainty_note),
    asString(output.distributed_evidence_note),
    asString(output.safe_summary),
  ]
    .filter(Boolean)
    .join(" ")
    .trim();
}

function hasVietnameseSignal(text: string): boolean {
  const normalized = text.toLowerCase();
  const accentedCharacters = normalized.match(/[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/g)?.length ?? 0;
  const words = normalized.match(/[\p{L}]+/gu) ?? [];
  const vietnameseWords = new Set([
    "mô", "hình", "rủi", "ro", "dự", "đoán", "không", "bằng", "chứng",
    "yếu", "tố", "tín", "hiệu", "góp", "phần", "tăng", "giảm", "khách",
  ]);
  const wordMatches = words.filter((word) => vietnameseWords.has(word)).length;
  return accentedCharacters >= 2 || wordMatches >= 3;
}

function hasHeavyEnglishProse(text: string): boolean {
  const words = text.toLowerCase().match(/[a-z]+/g) ?? [];
  const englishWords = new Set([
    "the", "and", "because", "therefore", "customer", "will", "with",
    "from", "this", "that", "shows", "means", "likely", "certainly",
  ]);
  return words.filter((word) => englishWords.has(word)).length >= 5;
}

function calculateDuplicateSentenceRate(text: string): number {
  const sentences = text
    .split(/[.!?]+/)
    .map((sentence) => sentence.toLowerCase().replace(/\s+/g, " ").trim())
    .filter((sentence) => sentence.length >= 12);
  if (sentences.length === 0) return 0;
  return (sentences.length - new Set(sentences).size) / sentences.length;
}

function findDuplicates(values: string[]): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value);
    seen.add(value);
  }
  return [...duplicates].sort();
}

function unique(values: string[]): string[] {
  return [...new Set(values)].sort();
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
