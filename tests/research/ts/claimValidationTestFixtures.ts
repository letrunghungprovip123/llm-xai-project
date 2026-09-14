import {
  CLAIM_SUBTYPES_BY_TYPE,
  type ClaimSubtype,
  type AtomicClaimRecordV3 as AtomicClaimRecord,
} from "../../../contracts/validation-claims";
import type {
  ClaimValidationEvidencePackage,
  ClaimValidationFeatureEvidence,
  ClaimValidationGenerationRow,
} from "../../../research/ts/claim_validation/runtimeTypes";

export function testClaim(
  overrides: Partial<AtomicClaimRecord> & {
    claim_type: AtomicClaimRecord["claim_type"];
  },
): AtomicClaimRecord {
  return {
    local_claim_index: 1,
    source_section: "safe_summary",
    source_factor_id: null,
    source_text: "Synthetic atomic claim.",
    source_span_start: 0,
    source_span_end: 23,
    subject_type: "narrative",
    feature_id: null,
    concept_id: null,
    direction: "unknown",
    magnitude: null,
    certainty: "deterministic",
    causal_strength: "none",
    numeric_value: null,
    numeric_unit: null,
    numeric_role: null,
    claim_origin: "llm",
    model_normalized_claim_key: "synthetic",
    semantic_signature: "synthetic",
    normalized_claim_key: "synthetic",
    claim_schema_version: "claims_v3",
    claim_id: `claim_${overrides.claim_type}_oracle`,
    parent_claim_id: `claim_parent_${overrides.claim_type}_oracle`,
    generation_id: "generation_001",
    model_id: "model_001",
    source_ir_id: "ir_001",
    case_id: "case_001",
    evidence_level: "S3",
    repeat_id: 1,
    source_input_sha256: "1".repeat(64),
    source_text_sha256: "2".repeat(64),
    extractor_provider: "deepseek",
    extractor_model_id: "deepseek-v4-flash",
    extractor_version: "atomic_claim_extractor_v2.1.0",
    extractor_prompt_version: "atomic_claim_extraction_prompt_v3",
    extractor_prompt_sha256: "3".repeat(64),
    extractor_status: "SUCCESS",
    claim_subtype:
      overrides.claim_subtype ?? defaultSubtype(overrides.claim_type),
    proposition_status: "COMPLETE",
    source_start: 0,
    source_end: 23,
    finalizer_version: "claim_finalizer_v2.0.0",
    finalization_policy_version: "claim_finalization_policy_v3",
    ...overrides,
    claim_type: overrides.claim_type,
  } as AtomicClaimRecord;
}

function defaultSubtype(
  claimType: AtomicClaimRecord["claim_type"],
): ClaimSubtype {
  return CLAIM_SUBTYPES_BY_TYPE[claimType][0];
}

export function numericTestClaim(options: {
  value: number;
  unit: string | null;
  role: AtomicClaimRecord["numeric_role"];
  target?: string;
  featureId?: string | null;
}): AtomicClaimRecord {
  return testClaim({
    claim_type: "numeric",
    numeric_value: options.value,
    numeric_unit: options.unit,
    numeric_role: options.role,
    feature_id: options.featureId ?? null,
    subject_type: options.featureId ? "feature" : "prediction",
    normalized_claim_key: `numeric|value:${options.value}|${options.target ?? ""}`,
  });
}

export function testEvidence(options: {
  level?: ClaimValidationEvidencePackage["evidence_level"];
  predictedLabel?: string;
  probability?: number;
  threshold?: number;
  features?: ClaimValidationFeatureEvidence[];
  concepts?: ClaimValidationEvidencePackage["prompt_payload"]["concept_evidence"];
  allowFinancialAdvice?: boolean;
  allowCausalClaim?: boolean;
  mustIncludeUncertainty?: boolean;
} = {}): ClaimValidationEvidencePackage {
  const level = options.level ?? "S3";
  const features = options.features ?? defaultFeatures();
  const concepts = options.concepts ?? [defaultConcept(features)];
  return {
    package_id: "package_001",
    source_ir_id: "ir_001",
    source_evidence_id: "evidence_001",
    evidence_level: level,
    prompt_payload: {
      evidence_level: level,
      prediction: {
        predicted_label: options.predictedLabel ?? "high_default_risk",
        probability: options.probability ?? 0.9334,
        threshold: options.threshold ?? 0.5,
        probability_display: "0.9334",
        probability_percent_display: "93.34%",
        threshold_display: "0.5000",
        threshold_percent_display: "50.00%",
        threshold_comparison: "above_or_equal_threshold",
        is_above_threshold: true,
      },
      selected_evidence: features,
      concept_evidence: concepts,
      selection_context: {
        selected_evidence_count: features.length,
        concept_group_count: concepts.length,
        mixed_concept_group_count: 0,
      },
      narrative_policy: {
        must_include_uncertainty: options.mustIncludeUncertainty ?? true,
      },
      constraints: {
        allowed_feature_ids: features.map((feature) => feature.feature_id),
        allowed_concept_ids: concepts.map((concept) => concept.concept),
        forbidden_rule_ids: ["forbid_real_world_causality"],
        claim_policy: {
          allow_prediction_claim: true,
          allow_feature_claim: true,
          allow_concept_claim: true,
          allow_direction_claim: true,
          allow_magnitude_claim: true,
          allow_causal_claim: options.allowCausalClaim ?? false,
          allow_financial_advice: options.allowFinancialAdvice ?? false,
        },
      },
    },
  };
}

export function testGeneration(): ClaimValidationGenerationRow {
  return {
    canonical_schema_version: "generation_index_v1",
    generation_id: "generation_001",
    package_id: "package_001",
    source_evidence_id: "evidence_001",
    source_ir_id: "ir_001",
    model_id: "model_001",
    case_id: "case_001",
    repeat_id: 1,
    evidence_level: "S3",
    usable: true,
    runtime_status: "SUCCESS",
    finish_reason: "stop",
    truncated_response: false,
    raw_json_parse_success: true,
    schema_valid: true,
    usability_reason_codes: [],
    generation_record: {
      generation_id: "generation_001",
      package_id: "package_001",
      source_evidence_id: "evidence_001",
      source_ir_id: "ir_001",
      model_id: "model_001",
      repeat_id: 1,
      evidence_level: "S3",
    },
  };
}

export function testProvenance() {
  return {
    claimsInputPath: "data/claims.jsonl",
    claimsInputSha256: "8".repeat(64),
    generationIndexPath: "data/generations.jsonl",
    generationIndexSha256: "9".repeat(64),
    evidencePackagesPath: "data/evidence.jsonl",
    evidencePackagesSha256: "a".repeat(64),
  };
}

function defaultFeatures(): ClaimValidationFeatureEvidence[] {
  return [
    {
      feature_id: "feature_a",
      shap_value: 0.2,
      abs_shap_value: 0.2,
      direction: "increases_risk",
      rank: 1,
      strength: "moderate",
      value: 2,
    },
    {
      feature_id: "feature_b",
      shap_value: -0.1,
      abs_shap_value: 0.1,
      direction: "decreases_risk",
      rank: 2,
      strength: "weak",
      value: 1,
    },
  ];
}

function defaultConcept(
  features: ClaimValidationFeatureEvidence[],
): ClaimValidationEvidencePackage["prompt_payload"]["concept_evidence"][number] {
  const representative = features.find(
    (feature) => feature.feature_id === "feature_a",
  ) ?? {
    feature_id: "feature_a",
    shap_value: 0.2,
    abs_shap_value: 0.2,
    direction: "increases_risk",
    rank: 1,
    strength: "moderate",
  };
  return {
    concept: "concept_a",
    direction: "increases_risk",
    representative_feature: representative,
    supporting_features: features,
    selected_feature_ids: features.map((feature) => feature.feature_id),
    feature_count: features.length,
    selected_abs_shap_sum: features.reduce(
      (sum, feature) => sum + feature.abs_shap_value,
      0,
    ),
  };
}
