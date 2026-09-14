import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../contracts/validation-claims";
import type {
  ClaimValidationEvidencePackage,
  ClaimValidationGenerationRow,
} from "./runtimeTypes";

export type ValidationIndexes = {
  claimById: Map<string, AtomicClaimRecord>;
  generationById: Map<string, ClaimValidationGenerationRow>;
  evidenceByPackageId: Map<string, ClaimValidationEvidencePackage>;
};

export function buildValidationIndexes(input: {
  claims: AtomicClaimRecord[];
  generations: ClaimValidationGenerationRow[];
  evidencePackages: ClaimValidationEvidencePackage[];
}): ValidationIndexes {
  return {
    claimById: uniqueIndex(input.claims, (claim) => claim.claim_id, "claim_id"),
    generationById: uniqueIndex(
      input.generations,
      (generation) => generation.generation_id,
      "generation_id",
    ),
    evidenceByPackageId: uniqueIndex(
      input.evidencePackages,
      (evidence) => evidence.package_id,
      "package_id",
    ),
  };
}

export function assertJoinedIdentity(
  claim: AtomicClaimRecord,
  generation: ClaimValidationGenerationRow,
  evidence: ClaimValidationEvidencePackage,
): void {
  const comparisons: Array<[string, unknown, unknown]> = [
    ["claim.model_id", claim.model_id, generation.model_id],
    ["claim.case_id", claim.case_id, generation.case_id],
    ["claim.evidence_level", claim.evidence_level, generation.evidence_level],
    ["claim.repeat_id", claim.repeat_id, generation.repeat_id],
    ["claim.source_ir_id", claim.source_ir_id, generation.source_ir_id],
    ["generation.package_id", generation.package_id, evidence.package_id],
    [
      "generation.source_evidence_id",
      generation.source_evidence_id,
      evidence.source_evidence_id,
    ],
    [
      "generation.evidence_level",
      generation.evidence_level,
      evidence.evidence_level,
    ],
    [
      "generation.source_ir_id",
      generation.source_ir_id,
      evidence.source_ir_id,
    ],
  ];
  const mismatch = comparisons.find(([, left, right]) => left !== right);
  if (mismatch) {
    throw new Error(
      `Conflicting join identity ${mismatch[0]}: ${String(mismatch[1])} != ${String(mismatch[2])}.`,
    );
  }
}

export function uniqueIndex<T>(
  values: readonly T[],
  keyOf: (value: T) => string,
  label: string,
): Map<string, T> {
  const result = new Map<string, T>();
  for (const value of values) {
    const key = keyOf(value);
    if (!key) throw new Error(`Empty ${label} is prohibited.`);
    if (result.has(key)) throw new Error(`Duplicate ${label}: ${key}`);
    result.set(key, value);
  }
  return result;
}
