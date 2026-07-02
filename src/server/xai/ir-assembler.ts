import type { PredictionResult } from "@/types/prediction";
import { validateIR } from "./ir-validator";

export async function assembleIRFromMockEvidence(
  customer: Record<string, unknown>,
  prediction: PredictionResult,
) {
  const positive = [];
  const negative = [];

  if (customer.poutcome === "success") {
    positive.push({
      feature: "poutcome",
      displayName: "Previous campaign outcome",
      value: "success",
      direction: "increase" as const,
      importance: 0.18,
    });
  }

  const age = Number(customer.age ?? 35);

  if (age < 25) {
    negative.push({
      feature: "age",
      displayName: "Age",
      value: age,
      direction: "decrease" as const,
      importance: -0.06,
    });
  }

  const ir = {
    irVersion: "v0.1",
    prediction: {
      label: prediction.predictedLabel,
      probability: prediction.probability,
      threshold: prediction.threshold,
      uncertainty: "medium" as const,
    },
    topPositiveFeatures: positive,
    topNegativeFeatures: negative,
    counterfactuals: [],
    modelMetadata: {
      modelName: prediction.modelName,
      modelVersion: prediction.modelVersion,
      xaiMethod: "mock-shap",
    },
    rules: [
      "Do not mention features not present in this IR.",
      "Do not change probability or label.",
      "Do not claim certainty.",
      "RAG context can explain terms but cannot add evidence.",
    ],
  };

  return validateIR(ir);
}
