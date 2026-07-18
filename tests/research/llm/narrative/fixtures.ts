import type {
  EvidenceLevel,
  EvidencePackage,
  RunOptions,
} from "../../../../research/llm/narrative/index";

const BASE_LEVELS: EvidenceLevel[] = ["S0", "S1", "S2", "S3", "S4", "S5"];

export function createEvidencePackage(level: EvidenceLevel): EvidencePackage {
  const selectedEvidence =
    level === "S0"
      ? []
      : [
          {
            rank: 1,
            feature_id: "feature_income",
            feature_name: "AMT_INCOME_TOTAL",
            display_name: "Thu nhập khai báo",
            concept: "income",
            concept_display_name: "Thu nhập",
            shap_value: 0.42,
            abs_shap_value: 0.42,
            direction: "increases_risk",
            strength: "high",
            safe_phrase:
              "Thu nhập khai báo góp phần làm tăng rủi ro dự đoán của mô hình.",
          },
        ];

  const conceptEvidence =
    level === "S4"
      ? [
          {
            concept: "income",
            concept_display_name: "Thu nhập",
            direction: "increases_risk",
            representative_feature: selectedEvidence[0],
            supporting_features: [],
            selected_feature_ids: ["feature_income"],
            feature_count: 1,
            selected_abs_shap_sum: 0.42,
          },
        ]
      : [];

  const backendSkeleton =
    level === "S5"
      ? {
          main_factor_slots: [
            {
              feature_id: "feature_income",
              display_name: "Thu nhập khai báo",
              concept: "income",
              concept_display_name: "Thu nhập",
              direction: "increases_risk",
              rank: 1,
              safe_phrase:
                "Thu nhập khai báo góp phần làm tăng rủi ro dự đoán của mô hình.",
            },
          ],
          required_uncertainty_note: true,
          must_follow_factor_order: true,
          must_not_add_factor_outside_skeleton: true,
          forbidden_wording: ["nguyên nhân duy nhất"],
        }
      : undefined;

  return {
    package_id: `pkg_${level}_ir_fixture_001`,
    source_ir_id: "ir_fixture_001",
    source_evidence_id: `evidence_${level}_fixture_001`,
    evidence_level: level,
    prompt_payload: {
      evidence_level: level,
      prediction: {
        predicted_class: 1,
        predicted_label: "rủi ro cao",
        probability: 0.64,
        probability_percent_display: "64.00%",
        threshold: 0.5,
        threshold_percent_display: "50.00%",
        threshold_comparison: "above",
      },
      selected_evidence: selectedEvidence,
      concept_evidence: conceptEvidence,
      selection_context: {
        selected_evidence_count: selectedEvidence.length,
        coverage: level === "S0" ? 0 : 0.82,
        coverage_threshold: 0.8,
        coverage_status: level === "S0" ? "not_applicable" : "passed",
        adaptive_k: selectedEvidence.length,
        entropy_level: level === "S4" ? "medium" : undefined,
        normalized_entropy: level === "S4" ? 0.51 : undefined,
        concept_group_count: conceptEvidence.length,
        mixed_concept_group_count: 0,
      },
      narrative_policy: {
        must_include_uncertainty: true,
        avoid_single_cause_wording: true,
        allow_main_reason_wording: false,
        must_include_distributed_evidence_note: level !== "S0",
        must_not_give_specific_feature_reason: level === "S0",
        must_include_partial_evidence_note: level === "S3" || level === "S4",
        must_not_claim_evidence_is_complete: true,
      },
      constraints: {
        allowed_feature_ids: selectedEvidence.map((item) => item.feature_id as string),
        allowed_concept_ids: conceptEvidence.map((item) => item.concept as string),
        forbidden_rule_ids: ["NO_CAUSAL_CLAIM"],
      },
      backend_explanation_skeleton: backendSkeleton,
    },
  };
}

export function createEvidencePackages(): EvidencePackage[] {
  return BASE_LEVELS.map(createEvidencePackage);
}

export function createTemplateRunOptions(
  inputPath: string,
  outputDir: string,
): RunOptions {
  return {
    input_path: inputPath,
    output_dir: outputDir,
    run_id: "run_template_fixture",
    model_ids: ["template_baseline"],
    levels: [...BASE_LEVELS],
    repeat_ids: [1],
    decoding: {
      temperature: 0.2,
      top_p: 1,
      max_tokens: 2000,
      frequency_penalty: 0,
      presence_penalty: 0,
    },
    prompt_version: "prompt_v1",
    output_schema_version: "1.0",
    experiment_stage: "development",
    chunk_start: 0,
    concurrency: 2,
    checkpoint_every: 2,
    timeout_ms: 1_000,
    max_retries: 0,
    retry_delay_ms: 0,
    base_seed: 20260710,
    resume: false,
  };
}
