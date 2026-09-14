import path from "node:path";
import { realpath } from "node:fs/promises";

import Ajv2020, { type ErrorObject } from "ajv/dist/2020";

import claimSchema from "../../../contracts/llm-validation/claims.schema.json";
import type { JsonObject } from "../../../contracts/llm-validation";
import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../contracts/validation-claims";
import { readJsonlStrict } from "../canonicalization/io";
import { parseClaimValidationEvidence } from "./evidenceParser";
import { parseClaimValidationGeneration } from "./generationParser";
import type {
  ClaimValidationEvidencePackage,
  ClaimValidationGenerationRow,
} from "./runtimeTypes";

export type ValidationInputs = {
  repositoryRoot: string;
  artifacts: {
    finalized_claims: InputArtifact;
    canonical_generation_index: InputArtifact;
    canonical_evidence_packages: InputArtifact;
  };
  claims: AtomicClaimRecord[];
  generations: ClaimValidationGenerationRow[];
  evidencePackages: ClaimValidationEvidencePackage[];
};

type InputArtifact = {
  path: string;
  sha256: string;
  record_count: number;
};

export const DEFAULT_CLAIMS_INPUT_PATH =
  "data/reports/llm_validation/validation_v1/claim_finalization_v4/claims_final.jsonl";
export const DEFAULT_GENERATION_INDEX_PATH =
  "data/reports/llm_validation/validation_v1/canonicalization/generation_index.jsonl";
export const DEFAULT_EVIDENCE_PACKAGES_PATH =
  "data/reports/llm_validation/validation_v1/canonicalization/evidence_packages_36.jsonl";

const ajv = new Ajv2020({
  allErrors: true,
  allowUnionTypes: true,
  strict: true,
});
const validateClaimSchema = ajv.compile(claimSchema);

export async function loadValidationInputs(options: {
  repositoryRoot?: string;
  claimsInputPath?: string;
  generationIndexPath?: string;
  evidencePackagesPath?: string;
}): Promise<ValidationInputs> {
  const root = await realpath(path.resolve(options.repositoryRoot ?? process.cwd()));
  const claimsPath = resolveInput(
    root,
    options.claimsInputPath ?? DEFAULT_CLAIMS_INPUT_PATH,
  );
  const generationPath = resolveInput(
    root,
    options.generationIndexPath ?? DEFAULT_GENERATION_INDEX_PATH,
  );
  const evidencePath = resolveInput(
    root,
    options.evidencePackagesPath ?? DEFAULT_EVIDENCE_PACKAGES_PATH,
  );
  const [claimInput, generationInput, evidenceInput] = await Promise.all([
    readJsonlStrict<JsonObject>(claimsPath),
    readJsonlStrict<JsonObject>(generationPath),
    readJsonlStrict<JsonObject>(evidencePath),
  ]);

  const claims = claimInput.records.map(({ value, line }) => {
    assertFinalizedClaimShape(value, `line ${line}`);
    return value;
  });
  const generations = generationInput.records.map(({ value, line }) =>
    parseClaimValidationGeneration(value, `generation row line ${line}`),
  );
  const evidencePackages = evidenceInput.records.map(({ value, line }) =>
    parseClaimValidationEvidence(value, `evidence package line ${line}`),
  );

  return {
    repositoryRoot: root,
    artifacts: {
      finalized_claims: artifact(root, claimInput),
      canonical_generation_index: artifact(root, generationInput),
      canonical_evidence_packages: artifact(root, evidenceInput),
    },
    claims,
    generations,
    evidencePackages,
  };
}

function resolveInput(repositoryRoot: string, inputPath: string): string {
  return path.resolve(repositoryRoot, inputPath);
}

function artifact(
  repositoryRoot: string,
  input: { path: string; sha256: string; records: unknown[] },
): InputArtifact {
  return {
    path: path.relative(repositoryRoot, input.path),
    sha256: input.sha256,
    record_count: input.records.length,
  };
}

export function assertFinalizedClaimShape(
  value: unknown,
  context = "input",
): asserts value is AtomicClaimRecord {
  if (!validateClaimSchema(value)) {
    throw new Error(
      `Invalid finalized claim at ${context}: ${formatErrors(validateClaimSchema.errors)}`,
    );
  }
}

function formatErrors(errors: ErrorObject[] | null | undefined): string {
  return (errors ?? [])
    .map((error) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
    .join("; ");
}
