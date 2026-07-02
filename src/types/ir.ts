export type ExplanationIR = {
  irVersion: string;
  prediction: {
    label: "yes" | "no";
    probability: number;
    threshold: number;
    uncertainty: "low" | "medium" | "high";
  };
  topPositiveFeatures: XaiFeature[];
  topNegativeFeatures: XaiFeature[];
  counterfactuals: CounterfactualItem[];
  modelMetadata: {
    modelName: string;
    modelVersion: string;
    xaiMethod: string;
  };
  rules: string[];
};

export type XaiFeature = {
  feature: string;
  displayName: string;
  value: string | number | boolean | null;
  direction: "increase" | "decrease";
  importance: number;
};

export type CounterfactualItem = {
  changedFeature: string;
  from: string | number | boolean | null;
  to: string | number | boolean | null;
  newProbability: number;
  actionability?: "actionable" | "not_actionable" | "partially_actionable";
};
