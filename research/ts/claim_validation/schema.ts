import { createHash } from "node:crypto";
import path from "node:path";

import Ajv2020, { type ErrorObject } from "ajv/dist/2020";

import claimValidationV2Schema from "../../../contracts/llm-validation/claim_validation_v2.schema.json";
import claimValidationV3Schema from "../../../contracts/llm-validation/claim_validation_v3.schema.json";
import claimValidationSchema from "../../../contracts/llm-validation/claim_validation_v4.schema.json";
import {
  CLAIM_SUBTYPES_BY_TYPE,
  type ClaimType,
} from "../../../contracts/validation-claims";
import { CLAIM_VALIDATION_SCHEMA_VERSION, EXECUTION_STATUS } from "./constants";
import { assertSemanticDecisionConsistency } from "./factConsistency";
import {
  SYSTEM_REASON_CODES,
  type ClaimValidationFactValues,
  type ClaimValidationResult,
} from "./types";

const ajv = new Ajv2020({
  allErrors: true,
  allowUnionTypes: true,
  strict: true,
});
const validateSchema = ajv.compile<ClaimValidationResult>(claimValidationSchema);
const validateV2Schema = ajv.compile(claimValidationV2Schema);
const validateV3Schema = ajv.compile(claimValidationV3Schema);
const systemReasonCodes = new Set<string>(SYSTEM_REASON_CODES);

const COMMON_FACT_FIELDS = ["exposure_status"] as const;
const FACT_FIELDS: ReadonlyArray<keyof ClaimValidationFactValues> = [
  "prediction_label",
  "probability",
  "numeric_value",
  "numeric_unit",
  "numeric_role",
  "feature_id",
  "concept_id",
  "direction",
  "magnitude",
  "rank",
  "certainty",
  "causal_strength",
  "exposure_status",
];
const ALLOWED_FACT_FIELDS: Record<
  ClaimType,
  ReadonlySet<keyof ClaimValidationFactValues>
> = {
  prediction: fields("prediction_label", "probability"),
  feature_presence: fields("feature_id"),
  feature_direction: fields("feature_id", "direction"),
  concept_presence: fields("concept_id"),
  concept_direction: fields("concept_id", "direction"),
  magnitude: fields("feature_id", "concept_id", "magnitude"),
  ranking: fields("feature_id", "concept_id", "rank"),
  numeric: fields(
    "feature_id",
    "concept_id",
    "numeric_value",
    "numeric_unit",
    "numeric_role",
  ),
  causal: fields("feature_id", "concept_id", "causal_strength"),
  uncertainty: fields("certainty"),
  distributed_evidence: fields(),
  recommendation: fields(),
  limitation: fields(),
};

export function createValidationId(input: {
  claim_id: string;
  validator_version: string;
  policy_version: string;
}): string {
  const digest = createHash("sha256")
    .update(input.claim_id)
    .update("\n")
    .update(input.validator_version)
    .update("\n")
    .update(input.policy_version)
    .digest("hex");
  return `validation_${digest}`;
}

export function assertClaimValidationResult(
  value: unknown,
): asserts value is ClaimValidationResult {
  if (!validateSchema(value)) {
    throw new Error(
      `Invalid ${CLAIM_VALIDATION_SCHEMA_VERSION} result: ${formatErrors(validateSchema.errors)}`,
    );
  }

  const result = value;
  const expectedValidationId = createValidationId(result);
  if (result.validation_id !== expectedValidationId) {
    throw new Error(
      `Invalid deterministic validation_id: expected ${expectedValidationId}.`,
    );
  }

  if (
    result.execution_status === EXECUTION_STATUS.ERROR &&
    !systemReasonCodes.has(result.reason_code)
  ) {
    throw new Error("ERROR result must use a SYSTEM reason code.");
  }
  if (result.primary_reason_code !== result.reason_code) {
    throw new Error("primary_reason_code must equal compatibility reason_code.");
  }
  if (result.reason_codes[0] !== result.primary_reason_code) {
    throw new Error("primary_reason_code must be first in reason_codes.");
  }
  if (result.evidence_status !== result.validation_status) {
    throw new Error("evidence_status must equal compatibility validation_status.");
  }
  const allowedSubtypes: readonly string[] =
    CLAIM_SUBTYPES_BY_TYPE[result.claim_type];
  if (!allowedSubtypes.includes(result.claim_subtype)) {
    throw new Error(
      `Subtype ${result.claim_subtype} is incompatible with ${result.claim_type}.`,
    );
  }
  if (result.execution_status === EXECUTION_STATUS.SUCCESS) {
    assertSemanticDecisionConsistency(
      {
        reasonCode: result.primary_reason_code,
        reasonCodes: result.reason_codes,
        expected: result.expected,
        observed: result.observed,
        message: result.message,
        normalizationsApplied: result.normalizations_applied,
        sourceRecordKeys: result.source_record_keys,
        policyStatus: result.policy_status,
        validationCoverage: result.validation_coverage,
        unresolvedFacts: result.unresolved_facts,
        numericComparison: result.numeric_comparison
          ? {
              difference: result.numeric_comparison.difference,
              tolerance: result.numeric_comparison.tolerance,
              tolerancePolicyId:
                result.numeric_comparison.tolerance_policy_id,
            }
          : null,
      },
      result.evidence_status,
    );
  }
  if (
    result.execution_status === EXECUTION_STATUS.SUCCESS &&
    systemReasonCodes.has(result.reason_code)
  ) {
    throw new Error("SUCCESS result cannot use a SYSTEM reason code.");
  }

  assertProjectRelativePath(result.claims_input_path);
  assertProjectRelativePath(result.generation_index_path);
  assertProjectRelativePath(result.evidence_packages_path);
  assertFactCompatibility(result.claim_type, "expected", result.expected);
  assertFactCompatibility(result.claim_type, "observed", result.observed);
}

/** Verifies the historical frozen v2 wire contract without accepting v3. */
export function assertClaimValidationV2Result(value: unknown): void {
  if (!validateV2Schema(value)) {
    throw new Error(
      `Invalid historical claim validation v2 result: ${formatErrors(validateV2Schema.errors)}`,
    );
  }
}

/** Verifies the historical frozen v3 wire contract without accepting v4. */
export function assertClaimValidationV3Result(value: unknown): void {
  if (!validateV3Schema(value)) {
    throw new Error(
      `Invalid historical claim validation v3 result: ${formatErrors(validateV3Schema.errors)}`,
    );
  }
}

function assertFactCompatibility(
  claimType: ClaimType,
  label: "expected" | "observed",
  facts: ClaimValidationFactValues,
): void {
  const allowedFields = ALLOWED_FACT_FIELDS[claimType];
  for (const field of FACT_FIELDS) {
    const value = facts[field];
    if (value !== null && !allowedFields.has(field)) {
      throw new Error(
        `${label}.${field} is incompatible with claim_type ${claimType}.`,
      );
    }
  }
}

function assertProjectRelativePath(filePath: string): void {
  if (
    path.isAbsolute(filePath) ||
    path.win32.isAbsolute(filePath) ||
    filePath.split(/[\\/]/u).includes("..")
  ) {
    throw new Error(`Path must be project-relative: ${filePath}`);
  }
}

function fields(
  ...specificFields: Array<keyof ClaimValidationFactValues>
): ReadonlySet<keyof ClaimValidationFactValues> {
  return new Set([...COMMON_FACT_FIELDS, ...specificFields]);
}

function formatErrors(errors: ErrorObject[] | null | undefined): string {
  return (errors ?? [])
    .map((error) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
    .join("; ");
}
