import { z } from "zod";

export const XaiFeatureSchema = z.object({
  feature: z.string(),
  displayName: z.string(),
  value: z.union([z.string(), z.number(), z.boolean(), z.null()]),
  direction: z.enum(["increase", "decrease"]),
  importance: z.number(),
});

export const CounterfactualSchema = z.object({
  changedFeature: z.string(),
  from: z.union([z.string(), z.number(), z.boolean(), z.null()]),
  to: z.union([z.string(), z.number(), z.boolean(), z.null()]),
  newProbability: z.number(),
  actionability: z
    .enum(["actionable", "not_actionable", "partially_actionable"])
    .optional(),
});

export const ExplanationIRSchema = z.object({
  irVersion: z.string(),
  prediction: z.object({
    label: z.enum(["yes", "no"]),
    probability: z.number(),
    threshold: z.number(),
    uncertainty: z.enum(["low", "medium", "high"]),
  }),
  topPositiveFeatures: z.array(XaiFeatureSchema),
  topNegativeFeatures: z.array(XaiFeatureSchema),
  counterfactuals: z.array(CounterfactualSchema),
  modelMetadata: z.object({
    modelName: z.string(),
    modelVersion: z.string(),
    xaiMethod: z.string(),
  }),
  rules: z.array(z.string()),
});

export type ExplanationIRInput = z.infer<typeof ExplanationIRSchema>;
