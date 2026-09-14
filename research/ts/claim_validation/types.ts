import type {
  ClaimCausalStrength,
  ClaimCertainty,
  ClaimDirection,
  ClaimMagnitude,
  ClaimNumericRole,
  ClaimSubtype,
  ClaimType,
} from "../../../contracts/validation-claims";
import type { EvidenceLevel } from "../../../contracts/llm-validation";
import {
  CLAIM_VALIDATION_SCHEMA_VERSION,
  EXECUTION_STATUS,
  REASON_CODE,
  VALIDATION_STATUS,
  VALIDATOR_MODE,
} from "./constants";
import type { ReasonCode } from "./constants";

export const EXECUTION_STATUSES = Object.values(EXECUTION_STATUS);
export const VALIDATION_STATUSES = [
  VALIDATION_STATUS.SUPPORTED,
  VALIDATION_STATUS.UNSUPPORTED,
  VALIDATION_STATUS.CONTRADICTED,
  VALIDATION_STATUS.NOT_VERIFIABLE,
  VALIDATION_STATUS.NOT_APPLICABLE,
] as const;
export const VALIDATOR_MODES = [
  VALIDATOR_MODE.DETERMINISTIC,
  VALIDATOR_MODE.SEMANTIC,
  VALIDATOR_MODE.HUMAN_ADJUDICATED,
] as const;
export const FAILED_STAGES = [
  "INPUT_SCHEMA",
  "CLAIM_JOIN",
  "GENERATION_JOIN",
  "EVIDENCE_JOIN",
  "POLICY_LOAD",
  "NORMALIZATION",
  "VALIDATION",
  "OUTPUT_SCHEMA",
] as const;
export const SYSTEM_REASON_CODES = [
  REASON_CODE.INVALID_CLAIM_SHAPE,
  REASON_CODE.CLAIM_JOIN_FAILED,
  REASON_CODE.GENERATION_JOIN_FAILED,
  REASON_CODE.EVIDENCE_JOIN_FAILED,
  REASON_CODE.POLICY_LOAD_FAILED,
  REASON_CODE.NORMALIZATION_FAILED,
  REASON_CODE.UNSUPPORTED_CLAIM_TYPE,
  REASON_CODE.OUTPUT_SCHEMA_FAILED,
] as const;

export type ExecutionStatus = (typeof EXECUTION_STATUSES)[number];
export type ValidationStatus = (typeof VALIDATION_STATUSES)[number];
export type ValidatorMode = (typeof VALIDATOR_MODES)[number];
export type FailedStage = (typeof FAILED_STAGES)[number];
export type SystemReasonCode = (typeof SYSTEM_REASON_CODES)[number];
export type PolicyStatus = "COMPLIANT" | "VIOLATION" | "NOT_APPLICABLE";
export type ValidationCoverage =
  | "DETERMINISTIC"
  | "SEMANTIC_REQUIRED"
  | "HUMAN_ADJUDICATED"
  | "UNVALIDATED";
export type EvidenceExposureState =
  | "NOT_EXPOSED"
  | "EXPOSED_FORBIDDEN"
  | "EXPOSED_ALLOWED"
  | "SOURCE_MISSING"
  | "NOT_APPLICABLE";

export type ExposureStatus =
  | "EXPOSED"
  | "NOT_EXPOSED"
  | "SOURCE_MISSING"
  | "NOT_APPLICABLE";

export type ClaimValidationFactValues = {
  prediction_label: string | null;
  probability: number | null;
  numeric_value: number | null;
  numeric_unit: string | null;
  numeric_role: ClaimNumericRole | null;
  feature_id: string | null;
  concept_id: string | null;
  direction: ClaimDirection | null;
  magnitude: ClaimMagnitude | null;
  rank: number | null;
  certainty: ClaimCertainty | null;
  causal_strength: ClaimCausalStrength | null;
  exposure_status: ExposureStatus | null;
};

export type ClaimValidationExecutionError = {
  error_code: string;
  error_message: string;
  failed_stage: FailedStage;
};

export type ClaimValidationIdentity = {
  schema_version: typeof CLAIM_VALIDATION_SCHEMA_VERSION;
  validation_id: string;
  claim_id: string;
  generation_id: string;
  case_id: string;
  model_id: string;
  evidence_level: EvidenceLevel;
  repeat_id: number;
  claim_type: ClaimType;
  claim_subtype: ClaimSubtype;
  claim_schema_version: "claims_v3";
  parent_claim_id: string | null;
  finalizer_version: string;
  finalization_policy_version: string;
  validator_mode: ValidatorMode;
  validator_version: string;
  policy_version: string;
  created_at: string;
  claims_input_path: string;
  claims_input_sha256: string;
  generation_index_path: string;
  generation_index_sha256: string;
  evidence_packages_path: string;
  evidence_packages_sha256: string;
  source_evidence_id: string | null;
  package_id: string | null;
  source_ir_id: string;
  expected: ClaimValidationFactValues;
  observed: ClaimValidationFactValues;
  message: string;
  normalizations_applied: string[];
  source_record_keys: string[];
  unresolved_facts: string[];
  numeric_comparison: {
    difference: number;
    tolerance: number;
    tolerance_policy_id: string;
  } | null;
  feature_exposure_status: EvidenceExposureState;
  concept_exposure_status: EvidenceExposureState;
};

export type ClaimValidationBaseIdentity = Omit<
  ClaimValidationIdentity,
  | "expected"
  | "observed"
  | "message"
  | "normalizations_applied"
  | "source_record_keys"
  | "unresolved_facts"
  | "numeric_comparison"
  | "feature_exposure_status"
  | "concept_exposure_status"
  | "error"
>;

export type ClaimValidationSuccess = ClaimValidationIdentity & {
  execution_status: typeof EXECUTION_STATUS.SUCCESS;
  validation_status: ValidationStatus;
  evidence_status: ValidationStatus;
  policy_status: PolicyStatus;
  validation_coverage: Exclude<ValidationCoverage, "UNVALIDATED">;
  reason_code: ReasonCode;
  primary_reason_code: ReasonCode;
  reason_codes: ReasonCode[];
  error: null;
};

export type ClaimValidationError = ClaimValidationIdentity & {
  execution_status: typeof EXECUTION_STATUS.ERROR;
  validation_status: null;
  evidence_status: null;
  policy_status: null;
  validation_coverage: "UNVALIDATED";
  reason_code: SystemReasonCode;
  primary_reason_code: SystemReasonCode;
  reason_codes: SystemReasonCode[];
  error: ClaimValidationExecutionError;
};

export type ClaimValidationResult =
  | ClaimValidationSuccess
  | ClaimValidationError;

export function emptyClaimValidationFactValues(): ClaimValidationFactValues {
  return {
    prediction_label: null,
    probability: null,
    numeric_value: null,
    numeric_unit: null,
    numeric_role: null,
    feature_id: null,
    concept_id: null,
    direction: null,
    magnitude: null,
    rank: null,
    certainty: null,
    causal_strength: null,
    exposure_status: null,
  };
}
