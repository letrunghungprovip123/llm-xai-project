import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../contracts/validation-claims";
import {
  CLAIM_VALIDATION_SCHEMA_VERSION,
  CLAIM_VALIDATOR_VERSION,
  DETERMINISTIC_RESULT_TIMESTAMP,
  EXECUTION_STATUS,
  VALIDATOR_MODE,
} from "./constants";
import { CLAIM_VALIDATION_POLICY } from "./policy";
import { reasonCodeByName } from "./reasonCodes";
import {
  assertClaimValidationResult,
  createValidationId,
} from "./schema";
import {
  emptyClaimValidationFactValues,
  type ClaimValidationBaseIdentity,
  type ClaimValidationResult,
  type FailedStage,
  type SystemReasonCode,
} from "./types";
import type {
  ClaimValidationEvidencePackage,
  ClaimValidationGenerationRow,
} from "./runtimeTypes";
import type { SemanticDecision } from "./validators";
import {
  buildEvidenceView,
  conceptExposureState,
  featureExposureState,
} from "./validators/shared";
import { assertSemanticDecisionConsistency } from "./factConsistency";
import type {
  EvidenceExposureState,
  PolicyStatus,
} from "./types";

export { CLAIM_VALIDATOR_VERSION } from "./constants";

export type ResultProvenance = {
  claimsInputPath: string;
  claimsInputSha256: string;
  generationIndexPath: string;
  generationIndexSha256: string;
  evidencePackagesPath: string;
  evidencePackagesSha256: string;
};

export function buildSuccessResult(input: {
  claim: AtomicClaimRecord;
  generation: ClaimValidationGenerationRow;
  evidence: ClaimValidationEvidencePackage;
  decision: SemanticDecision;
  provenance: ResultProvenance;
}): ClaimValidationResult {
  const { claim, generation, evidence, decision: semantic, provenance } = input;
  const reason = reasonCodeByName(semantic.reasonCode);
  const route = CLAIM_VALIDATION_POLICY.claim_type_routing.find(
    (candidate) => candidate.claim_type === claim.claim_type,
  );
  if (
    !route ||
    reason.execution_status !== EXECUTION_STATUS.SUCCESS ||
    reason.validation_status === null ||
    !reason.allowed_claim_types.includes(claim.claim_type) ||
    !route.allowed_statuses.includes(reason.validation_status) ||
    !route.allowed_reason_families.some((family) => family === reason.family)
  ) {
    throw new Error(
      `Reason ${semantic.reasonCode} is incompatible with ${claim.claim_type}.`,
    );
  }
  for (const reasonCode of semantic.reasonCodes) {
    const additionalReason = reasonCodeByName(reasonCode);
    if (!additionalReason.allowed_claim_types.includes(claim.claim_type)) {
      throw new Error(
        `Reason ${reasonCode} is incompatible with ${claim.claim_type}.`,
      );
    }
  }
  assertSemanticDecisionConsistency(semantic, reason.validation_status);
  const exposure = exposureStatuses(claim, evidence);
  const policyStatus = resolvedPolicyStatus(semantic.policyStatus, exposure);

  const result: ClaimValidationResult = {
    ...identity(claim, generation, evidence, provenance),
    execution_status: EXECUTION_STATUS.SUCCESS,
    validation_status: reason.validation_status,
    evidence_status: reason.validation_status,
    policy_status: policyStatus,
    validation_coverage: semantic.validationCoverage,
    reason_code: semantic.reasonCode,
    primary_reason_code: semantic.reasonCode,
    reason_codes: semantic.reasonCodes,
    expected: semantic.expected,
    observed: semantic.observed,
    message: semantic.message,
    normalizations_applied: [...new Set(semantic.normalizationsApplied)].sort(),
    source_record_keys: [
      `claim:${claim.claim_id}`,
      `generation:${generation.generation_id}`,
      `package:${evidence.package_id}`,
      ...semantic.sourceRecordKeys,
    ].filter((value, index, values) => values.indexOf(value) === index),
    unresolved_facts: [...new Set(semantic.unresolvedFacts)].sort(),
    numeric_comparison: semantic.numericComparison
      ? {
          difference: semantic.numericComparison.difference,
          tolerance: semantic.numericComparison.tolerance,
          tolerance_policy_id:
            semantic.numericComparison.tolerancePolicyId,
        }
      : null,
    feature_exposure_status: exposure.feature,
    concept_exposure_status: exposure.concept,
    error: null,
  };
  assertClaimValidationResult(result);
  return result;
}

export function buildErrorResult(input: {
  claim: AtomicClaimRecord;
  generation: ClaimValidationGenerationRow | null;
  evidence: ClaimValidationEvidencePackage | null;
  provenance: ResultProvenance;
  reasonCode: SystemReasonCode;
  failedStage: FailedStage;
  errorMessage: string;
}): ClaimValidationResult {
  const {
    claim,
    generation,
    evidence,
    provenance,
    reasonCode,
    failedStage,
    errorMessage,
  } = input;
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  const exposure = exposureStatuses(claim, evidence);
  const result: ClaimValidationResult = {
    ...errorIdentity(claim, generation, evidence, provenance),
    execution_status: EXECUTION_STATUS.ERROR,
    validation_status: null,
    evidence_status: null,
    policy_status: null,
    validation_coverage: "UNVALIDATED",
    reason_code: reasonCode,
    primary_reason_code: reasonCode,
    reason_codes: [reasonCode],
    expected,
    observed,
    message: errorMessage,
    normalizations_applied: [],
    source_record_keys: [
      `claim:${claim.claim_id}`,
      ...(generation ? [`generation:${generation.generation_id}`] : []),
      ...(evidence ? [`package:${evidence.package_id}`] : []),
    ],
    unresolved_facts: [],
    numeric_comparison: null,
    feature_exposure_status: exposure.feature,
    concept_exposure_status: exposure.concept,
    error: {
      error_code: reasonCode,
      error_message: errorMessage,
      failed_stage: failedStage,
    },
  };
  assertClaimValidationResult(result);
  return result;
}

function errorIdentity(
  claim: AtomicClaimRecord,
  generation: ClaimValidationGenerationRow | null,
  evidence: ClaimValidationEvidencePackage | null,
  provenance: ResultProvenance,
): ClaimValidationBaseIdentity {
  return {
    schema_version: CLAIM_VALIDATION_SCHEMA_VERSION,
    validation_id: createValidationId({
      claim_id: claim.claim_id,
      validator_version: CLAIM_VALIDATOR_VERSION,
      policy_version: CLAIM_VALIDATION_POLICY.policy_version,
    }),
    claim_id: claim.claim_id,
    generation_id: claim.generation_id,
    case_id: claim.case_id ?? generation?.case_id ?? "UNRESOLVED_CASE",
    model_id: claim.model_id,
    evidence_level: claim.evidence_level,
    repeat_id: claim.repeat_id,
    claim_type: claim.claim_type,
    claim_subtype: claim.claim_subtype,
    claim_schema_version: claim.claim_schema_version,
    parent_claim_id: claim.parent_claim_id,
    finalizer_version: claim.finalizer_version,
    finalization_policy_version: claim.finalization_policy_version,
    validator_mode: VALIDATOR_MODE.DETERMINISTIC,
    validator_version: CLAIM_VALIDATOR_VERSION,
    policy_version: CLAIM_VALIDATION_POLICY.policy_version,
    created_at: DETERMINISTIC_RESULT_TIMESTAMP,
    ...provenanceFields(provenance),
    source_evidence_id:
      evidence?.source_evidence_id ?? generation?.source_evidence_id ?? null,
    package_id: evidence?.package_id ?? generation?.package_id ?? null,
    source_ir_id: claim.source_ir_id,
  };
}

function identity(
  claim: AtomicClaimRecord,
  generation: ClaimValidationGenerationRow,
  evidence: ClaimValidationEvidencePackage,
  provenance: ResultProvenance,
): ClaimValidationBaseIdentity {
  return {
    schema_version: CLAIM_VALIDATION_SCHEMA_VERSION,
    validation_id: createValidationId({
      claim_id: claim.claim_id,
      validator_version: CLAIM_VALIDATOR_VERSION,
      policy_version: CLAIM_VALIDATION_POLICY.policy_version,
    }),
    claim_id: claim.claim_id,
    generation_id: claim.generation_id,
    case_id: claim.case_id ?? generation.case_id ?? "UNRESOLVED_CASE",
    model_id: claim.model_id,
    evidence_level: claim.evidence_level,
    repeat_id: claim.repeat_id,
    claim_type: claim.claim_type,
    claim_subtype: claim.claim_subtype,
    claim_schema_version: claim.claim_schema_version,
    parent_claim_id: claim.parent_claim_id,
    finalizer_version: claim.finalizer_version,
    finalization_policy_version: claim.finalization_policy_version,
    validator_mode: VALIDATOR_MODE.DETERMINISTIC,
    validator_version: CLAIM_VALIDATOR_VERSION,
    policy_version: CLAIM_VALIDATION_POLICY.policy_version,
    created_at: DETERMINISTIC_RESULT_TIMESTAMP,
    ...provenanceFields(provenance),
    source_evidence_id: evidence.source_evidence_id ?? null,
    package_id: evidence.package_id,
    source_ir_id: claim.source_ir_id,
  };
}

function exposureStatuses(
  claim: AtomicClaimRecord,
  evidence: ClaimValidationEvidencePackage | null,
): { feature: EvidenceExposureState; concept: EvidenceExposureState } {
  if (!evidence) {
    return {
      feature: claim.feature_id ? "SOURCE_MISSING" : "NOT_APPLICABLE",
      concept: claim.concept_id ? "SOURCE_MISSING" : "NOT_APPLICABLE",
    };
  }
  const view = buildEvidenceView(evidence);
  return {
    feature: claim.feature_id
      ? featureExposureState(view, claim.feature_id)
      : "NOT_APPLICABLE",
    concept: claim.concept_id
      ? conceptExposureState(view, claim.concept_id)
      : "NOT_APPLICABLE",
  };
}

function resolvedPolicyStatus(
  decisionStatus: PolicyStatus,
  exposure: { feature: EvidenceExposureState; concept: EvidenceExposureState },
): PolicyStatus {
  if (
    exposure.feature === "EXPOSED_FORBIDDEN" ||
    exposure.concept === "EXPOSED_FORBIDDEN"
  ) {
    return "VIOLATION";
  }
  if (decisionStatus !== "NOT_APPLICABLE") return decisionStatus;
  if (
    exposure.feature === "EXPOSED_ALLOWED" ||
    exposure.concept === "EXPOSED_ALLOWED"
  ) {
    return "COMPLIANT";
  }
  return "NOT_APPLICABLE";
}

function provenanceFields(provenance: ResultProvenance): {
  claims_input_path: string;
  claims_input_sha256: string;
  generation_index_path: string;
  generation_index_sha256: string;
  evidence_packages_path: string;
  evidence_packages_sha256: string;
} {
  return {
    claims_input_path: provenance.claimsInputPath,
    claims_input_sha256: provenance.claimsInputSha256,
    generation_index_path: provenance.generationIndexPath,
    generation_index_sha256: provenance.generationIndexSha256,
    evidence_packages_path: provenance.evidencePackagesPath,
    evidence_packages_sha256: provenance.evidencePackagesSha256,
  };
}
