import type {
  AtomicClaimDraft,
  AtomicClaimRecord,
  ClaimDirection,
} from "../../../contracts/validation-claims";
import { sha256 } from "../common/utils";
import {
  buildSemanticSignature,
  compareClaimPreference,
  compareClaims,
  locateNumericSource,
} from "../claim_extraction/claimPostprocessor";
import type {
  GenerationTextDocument,
  GenerationTextSpan,
} from "../claim_extraction/generationTextAdapter";

export const CLAIM_FINALIZER_VERSION = "claim_finalizer_v1.1.0";
export const CLAIM_FINALIZATION_POLICY_VERSION = "claim_finalization_policy_v2";

export const CLAIM_FINALIZATION_RULE_CODES = [
  "EXPLICIT_PREDICTION_DIRECTION",
  "SAFE_SUMMARY_NO_EVIDENCE",
  "SELECTED_EVIDENCE_COUNT",
  "SELECTED_EVIDENCE_NUMERIC_COUNT",
  "ADD_CONCEPT_GROUP_COUNT",
  "NON_CAUSAL_LIMITATION",
  "AGGREGATE_PREDICTION_TO_EVIDENCE",
  "UNKNOWN_DIRECTION_TO_EVIDENCE",
  "ASSOCIATIONAL_CAUSAL_TO_EVIDENCE",
  "UNCERTAINTY_CAUSAL_STRENGTH",
  "COVERAGE_THRESHOLD_NUMERIC_ROLE",
  "EXPAND_DIRECTIONAL_SOURCE",
  "MINIMIZE_NUMERIC_SOURCE",
  "NUMERIC_ORIGIN",
  "REBUILD_SEMANTIC_SIGNATURE",
  "REBUILD_CLAIM_ID",
  "SEMANTIC_DEDUPLICATION",
  "REINDEX_LOCAL_CLAIMS",
  "STORED_RESPONSE_REPLAY_CANONICALIZATION",
  "DROP_POLICY_ABSENCE_CLAIM",
  "COUNT_FACT_CANONICALIZATION",
] as const;

export type ClaimFinalizationRuleCode =
  (typeof CLAIM_FINALIZATION_RULE_CODES)[number];

export type TracedClaim = {
  record: AtomicClaimRecord;
  source_claim_ids: string[];
  rule_codes: Set<ClaimFinalizationRuleCode>;
};

type SelectedCountMetadata = {
  selectedEvidenceCount: number | null;
  conceptGroupCount: number | null;
  selectedEvidenceSpan: { start: number; end: number; text: string } | null;
  conceptGroupSpan: { start: number; end: number; text: string } | null;
};

export function finalizeGenerationClaims(
  claims: AtomicClaimRecord[],
  document: GenerationTextDocument,
): TracedClaim[] {
  const normalized = claims
    .filter((record) =>
      !isPolicyAbsenceSlot(record.source_section, record.source_text)
    )
    .map((record) =>
      normalizeClaim({
        record: { ...record },
        source_claim_ids: [record.claim_id],
        rule_codes: new Set<ClaimFinalizationRuleCode>(),
      }, document),
    );

  addMissingSelectedCountClaims(normalized, document);
  canonicalizeCountFacts(normalized, document);

  const signed = normalized.map((claim) => rebuildIdentity(claim));
  const deduplicated = deduplicate(signed);
  deduplicated.sort((left, right) =>
    compareClaims(left.record, right.record),
  );

  const finalized = deduplicated.map((claim, index) => {
    const localClaimIndex = index + 1;
    if (claim.record.local_claim_index !== localClaimIndex) {
      claim.record = {
        ...claim.record,
        local_claim_index: localClaimIndex,
      };
      claim.rule_codes.add("REINDEX_LOCAL_CLAIMS");
    }
    return claim;
  });

  assertCountFactCompleteness(
    finalized.map((claim) => claim.record),
    document,
  );
  return finalized;
}

export function isPolicyAbsenceSlot(
  sourceSection: string,
  sourceText: string,
): boolean {
  if (sourceSection !== "distributed_evidence_note") return false;
  const normalized = normalizeText(sourceText);
  return [
    "khong co yeu cau phan phoi bang chung",
    "khong co distributed evidence note do policy khong yeu cau",
  ].includes(normalized.replace(/[^a-z0-9 ]/gu, "").trim());
}

function normalizeClaim(
  traced: TracedClaim,
  document: GenerationTextDocument,
): TracedClaim {
  let claim = traced.record;
  const explicitDirection = explicitPredictionDirection(claim.source_text);

  if (
    claim.claim_type === "prediction"
    && explicitDirection
    && claim.direction !== explicitDirection
  ) {
    claim = { ...claim, direction: explicitDirection };
    traced.rule_codes.add("EXPLICIT_PREDICTION_DIRECTION");
  }

  if (
    claim.source_section === "safe_summary"
    && saysNoEvidenceWasIdentified(claim.source_text)
    && (
      claim.claim_type !== "uncertainty"
      || claim.subject_type !== "evidence"
      || claim.direction !== "unknown"
    )
  ) {
    claim = {
      ...claim,
      claim_type: "uncertainty",
      subject_type: "evidence",
      source_factor_id: null,
      feature_id: null,
      concept_id: null,
      direction: "unknown",
      magnitude: null,
      causal_strength: "none",
      numeric_value: null,
      numeric_unit: null,
      numeric_role: null,
    };
    traced.rule_codes.add("SAFE_SUMMARY_NO_EVIDENCE");
  }

  const selectedCounts = readSelectedCountMetadata(claim, document);
  if (
    selectedCounts
    && claim.claim_type !== "numeric"
    && isSelectedCountNarrativeClaim(claim)
  ) {
    claim = {
      ...claim,
      claim_type: "distributed_evidence",
      subject_type: "evidence",
      feature_id: null,
      concept_id: null,
      direction: "unknown",
      magnitude: null,
      causal_strength: "none",
      numeric_value: null,
      numeric_unit: null,
      numeric_role: null,
      model_normalized_claim_key: "selected_evidence_count",
    };
    traced.rule_codes.add("SELECTED_EVIDENCE_COUNT");
  }

  if (claim.claim_type === "numeric" && selectedCounts) {
    const numericValue = claim.numeric_value;
    const isSelectedEvidenceCount =
      numericValue !== null
      && selectedCounts.selectedEvidenceCount === numericValue
      && spanMatches(claim, selectedCounts.selectedEvidenceSpan);
    const isConceptGroupCount =
      numericValue !== null
      && selectedCounts.conceptGroupCount === numericValue
      && spanMatches(claim, selectedCounts.conceptGroupSpan);

    if (isSelectedEvidenceCount || isConceptGroupCount) {
      claim = {
        ...claim,
        subject_type: "evidence",
        feature_id: null,
        concept_id: null,
        direction: "unknown",
        magnitude: null,
        causal_strength: "none",
        numeric_unit: "count",
        numeric_role: "other",
        claim_origin: "derived_numeric",
        model_normalized_claim_key: isConceptGroupCount
          ? "concept_group_count"
          : "selected_evidence_count",
      };
      traced.rule_codes.add("SELECTED_EVIDENCE_NUMERIC_COUNT");
    }
  }

  if (looksLikeNonCausalLimitation(claim.source_text)) {
    claim = {
      ...claim,
      claim_type: "limitation",
      subject_type: "narrative",
      feature_id: null,
      concept_id: null,
      direction: "unknown",
      magnitude: null,
      causal_strength: "none",
      numeric_value: null,
      numeric_unit: null,
      numeric_role: null,
      model_normalized_claim_key: "non_causal_model_limitation",
    };
    traced.rule_codes.add("NON_CAUSAL_LIMITATION");
  }

  if (
    claim.claim_type === "prediction"
    && claim.source_section === "safe_summary"
    && looksLikeEvidenceSynthesis(claim.source_text)
  ) {
    claim = {
      ...claim,
      claim_type: "distributed_evidence",
      subject_type: "evidence",
      feature_id: null,
      concept_id: null,
      magnitude: null,
      causal_strength: "associational",
      numeric_value: null,
      numeric_unit: null,
      numeric_role: null,
    };
    traced.rule_codes.add("AGGREGATE_PREDICTION_TO_EVIDENCE");
  }

  if (
    (claim.claim_type === "feature_direction"
      || claim.claim_type === "concept_direction")
    && claim.direction === "unknown"
  ) {
    claim = {
      ...claim,
      claim_type: "distributed_evidence",
      magnitude: null,
      causal_strength: "associational",
      numeric_value: null,
      numeric_unit: null,
      numeric_role: null,
    };
    traced.rule_codes.add("UNKNOWN_DIRECTION_TO_EVIDENCE");
  }

  if (
    claim.claim_type === "causal"
    && claim.causal_strength !== "causal"
  ) {
    claim = {
      ...claim,
      claim_type: "distributed_evidence",
      subject_type: claim.feature_id
        ? "feature"
        : claim.concept_id
          ? "concept"
          : "evidence",
      magnitude: null,
      causal_strength: "associational",
      numeric_value: null,
      numeric_unit: null,
      numeric_role: null,
    };
    traced.rule_codes.add("ASSOCIATIONAL_CAUSAL_TO_EVIDENCE");
  }

  if (
    claim.claim_type === "uncertainty"
    && claim.causal_strength === "causal"
  ) {
    claim = { ...claim, causal_strength: "none" };
    traced.rule_codes.add("UNCERTAINTY_CAUSAL_STRENGTH");
  }

  if (
    claim.claim_type === "numeric"
    && claim.numeric_role === "decision_threshold"
    && looksLikeCoverageThreshold(claim)
  ) {
    claim = { ...claim, numeric_role: "other" };
    traced.rule_codes.add("COVERAGE_THRESHOLD_NUMERIC_ROLE");
  }

  const expanded = expandDirectionalSource(claim, document);
  if (expanded) {
    claim = {
      ...claim,
      source_text: expanded.text,
      source_span_start: expanded.start,
      source_span_end: expanded.end,
      source_text_sha256: sha256(expanded.text),
    };
    traced.rule_codes.add("EXPAND_DIRECTIONAL_SOURCE");
  }

  if (claim.claim_type === "numeric") {
    const numericSource = locateNumericSource(claim);
    if (
      numericSource.text !== claim.source_text
      || numericSource.start !== claim.source_span_start
      || numericSource.end !== claim.source_span_end
    ) {
      claim = {
        ...claim,
        source_text: numericSource.text,
        source_span_start: numericSource.start,
        source_span_end: numericSource.end,
        source_text_sha256: sha256(numericSource.text),
      };
      traced.rule_codes.add("MINIMIZE_NUMERIC_SOURCE");
    }
    if (claim.claim_origin === "deterministic_metadata") {
      claim = { ...claim, claim_origin: "derived_numeric" };
      traced.rule_codes.add("NUMERIC_ORIGIN");
    }
  }

  traced.record = claim;
  return traced;
}


export type CountFact = {
  target: string;
  value: number;
  source_section: AtomicClaimRecord["source_section"];
  source_factor_id: string | null;
  source_text: string;
  source_span_start: number;
  source_span_end: number;
};

const COUNT_FACT_PATTERN =
  /(\d+)\s+(yếu\s+tố|yeu\s+to|đặc\s+trưng|dac\s+trung|tín\s+hiệu|tin\s+hieu|features?|factors?|signals?|nhóm\s+khái\s+niệm|nhom\s+khai\s+niem|nhóm\s+concept|nhom\s+concept|concept\s+groups?|nhóm\s+hỗn\s+hợp|nhom\s+hon\s+hop|mixed\s+concept\s+groups?|nhóm\s+yếu\s+tố|nhom\s+yeu\s+to|nhóm|nhom|groups?)(?=\s|[.,;:)]|$)/giu;

const COUNT_TARGET_PATTERN =
  /^(?:selected_evidence_count|concept_group_count|mixed_concept_group_count|factor_member_count:[a-z0-9_.-]+)$/u;

export function extractCountFacts(
  document: GenerationTextDocument,
): CountFact[] {
  const bySemanticFact = new Map<string, CountFact>();
  const spans = [...document.section_spans].sort(
    (left, right) => left.start - right.start,
  );

  for (const span of spans) {
    const sectionText = document.generation_text.slice(span.start, span.end);
    for (const match of sectionText.matchAll(COUNT_FACT_PATTERN)) {
      const numericText = match[1];
      const noun = match[2];
      if (!numericText || !noun) continue;
      const value = Number(numericText);
      if (!Number.isSafeInteger(value) || value < 0) continue;

      const target = classifyCountTarget(
        noun,
        span.source_section,
        span.source_factor_id,
      );
      const localStart = (match.index ?? 0) + match[0].indexOf(numericText);
      const sourceSpanStart = span.start + localStart;
      const fact: CountFact = {
        target,
        value,
        source_section: span.source_section,
        source_factor_id: span.source_factor_id,
        source_text: numericText,
        source_span_start: sourceSpanStart,
        source_span_end: sourceSpanStart + numericText.length,
      };
      const key = `${target}|${value}`;
      const existing = bySemanticFact.get(key);
      if (!existing || fact.source_span_start < existing.source_span_start) {
        bySemanticFact.set(key, fact);
      }
    }
  }

  return [...bySemanticFact.values()].sort(
    (left, right) => left.source_span_start - right.source_span_start
      || left.target.localeCompare(right.target)
      || left.value - right.value,
  );
}

function classifyCountTarget(
  noun: string,
  sourceSection: AtomicClaimRecord["source_section"],
  sourceFactorId: string | null,
): string {
  const normalizedNoun = normalizeText(noun);
  if (
    normalizedNoun.includes("nhom hon hop")
    || normalizedNoun.includes("mixed concept group")
  ) {
    return "mixed_concept_group_count";
  }
  if (
    normalizedNoun.includes("nhom khai niem")
    || normalizedNoun.includes("nhom concept")
    || normalizedNoun.includes("concept group")
    || normalizedNoun.includes("nhom yeu to")
    || normalizedNoun === "nhom"
    || normalizedNoun === "group"
    || normalizedNoun === "groups"
  ) {
    return "concept_group_count";
  }
  if (sourceSection === "factor_explanation" && sourceFactorId) {
    return `factor_member_count:${sourceFactorId}`;
  }
  return "selected_evidence_count";
}

function canonicalizeCountFacts(
  claims: TracedClaim[],
  document: GenerationTextDocument,
): void {
  for (const fact of extractCountFacts(document)) {
    const exact = claims.filter((claim) =>
      claim.record.claim_type === "numeric"
      && claim.record.source_span_start === fact.source_span_start
      && claim.record.source_span_end === fact.source_span_end
      && claim.record.numeric_value === fact.value
    );
    const semantic = claims.filter((claim) =>
      claim.record.claim_type === "numeric"
      && claim.record.numeric_value === fact.value
      && claim.record.model_normalized_claim_key === fact.target
    );
    const candidates = exact.length > 0 ? exact : semantic;

    if (candidates.length > 0) {
      for (const candidate of candidates) {
        candidate.record = toCanonicalCountClaim(candidate.record, fact);
        candidate.rule_codes.add("COUNT_FACT_CANONICALIZATION");
      }
      continue;
    }

    const template = findCountClaimTemplate(claims, fact);
    if (!template) {
      throw new Error(
        `Cannot create count fact ${fact.target}=${fact.value}: no claim lineage template.`,
      );
    }
    claims.push({
      record: toCanonicalCountClaim(template.record, fact),
      source_claim_ids: [...template.source_claim_ids],
      rule_codes: new Set<ClaimFinalizationRuleCode>([
        "COUNT_FACT_CANONICALIZATION",
      ]),
    });
  }
}

function findCountClaimTemplate(
  claims: TracedClaim[],
  fact: CountFact,
): TracedClaim | null {
  const sameSpan = claims.filter((claim) =>
    claim.record.source_section === fact.source_section
    && claim.record.source_factor_id === fact.source_factor_id
    && claim.record.source_span_start <= fact.source_span_start
    && claim.record.source_span_end >= fact.source_span_end
  );
  const sameSlot = claims.filter((claim) =>
    claim.record.source_section === fact.source_section
    && claim.record.source_factor_id === fact.source_factor_id
  );
  const candidates = sameSpan.length > 0
    ? sameSpan
    : sameSlot.length > 0
      ? sameSlot
      : claims;
  return [...candidates].sort((left, right) =>
    compareClaims(left.record, right.record)
  )[0] ?? null;
}

function toCanonicalCountClaim(
  source: AtomicClaimRecord,
  fact: CountFact,
): AtomicClaimRecord {
  return {
    ...source,
    local_claim_index: 0,
    source_section: fact.source_section,
    source_factor_id: fact.source_factor_id,
    source_text: fact.source_text,
    source_span_start: fact.source_span_start,
    source_span_end: fact.source_span_end,
    source_text_sha256: sha256(fact.source_text),
    claim_type: "numeric",
    subject_type: "evidence",
    feature_id: null,
    concept_id: null,
    direction: "unknown",
    magnitude: null,
    certainty: "deterministic",
    causal_strength: "none",
    numeric_value: fact.value,
    numeric_unit: "count",
    numeric_role: "other",
    claim_origin: "derived_numeric",
    model_normalized_claim_key: fact.target,
    semantic_signature: "",
    normalized_claim_key: "",
    claim_id: "",
  };
}

export function assertCountFactCompleteness(
  claims: AtomicClaimRecord[],
  document: GenerationTextDocument,
): void {
  for (const fact of extractCountFacts(document)) {
    const matches = claims.filter((claim) =>
      claim.claim_type === "numeric"
      && claim.subject_type === "evidence"
      && claim.numeric_value === fact.value
      && claim.numeric_unit === "count"
      && claim.numeric_role === "other"
      && claim.claim_origin === "derived_numeric"
      && claim.model_normalized_claim_key === fact.target
      && claim.source_text === fact.source_text
      && claim.source_span_start === fact.source_span_start
      && claim.source_span_end === fact.source_span_end
    );
    if (matches.length !== 1) {
      throw new Error(
        `Count fact completeness failure: ${fact.target}=${fact.value}; `
          + `matches=${matches.length}; section=${fact.source_section}; `
          + `factor=${fact.source_factor_id ?? "none"}.`,
      );
    }
  }
}

function buildFinalSemanticSignature(claim: AtomicClaimRecord): string {
  const base = buildSemanticSignature(claim);
  const target = claim.model_normalized_claim_key;
  if (
    claim.claim_type === "numeric"
    && claim.numeric_unit === "count"
    && target
    && COUNT_TARGET_PATTERN.test(target)
  ) {
    return `${base}|target:${target}`;
  }
  return base;
}

function addMissingSelectedCountClaims(
  claims: TracedClaim[],
  document: GenerationTextDocument,
): void {
  const candidates = claims.filter(
    (claim) => readSelectedCountMetadata(claim.record, document) !== null,
  );
  if (candidates.length === 0) return;

  const first = candidates[0];
  if (!first) return;
  const metadata = readSelectedCountMetadata(first.record, document);
  if (!metadata?.conceptGroupCount || !metadata.conceptGroupSpan) return;

  const exists = claims.some(
    (claim) =>
      claim.record.claim_type === "numeric"
      && claim.record.numeric_value === metadata.conceptGroupCount
      && claim.record.model_normalized_claim_key === "concept_group_count",
  );
  if (exists) return;

  const source = first.record;
  const added: AtomicClaimRecord = {
    ...source,
    local_claim_index: 0,
    source_text: metadata.conceptGroupSpan.text,
    source_span_start: metadata.conceptGroupSpan.start,
    source_span_end: metadata.conceptGroupSpan.end,
    source_text_sha256: sha256(metadata.conceptGroupSpan.text),
    claim_type: "numeric",
    subject_type: "evidence",
    feature_id: null,
    concept_id: null,
    direction: "unknown",
    magnitude: null,
    causal_strength: "none",
    numeric_value: metadata.conceptGroupCount,
    numeric_unit: "count",
    numeric_role: "other",
    claim_origin: "derived_numeric",
    model_normalized_claim_key: "concept_group_count",
    semantic_signature: "",
    normalized_claim_key: "",
    claim_id: "",
  };

  claims.push({
    record: added,
    source_claim_ids: [...first.source_claim_ids],
    rule_codes: new Set<ClaimFinalizationRuleCode>([
      "ADD_CONCEPT_GROUP_COUNT",
    ]),
  });
}

function rebuildIdentity(claim: TracedClaim): TracedClaim {
  const signature = buildFinalSemanticSignature(claim.record);
  let record = claim.record;
  if (
    record.semantic_signature !== signature
    || record.normalized_claim_key !== signature
  ) {
    record = {
      ...record,
      semantic_signature: signature,
      normalized_claim_key: signature,
    };
    claim.rule_codes.add("REBUILD_SEMANTIC_SIGNATURE");
  }

  const claimId = buildClaimId(
    record.generation_id,
    signature,
    record.source_span_start,
  );
  if (record.claim_id !== claimId) {
    record = { ...record, claim_id: claimId };
    claim.rule_codes.add("REBUILD_CLAIM_ID");
  }

  claim.record = record;
  return claim;
}

function deduplicate(claims: TracedClaim[]): TracedClaim[] {
  const bySignature = new Map<string, TracedClaim>();
  for (const claim of claims) {
    const signature = claim.record.semantic_signature;
    const existing = bySignature.get(signature);
    if (!existing) {
      bySignature.set(signature, claim);
      continue;
    }

    const preferred = compareClaimPreference(
      claim.record,
      existing.record,
    ) < 0 ? claim : existing;
    const discarded = preferred === claim ? existing : claim;
    preferred.rule_codes.add("SEMANTIC_DEDUPLICATION");
    preferred.source_claim_ids = uniqueStrings([
      ...preferred.source_claim_ids,
      ...discarded.source_claim_ids,
    ]);
    bySignature.set(signature, preferred);
  }
  return [...bySignature.values()];
}


function isSelectedCountNarrativeClaim(
  claim: AtomicClaimRecord,
): boolean {
  if (
    /(?:selected_evidence_count|concept_group_count)/u.test(
      claim.model_normalized_claim_key ?? "",
    )
  ) {
    return true;
  }
  return SELECTED_EVIDENCE_COUNT_PATTERN.test(claim.source_text);
}

function spanMatches(
  claim: AtomicClaimRecord,
  span: { start: number; end: number } | null,
): boolean {
  return span !== null
    && claim.source_span_start === span.start
    && claim.source_span_end === span.end;
}

const SELECTED_EVIDENCE_COUNT_PATTERN =
  /(\d+)\s+(?:yếu tố|đặc trưng|features?|factors?)(?=\s|[.,;:)]|$)/iu;

const CONCEPT_GROUP_COUNT_PATTERN =
  /(\d+)\s+(?:nhóm\s+khái\s+niệm|concept\s+groups?)(?=\s|[.,;:)]|$)/iu;

function readSelectedCountMetadata(
  claim: AtomicClaimRecord,
  document: GenerationTextDocument,
): SelectedCountMetadata | null {
  if (claim.source_section !== "prediction_summary") return null;
  const span = findDeclaredSpan(claim, document);
  if (!span) return null;
  const sectionText = document.generation_text.slice(span.start, span.end);
  const normalized = normalizeText(sectionText);
  const modelKey = normalizeText(claim.model_normalized_claim_key ?? "");
  if (
    !/(?:dua tren|based on|selected|duoc chon)/u.test(
      `${normalized} ${modelKey}`,
    )
  ) {
    return null;
  }

  const selected = findCount(
    sectionText,
    SELECTED_EVIDENCE_COUNT_PATTERN,
    span.start,
  );
  if (!selected) return null;

  const conceptGroups = findCount(
    sectionText,
    CONCEPT_GROUP_COUNT_PATTERN,
    span.start,
  );

  return {
    selectedEvidenceCount: selected.value,
    conceptGroupCount: conceptGroups?.value ?? null,
    selectedEvidenceSpan: selected,
    conceptGroupSpan: conceptGroups,
  };
}

function findCount(
  text: string,
  pattern: RegExp,
  absoluteStart: number,
): { value: number; start: number; end: number; text: string } | null {
  const match = pattern.exec(text);
  const numericText = match?.[1];
  if (!match || numericText === undefined) return null;
  const localStart = (match.index ?? 0) + match[0].indexOf(numericText);
  const start = absoluteStart + localStart;
  return {
    value: Number(numericText),
    start,
    end: start + numericText.length,
    text: numericText,
  };
}

function expandDirectionalSource(
  claim: AtomicClaimRecord,
  document: GenerationTextDocument,
): { text: string; start: number; end: number } | null {
  if (
    claim.claim_type !== "feature_direction"
    && claim.claim_type !== "concept_direction"
  ) {
    return null;
  }
  if (
    claim.direction !== "increase_risk"
    && claim.direction !== "decrease_risk"
  ) {
    return null;
  }
  if (textSupportsDirection(claim.source_text, claim.direction)) return null;

  const span = findDeclaredSpan(claim, document);
  if (!span) return null;
  const fullText = document.generation_text.slice(span.start, span.end);
  if (!textSupportsDirection(fullText, claim.direction)) return null;
  const opposite: ClaimDirection = claim.direction === "increase_risk"
    ? "decrease_risk"
    : "increase_risk";
  if (textSupportsDirection(fullText, opposite)) return null;

  return { text: fullText, start: span.start, end: span.end };
}

function findDeclaredSpan(
  claim: AtomicClaimDraft,
  document: GenerationTextDocument,
): GenerationTextSpan | null {
  return document.section_spans.find(
    (span) =>
      span.source_section === claim.source_section
      && span.source_factor_id === claim.source_factor_id
      && claim.source_span_start >= span.start
      && claim.source_span_end <= span.end,
  ) ?? null;
}

function explicitPredictionDirection(
  sourceText: string,
): "increase_risk" | "decrease_risk" | null {
  const normalized = normalizeText(sourceText);
  const lowRisk = [
    "rui ro thap",
    "nguy co thap",
    "low default risk",
    "low risk of default",
  ].some((phrase) => normalized.includes(phrase));
  const highRisk = [
    "rui ro cao",
    "rui ro tin dung cao",
    "nguy co cao",
    "high default risk",
    "high risk of default",
  ].some((phrase) => normalized.includes(phrase));
  if (lowRisk === highRisk) return null;
  return lowRisk ? "decrease_risk" : "increase_risk";
}

function textSupportsDirection(
  sourceText: string,
  direction: ClaimDirection,
): boolean {
  const normalized = normalizeText(sourceText);
  const phrases = direction === "increase_risk"
    ? [
      "tang rui ro",
      "tang nguy co",
      "lam tang kha nang vo no",
      "increase risk",
      "increases risk",
      "higher risk",
    ]
    : [
      "giam rui ro",
      "giam nguy co",
      "lam giam kha nang vo no",
      "decrease risk",
      "decreases risk",
      "lower risk",
    ];
  return phrases.some((phrase) => normalized.includes(phrase));
}

function saysNoEvidenceWasIdentified(sourceText: string): boolean {
  const normalized = normalizeText(sourceText);
  return [
    "khong co yeu to duoc xac dinh",
    "khong co bang chung cu the",
    "no factors were identified",
    "no evidence was identified",
  ].some((phrase) => normalized.includes(phrase));
}

function looksLikeNonCausalLimitation(sourceText: string): boolean {
  const normalized = normalizeText(sourceText);
  return [
    "khong khang dinh quan he nhan qua",
    "khong phai nguyen nhan thuc te",
    "not assert a causal relationship",
    "not a real world cause",
    "not actual causes",
  ].some((phrase) => normalized.includes(phrase));
}

function looksLikeEvidenceSynthesis(sourceText: string): boolean {
  const normalized = normalizeText(sourceText);
  return [
    "gop phan tang rui ro",
    "gop phan giam rui ro",
    "gop phan vao du doan",
    "chu yeu do",
    "dua tren cac yeu to",
    "due to the factors",
    "based on the factors",
  ].some((phrase) => normalized.includes(phrase));
}

function looksLikeCoverageThreshold(claim: AtomicClaimRecord): boolean {
  const text = normalizeText(
    `${claim.model_normalized_claim_key ?? ""} ${claim.source_text}`,
  );
  return ["coverage", "do phu", "bao phu"]
    .some((phrase) => text.includes(phrase));
}

function buildClaimId(
  generationId: string,
  semanticSignature: string,
  sourceSpanStart: number,
): string {
  return `claim_${sha256(
    `${generationId}|${semanticSignature}|${sourceSpanStart}`,
  ).slice(0, 32)}`;
}

function normalizeText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/đ/gu, "d")
    .replace(/Đ/gu, "D")
    .toLowerCase()
    .replace(/[_-]+/gu, " ")
    .replace(/[^a-z0-9\s]/gu, " ")
    .replace(/\s+/gu, " ")
    .trim();
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort();
}
