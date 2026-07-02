export type AudienceType = "general" | "marketing" | "auditor";

export type LLMExplanationResult = {
  text: string;
  audience: AudienceType;
  promptVersion: string;
  llmModel: string;
};
