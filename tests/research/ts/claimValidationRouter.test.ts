import assert from "node:assert/strict";
import test from "node:test";

import {
  CLAIM_SUBTYPES_BY_TYPE,
  type AtomicClaimRecordV3 as AtomicClaimRecord,
} from "../../../contracts/validation-claims";
import type {
  ClaimValidationEvidencePackage,
  ClaimValidationGenerationRow,
} from "../../../research/ts/claim_validation/runtimeTypes";
import {
  assertFinalizedClaimShape,
} from "../../../research/ts/claim_validation/input";
import {
  buildErrorResult,
  buildSuccessResult,
  CLAIM_VALIDATOR_VERSION,
} from "../../../research/ts/claim_validation/result";
import { createValidationId } from "../../../research/ts/claim_validation/schema";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";

test("synthetic deterministic validators cover claim families and boundaries", async (t) => {
  const cases: Array<{
    name: string;
    claim: AtomicClaimRecord;
    evidence: ClaimValidationEvidencePackage;
    reason: string;
  }> = [
    {
      name: "prediction exact match",
      claim: claim({ claim_type: "prediction", direction: "increase_risk" }),
      evidence: evidence(),
      reason: "EXACT_MATCH",
    },
    {
      name: "prediction mismatch",
      claim: claim({ claim_type: "prediction", direction: "decrease_risk" }),
      evidence: evidence(),
      reason: "PREDICTION_LABEL_MISMATCH",
    },
    {
      name: "S0 feature claim",
      claim: claim({
        claim_type: "feature_presence",
        feature_id: "feature_a",
        evidence_level: "S0",
        subject_type: "feature",
      }),
      evidence: evidence({ level: "S0", features: [] }),
      reason: "FEATURE_NOT_EXPOSED",
    },
    {
      name: "feature exposed",
      claim: claim({
        claim_type: "feature_presence",
        feature_id: "feature_a",
        subject_type: "feature",
      }),
      evidence: evidence(),
      reason: "EXACT_MATCH",
    },
    {
      name: "feature absent",
      claim: claim({
        claim_type: "feature_presence",
        feature_id: "missing",
        subject_type: "feature",
      }),
      evidence: evidence(),
      reason: "FEATURE_NOT_FOUND_IN_EVIDENCE",
    },
    {
      name: "feature alias unresolved",
      claim: claim({
        claim_type: "feature_presence",
        feature_id: "FEATURE_A",
        subject_type: "feature",
      }),
      evidence: evidence(),
      reason: "FEATURE_ALIAS_UNRESOLVED",
    },
    {
      name: "direction normalized match",
      claim: claim({
        claim_type: "feature_direction",
        feature_id: "feature_a",
        subject_type: "feature",
        direction: "increase_risk",
      }),
      evidence: evidence(),
      reason: "NORMALIZED_MATCH",
    },
    {
      name: "direction reversed",
      claim: claim({
        claim_type: "feature_direction",
        feature_id: "feature_a",
        subject_type: "feature",
        direction: "decrease_risk",
      }),
      evidence: evidence(),
      reason: "DIRECTION_REVERSED",
    },
    {
      name: "near-zero direction",
      claim: claim({
        claim_type: "feature_direction",
        feature_id: "feature_a",
        subject_type: "feature",
        direction: "increase_risk",
      }),
      evidence: evidence({
        features: [
          {
            feature_id: "feature_a",
            shap_value: 0,
            abs_shap_value: 0,
            direction: "increases_risk",
            rank: 1,
          },
        ],
      }),
      reason: "DIRECTION_NEUTRAL",
    },
    {
      name: "mixed direction",
      claim: claim({
        claim_type: "feature_direction",
        feature_id: "feature_a",
        subject_type: "feature",
        direction: "increase_risk",
      }),
      evidence: evidence({
        features: [
          {
            feature_id: "feature_a",
            shap_value: 0.2,
            abs_shap_value: 0.2,
            direction: "mixed",
            rank: 1,
          },
        ],
      }),
      reason: "DIRECTION_MIXED_OR_UNKNOWN",
    },
    {
      name: "concept exposed",
      claim: claim({
        claim_type: "concept_presence",
        concept_id: "concept_a",
        subject_type: "concept",
      }),
      evidence: evidence(),
      reason: "EXACT_MATCH",
    },
    {
      name: "concept absent",
      claim: claim({
        claim_type: "concept_presence",
        concept_id: "missing",
        subject_type: "concept",
      }),
      evidence: evidence(),
      reason: "CONCEPT_NOT_FOUND_IN_EVIDENCE",
    },
    {
      name: "numeric exact count",
      claim: numericClaim(2, "count", "other", "target:selected_evidence_count"),
      evidence: evidence(),
      reason: "EXACT_MATCH",
    },
    {
      name: "numeric within tolerance",
      claim: numericClaim(93.344, "percent", "prediction_score"),
      evidence: evidence(),
      reason: "TOLERANCE_MATCH",
    },
    {
      name: "numeric outside tolerance",
      claim: numericClaim(93.5, "percent", "prediction_score"),
      evidence: evidence(),
      reason: "NUMERIC_OUTSIDE_TOLERANCE",
    },
    {
      name: "numeric unsupported role",
      claim: numericClaim(1.25, null, "feature_value", "", "feature_a"),
      evidence: evidence(),
      reason: "NUMERIC_ROLE_UNSUPPORTED",
    },
    {
      name: "ranking exact",
      claim: claim({
        claim_type: "ranking",
        feature_id: "feature_a",
        subject_type: "feature",
      }),
      evidence: evidence(),
      reason: "EXACT_MATCH",
    },
    {
      name: "ranking tie",
      claim: claim({
        claim_type: "ranking",
        feature_id: "feature_a",
        subject_type: "feature",
      }),
      evidence: evidence({
        features: [
          {
            feature_id: "feature_a",
            shap_value: 0.2,
            abs_shap_value: 0.2,
            direction: "increases_risk",
            rank: 1,
          },
          {
            feature_id: "feature_b",
            shap_value: 0.2,
            abs_shap_value: 0.2,
            direction: "increases_risk",
            rank: 1,
          },
        ],
      }),
      reason: "RANK_TIE_AMBIGUOUS",
    },
    {
      name: "magnitude unavailable",
      claim: claim({
        claim_type: "magnitude",
        feature_id: "feature_a",
        subject_type: "feature",
        magnitude: "strong",
      }),
      evidence: evidence(),
      reason: "MAGNITUDE_SOURCE_MISSING",
    },
    {
      name: "uncertainty grounded",
      claim: claim({
        claim_type: "uncertainty",
        certainty: "hedged",
        subject_type: "evidence",
      }),
      evidence: evidence(),
      reason: "EXACT_MATCH",
    },
    {
      name: "certainty overclaim",
      claim: claim({
        claim_type: "uncertainty",
        certainty: "deterministic",
        source_text: "Kết quả này đảm bảo rằng dự đoán chính xác tuyệt đối.",
      }),
      evidence: evidence(),
      reason: "CERTAINTY_OVERCLAIM",
    },
    {
      name: "negated guarantee is grounded uncertainty",
      claim: claim({
        claim_type: "uncertainty",
        certainty: "hedged",
        source_text: "Mô hình không thể đảm bảo kết quả chính xác tuyệt đối.",
      }),
      evidence: evidence(),
      reason: "EXACT_MATCH",
    },
    {
      name: "hedged accuracy language is not a guarantee",
      claim: claim({
        claim_type: "uncertainty",
        certainty: "hedged",
        source_text: "Cần xem xét thêm thông tin để đảm bảo tính chính xác.",
      }),
      evidence: evidence(),
      reason: "EXACT_MATCH",
    },
    {
      name: "recommendation requires semantic review",
      claim: claim({ claim_type: "recommendation" }),
      evidence: evidence(),
      reason: "SEMANTIC_SOURCE_UNFROZEN",
    },
    {
      name: "causal overclaim",
      claim: claim({
        claim_type: "causal",
        causal_strength: "causal",
        subject_type: "feature",
      }),
      evidence: evidence(),
      reason: "CAUSAL_OVERCLAIM",
    },
    {
      name: "distributed evidence",
      claim: claim({
        claim_type: "distributed_evidence",
        subject_type: "evidence",
      }),
      evidence: evidence(),
      reason: "EXACT_MATCH",
    },
    {
      name: "limitation grounded",
      claim: claim({ claim_type: "limitation" }),
      evidence: evidence(),
      reason: "EXACT_MATCH",
    },
  ];

  for (const item of cases) {
    await t.test(item.name, () => {
      assert.equal(
        validateClaimDeterministically(item.claim, item.evidence).reasonCode,
        item.reason,
      );
    });
  }
});

test("success result is schema-valid and uses deterministic validation_id", () => {
  const inputClaim = claim({
    claim_type: "feature_direction",
    feature_id: "feature_a",
    subject_type: "feature",
    direction: "increase_risk",
  });
  const packageItem = evidence();
  const result = buildSuccessResult({
    claim: inputClaim,
    generation: generation(),
    evidence: packageItem,
    decision: validateClaimDeterministically(inputClaim, packageItem),
    provenance: provenance(),
  });
  assert.equal(
    result.validation_id,
    createValidationId({
      claim_id: inputClaim.claim_id,
      validator_version: CLAIM_VALIDATOR_VERSION,
      policy_version: "claim_validation_policy_v1",
    }),
  );
  assert.equal(result.validation_status, "SUPPORTED");
});

test("missing evidence join produces a schema-valid terminal ERROR result", () => {
  const result = buildErrorResult({
    claim: claim({ claim_type: "prediction" }),
    generation: generation(),
    evidence: null,
    provenance: provenance(),
    reasonCode: "EVIDENCE_JOIN_FAILED",
    failedStage: "EVIDENCE_JOIN",
    errorMessage: "Synthetic missing evidence.",
  });
  assert.equal(result.execution_status, "ERROR");
  assert.equal(result.validation_status, null);
  assert.equal(result.reason_code, "EVIDENCE_JOIN_FAILED");
});

test("missing generation join remains schema-valid without invented evidence IDs", () => {
  const result = buildErrorResult({
    claim: claim({ claim_type: "prediction" }),
    generation: null,
    evidence: null,
    provenance: provenance(),
    reasonCode: "GENERATION_JOIN_FAILED",
    failedStage: "GENERATION_JOIN",
    errorMessage: "Synthetic missing generation.",
  });
  assert.equal(result.execution_status, "ERROR");
  assert.equal(result.source_evidence_id, null);
  assert.equal(result.package_id, null);
});

test("malformed and unsupported claims fail closed", () => {
  const malformed = claim({ claim_type: "feature_presence" });
  malformed.feature_id = null;
  assert.throws(
    () => assertFinalizedClaimShape(malformed),
    /Invalid finalized claim/u,
  );
  const unsupported = {
    ...claim({ claim_type: "prediction" }),
    claim_type: "unsupported",
  } as unknown as AtomicClaimRecord;
  assert.throws(
    () => validateClaimDeterministically(unsupported, evidence()),
    /Unsupported claim type/u,
  );
});

function numericClaim(
  value: number,
  unit: string | null,
  role: AtomicClaimRecord["numeric_role"],
  target = "",
  featureId: string | null = null,
): AtomicClaimRecord {
  return claim({
    claim_type: "numeric",
    numeric_value: value,
    numeric_unit: unit,
    numeric_role: role,
    feature_id: featureId,
    subject_type: featureId ? "feature" : "prediction",
    normalized_claim_key: `numeric|value:${value}|${target}`,
  });
}

function claim(
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
    claim_id: `claim_${overrides.claim_type}_synthetic`,
    parent_claim_id: `claim_parent_${overrides.claim_type}_synthetic`,
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
      overrides.claim_subtype ?? CLAIM_SUBTYPES_BY_TYPE[overrides.claim_type][0],
    proposition_status: "COMPLETE",
    source_start: 0,
    source_end: 23,
    finalizer_version: "claim_finalizer_v2.0.0",
    finalization_policy_version: "claim_finalization_policy_v3",
    ...overrides,
    claim_type: overrides.claim_type,
  } as AtomicClaimRecord;
}

function evidence(options: {
  level?: ClaimValidationEvidencePackage["evidence_level"];
  features?: ClaimValidationEvidencePackage["prompt_payload"]["selected_evidence"];
} = {}): ClaimValidationEvidencePackage {
  const level = options.level ?? "S3";
  const features = options.features ?? [
    {
      feature_id: "feature_a",
      shap_value: 0.2,
      abs_shap_value: 0.2,
      direction: "increases_risk",
      rank: 1,
    },
    {
      feature_id: "feature_b",
      shap_value: -0.1,
      abs_shap_value: 0.1,
      direction: "decreases_risk",
      rank: 2,
    },
  ];
  return {
    package_id: "package_001",
    source_ir_id: "ir_001",
    source_evidence_id: "evidence_001",
    evidence_level: level,
    prompt_payload: {
      evidence_level: level,
      prediction: {
        predicted_label: "high_default_risk",
        probability: 0.9334,
        threshold: 0.5,
        probability_display: "0.9334",
        probability_percent_display: "93.34%",
        threshold_display: "0.5000",
        threshold_percent_display: "50.00%",
        threshold_comparison: "above_or_equal_threshold",
        is_above_threshold: true,
      },
      selected_evidence: features,
      concept_evidence: [
        {
          concept: "concept_a",
          direction: "increases_risk",
          selected_abs_shap_sum: 0.3,
          feature_count: 2,
          representative_feature: {
            feature_id: "feature_a",
            shap_value: 0.2,
            abs_shap_value: 0.2,
            direction: "increases_risk",
            rank: 1,
          },
          supporting_features: features,
          selected_feature_ids: features.map((item) => item.feature_id),
        },
      ],
      selection_context: {
        selected_evidence_count: features.length,
        concept_group_count: 1,
        mixed_concept_group_count: 0,
      },
      narrative_policy: { must_include_uncertainty: true },
      constraints: {
        allowed_feature_ids: features
          .map((item) => item.feature_id)
          .filter((value): value is string => Boolean(value)),
        allowed_concept_ids: ["concept_a"],
        forbidden_rule_ids: ["forbid_real_world_causality"],
        claim_policy: {
          allow_prediction_claim: true,
          allow_feature_claim: true,
          allow_concept_claim: true,
          allow_direction_claim: true,
          allow_causal_claim: false,
          allow_financial_advice: false,
        },
      },
    },
  };
}

function generation(): ClaimValidationGenerationRow {
  return {
    canonical_schema_version: "generation_index_v1",
    generation_id: "generation_001",
    model_id: "model_001",
    case_id: "case_001",
    source_ir_id: "ir_001",
    evidence_level: "S3",
    repeat_id: 1,
    package_id: "package_001",
    source_evidence_id: "evidence_001",
    runtime_status: "SUCCESS",
    finish_reason: "stop",
    truncated_response: false,
    raw_json_parse_success: true,
    schema_valid: true,
    usable: true,
    usability_reason_codes: [],
    generation_record: {
      generation_id: "generation_001",
      package_id: "package_001",
      source_ir_id: "ir_001",
      source_evidence_id: "evidence_001",
      evidence_level: "S3",
      model_id: "model_001",
      repeat_id: 1,
    },
  };
}

function provenance() {
  return {
    claimsInputPath: "data/claims.jsonl",
    claimsInputSha256: "8".repeat(64),
    generationIndexPath: "data/generations.jsonl",
    generationIndexSha256: "9".repeat(64),
    evidencePackagesPath: "data/evidence.jsonl",
    evidencePackagesSha256: "a".repeat(64),
  };
}
