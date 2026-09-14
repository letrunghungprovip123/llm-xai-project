import compatibilityConfig from "../../../config/research/ts-validation/claim_type_compatibility.json";
import {
  CLAIM_SUBTYPES_BY_TYPE,
  CLAIM_TYPES,
  type AtomicClaimRecordV3,
  type ClaimSubtype,
  type ClaimType,
} from "../../../contracts/validation-claims";

export type ClaimTypeCompatibilityRule = {
  claim_type: ClaimType;
  claim_subtype: ClaimSubtype;
  allowed_source_sections: AtomicClaimRecordV3["source_section"][];
  required_fields: string[];
  forbidden_fields: string[];
  allowed_subject_types: AtomicClaimRecordV3["subject_type"][];
  complete_proposition_required: boolean;
  deterministic_validator: string;
  semantic_fallback_allowed: boolean;
  policy_relevance: string;
};

type CompatibilityConfig = {
  schema_version: "claim_type_compatibility_v1";
  status: "FROZEN";
  rules: ClaimTypeCompatibilityRule[];
};

export function loadClaimTypeCompatibility(): CompatibilityConfig {
  const config = parseCompatibilityConfig(compatibilityConfig);
  assertCompleteCompatibilityMatrix(config.rules);
  return config;
}

export function assertClaimCompatible(claim: AtomicClaimRecordV3): void {
  const config = loadClaimTypeCompatibility();
  const rule = config.rules.find(
    (candidate) =>
      candidate.claim_type === claim.claim_type
      && candidate.claim_subtype === claim.claim_subtype,
  );
  if (!rule) {
    throw new Error(
      `No compatibility rule for ${claim.claim_type}/${claim.claim_subtype}.`,
    );
  }
  if (!rule.allowed_source_sections.includes(claim.source_section)) {
    throw new Error(
      `Disallowed source section for ${claim.claim_id} `
        + `(parent=${claim.parent_claim_id ?? "none"}, `
        + `${claim.claim_type}/${claim.claim_subtype}): ${claim.source_section}.`,
    );
  }
  if (!rule.allowed_subject_types.includes(claim.subject_type)) {
    throw new Error(
      `Disallowed subject type for ${claim.claim_id} `
        + `(parent=${claim.parent_claim_id ?? "none"}, `
        + `${claim.claim_type}/${claim.claim_subtype}): ${claim.subject_type}.`,
    );
  }
  if (
    rule.complete_proposition_required
    && claim.proposition_status !== "COMPLETE"
  ) {
    throw new Error(`Incomplete proposition is not final: ${claim.claim_id}.`);
  }
  for (const field of rule.required_fields) {
    if (!isPresent(readField(claim, field))) {
      throw new Error(
        `Missing required field ${field}: ${claim.claim_id} `
          + `(parent=${claim.parent_claim_id ?? "none"}, `
          + `${claim.claim_type}/${claim.claim_subtype}).`,
      );
    }
  }
  for (const field of rule.forbidden_fields) {
    if (isPresent(readField(claim, field))) {
      throw new Error(`Forbidden field ${field}: ${claim.claim_id}.`);
    }
  }
}

function assertCompleteCompatibilityMatrix(
  rules: readonly ClaimTypeCompatibilityRule[],
): void {
  const keys = new Set<string>();
  for (const rule of rules) {
    const key = `${rule.claim_type}/${rule.claim_subtype}`;
    if (keys.has(key)) throw new Error(`Duplicate compatibility rule: ${key}.`);
    keys.add(key);
  }
  for (const claimType of CLAIM_TYPES) {
    for (const subtype of CLAIM_SUBTYPES_BY_TYPE[claimType]) {
      const key = `${claimType}/${subtype}`;
      if (!keys.has(key)) throw new Error(`Missing compatibility rule: ${key}.`);
    }
  }
}

function parseCompatibilityConfig(value: unknown): CompatibilityConfig {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Claim-type compatibility config must be an object.");
  }
  const record = value as Record<string, unknown>;
  if (
    record.schema_version !== "claim_type_compatibility_v1"
    || record.status !== "FROZEN"
    || !Array.isArray(record.rules)
  ) {
    throw new Error("Invalid claim-type compatibility config header.");
  }
  const rules = record.rules.map(parseRule);
  return {
    schema_version: "claim_type_compatibility_v1",
    status: "FROZEN",
    rules,
  };
}

function parseRule(value: unknown): ClaimTypeCompatibilityRule {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Compatibility rule must be an object.");
  }
  const rule = value as Record<string, unknown>;
  const claimType = readEnum(rule.claim_type, CLAIM_TYPES, "claim_type");
  const subtype = readEnum(
    rule.claim_subtype,
    CLAIM_SUBTYPES_BY_TYPE[claimType],
    "claim_subtype",
  );
  return {
    claim_type: claimType,
    claim_subtype: subtype,
    allowed_source_sections: readStringArray(
      rule.allowed_source_sections,
      "allowed_source_sections",
    ),
    required_fields: readStringArray(rule.required_fields, "required_fields"),
    forbidden_fields: readStringArray(rule.forbidden_fields, "forbidden_fields"),
    allowed_subject_types: readStringArray(
      rule.allowed_subject_types,
      "allowed_subject_types",
    ),
    complete_proposition_required: readBoolean(
      rule.complete_proposition_required,
      "complete_proposition_required",
    ),
    deterministic_validator: readString(
      rule.deterministic_validator,
      "deterministic_validator",
    ),
    semantic_fallback_allowed: readBoolean(
      rule.semantic_fallback_allowed,
      "semantic_fallback_allowed",
    ),
    policy_relevance: readString(rule.policy_relevance, "policy_relevance"),
  };
}

function readField(
  claim: AtomicClaimRecordV3,
  field: string,
): unknown {
  return (claim as unknown as Record<string, unknown>)[field];
}

function isPresent(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "";
}

function readString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value) {
    throw new Error(`${field} must be a non-empty string.`);
  }
  return value;
}

function readBoolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${field} must be boolean.`);
  return value;
}

function readStringArray<T extends string>(
  value: unknown,
  field: string,
): T[] {
  if (
    !Array.isArray(value)
    || value.some((item) => typeof item !== "string" || !item)
  ) {
    throw new Error(`${field} must be a string array.`);
  }
  return value.slice() as T[];
}

function readEnum<const Values extends readonly string[]>(
  value: unknown,
  values: Values,
  field: string,
): Values[number] {
  if (typeof value !== "string" || !values.includes(value)) {
    throw new Error(`${field} has an unsupported value: ${String(value)}.`);
  }
  return value;
}
