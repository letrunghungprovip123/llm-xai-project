import { sha256 } from "../common/utils";
import type { CanonicalGenerationRow } from "../../../contracts/llm-validation";
import type { ClaimSourceSection } from "../../../contracts/validation-claims";
import { isPlainObject } from "../canonicalization/io";

export type GenerationTextSpan = {
  source_section: ClaimSourceSection;
  source_factor_id: string | null;
  start: number;
  end: number;
};

export type GenerationTextDocument = {
  generation_text: string;
  source_input_sha256: string;
  section_spans: GenerationTextSpan[];
  factor_metadata: Array<{
    source_factor_id: string;
    declared_feature_ids: string[];
    declared_concept_ids: string[];
  }>;
};

// Adapter tạo một chuỗi ổn định để source span có thể kiểm tra lại hoàn toàn bằng code.
export function buildGenerationTextDocument(
  row: CanonicalGenerationRow,
): GenerationTextDocument {
  const output = isPlainObject(row.generation_record.parsed_output)
    ? row.generation_record.parsed_output
    : null;
  if (!output) {
    return {
      generation_text: "",
      source_input_sha256: sha256(""),
      section_spans: [],
      factor_metadata: [],
    };
  }

  let text = "";
  const spans: GenerationTextSpan[] = [];
  const factorMetadata: GenerationTextDocument["factor_metadata"] = [];

  const append = (
    section: ClaimSourceSection,
    value: string,
    factorId: string | null = null,
  ): void => {
    if (!value.trim()) return;
    const label = factorId
      ? `[${section}:${factorId}]\n`
      : `[${section}]\n`;
    text += label;
    const start = text.length;
    text += value;
    const end = text.length;
    text += "\n\n";
    spans.push({
      source_section: section,
      source_factor_id: factorId,
      start,
      end,
    });
  };

  append("prediction_summary", readString(output.prediction_summary));

  const factors = Array.isArray(output.factors) ? output.factors : [];
  for (const rawFactor of factors) {
    if (!isPlainObject(rawFactor)) continue;
    const factorId = readString(rawFactor.factor_id);
    if (!factorId) continue;
    factorMetadata.push({
      source_factor_id: factorId,
      declared_feature_ids: readStringArray(rawFactor.declared_feature_ids),
      declared_concept_ids: readStringArray(rawFactor.declared_concept_ids),
    });
    append("factor_name", readString(rawFactor.factor_name), factorId);
    append("factor_explanation", readString(rawFactor.explanation), factorId);
  }

  append("uncertainty_note", readString(output.uncertainty_note));
  append(
    "distributed_evidence_note",
    readString(output.distributed_evidence_note),
  );
  append("safe_summary", readString(output.safe_summary));

  const sourceInputSha256 = sha256(
    JSON.stringify({
      generation_text: text,
      section_spans: spans,
      factor_metadata: factorMetadata,
    }),
  );

  return {
    generation_text: text,
    source_input_sha256: sourceInputSha256,
    section_spans: spans,
    factor_metadata: factorMetadata,
  };
}

export function findContainingSpan(
  document: GenerationTextDocument,
  start: number,
  end: number,
): GenerationTextSpan | null {
  return (
    document.section_spans.find(
      (span) => start >= span.start && end <= span.end && start < end,
    ) ?? null
  );
}

// Tìm exact quote trong đúng section/factor và luôn chọn lần xuất hiện sớm nhất.
export function locateExactSourceSpan(
  document: GenerationTextDocument,
  sourceSection: ClaimSourceSection,
  sourceFactorId: string | null,
  sourceText: string,
): { start: number; end: number } | null {
  if (!sourceText) return null;

  const candidateSpans = document.section_spans
    .filter(
      (span) =>
        span.source_section === sourceSection &&
        span.source_factor_id === sourceFactorId,
    )
    .sort((left, right) => left.start - right.start);

  for (const span of candidateSpans) {
    const start = document.generation_text.indexOf(sourceText, span.start);
    const end = start + sourceText.length;
    if (start >= span.start && end <= span.end) {
      return { start, end };
    }
  }

  return null;
}

function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is string => typeof item === "string" && item.length > 0,
  );
}
