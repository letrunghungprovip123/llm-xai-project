import Ajv2020, { type ErrorObject } from "ajv/dist/2020";

import policyJson from "../../../config/research/ts-validation/claim_validation_policy_v1.json";
import policySchema from "../../../contracts/llm-validation/claim_validation_policy.schema.json";
import {
  CLAIM_TYPES,
  type ClaimType,
} from "../../../contracts/validation-claims";
import type {
  ClaimValidationFactValues,
  ValidationStatus,
} from "./types";

export type ReasonFamily =
  | "MATCH"
  | "PREDICTION"
  | "EXPOSURE"
  | "FEATURE"
  | "CONCEPT"
  | "DIRECTION"
  | "NUMERIC"
  | "RANKING"
  | "MAGNITUDE"
  | "UNCERTAINTY"
  | "POLICY"
  | "SYSTEM";

export type ClaimTypeRoute = {
  claim_type: ClaimType;
  validator_family: Exclude<ReasonFamily, "MATCH" | "EXPOSURE" | "SYSTEM">;
  allowed_statuses: ValidationStatus[];
  allowed_reason_families: Exclude<ReasonFamily, "SYSTEM">[];
  required_expected_fields: Array<keyof ClaimValidationFactValues>;
  required_observed_fields: Array<keyof ClaimValidationFactValues>;
  not_applicable_allowed: boolean;
  hard_safety_failure_possible: boolean;
};

export type ClaimValidationPolicy = {
  schema_version: "claim_validation_policy_v1";
  policy_version: "claim_validation_policy_v1";
  status: "FROZEN";
  status_taxonomy_version: "claim_validation_status_taxonomy_v1";
  reason_code_taxonomy_version: "claim_validation_reason_codes_v1";
  numeric_policy_version: "numeric_tolerance_policy_v1";
  direction_normalization: Record<string, string>;
  near_zero_shap_epsilon: 1e-12;
  evidence_exposure_boundary: {
    validation_source: "canonical_evidence_package";
    hidden_IR_prohibited: true;
    s0: {
      exposed_claim_families: ["PREDICTION"];
      unexposed_claim_families: ReasonFamily[];
      unexposed_behavior: "UNSUPPORTED_WITH_EXPOSURE_REASON";
    };
  };
  one_result_per_claim: true;
  unresolved_join_behavior: "ERROR";
  unsupported_claim_type_behavior: "ERROR";
  claim_type_routing: ClaimTypeRoute[];
};

const ajv = new Ajv2020({
  allErrors: true,
  allowUnionTypes: true,
  strict: true,
});
const validatePolicySchema = ajv.compile<ClaimValidationPolicy>(policySchema);
const policyInput: unknown = policyJson;

export function assertClaimValidationPolicy(
  value: unknown = CLAIM_VALIDATION_POLICY,
): asserts value is ClaimValidationPolicy {
  if (!validatePolicySchema(value)) {
    throw new Error(
      `Invalid claim validation policy: ${formatErrors(validatePolicySchema.errors)}`,
    );
  }

  const policy = value;
  const routeTypes = policy.claim_type_routing.map((route) => route.claim_type);
  if (new Set(routeTypes).size !== CLAIM_TYPES.length) {
    throw new Error("Claim validation policy must contain one route per claim type.");
  }
  for (const claimType of CLAIM_TYPES) {
    if (!routeTypes.includes(claimType)) {
      throw new Error(`Missing claim-type route: ${claimType}`);
    }
  }
  for (const route of policy.claim_type_routing) {
    if (
      route.allowed_statuses.includes("NOT_APPLICABLE") !==
      route.not_applicable_allowed
    ) {
      throw new Error(
        `NOT_APPLICABLE flag/status mismatch for ${route.claim_type}.`,
      );
    }
  }
}

assertClaimValidationPolicy(policyInput);
export const CLAIM_VALIDATION_POLICY = policyInput;

export function normalizeDirection(
  value: string,
): string {
  assertClaimValidationPolicy();
  const normalized = CLAIM_VALIDATION_POLICY.direction_normalization[value];
  if (!normalized) throw new Error(`Unsupported direction: ${value}`);
  return normalized;
}

function formatErrors(errors: ErrorObject[] | null | undefined): string {
  return (errors ?? [])
    .map((error) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
    .join("; ");
}
