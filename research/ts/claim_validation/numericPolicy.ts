import path from "node:path";

import Ajv2020, { type ErrorObject } from "ajv/dist/2020";

import numericPolicyJson from "../../../config/research/ts-validation/numeric_tolerance_policy_v1.json";
import numericPolicySchema from "../../../contracts/llm-validation/numeric_tolerance_policy.schema.json";
import {
  CLAIM_NUMERIC_ROLES,
  type ClaimNumericRole,
} from "../../../contracts/validation-claims";

export type NumericToleranceRule = {
  numeric_role: ClaimNumericRole;
  unit: string;
  normalization:
    | "PERCENT_TO_UNIT_INTERVAL"
    | "UNIT_INTERVAL_IDENTITY"
    | "EXACT_INTEGER"
    | "NONE";
  comparison_mode: "EXACT" | "HALF_DISPLAY_UNIT" | "NOT_VERIFIABLE";
  absolute_tolerance: number | null;
  relative_tolerance: number | null;
  display_precision_source: string | null;
  unsupported_behavior: "NOT_VERIFIABLE";
};

export type NumericTolerancePolicy = {
  schema_version: "numeric_tolerance_policy_v1";
  numeric_policy_version: "numeric_tolerance_policy_v1";
  status: "FROZEN";
  unknown_role_behavior: "NOT_VERIFIABLE";
  rules: NumericToleranceRule[];
  source_references: Array<{
    path: string;
    symbol: string;
    rationale: string;
  }>;
};

const ajv = new Ajv2020({
  allErrors: true,
  allowUnionTypes: true,
  strict: true,
});
const validateNumericPolicySchema =
  ajv.compile<NumericTolerancePolicy>(numericPolicySchema);
const numericPolicyInput: unknown = numericPolicyJson;

export function assertNumericTolerancePolicy(
  value: unknown = NUMERIC_TOLERANCE_POLICY,
): asserts value is NumericTolerancePolicy {
  if (!validateNumericPolicySchema(value)) {
    throw new Error(
      `Invalid numeric tolerance policy: ${formatErrors(validateNumericPolicySchema.errors)}`,
    );
  }

  const policy = value;
  const keys = policy.rules.map(
    (rule) => `${rule.numeric_role}\u0000${normalizeNumericUnit(rule.unit)}`,
  );
  if (new Set(keys).size !== keys.length) {
    throw new Error("Numeric tolerance rules must have unique role/unit keys.");
  }

  const currentRoles = CLAIM_NUMERIC_ROLES.filter(
    (role): role is ClaimNumericRole => role !== "not_applicable",
  );
  for (const role of currentRoles) {
    if (!policy.rules.some((rule) => rule.numeric_role === role)) {
      throw new Error(`Numeric tolerance policy does not cover role: ${role}`);
    }
  }

  for (const rule of policy.rules) {
    if (
      rule.comparison_mode === "NOT_VERIFIABLE" &&
      (rule.absolute_tolerance !== null || rule.relative_tolerance !== null)
    ) {
      throw new Error(
        `NOT_VERIFIABLE rule cannot define tolerance: ${rule.numeric_role}/${rule.unit}`,
      );
    }
    if (
      rule.comparison_mode === "HALF_DISPLAY_UNIT" &&
      (!(rule.absolute_tolerance && rule.absolute_tolerance > 0) ||
        !rule.display_precision_source)
    ) {
      throw new Error(
        `HALF_DISPLAY_UNIT rule needs positive tolerance and source: ${rule.numeric_role}/${rule.unit}`,
      );
    }
    if (
      rule.comparison_mode === "EXACT" &&
      rule.absolute_tolerance !== 0
    ) {
      throw new Error(
        `EXACT rule must use zero absolute tolerance: ${rule.numeric_role}/${rule.unit}`,
      );
    }
  }

  for (const reference of policy.source_references) {
    if (
      path.isAbsolute(reference.path) ||
      path.win32.isAbsolute(reference.path) ||
      reference.path.split(/[\\/]/u).includes("..")
    ) {
      throw new Error(`Numeric policy source path must be project-relative.`);
    }
  }
}

assertNumericTolerancePolicy(numericPolicyInput);
export const NUMERIC_TOLERANCE_POLICY = numericPolicyInput;

export function normalizeNumericUnit(unit: string | null): string {
  const normalized = unit?.trim().toLowerCase() ?? "";
  if (["%", "percent", "percentage", "phần trăm"].includes(normalized)) {
    return "percent";
  }
  if (["probability", "probability_0_to_1", "rate_0_to_1"].includes(normalized)) {
    return "probability";
  }
  if (["count", "counts", "integer"].includes(normalized)) return "count";
  if (["rank", "ordinal"].includes(normalized)) return "rank";
  return normalized || "unitless";
}

export function numericRuleFor(
  role: ClaimNumericRole,
  unit: string | null,
): NumericToleranceRule {
  assertNumericTolerancePolicy();
  const normalizedUnit = normalizeNumericUnit(unit);
  const exact = NUMERIC_TOLERANCE_POLICY.rules.find(
    (rule) =>
      rule.numeric_role === role &&
      normalizeNumericUnit(rule.unit) === normalizedUnit,
  );
  const fallback = NUMERIC_TOLERANCE_POLICY.rules.find(
    (rule) => rule.numeric_role === role && rule.unit === "*",
  );
  if (exact) return exact;
  if (fallback) return fallback;
  throw new Error(`No numeric policy for role/unit: ${role}/${normalizedUnit}`);
}

function formatErrors(errors: ErrorObject[] | null | undefined): string {
  return (errors ?? [])
    .map((error) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
    .join("; ");
}
