// src/server/validator/claim-schema.ts

import { z } from "zod";

export const CLAIM_EXTRACTION_STAGE_VERSION = "v1.0";

export const REQUIRED_EXPLANATION_SECTIONS = [
  "prediction",
  "contribution_overview",
  "main_risk_drivers",
  "supporting_evidence_groups",
  "risk_reducing_factors",
  "limitations",
] as const;

export const CLAIM_SECTIONS = [
  ...REQUIRED_EXPLANATION_SECTIONS,
  "unknown",
] as const;

export const CLAIM_TYPES = [
  "prediction",
  "contribution_accounting",
  "feature_mention",
  "concept_mention",
  "direction",
  "contribution_value",
  "referenced_term",
  "limitation",
  "forbidden_wording",
  "raw_technical_leakage",
  "unsupported_customer_claim",
  "remaining_summary",
  "unknown",
] as const;

export const CLAIM_DIRECTIONS = [
  "increases_risk",
  "decreases_risk",
  "neutral",
  "unknown",
] as const;

export const CLAIM_CONFIDENCE_LEVELS = ["high", "medium", "low"] as const;

export type ClaimSection = (typeof CLAIM_SECTIONS)[number];
export type ClaimType = (typeof CLAIM_TYPES)[number];
export type ClaimDirection = (typeof CLAIM_DIRECTIONS)[number];
export type ClaimConfidence = (typeof CLAIM_CONFIDENCE_LEVELS)[number];

export const ExtractedClaimSchema = z
  .object({
    claim_id: z.string(),
    section: z.enum(CLAIM_SECTIONS),
    claim_type: z.enum(CLAIM_TYPES),
    text: z.string(),
    normalized_subject: z.string(),
    direction: z.enum(CLAIM_DIRECTIONS),
    value_mentioned: z.string(),
    evidence_refs: z.array(z.string()),
    confidence: z.enum(CLAIM_CONFIDENCE_LEVELS),
  })
  .strict();

export const ClaimExtractionPayloadSchema = z
  .object({
    claims: z.array(ExtractedClaimSchema),
    claim_count: z.number().int(),
  })
  .strict();

export type ExtractedClaim = z.infer<typeof ExtractedClaimSchema>;
export type ClaimExtractionPayload = z.infer<
  typeof ClaimExtractionPayloadSchema
>;

export type ClaimExtractionQuality = {
  parseable_json: boolean;
  schema_valid: boolean;
  error: string | null;
  warning: string | null;
};

export type ClaimExtractionArtifactRecord = {
  claim_extraction_id: string;
  ir_id: string;
  explanation_id: string;
  customer_id: string | null;
  generator_type: "template" | "llm_api" | string;
  run_mode: string;
  extractor_type: "bedrock_structured_outputs";
  extractor_version: string;
  bedrock: {
    provider: "amazon_bedrock";
    endpoint: "bedrock-runtime";
    region_name: string;
    model_id: string;
    structured_output: true;
    max_tokens: number;
    temperature: number;
  };
  claim_extraction: ClaimExtractionPayload;
  quality: ClaimExtractionQuality;
  created_at: string;
};

/**
 * JSON Schema for Amazon Bedrock Structured Outputs.
 *
 * Keep this schema intentionally simple because Bedrock Structured Outputs
 * supports a subset of JSON Schema features:
 * - no recursive schemas
 * - no external refs
 * - no string minLength/maxLength
 * - no numeric min/max
 * - additionalProperties must be false
 */
export const CLAIM_EXTRACTION_JSON_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    claims: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          claim_id: {
            type: "string",
            description:
              "Stable claim id within this explanation, e.g. claim_001.",
          },
          section: {
            type: "string",
            enum: [...CLAIM_SECTIONS],
            description: "Explanation section where this claim appears.",
          },
          claim_type: {
            type: "string",
            enum: [...CLAIM_TYPES],
            description: "Type of extracted claim.",
          },
          text: {
            type: "string",
            description: "Original sentence or phrase from the explanation.",
          },
          normalized_subject: {
            type: "string",
            description:
              "Normalized safe subject of the claim. Use Vietnamese concept-level phrase if feature name is technical.",
          },
          direction: {
            type: "string",
            enum: [...CLAIM_DIRECTIONS],
            description: "Risk direction expressed by the claim.",
          },
          value_mentioned: {
            type: "string",
            description:
              "Mentioned numeric value, such as '+6.84 điểm phần trăm' or '52.34%'. Empty string if none.",
          },
          evidence_refs: {
            type: "array",
            items: {
              type: "string",
            },
            description:
              "Evidence ids or group ids explicitly referenced by the claim. Empty list if not explicit.",
          },
          confidence: {
            type: "string",
            enum: [...CLAIM_CONFIDENCE_LEVELS],
            description:
              "Extractor confidence: high for direct metadata, medium for clear text, low for inferred or ambiguous text.",
          },
        },
        required: [
          "claim_id",
          "section",
          "claim_type",
          "text",
          "normalized_subject",
          "direction",
          "value_mentioned",
          "evidence_refs",
          "confidence",
        ],
      },
    },
    claim_count: {
      type: "integer",
      description: "Number of claims in the claims array.",
    },
  },
  required: ["claims", "claim_count"],
} as const;

export function validateClaimExtractionPayload(
  payload: unknown,
): ClaimExtractionPayload {
  const parsed = ClaimExtractionPayloadSchema.parse(payload);

  if (parsed.claim_count !== parsed.claims.length) {
    return {
      ...parsed,
      claim_count: parsed.claims.length,
    };
  }

  return parsed;
}
