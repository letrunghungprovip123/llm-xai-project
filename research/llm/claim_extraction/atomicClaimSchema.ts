import type {
  AtomicClaimDraft,
  AtomicClaimExtractionPayload,
  ClaimCausalStrength,
  ClaimCertainty,
  ClaimDirection,
  ClaimMagnitude,
  ClaimNumericRole,
  ClaimSubjectType,
} from "../../../contracts/validation-claims";
import {
  CLAIM_DIRECTIONS,
  CLAIM_NUMERIC_ROLES,
  CLAIM_SOURCE_SECTIONS,
  CLAIM_TYPES,
} from "../../../contracts/validation-claims";
import { isPlainObject } from "../canonicalization/io";
import { postprocessAtomicClaims } from "./claimPostprocessor";
import type { GenerationTextDocument } from "./generationTextAdapter";
import { locateExactSourceSpan } from "./generationTextAdapter";

export const ATOMIC_CLAIM_EXTRACTOR_VERSION = "atomic_claim_extractor_v2.1.0";
export const ATOMIC_CLAIM_PROMPT_VERSION = "atomic_claim_extraction_prompt_v3";

const SUBJECT_TYPES: ClaimSubjectType[] = [
  "prediction", "feature", "concept", "evidence", "narrative", "none",
];
const MAGNITUDES = ["weak", "moderate", "strong", "unknown", "not_applicable"] as const;
const CERTAINTIES: ClaimCertainty[] = [
  "deterministic", "probabilistic", "hedged", "unknown",
];
const CAUSAL_STRENGTHS: ClaimCausalStrength[] = [
  "associational", "causal", "none", "unknown",
];
const NUMERIC_ROLES = [...CLAIM_NUMERIC_ROLES] as const;
const PERCENT_UNITS = new Set(["%", "percent", "percentage", "phần trăm"]);
const PROVIDER_CLAIM_TYPES = CLAIM_TYPES.filter(
  (claimType) =>
    claimType !== "feature_presence" && claimType !== "concept_presence",
);
const PROVIDER_SOURCE_SECTIONS = CLAIM_SOURCE_SECTIONS.filter(
  (sourceSection) => sourceSection !== "factor_name",
);

// Structured output chỉ chứa dữ liệu model có thể xác định đáng tin cậy từ văn bản.
export const ATOMIC_CLAIM_RESPONSE_JSON_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    claims: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          source_section: { type: "string", enum: PROVIDER_SOURCE_SECTIONS },
          source_factor_id: { type: "string" },
          source_text: { type: "string" },
          claim_type: { type: "string", enum: PROVIDER_CLAIM_TYPES },
          subject_type: { type: "string", enum: SUBJECT_TYPES },
          feature_id: { type: "string" },
          concept_id: { type: "string" },
          direction: { type: "string", enum: [...CLAIM_DIRECTIONS] },
          magnitude: { type: "string", enum: [...MAGNITUDES] },
          certainty: { type: "string", enum: CERTAINTIES },
          causal_strength: { type: "string", enum: CAUSAL_STRENGTHS },
          numeric_value_text: { type: "string" },
          numeric_unit: { type: "string" },
          numeric_role: { type: "string", enum: [...NUMERIC_ROLES] },
          normalized_claim_key: { type: "string" },
        },
        required: [
          "source_section", "source_factor_id", "source_text", "claim_type",
          "subject_type", "feature_id", "concept_id", "direction",
          "magnitude", "certainty", "causal_strength", "numeric_value_text",
          "numeric_unit", "numeric_role", "normalized_claim_key",
        ],
      },
    },
  },
  required: ["claims"],
} as const;

export class ClaimExtractionValidationError extends Error {
  readonly code: "RESPONSE_SCHEMA_INVALID" | "SOURCE_SPAN_INVALID";

  constructor(
    code: "RESPONSE_SCHEMA_INVALID" | "SOURCE_SPAN_INVALID",
    message: string,
  ) {
    super(message);
    this.name = "ClaimExtractionValidationError";
    this.code = code;
  }
}

// Hậu kiểm schema, neo exact quote rồi giao phần atomicity/dedup cho code.
export function validateAndNormalizeClaimPayload(
  value: unknown,
  document: GenerationTextDocument,
): AtomicClaimExtractionPayload {
  if (!isPlainObject(value) || !Array.isArray(value.claims)) {
    throw new ClaimExtractionValidationError(
      "RESPONSE_SCHEMA_INVALID",
      "Provider payload must contain a claims array.",
    );
  }
  if (value.claims.length > 60) {
    throw new ClaimExtractionValidationError(
      "RESPONSE_SCHEMA_INVALID",
      "Claim count exceeded the safety limit of 60.",
    );
  }

  const llmDrafts = value.claims.map((item, index) =>
    parseClaimDraft(item, index, document),
  );
  const processed = postprocessAtomicClaims(llmDrafts, document);
  if (processed.claims.length > 120) {
    throw new ClaimExtractionValidationError(
      "RESPONSE_SCHEMA_INVALID",
      "Final claim count exceeded the safety limit of 120.",
    );
  }

  return {
    claims: processed.claims,
    postprocess_metrics: processed.metrics,
  };
}

function parseClaimDraft(
  value: unknown,
  arrayIndex: number,
  document: GenerationTextDocument,
): AtomicClaimDraft {
  if (!isPlainObject(value)) {
    invalid(`Claim at index ${arrayIndex} must be an object.`);
  }

  const item = value as Record<string, unknown>;
  const sourceSection = readEnum(
    item.source_section,
    CLAIM_SOURCE_SECTIONS,
    "source_section",
  );
  const sourceFactorId = emptyToNull(
    readString(item.source_factor_id, "source_factor_id"),
  );
  const sourceText = readNonEmptyString(item.source_text, "source_text");
  const sourceSpan = locateExactSourceSpan(
    document,
    sourceSection,
    sourceFactorId,
    sourceText,
  );

  if (!sourceSpan) {
    throw new ClaimExtractionValidationError(
      "SOURCE_SPAN_INVALID",
      `Claim ${arrayIndex + 1} source_text was not found exactly in its declared section and factor.`,
    );
  }

  const magnitudeValue = readEnum(item.magnitude, MAGNITUDES, "magnitude");
  const claimType = readEnum(item.claim_type, CLAIM_TYPES, "claim_type");
  const subjectType = readEnum(item.subject_type, SUBJECT_TYPES, "subject_type");
  const featureId = emptyToNull(readString(item.feature_id, "feature_id"));
  const conceptId = emptyToNull(readString(item.concept_id, "concept_id"));
  const numeric = parseNumericClaimValue(
    readString(item.numeric_value_text, "numeric_value_text"),
    readString(item.numeric_unit, "numeric_unit"),
  );
  const numericRoleValue = readEnum(
    item.numeric_role,
    NUMERIC_ROLES,
    "numeric_role",
  );
  const numericRole = numericRoleValue === "not_applicable"
    ? null
    : (numericRoleValue as ClaimNumericRole);
  validateNumericFields(claimType, numeric.value, numericRole);
  validateClaimSubject(claimType, subjectType, featureId, conceptId);
  validateDeclaredIdentifiers(
    document,
    sourceFactorId,
    featureId,
    conceptId,
    arrayIndex,
  );
  const modelNormalizedClaimKey = normalizeKey(
    readNonEmptyString(item.normalized_claim_key, "normalized_claim_key"),
  );

  return {
    local_claim_index: arrayIndex + 1,
    source_section: sourceSection,
    source_factor_id: sourceFactorId,
    source_text: sourceText,
    source_span_start: sourceSpan.start,
    source_span_end: sourceSpan.end,
    claim_type: claimType,
    subject_type: subjectType,
    feature_id: featureId,
    concept_id: conceptId,
    direction: readEnum(item.direction, CLAIM_DIRECTIONS, "direction"),
    magnitude:
      magnitudeValue === "not_applicable"
        ? null
        : (magnitudeValue as ClaimMagnitude),
    certainty: readEnum(item.certainty, CERTAINTIES, "certainty"),
    causal_strength: readEnum(
      item.causal_strength,
      CAUSAL_STRENGTHS,
      "causal_strength",
    ),
    numeric_value: numeric.value,
    numeric_unit: numeric.unit,
    numeric_role: numericRole,
    claim_origin: "llm",
    model_normalized_claim_key: modelNormalizedClaimKey,
    semantic_signature: "",
    normalized_claim_key: "",
  };
}

function validateNumericFields(
  claimType: AtomicClaimDraft["claim_type"],
  numericValue: number | null,
  numericRole: ClaimNumericRole | null,
): void {
  if ((numericValue === null) !== (numericRole === null)) {
    invalid(
      "numeric_role must be set exactly when numeric_value_text is present.",
    );
  }
  if (claimType === "numeric" && numericValue === null) {
    invalid("A numeric claim must contain numeric_value_text and numeric_role.");
  }
}

function validateClaimSubject(
  claimType: AtomicClaimDraft["claim_type"],
  subjectType: ClaimSubjectType,
  featureId: string | null,
  conceptId: string | null,
): void {
  if (featureId && conceptId) {
    invalid("One atomic claim must not target feature_id and concept_id together.");
  }
  if (
    (claimType === "feature_presence" || claimType === "feature_direction") &&
    (subjectType !== "feature" || !featureId)
  ) {
    invalid(`${claimType} requires subject_type=feature and a feature_id.`);
  }
  if (
    (claimType === "concept_presence" || claimType === "concept_direction") &&
    (subjectType !== "concept" || !conceptId)
  ) {
    invalid(`${claimType} requires subject_type=concept and a concept_id.`);
  }
}

// ID có factor phải thuộc đúng factor; ID ở global section phải có trong document.
function validateDeclaredIdentifiers(
  document: GenerationTextDocument,
  sourceFactorId: string | null,
  featureId: string | null,
  conceptId: string | null,
  arrayIndex: number,
): void {
  const candidateFactors = sourceFactorId
    ? document.factor_metadata.filter(
      (factor) => factor.source_factor_id === sourceFactorId,
    )
    : document.factor_metadata;

  if (
    featureId &&
    !candidateFactors.some((factor) =>
      factor.declared_feature_ids.includes(featureId))
  ) {
    invalid(
      `Claim ${arrayIndex + 1} feature_id is not declared by its source factor/document: ${featureId}`,
    );
  }
  if (
    conceptId &&
    !candidateFactors.some((factor) =>
      factor.declared_concept_ids.includes(conceptId))
  ) {
    invalid(
      `Claim ${arrayIndex + 1} concept_id is not declared by its source factor/document: ${conceptId}`,
    );
  }
}

// Parser chỉ nhận định dạng số rõ ràng và chuẩn hóa phần trăm thành cùng một unit.
export function parseNumericClaimValue(
  numericValueText: string,
  numericUnit: string,
): { value: number | null; unit: string | null } {
  const rawText = numericValueText.trim();
  const rawUnit = normalizeUnit(numericUnit);

  if (!rawText) {
    if (rawUnit) {
      invalid("numeric_unit must be empty when numeric_value_text is empty.");
    }
    return { value: null, unit: null };
  }

  const hasPercentSuffix = rawText.endsWith("%");
  const numberText = hasPercentSuffix
    ? rawText.slice(0, -1).trim()
    : rawText;

  if (hasPercentSuffix && rawUnit && !PERCENT_UNITS.has(rawUnit)) {
    invalid(
      `numeric_unit conflicts with the percent suffix: ${numericUnit.trim()}`,
    );
  }

  const value = parseStrictFiniteNumber(numberText);
  if (value === null) {
    invalid(`numeric_value_text is not a supported finite number: ${rawText}`);
  }

  const unit = hasPercentSuffix || PERCENT_UNITS.has(rawUnit)
    ? "percent"
    : rawUnit || null;
  return { value, unit };
}

function parseStrictFiniteNumber(value: string): number | null {
  const compact = value.replace(/[\s\u00a0\u202f]/gu, "");
  let normalized: string;

  if (/^[+-]?\d+$/u.test(compact)) {
    normalized = compact;
  } else if (/^[+-]?[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?$/u.test(compact)) {
    normalized = compact.replace(/,/gu, "");
  } else if (/^[+-]?[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?$/u.test(compact)) {
    normalized = compact.replace(/\./gu, "").replace(",", ".");
  } else if (/^[+-]?\d+\.\d+$/u.test(compact)) {
    normalized = compact;
  } else if (/^[+-]?\d+,\d+$/u.test(compact)) {
    normalized = compact.replace(",", ".");
  } else {
    return null;
  }

  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeKey(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/gu, " ");
}

function normalizeUnit(value: string): string {
  return value.normalize("NFC").trim().toLowerCase().replace(/\s+/gu, " ");
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function readString(value: unknown, field: string): string {
  if (typeof value !== "string") invalid(`${field} must be a string.`);
  return value as string;
}

function readNonEmptyString(value: unknown, field: string): string {
  const result = readString(value, field);
  if (!result.trim()) invalid(`${field} must not be empty.`);
  return result;
}

function readEnum<T extends string>(
  value: unknown,
  values: readonly T[],
  field: string,
): T {
  if (typeof value !== "string" || !values.includes(value as T)) {
    invalid(`${field} has an unsupported value: ${String(value)}`);
  }
  return value as T;
}

function invalid(message: string): never {
  throw new ClaimExtractionValidationError("RESPONSE_SCHEMA_INVALID", message);
}
