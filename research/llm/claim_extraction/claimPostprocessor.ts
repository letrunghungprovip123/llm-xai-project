import type {
  AtomicClaimDraft,
  ClaimExtractionPostprocessMetrics,
  ClaimNumericRole,
  ClaimSourceSection,
} from "../../../contracts/validation-claims";
import type { GenerationTextDocument, GenerationTextSpan } from "./generationTextAdapter";

const SECTION_ORDER: ClaimSourceSection[] = [
  "prediction_summary",
  "factor_name",
  "factor_explanation",
  "uncertainty_note",
  "distributed_evidence_note",
  "safe_summary",
];

type DeduplicationResult = {
  claims: AtomicClaimDraft[];
  duplicateCount: number;
  redundantSourceSlots: Set<string>;
};

// Hậu xử lý bổ sung claim chắc chắn từ metadata rồi chuẩn hóa atomicity và dedup.
export function postprocessAtomicClaims(
  llmClaims: AtomicClaimDraft[],
  document: GenerationTextDocument,
): { claims: AtomicClaimDraft[]; metrics: ClaimExtractionPostprocessMetrics } {
  const causalResult = demoteModelContributionCausality(llmClaims);
  const deterministicClaims = buildDeterministicPresenceClaims(document);
  const firstPass = deduplicateClaims(
    [...causalResult.claims, ...deterministicClaims].map(withSemanticSignature),
  );

  const splitResult = splitNumericAttributes(firstPass.claims);
  const secondPass = deduplicateClaims(
    splitResult.claims.map(withSemanticSignature),
  );
  const finalClaims = secondPass.claims
    .sort(compareClaims)
    .map((claim, index) => ({
      ...claim,
      local_claim_index: index + 1,
    }));

  const redundantSourceSlots = new Set([
    ...firstPass.redundantSourceSlots,
    ...secondPass.redundantSourceSlots,
  ]);
  const coverage = calculateCoverage(
    document,
    finalClaims,
    redundantSourceSlots,
  );

  return {
    claims: finalClaims,
    metrics: {
      llm_claim_count: llmClaims.length,
      deterministic_claim_count_added: deterministicClaims.length,
      derived_numeric_claim_count_added: splitResult.derivedCount,
      causal_overclaim_count_demoted: causalResult.demotedCount,
      semantic_duplicate_count_removed:
        firstPass.duplicateCount + secondPass.duplicateCount,
      final_claim_count: finalClaims.length,
      ...coverage,
    },
  };
}

// Ngôn ngữ đóng góp vào dự đoán là liên hệ trong mô hình, không phải nhân quả đời thực.
function demoteModelContributionCausality(
  claims: AtomicClaimDraft[],
): { claims: AtomicClaimDraft[]; demotedCount: number } {
  let demotedCount = 0;
  const normalizedClaims = claims.map((claim) => {
    const isDirectionClaim =
      claim.claim_type === "feature_direction" ||
      claim.claim_type === "concept_direction";
    if (
      !isDirectionClaim ||
      claim.causal_strength !== "causal" ||
      !looksLikeModelContribution(claim.source_text)
    ) {
      return claim;
    }

    demotedCount += 1;
    return {
      ...claim,
      causal_strength: "associational" as const,
    };
  });

  return { claims: normalizedClaims, demotedCount };
}

function looksLikeModelContribution(sourceText: string): boolean {
  const normalized = sourceText.normalize("NFC").toLowerCase();
  const explicitlyCausal = ["gây ra", "dẫn đến", "là nguyên nhân", "khiến cho"]
    .some((phrase) => normalized.includes(phrase));
  if (explicitlyCausal) return false;

  return [
    "góp phần",
    "đóng góp",
    "liên quan",
    "tương quan",
    "ảnh hưởng đến dự đoán",
    "trong mô hình",
    "của mô hình",
  ].some((phrase) => normalized.includes(phrase));
}

// Presence được lấy từ declared IDs nên ổn định và không cần tốn thêm output token.
function buildDeterministicPresenceClaims(
  document: GenerationTextDocument,
): AtomicClaimDraft[] {
  const claims: AtomicClaimDraft[] = [];

  const nextOccurrenceByFactorId = new Map<string, number>();
  for (const factor of document.factor_metadata) {
    const occurrence = nextOccurrenceByFactorId.get(
      factor.source_factor_id,
    ) ?? 0;
    nextOccurrenceByFactorId.set(factor.source_factor_id, occurrence + 1);
    const factorNameSpan = findFactorNameSpan(
      document,
      factor.source_factor_id,
      occurrence,
    );
    if (!factorNameSpan) continue;

    const sourceText = document.generation_text.slice(
      factorNameSpan.start,
      factorNameSpan.end,
    );
    for (const featureId of uniqueStrings(factor.declared_feature_ids)) {
      claims.push(
        buildPresenceClaim({
          sourceText,
          span: factorNameSpan,
          featureId,
          conceptId: null,
        }),
      );
    }
    for (const conceptId of uniqueStrings(factor.declared_concept_ids)) {
      claims.push(
        buildPresenceClaim({
          sourceText,
          span: factorNameSpan,
          featureId: null,
          conceptId,
        }),
      );
    }
  }

  return claims;
}

function buildPresenceClaim(input: {
  sourceText: string;
  span: GenerationTextSpan;
  featureId: string | null;
  conceptId: string | null;
}): AtomicClaimDraft {
  const isFeature = input.featureId !== null;
  return {
    local_claim_index: 0,
    source_section: "factor_name",
    source_factor_id: input.span.source_factor_id,
    source_text: input.sourceText,
    source_span_start: input.span.start,
    source_span_end: input.span.end,
    claim_type: isFeature ? "feature_presence" : "concept_presence",
    subject_type: isFeature ? "feature" : "concept",
    feature_id: input.featureId,
    concept_id: input.conceptId,
    direction: "unknown",
    magnitude: null,
    certainty: "deterministic",
    causal_strength: "none",
    numeric_value: null,
    numeric_unit: null,
    numeric_role: null,
    claim_origin: "deterministic_metadata",
    model_normalized_claim_key: null,
    semantic_signature: "",
    normalized_claim_key: "",
  };
}

// Numeric gắn trên claim khác sẽ được tách thành claim riêng với quote ngắn nhất.
function splitNumericAttributes(claims: AtomicClaimDraft[]): {
  claims: AtomicClaimDraft[];
  derivedCount: number;
} {
  const result: AtomicClaimDraft[] = [];
  let derivedCount = 0;

  for (const claim of claims) {
    if (claim.claim_type === "numeric") {
      const numericSource = locateNumericSource(claim);
      result.push({
        ...claim,
        source_text: numericSource.text,
        source_span_start: numericSource.start,
        source_span_end: numericSource.end,
      });
      continue;
    }

    if (claim.numeric_value === null) {
      result.push(claim);
      continue;
    }

    const numericSource = locateNumericSource(claim);
    const numericRole = claim.numeric_role ?? inferNumericRole(claim);
    const baseClaim: AtomicClaimDraft = {
      ...claim,
      numeric_value: null,
      numeric_unit: null,
      numeric_role: null,
      semantic_signature: "",
      normalized_claim_key: "",
    };
    const numericClaim: AtomicClaimDraft = {
      ...claim,
      local_claim_index: 0,
      source_text: numericSource.text,
      source_span_start: numericSource.start,
      source_span_end: numericSource.end,
      claim_type: "numeric",
      direction: "unknown",
      magnitude: null,
      causal_strength: "none",
      numeric_role: numericRole,
      claim_origin: "derived_numeric",
      semantic_signature: "",
      normalized_claim_key: "",
    };

    result.push(baseClaim, numericClaim);
    derivedCount += 1;
  }

  return { claims: result, derivedCount };
}

export function locateNumericSource(claim: AtomicClaimDraft): {
  text: string;
  start: number;
  end: number;
} {
  const pattern = /[+-]?\d+(?:[.,]\d+)*(?:\s*%)?/gu;
  for (const match of claim.source_text.matchAll(pattern)) {
    const raw = match[0];
    const parsed = parseNumericToken(raw);
    if (parsed === null || !numbersEqual(parsed, claim.numeric_value)) continue;

    const leadingSpace = raw.length - raw.trimStart().length;
    const text = raw.trim();
    const start = claim.source_span_start + (match.index ?? 0) + leadingSpace;
    return { text, start, end: start + text.length };
  }

  return {
    text: claim.source_text,
    start: claim.source_span_start,
    end: claim.source_span_end,
  };
}

function parseNumericToken(value: string): number | null {
  const compact = value.replace(/[%\s\u00a0\u202f]/gu, "");
  let normalized = compact;

  if (/^[+-]?[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?$/u.test(compact)) {
    normalized = compact.replace(/,/gu, "");
  } else if (/^[+-]?[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?$/u.test(compact)) {
    normalized = compact.replace(/\./gu, "").replace(",", ".");
  } else if (/^[+-]?\d+,\d+$/u.test(compact)) {
    normalized = compact.replace(",", ".");
  } else if (!/^[+-]?\d+(?:\.\d+)?$/u.test(compact)) {
    return null;
  }

  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function inferNumericRole(claim: AtomicClaimDraft): ClaimNumericRole {
  if (claim.claim_type === "ranking") return "rank";
  if (claim.subject_type === "prediction") return "prediction_score";
  if (claim.subject_type === "feature") return "feature_value";
  return "other";
}

// Signature chỉ giữ nội dung kiểm định, không phụ thuộc section hoặc cách model đặt key.
function withSemanticSignature(claim: AtomicClaimDraft): AtomicClaimDraft {
  const signature = buildSemanticSignature(claim);
  return {
    ...claim,
    semantic_signature: signature,
    normalized_claim_key: signature,
  };
}

export function buildSemanticSignature(claim: AtomicClaimDraft): string {
  const feature = normalizePart(claim.feature_id);
  const concept = normalizePart(claim.concept_id);
  const magnitude = claim.magnitude ?? "none";
  const numeric = claim.numeric_value === null
    ? "none"
    : `${formatNumber(claim.numeric_value)}:${normalizePart(claim.numeric_unit)}`;
  const numericRole = claim.numeric_role ?? "none";

  switch (claim.claim_type) {
    case "feature_presence":
      return `feature_presence|feature:${feature}`;
    case "concept_presence":
      return `concept_presence|concept:${concept}`;
    case "feature_direction":
      return [
        "feature_direction",
        `feature:${feature}`,
        `direction:${claim.direction}`,
        `causal:${claim.causal_strength}`,
      ].join("|");
    case "concept_direction":
      return [
        "concept_direction",
        `concept:${concept}`,
        `direction:${claim.direction}`,
        `causal:${claim.causal_strength}`,
      ].join("|");
    case "prediction":
      return [
        "prediction",
        `direction:${claim.direction}`,
        `magnitude:${magnitude}`,
        `certainty:${claim.certainty}`,
        `numeric:${numeric}`,
      ].join("|");
    case "numeric":
      return [
        "numeric",
        `subject:${claim.subject_type}`,
        `feature:${feature}`,
        `concept:${concept}`,
        `role:${numericRole}`,
        `value:${numeric}`,
      ].join("|");
    case "magnitude":
      return [
        "magnitude",
        `subject:${claim.subject_type}`,
        `feature:${feature}`,
        `concept:${concept}`,
        `value:${magnitude}`,
      ].join("|");
    default:
      return [
        claim.claim_type,
        `subject:${claim.subject_type}`,
        `feature:${feature}`,
        `concept:${concept}`,
        `model_key:${normalizePart(claim.model_normalized_claim_key)}`,
      ].join("|");
  }
}

function deduplicateClaims(claims: AtomicClaimDraft[]): DeduplicationResult {
  const bySignature = new Map<string, AtomicClaimDraft>();
  const redundantSourceSlots = new Set<string>();
  let duplicateCount = 0;

  for (const claim of claims) {
    const existing = bySignature.get(claim.semantic_signature);
    if (!existing) {
      bySignature.set(claim.semantic_signature, claim);
      continue;
    }

    duplicateCount += 1;
    const preferred = compareClaimPreference(claim, existing) < 0
      ? claim
      : existing;
    const discarded = preferred === claim ? existing : claim;
    bySignature.set(claim.semantic_signature, preferred);
    redundantSourceSlots.add(sourceSlot(discarded));
  }

  return {
    claims: [...bySignature.values()],
    duplicateCount,
    redundantSourceSlots,
  };
}

export function compareClaimPreference(
  left: AtomicClaimDraft,
  right: AtomicClaimDraft,
): number {
  return (
    sectionRank(left) - sectionRank(right) ||
    originRank(left) - originRank(right) ||
    left.source_span_start - right.source_span_start ||
    left.source_span_end - right.source_span_end
  );
}

function sectionRank(claim: AtomicClaimDraft): number {
  if (claim.claim_type === "feature_presence" || claim.claim_type === "concept_presence") {
    return claim.source_section === "factor_name" ? 0 : 1;
  }
  if (claim.claim_type === "feature_direction" || claim.claim_type === "concept_direction") {
    return claim.source_section === "factor_explanation" ? 0 : 1;
  }
  return SECTION_ORDER.indexOf(claim.source_section);
}

function originRank(claim: AtomicClaimDraft): number {
  if (claim.claim_type === "feature_presence" || claim.claim_type === "concept_presence") {
    return claim.claim_origin === "deterministic_metadata" ? 0 : 1;
  }
  if (claim.claim_origin === "llm") return 0;
  if (claim.claim_origin === "derived_numeric") return 1;
  return 2;
}

function calculateCoverage(
  document: GenerationTextDocument,
  claims: AtomicClaimDraft[],
  redundantSourceSlots: Set<string>,
): Pick<
  ClaimExtractionPostprocessMetrics,
  | "nonempty_source_slot_count"
  | "claimed_source_slot_count"
  | "semantically_redundant_source_slots"
  | "unclaimed_source_slots"
  | "effective_source_coverage_rate"
> {
  const allSlots = document.section_spans.map(sourceSlot);
  const claimedSlots = new Set(claims.map(sourceSlot));
  const redundantOnly = [...redundantSourceSlots]
    .filter((slot) => !claimedSlots.has(slot))
    .sort();
  const coveredSlots = new Set([...claimedSlots, ...redundantOnly]);
  const unclaimedSourceSlots = allSlots
    .filter((slot) => !coveredSlots.has(slot))
    .sort();
  const coverageRate = allSlots.length === 0
    ? 1
    : coveredSlots.size / allSlots.length;

  return {
    nonempty_source_slot_count: allSlots.length,
    claimed_source_slot_count: claimedSlots.size,
    semantically_redundant_source_slots: redundantOnly,
    unclaimed_source_slots: unclaimedSourceSlots,
    effective_source_coverage_rate: Number(coverageRate.toFixed(6)),
  };
}

export function compareClaims(left: AtomicClaimDraft, right: AtomicClaimDraft): number {
  return (
    left.source_span_start - right.source_span_start ||
    left.source_span_end - right.source_span_end ||
    left.claim_type.localeCompare(right.claim_type) ||
    left.semantic_signature.localeCompare(right.semantic_signature)
  );
}

function sourceSlot(value: AtomicClaimDraft | GenerationTextSpan): string {
  return value.source_factor_id
    ? `${value.source_section}:${value.source_factor_id}`
    : value.source_section;
}

function findFactorNameSpan(
  document: GenerationTextDocument,
  factorId: string,
  occurrence: number,
): GenerationTextSpan | null {
  return document.section_spans.filter(
    (span) =>
      span.source_section === "factor_name" &&
      span.source_factor_id === factorId,
  )[occurrence] ?? null;
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

function normalizePart(value: string | null): string {
  return value?.normalize("NFC").trim().toLowerCase().replace(/\s+/gu, " ") || "none";
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(15)));
}

function numbersEqual(left: number, right: number | null): boolean {
  if (right === null) return false;
  const tolerance = Math.max(1e-9, Math.abs(right) * 1e-9);
  return Math.abs(left - right) <= tolerance;
}
