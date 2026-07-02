import { ExplanationIRSchema } from "./ir-schema";

export function validateIR(ir: unknown) {
  return ExplanationIRSchema.parse(ir);
}
