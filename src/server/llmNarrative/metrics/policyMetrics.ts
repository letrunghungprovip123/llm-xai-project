import { COMMON_FORBIDDEN_PHRASES } from "../config";
import type {
  EvidencePackage,
  ExplanationOutput,
  PolicyMetrics,
} from "../../../types/types";
import { normalizeText } from "../../../utils/llmNarrative/utils";

export function buildPolicyMetrics(
  packageItem: EvidencePackage,
  output: ExplanationOutput | null,
): PolicyMetrics {
  const policy = packageItem.prompt_payload.narrative_policy;
  const uncertaintyRequired = Boolean(policy.must_include_uncertainty);
  const distributedRequired = Boolean(
    policy.must_include_distributed_evidence_note,
  );
  const partialRequired = Boolean(policy.must_include_partial_evidence_note);
  const text = output ? collectOutputText(output) : "";
  const normalizedText = normalizeText(text);

  const extraForbidden =
    packageItem.prompt_payload.backend_explanation_skeleton
      ?.forbidden_wording || [];
  const forbiddenPhrases = [...COMMON_FORBIDDEN_PHRASES, ...extraForbidden];
  const matches = forbiddenPhrases.filter((phrase) => {
    return normalizedText.includes(normalizeText(phrase));
  });

  const singleCausePhrases = [
    "nguyên nhân duy nhất",
    "lý do duy nhất",
    "chỉ do",
    "only reason",
    "sole cause",
  ];

  const singleCauseViolation = singleCausePhrases.some((phrase) => {
    return normalizedText.includes(normalizeText(phrase));
  });

  return {
    uncertainty_required: uncertaintyRequired,
    uncertainty_compliant: uncertaintyRequired
      ? Boolean(output?.uncertainty_note.trim())
      : null,
    distributed_note_required: distributedRequired,
    distributed_note_compliant: distributedRequired
      ? Boolean(output?.distributed_evidence_note.trim())
      : null,
    partial_evidence_note_required: partialRequired,
    partial_evidence_note_compliant: partialRequired
      ? hasPartialEvidenceLanguage(output?.uncertainty_note || "")
      : null,
    single_cause_violation: singleCauseViolation,
    forbidden_phrase_violation: matches.length > 0,
    forbidden_phrase_matches: matches,
  };
}

function collectOutputText(output: ExplanationOutput): string {
  return [
    output.prediction_summary,
    ...output.factors.map(
      (factor) => `${factor.factor_name} ${factor.explanation}`,
    ),
    output.uncertainty_note,
    output.distributed_evidence_note,
    output.safe_summary,
  ].join(" ");
}

function hasPartialEvidenceLanguage(text: string): boolean {
  const normalized = normalizeText(text);
  const phrases = [
    "evidence nổi bật",
    "bằng chứng nổi bật",
    "các tín hiệu được cung cấp",
    "không phải toàn bộ",
    "một phần bằng chứng",
    "partial evidence",
  ];

  return phrases.some((phrase) => normalized.includes(normalizeText(phrase)));
}
