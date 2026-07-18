import type {
  EvidencePackageRecord,
  JsonObject,
} from "../../../contracts/llm-validation";
import { isPlainObject } from "../canonicalization/io";

export const REQUIRED_OUTPUT_FIELDS = [
  "prediction_summary",
  "factors",
  "uncertainty_note",
  "distributed_evidence_note",
  "safe_summary",
] as const;

export type ExplanationFactor = {
  factor_id: string;
  role: string;
  declared_feature_ids: string[];
  declared_concept_ids: string[];
};

export function findMissingRequiredSections(
  output: JsonObject | null,
): string[] {
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

export function readFactors(value: unknown): ExplanationFactor[] {
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

export function getConstraints(evidence: EvidencePackageRecord): JsonObject {
  if (isPlainObject(evidence.constraints)) return evidence.constraints;
  const promptPayload = asObject(evidence.prompt_payload);
  return asObject(promptPayload.constraints);
}

export function getSkeleton(evidence: EvidencePackageRecord): JsonObject {
  const promptPayload = asObject(evidence.prompt_payload);
  return asObject(promptPayload.backend_explanation_skeleton);
}

export function getSkeletonFeatureIds(skeleton: JsonObject): string[] {
  const slots = skeleton.main_factor_slots;
  if (!Array.isArray(slots)) return [];
  return slots
    .map((slot) => (isPlainObject(slot) ? asString(slot.feature_id) : ""))
    .filter(Boolean);
}

export function matchesSkeletonOrder(
  factors: ExplanationFactor[],
  expectedFeatureIds: string[],
): boolean {
  if (factors.length !== expectedFeatureIds.length) return false;
  return expectedFeatureIds.every((featureId, index) => {
    const factor = factors[index];
    return factor?.declared_feature_ids[0] === featureId;
  });
}

export function collectNarrativeText(output: JsonObject | null): string {
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

export function hasVietnameseSignal(text: string): boolean {
  const normalized = text.toLowerCase();
  const accentedCharacters =
    normalized.match(
      /[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/g,
    )?.length ?? 0;
  const words = normalized.match(/[\p{L}]+/gu) ?? [];
  const vietnameseWords = new Set([
    "mô",
    "hình",
    "rủi",
    "ro",
    "dự",
    "đoán",
    "không",
    "bằng",
    "chứng",
    "yếu",
    "tố",
    "tín",
    "hiệu",
    "góp",
    "phần",
    "tăng",
    "giảm",
    "khách",
  ]);
  const wordMatches = words.filter((word) => vietnameseWords.has(word)).length;
  return accentedCharacters >= 2 || wordMatches >= 3;
}

export function hasHeavyEnglishProse(text: string): boolean {
  const words = text.toLowerCase().match(/[a-z]+/g) ?? [];
  const englishWords = new Set([
    "the",
    "and",
    "because",
    "therefore",
    "customer",
    "will",
    "with",
    "from",
    "this",
    "that",
    "shows",
    "means",
    "likely",
    "certainly",
  ]);
  return words.filter((word) => englishWords.has(word)).length >= 5;
}

export function calculateDuplicateSentenceRate(text: string): number {
  const sentences = text
    .split(/[.!?]+/)
    .map((sentence) => sentence.toLowerCase().replace(/\s+/g, " ").trim())
    .filter((sentence) => sentence.length >= 12);
  if (sentences.length === 0) return 0;
  return (sentences.length - new Set(sentences).size) / sentences.length;
}

export function findDuplicates(values: string[]): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value);
    seen.add(value);
  }
  return [...duplicates].sort();
}

export function unique(values: string[]): string[] {
  return [...new Set(values)].sort();
}

function asObject(value: unknown): JsonObject {
  return isPlainObject(value) ? value : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}
