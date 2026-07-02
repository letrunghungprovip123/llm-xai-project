import type { AudienceType } from "@/types/explanation";
import type { ExplanationIR } from "@/types/ir";
import type { ValidationResult } from "@/types/validation";
import { generateExplanation } from "@/server/llm/explanation-generator";

export async function refineExplanation(input: {
  ir: ExplanationIR;
  explanationText: string;
  validation: ValidationResult;
  audience: AudienceType;
}) {
  const explanation = await generateExplanation({
    ir: input.ir,
    audience: input.audience,
  });

  return {
    explanation,
    feedbackUsed: input.validation.feedback,
    previousText: input.explanationText,
  };
}
