import type {
  EvidenceLevel,
  ExplanationFactor,
  ExplanationOutput,
  FactorDirection,
  FactorRole,
  ParseResult,
} from "../../types/types";

export const EXPLANATION_JSON_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: [
    "prediction_summary",
    "factors",
    "uncertainty_note",
    "distributed_evidence_note",
    "safe_summary",
  ],
  properties: {
    prediction_summary: {
      type: "string",
    },
    factors: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "factor_id",
          "role",
          "factor_name",
          "declared_feature_ids",
          "declared_concept_ids",
          "direction",
          "explanation",
        ],
        properties: {
          factor_id: {
            type: "string",
          },
          role: {
            type: "string",
            enum: ["main", "supporting"],
          },
          factor_name: {
            type: "string",
          },
          declared_feature_ids: {
            type: "array",
            items: {
              type: "string",
            },
          },
          declared_concept_ids: {
            type: "array",
            items: {
              type: "string",
            },
          },
          direction: {
            type: "string",
            enum: ["increase_risk", "decrease_risk", "mixed", "unknown"],
          },
          explanation: {
            type: "string",
          },
        },
      },
    },
    uncertainty_note: {
      type: "string",
    },
    distributed_evidence_note: {
      type: "string",
    },
    safe_summary: {
      type: "string",
    },
  },
} as const;

export function parseExplanationOutput(
  rawOutput: string | null,
  evidenceLevel: EvidenceLevel,
): ParseResult {
  if (!rawOutput || !rawOutput.trim()) {
    return {
      raw_json_parse_success: false,
      json_parse_success: false,
      cleaned_output: null,
      cleanup_type: "failed",
      parsed_output: null,
      schema_valid: false,
      missing_required_fields: [
        "prediction_summary",
        "factors",
        "uncertainty_note",
        "distributed_evidence_note",
        "safe_summary",
      ],
      validation_errors: ["Output is empty."],
    };
  }

  const rawText = rawOutput.trim();
  const rawParsed = tryParseJson(rawText);

  if (rawParsed.success) {
    return buildParseResult(
      rawParsed.value,
      rawText,
      true,
      "none",
      evidenceLevel,
    );
  }

  const withoutFence = removeCodeFence(rawText);
  if (withoutFence !== rawText) {
    const fenceParsed = tryParseJson(withoutFence);
    if (fenceParsed.success) {
      return buildParseResult(
        fenceParsed.value,
        withoutFence,
        false,
        "removed_code_fence",
        evidenceLevel,
      );
    }
  }

  const extracted = extractJsonObject(withoutFence);
  if (extracted) {
    const extractedParsed = tryParseJson(extracted);
    if (extractedParsed.success) {
      return buildParseResult(
        extractedParsed.value,
        extracted,
        false,
        "extracted_json_object",
        evidenceLevel,
      );
    }
  }

  return {
    raw_json_parse_success: false,
    json_parse_success: false,
    cleaned_output: null,
    cleanup_type: "failed",
    parsed_output: null,
    schema_valid: false,
    missing_required_fields: [],
    validation_errors: ["Output is not valid JSON."],
  };
}

function tryParseJson(
  text: string,
): { success: true; value: unknown } | { success: false } {
  try {
    return {
      success: true,
      value: JSON.parse(text),
    };
  } catch {
    return {
      success: false,
    };
  }
}

function removeCodeFence(text: string): string {
  const trimmed = text.trim();

  if (!trimmed.startsWith("```")) {
    return trimmed;
  }

  const lines = trimmed.split(/\r?\n/);
  if (lines.length < 3) {
    return trimmed;
  }

  if (!lines[lines.length - 1].trim().startsWith("```")) {
    return trimmed;
  }

  return lines.slice(1, -1).join("\n").trim();
}

function extractJsonObject(text: string): string | null {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");

  if (start < 0 || end <= start) {
    return null;
  }

  return text.slice(start, end + 1).trim();
}

function buildParseResult(
  value: unknown,
  cleanedOutput: string,
  rawParseSuccess: boolean,
  cleanupType: ParseResult["cleanup_type"],
  evidenceLevel: EvidenceLevel,
): ParseResult {
  const validation = validateExplanationOutput(value, evidenceLevel);

  return {
    raw_json_parse_success: rawParseSuccess,
    json_parse_success: true,
    cleaned_output: cleanedOutput,
    cleanup_type: cleanupType,
    parsed_output: validation.output,
    schema_valid:
      validation.output !== null &&
      validation.missingFields.length === 0 &&
      validation.errors.length === 0,
    missing_required_fields: validation.missingFields,
    validation_errors: validation.errors,
  };
}

function validateExplanationOutput(
  value: unknown,
  evidenceLevel: EvidenceLevel,
): {
  output: ExplanationOutput | null;
  missingFields: string[];
  errors: string[];
} {
  const missingFields: string[] = [];
  const errors: string[] = [];

  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {
      output: null,
      missingFields,
      errors: ["Output root must be an object."],
    };
  }

  const source = value as Record<string, unknown>;
  const predictionSummary = readRequiredString(
    source,
    "prediction_summary",
    missingFields,
    errors,
  );
  const uncertaintyNote = readRequiredString(
    source,
    "uncertainty_note",
    missingFields,
    errors,
  );
  const distributedEvidenceNote = readStringField(
    source,
    "distributed_evidence_note",
    missingFields,
    errors,
  );
  const safeSummary = readRequiredString(
    source,
    "safe_summary",
    missingFields,
    errors,
  );

  const factors: ExplanationFactor[] = [];
  if (!("factors" in source)) {
    missingFields.push("factors");
  } else if (!Array.isArray(source.factors)) {
    errors.push("factors must be an array.");
  } else {
    for (let index = 0; index < source.factors.length; index += 1) {
      const factor = validateFactor(source.factors[index], index, errors);
      if (factor) {
        factors.push(factor);
      }
    }
  }

  if (evidenceLevel === "S0" && factors.length > 0) {
    errors.push("S0 must return an empty factors array.");
  }

  if (missingFields.length > 0 || errors.length > 0) {
    return {
      output: null,
      missingFields,
      errors,
    };
  }

  return {
    output: {
      prediction_summary: predictionSummary as string,
      factors,
      uncertainty_note: uncertaintyNote as string,
      distributed_evidence_note: distributedEvidenceNote as string,
      safe_summary: safeSummary as string,
    },
    missingFields,
    errors,
  };
}

function readRequiredString(
  source: Record<string, unknown>,
  key: string,
  missingFields: string[],
  errors: string[],
): string | null {
  const value = readStringField(source, key, missingFields, errors);

  if (typeof value === "string" && value.trim().length === 0) {
    errors.push(`${key} must not be empty.`);
  }

  return value;
}

function readStringField(
  source: Record<string, unknown>,
  key: string,
  missingFields: string[],
  errors: string[],
): string | null {
  if (!(key in source)) {
    missingFields.push(key);
    return null;
  }

  if (typeof source[key] !== "string") {
    errors.push(`${key} must be a string.`);
    return null;
  }

  return source[key] as string;
}

function validateFactor(
  value: unknown,
  index: number,
  errors: string[],
): ExplanationFactor | null {
  const prefix = `factors[${index}]`;

  if (!value || typeof value !== "object" || Array.isArray(value)) {
    errors.push(`${prefix} must be an object.`);
    return null;
  }

  const source = value as Record<string, unknown>;
  const factorId = readFactorString(source, "factor_id", prefix, errors);
  const factorName = readFactorString(source, "factor_name", prefix, errors);
  const explanation = readFactorString(source, "explanation", prefix, errors);
  const role = source.role;
  const direction = source.direction;

  if (!isFactorRole(role)) {
    errors.push(`${prefix}.role must be main or supporting.`);
  }

  if (!isFactorDirection(direction)) {
    errors.push(`${prefix}.direction is invalid.`);
  }

  const featureIds = readStringArray(
    source,
    "declared_feature_ids",
    prefix,
    errors,
  );
  const conceptIds = readStringArray(
    source,
    "declared_concept_ids",
    prefix,
    errors,
  );

  if (
    !factorId ||
    !factorName ||
    !explanation ||
    !isFactorRole(role) ||
    !isFactorDirection(direction)
  ) {
    return null;
  }

  return {
    factor_id: factorId,
    role,
    factor_name: factorName,
    declared_feature_ids: featureIds,
    declared_concept_ids: conceptIds,
    direction,
    explanation,
  };
}

function readFactorString(
  source: Record<string, unknown>,
  key: string,
  prefix: string,
  errors: string[],
): string | null {
  const value = source[key];

  if (typeof value !== "string" || value.trim().length === 0) {
    errors.push(`${prefix}.${key} must be a non-empty string.`);
    return null;
  }

  return value;
}

function readStringArray(
  source: Record<string, unknown>,
  key: string,
  prefix: string,
  errors: string[],
): string[] {
  const value = source[key];

  if (!Array.isArray(value)) {
    errors.push(`${prefix}.${key} must be an array.`);
    return [];
  }

  const result: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") {
      errors.push(`${prefix}.${key} must contain strings only.`);
      continue;
    }
    result.push(item);
  }

  return result;
}

function isFactorRole(value: unknown): value is FactorRole {
  return value === "main" || value === "supporting";
}

function isFactorDirection(value: unknown): value is FactorDirection {
  return (
    value === "increase_risk" ||
    value === "decrease_risk" ||
    value === "mixed" ||
    value === "unknown"
  );
}
