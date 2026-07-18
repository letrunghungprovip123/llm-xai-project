import { z } from "zod";
import { predictCustomerMock } from "@/server/artifacts/prediction-reader";
import { assembleIRFromMockEvidence } from "@/server/xai/ir-assembler";
import { generateExplanation, generateExplanationFromIr } from "@/server/llm/explanation-generator";
import { validateFaithfulness } from "@/server/validator/rule-validator";
import { refineExplanation } from "@/server/validator/self-refinement";

export const ExplainPipelineRequestSchema = z.object({
  customer: z.record(z.string(), z.any()),
  audience: z.enum(["general", "marketing", "auditor"]).default("general"),
});

export async function runExplanationPipeline(input: unknown) {
  const parsed = ExplainPipelineRequestSchema.parse(input);

  const prediction = await predictCustomerMock(parsed.customer);
  const ir = await assembleIRFromMockEvidence(parsed.customer, prediction);

  const explanation = await generateExplanation({
    ir,
    audience: parsed.audience,
  });

  const validation = validateFaithfulness(ir, explanation.text);

  let finalExplanation = explanation;
  let finalValidation = validation;
  let refinement = null;

  if (validation.status === "failed") {
    refinement = await refineExplanation({
      ir,
      explanationText: explanation.text,
      validation,
      audience: parsed.audience,
    });

    finalExplanation = refinement.explanation;
    finalValidation = validateFaithfulness(ir, finalExplanation.text);
  }

  return {
    prediction,
    ir,
    explanation: finalExplanation,
    validation: finalValidation,
    refinement,
  };
}
