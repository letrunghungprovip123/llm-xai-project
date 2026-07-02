import type { PredictionResult } from "@/types/prediction";

export async function predictCustomerMock(
  customer: Record<string, unknown>,
): Promise<PredictionResult> {
  const age = Number(customer.age ?? 35);
  const poutcome = String(customer.poutcome ?? "nonexistent");

  let probability = 0.35;

  if (age >= 30) probability += 0.08;
  if (poutcome === "success") probability += 0.25;

  probability = Math.max(0.01, Math.min(0.99, probability));

  return {
    predictedLabel: probability >= 0.5 ? "yes" : "no",
    probability: Number(probability.toFixed(4)),
    threshold: 0.5,
    modelName: "mock-xgboost",
    modelVersion: "v0.1",
  };
}
