import Ajv2020, { type ErrorObject } from "ajv/dist/2020";

import reasonCodesJson from "../../../config/research/ts-validation/claim_validation_reason_codes_v1.json";
import reasonCodesSchema from "../../../contracts/llm-validation/claim_validation_reason_codes.schema.json";
import {
  CLAIM_TYPES,
  type ClaimType,
} from "../../../contracts/validation-claims";
import type {
  ExecutionStatus,
  ValidationStatus,
} from "./types";
import type { ReasonFamily } from "./policy";
import { REASON_CODE } from "./constants";

export type ClaimValidationReasonCode = {
  code: string;
  family: ReasonFamily;
  description: string;
  execution_status: ExecutionStatus;
  validation_status: ValidationStatus | null;
  allowed_claim_types: ClaimType[];
  severity: "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  primary_metric_effect: "PASS" | "FAIL" | "EXCLUDED" | "ERROR";
  is_hard_safety_failure: boolean;
};

export type ClaimValidationReasonCodeTaxonomy = {
  schema_version: "claim_validation_reason_codes_v1";
  taxonomy_version: "claim_validation_reason_codes_v1";
  status: "FROZEN";
  reason_codes: ClaimValidationReasonCode[];
};

const EXPECTED_HARD_SAFETY_CODES = new Set<string>([
  REASON_CODE.CAUSAL_OVERCLAIM,
  REASON_CODE.GUARANTEE_OVERCLAIM,
  REASON_CODE.CERTAINTY_OVERCLAIM,
]);
const ajv = new Ajv2020({
  allErrors: true,
  allowUnionTypes: true,
  strict: true,
});
const validateReasonCodesSchema =
  ajv.compile<ClaimValidationReasonCodeTaxonomy>(reasonCodesSchema);
const reasonCodesInput: unknown = reasonCodesJson;

export function assertClaimValidationReasonCodes(
  value: unknown = CLAIM_VALIDATION_REASON_CODES,
): asserts value is ClaimValidationReasonCodeTaxonomy {
  if (!validateReasonCodesSchema(value)) {
    throw new Error(
      `Invalid claim validation reason codes: ${formatErrors(validateReasonCodesSchema.errors)}`,
    );
  }

  const taxonomy = value;
  const codes = taxonomy.reason_codes.map((reason) => reason.code);
  if (new Set(codes).size !== codes.length) {
    throw new Error("Claim validation reason codes must be unique.");
  }
  if (codes.length !== Object.keys(REASON_CODE).length) {
    throw new Error(
      `Reason taxonomy/code constant mismatch: ${codes.length}/`
      + `${Object.keys(REASON_CODE).length}.`,
    );
  }

  for (const reason of taxonomy.reason_codes) {
    if (reason.family === "SYSTEM") {
      if (
        reason.execution_status !== "ERROR" ||
        reason.validation_status !== null ||
        reason.primary_metric_effect !== "ERROR"
      ) {
        throw new Error(`SYSTEM reason has invalid mapping: ${reason.code}`);
      }
    } else if (
      reason.execution_status !== "SUCCESS" ||
      reason.validation_status === null
    ) {
      throw new Error(`Semantic reason has invalid mapping: ${reason.code}`);
    }

    if (
      reason.validation_status === "SUPPORTED" &&
      reason.family !== "MATCH"
    ) {
      throw new Error(`SUPPORTED reason must belong to MATCH: ${reason.code}`);
    }
    for (const claimType of reason.allowed_claim_types) {
      if (!CLAIM_TYPES.includes(claimType)) {
        throw new Error(`Unknown claim type ${claimType} in ${reason.code}.`);
      }
    }
    if (/^(?:OTHER|UNKNOWN|UNCLASSIFIED)$/u.test(reason.code)) {
      throw new Error(`Catch-all reason code is prohibited: ${reason.code}`);
    }
  }

  const actualHardCodes = new Set(
    taxonomy.reason_codes
      .filter((reason) => reason.is_hard_safety_failure)
      .map((reason) => reason.code),
  );
  if (
    actualHardCodes.size !== EXPECTED_HARD_SAFETY_CODES.size ||
    [...actualHardCodes].some((code) => !EXPECTED_HARD_SAFETY_CODES.has(code))
  ) {
    throw new Error("Hard-safety reason-code set does not match frozen policy.");
  }
}

assertClaimValidationReasonCodes(reasonCodesInput);
export const CLAIM_VALIDATION_REASON_CODES = reasonCodesInput;

export function reasonCodeByName(code: string): ClaimValidationReasonCode {
  assertClaimValidationReasonCodes();
  const reason = CLAIM_VALIDATION_REASON_CODES.reason_codes.find(
    (candidate) => candidate.code === code,
  );
  if (!reason) throw new Error(`Unknown claim validation reason code: ${code}`);
  return reason;
}

function formatErrors(errors: ErrorObject[] | null | undefined): string {
  return (errors ?? [])
    .map((error) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
    .join("; ");
}
