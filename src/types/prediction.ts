export type PredictionResult = {
  predictedLabel: "yes" | "no";
  probability: number;
  threshold: number;
  modelName: string;
  modelVersion: string;
};
