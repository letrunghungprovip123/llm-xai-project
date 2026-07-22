import type {
  AtomicClaimDraft,
  AtomicClaimExtractionPayload,
  ClaimCausalStrength,
  ClaimCertainty,
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

type JsonRecord = Record<string, unknown>;

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
  const canonicalValue = canonicalizeProviderPayload(value, document);
  if (!isPlainObject(canonicalValue) || !Array.isArray(canonicalValue.claims)) {
    throw new ClaimExtractionValidationError(
      "RESPONSE_SCHEMA_INVALID",
      "Provider payload must contain a claims array.",
    );
  }
  if (canonicalValue.claims.length > 60) {
    throw new ClaimExtractionValidationError(
      "RESPONSE_SCHEMA_INVALID",
      "Claim count exceeded the safety limit of 60.",
    );
  }

  const llmDrafts = canonicalValue.claims.map((item, index) =>
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

// Provider output is canonicalized deterministically before strict validation.
// This is part of the extractor contract, not a dataset-specific repair path.
function canonicalizeProviderPayload(
  value: unknown,
  document: GenerationTextDocument,
): unknown {
  if (!isPlainObject(value) || !Array.isArray(value.claims)) return value;

  let changed = false;
  const claims = value.claims.map((rawClaim) => {
    if (!isPlainObject(rawClaim)) return rawClaim;

    const claim: JsonRecord = { ...rawClaim };
    if (canonicalizeNumericFields(claim)) changed = true;
    if (canonicalizeDirectionalSubject(claim, document)) changed = true;
    if (canonicalizeKnownSemantics(claim)) changed = true;
    if (anchorToUniqueDeclaredSourceSlot(claim, document)) changed = true;
    return claim;
  });

  return changed ? { ...value, claims } : value;
}

function canonicalizeNumericFields(claim: JsonRecord): boolean {
  const claimType = readLooseString(claim.claim_type);
  const sourceText = readLooseString(claim.source_text);
  const numericValueText = readLooseString(claim.numeric_value_text);
  const numericRole = readLooseString(claim.numeric_role);
  let changed = false;

  if (!numericValueText) {
    if (readLooseString(claim.numeric_unit)) {
      claim.numeric_unit = "";
      changed = true;
    }

    if (numericRole && numericRole !== "not_applicable") {
      if (claimType === "numeric") {
        retypeQualitativeNumericClaim(claim, sourceText);
      } else {
        claim.numeric_role = "not_applicable";
        claim.numeric_unit = "";
      }
      changed = true;
    }
    return changed;
  }

  if (!isSupportedFiniteNumber(numericValueText)) {
    if (claimType === "numeric") {
      retypeQualitativeNumericClaim(claim, sourceText);
    } else {
      clearNumericFields(claim);
    }
    return true;
  }

  if (!numericRole || numericRole === "not_applicable") {
    claim.numeric_role = inferProviderNumericRole(claim, sourceText);
    return true;
  }

  return changed;
}

function retypeQualitativeNumericClaim(
  claim: JsonRecord,
  sourceText: string,
): void {
  const normalized = normalizeVietnamese(sourceText);

  if (normalized.includes("gan nguong")) {
    claim.claim_type = "uncertainty";
    claim.subject_type = "prediction";
    claim.direction = "unknown";
    claim.magnitude = "unknown";
    claim.causal_strength = "none";
  } else if (
    normalized.includes("duoi nguong")
    || normalized.includes("rat thap")
    || normalized.includes("xac suat thap")
    || normalized.includes("nguy co thap")
    || normalized.includes("rui ro thap")
  ) {
    claim.claim_type = "prediction";
    claim.subject_type = "prediction";
    claim.direction = "decrease_risk";
    claim.magnitude = "not_applicable";
    claim.causal_strength = "none";
  } else {
    claim.claim_type = "uncertainty";
    claim.subject_type = "prediction";
    claim.direction = "unknown";
    claim.magnitude = "unknown";
    claim.causal_strength = "none";
  }

  claim.feature_id = "";
  claim.concept_id = "";
  clearNumericFields(claim);
}

function clearNumericFields(claim: JsonRecord): void {
  claim.numeric_value_text = "";
  claim.numeric_unit = "";
  claim.numeric_role = "not_applicable";
}

function inferProviderNumericRole(
  claim: JsonRecord,
  sourceText: string,
): string {
  const claimType = readLooseString(claim.claim_type);
  const subjectType = readLooseString(claim.subject_type);
  const normalized = normalizeVietnamese(sourceText);

  if (claimType === "ranking") return "rank";
  if (subjectType === "prediction" && normalized.includes("nguong")) {
    return "decision_threshold";
  }
  if (subjectType === "prediction") return "prediction_score";
  if (subjectType === "feature") return "feature_value";
  return "other";
}

function canonicalizeDirectionalSubject(
  claim: JsonRecord,
  document: GenerationTextDocument,
): boolean {
  const claimType = readLooseString(claim.claim_type);
  if (
    claimType !== "feature_direction"
    && claimType !== "concept_direction"
  ) {
    return false;
  }

  const featureId = readLooseString(claim.feature_id);
  const conceptId = readLooseString(claim.concept_id);
  const subjectType = readLooseString(claim.subject_type);
  const factorId = readLooseString(claim.source_factor_id);
  const declared = collectDeclaredIds(document, factorId);

  if (claimType === "feature_direction") {
    const valid =
      subjectType === "feature"
      && Boolean(featureId)
      && declared.features.includes(featureId)
      && !conceptId;
    if (valid) return false;

    if (declared.features.length === 1) {
      claim.subject_type = "feature";
      claim.feature_id = declared.features[0] ?? "";
      claim.concept_id = "";
      return true;
    }

    retypeAsDistributedEvidence(claim);
    return true;
  }

  const valid =
    subjectType === "concept"
    && Boolean(conceptId)
    && declared.concepts.includes(conceptId)
    && !featureId;
  if (valid) return false;

  if (declared.concepts.length === 1) {
    claim.subject_type = "concept";
    claim.concept_id = declared.concepts[0] ?? "";
    claim.feature_id = "";
    return true;
  }

  retypeAsDistributedEvidence(claim);
  return true;
}

function collectDeclaredIds(
  document: GenerationTextDocument,
  factorId: string,
): { features: string[]; concepts: string[] } {
  const factors = document.factor_metadata.filter(
    (factor) => !factorId || factor.source_factor_id === factorId,
  );

  return {
    features: uniqueStrings(
      factors.flatMap((factor) => factor.declared_feature_ids),
    ),
    concepts: uniqueStrings(
      factors.flatMap((factor) => factor.declared_concept_ids),
    ),
  };
}

function retypeAsDistributedEvidence(claim: JsonRecord): void {
  claim.claim_type = "distributed_evidence";
  claim.subject_type = "evidence";
  claim.feature_id = "";
  claim.concept_id = "";
}

function canonicalizeKnownSemantics(claim: JsonRecord): boolean {
  const section = readLooseString(claim.source_section);
  const claimType = readLooseString(claim.claim_type);
  const sourceText = readLooseString(claim.source_text);
  const normalizedText = normalizeVietnamese(sourceText);
  let changed = false;

  if (claimType === "prediction") {
    const explicitDirection = explicitPredictionDirection(normalizedText);
    if (explicitDirection && claim.direction !== explicitDirection) {
      claim.direction = explicitDirection;
      changed = true;
    }
  }

  if (
    section === "safe_summary"
    && saysNoEvidenceWasIdentified(normalizedText)
  ) {
    claim.claim_type = "uncertainty";
    claim.subject_type = "evidence";
    claim.source_factor_id = "";
    claim.feature_id = "";
    claim.concept_id = "";
    claim.direction = "unknown";
    changed = true;
  }

  return changed;
}

function anchorToUniqueDeclaredSourceSlot(
  claim: JsonRecord,
  document: GenerationTextDocument,
): boolean {
  const sourceText = readLooseString(claim.source_text);
  if (!sourceText) return false;

  const section = readLooseString(claim.source_section);
  const factorId = readLooseString(claim.source_factor_id) || null;
  const candidates = document.section_spans.filter(
    (span) =>
      span.source_section === section
      && span.source_factor_id === factorId,
  );

  if (isExactWithinAnySpan(sourceText, candidates, document)) return false;
  if (candidates.length !== 1) return false;

  const target = candidates[0];
  if (!target) return false;
  claim.source_text = document.generation_text.slice(target.start, target.end);
  return true;
}

function isExactWithinAnySpan(
  sourceText: string,
  spans: GenerationTextDocument["section_spans"],
  document: GenerationTextDocument,
): boolean {
  return spans.some((span) => {
    const start = document.generation_text.indexOf(sourceText, span.start);
    const end = start + sourceText.length;
    return start >= span.start && end <= span.end;
  });
}

function isSupportedFiniteNumber(value: string): boolean {
  const trimmed = value.trim();
  const numberText = trimmed.endsWith("%")
    ? trimmed.slice(0, -1).trim()
    : trimmed;
  return parseStrictFiniteNumber(numberText) !== null;
}

function explicitPredictionDirection(
  text: string,
): "increase_risk" | "decrease_risk" | null {
  const lowRisk = [
    "rui ro thap",
    "rui ro tin dung la thap",
    "nguy co thap",
    "low default risk",
    "low risk of default",
  ].some((phrase) => text.includes(phrase));
  const highRisk = [
    "rui ro cao",
    "rui ro tin dung la cao",
    "rui ro tin dung cao",
    "nguy co cao",
    "high default risk",
    "high risk of default",
  ].some((phrase) => text.includes(phrase));

  if (lowRisk === highRisk) return null;
  return lowRisk ? "decrease_risk" : "increase_risk";
}

function saysNoEvidenceWasIdentified(text: string): boolean {
  return text.includes("khong co yeu to duoc xac dinh")
    || text.includes("khong co bang chung cu the");
}

function normalizeVietnamese(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();
}

function uniqueStrings(values: readonly string[]): string[] {
  return [...new Set(values.filter((value) => value.length > 0))];
}

function readLooseString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
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
