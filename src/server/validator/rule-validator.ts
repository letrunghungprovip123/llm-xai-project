import type { ExplanationIR } from "@/types/ir";
import type { ValidationResult } from "@/types/validation";

const overclaimTerms = [
  "certainly",
  "guaranteed",
  "always",
  "never",
  "chắc chắn",
  "đảm bảo",
  "luôn luôn",
];

export function validateFaithfulness(
  ir: ExplanationIR,
  explanationText: string,
): ValidationResult {
  const text = explanationText.toLowerCase();
  const errors: ValidationResult["errors"] = [];

  const probability = String(ir.prediction.probability);
  const label = String(ir.prediction.label).toLowerCase();

  if (!text.includes(probability)) {
    errors.push({
      type: "probability_mismatch",
      message: "Explanation does not mention the exact probability from IR.",
    });
  }

  if (!text.includes(label)) {
    errors.push({
      type: "label_mismatch",
      message: "Explanation does not mention the predicted label from IR.",
    });
  }

  if (overclaimTerms.some((term) => text.includes(term))) {
    errors.push({
      type: "overclaim",
      message: "Explanation uses overly certain language.",
    });
  }

  const evidenceNames = [
    ...ir.topPositiveFeatures,
    ...ir.topNegativeFeatures,
  ].flatMap((f) => [f.feature.toLowerCase(), f.displayName.toLowerCase()]);

  if (
    evidenceNames.length > 0 &&
    !evidenceNames.some((name) => text.includes(name))
  ) {
    errors.push({
      type: "missing_evidence",
      message: "Explanation does not mention any evidence feature from IR.",
    });
  }

  const score = Math.max(0, 1 - errors.length * 0.2);

  return {
    status: errors.length === 0 ? "passed" : "failed",
    faithfulnessScore: Number(score.toFixed(2)),
    errors,
    feedback:
      errors.length > 0
        ? "Revise explanation to match IR evidence, probability, label, and avoid unsupported claims."
        : null,
  };
}
