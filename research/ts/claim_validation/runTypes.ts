export type ClaimValidationOptions = {
  claimsInputPath: string;
  generationIndexPath: string;
  evidencePackagesPath: string;
  outputDirectory: string;
  mode: "deterministic";
  smoke: boolean;
  smokeLimit: number;
  force: boolean;
  repositoryRoot?: string;
};

export type ClaimValidationRunSummary = {
  mode: "SMOKE" | "FULL";
  inputClaimCount: number;
  selectedClaimCount: number;
  outputResultCount: number;
  executionErrorCount: number;
  statusCounts: Record<string, number>;
  reasonCodeCounts: Record<string, number>;
  outputDirectory: string;
  resultsSha256: string;
  generationSummaryCount: number;
};
