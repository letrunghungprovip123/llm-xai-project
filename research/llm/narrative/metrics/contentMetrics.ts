import { MAX_OUTPUT_WORDS, MIN_OUTPUT_WORDS } from "../config";
import type { ContentMetrics, ExplanationOutput } from "../../../../contracts/narrative";

export function buildContentMetrics(
  output: ExplanationOutput | null,
): ContentMetrics {
  if (!output) {
    return emptyContentMetrics();
  }

  const allText = [
    output.prediction_summary,
    ...output.factors.map(
      (factor) => `${factor.factor_name} ${factor.explanation}`,
    ),
    output.uncertainty_note,
    output.distributed_evidence_note,
    output.safe_summary,
  ]
    .join(" ")
    .trim();

  const words = countWords(allText);
  const sentences = countSentences(allText);
  const technicalTerms = countTechnicalTerms(allText);
  const mainCount = output.factors.filter(
    (factor) => factor.role === "main",
  ).length;
  const supportingCount = output.factors.filter(
    (factor) => factor.role === "supporting",
  ).length;

  return {
    has_prediction_summary: output.prediction_summary.trim().length > 0,
    has_factors: output.factors.length > 0,
    has_uncertainty_note: output.uncertainty_note.trim().length > 0,
    has_distributed_evidence_note:
      output.distributed_evidence_note.trim().length > 0,
    has_safe_summary: output.safe_summary.trim().length > 0,
    main_factor_count: mainCount,
    supporting_factor_count: supportingCount,
    total_factor_count: output.factors.length,
    output_char_count: allText.length,
    output_word_count: words,
    sentence_count: sentences,
    average_sentence_length: sentences > 0 ? words / sentences : null,
    technical_term_count: technicalTerms,
    technical_term_ratio: words > 0 ? technicalTerms / words : null,
    too_short: words < MIN_OUTPUT_WORDS,
    too_long: words > MAX_OUTPUT_WORDS,
  };
}

function emptyContentMetrics(): ContentMetrics {
  return {
    has_prediction_summary: false,
    has_factors: false,
    has_uncertainty_note: false,
    has_distributed_evidence_note: false,
    has_safe_summary: false,
    main_factor_count: 0,
    supporting_factor_count: 0,
    total_factor_count: 0,
    output_char_count: 0,
    output_word_count: 0,
    sentence_count: 0,
    average_sentence_length: null,
    technical_term_count: 0,
    technical_term_ratio: null,
    too_short: true,
    too_long: false,
  };
}

function countWords(text: string): number {
  if (!text.trim()) {
    return 0;
  }

  return text.trim().split(/\s+/).length;
}

function countSentences(text: string): number {
  if (!text.trim()) {
    return 0;
  }

  const matches = text.match(/[.!?]+(?:\s|$)/g);
  return Math.max(matches ? matches.length : 0, 1);
}

function countTechnicalTerms(text: string): number {
  const tokens = text.split(/\s+/);
  let count = 0;

  for (const token of tokens) {
    if (token.includes("_") || /[A-Z]{2,}/.test(token) || /SHAP/i.test(token)) {
      count += 1;
    }
  }

  return count;
}
