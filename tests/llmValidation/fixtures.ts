import type {
  CanonicalGenerationRow,
  EvidencePackageRecord,
  EvidenceLevel,
  JsonObject,
} from "../../src/types/llm-validation";

export function canonicalRow(input: {
  evidenceLevel?: EvidenceLevel;
  usable?: boolean;
  parsedOutput?: JsonObject | null;
  generationId?: string;
  modelId?: string;
} = {}): CanonicalGenerationRow {
  const evidenceLevel = input.evidenceLevel ?? "S5";
  const usable = input.usable ?? true;
  const parsedOutput =
    input.parsedOutput === undefined ? defaultParsedOutput() : input.parsedOutput;
  const modelId = input.modelId ?? "qwen3_8b";
  const generationId = input.generationId ?? `${modelId}_case_1_${evidenceLevel}`;

  return {
    canonical_schema_version: "generation_index_v1",
    canonical_key: `${modelId}::r1::ir_case_1::${evidenceLevel}`,
    cohort_key: `ir_case_1::${evidenceLevel}`,
    matrix_role: "main",
    model_order: 1,
    case_order: 1,
    evidence_level_order: Number(evidenceLevel.slice(1)),
    is_baseline: false,
    eligible_for_selection: evidenceLevel !== "S0",
    generation_id: generationId,
    run_id: "run_1",
    experiment_stage: "evaluation",
    model_id: modelId,
    model_revision: "revision_1",
    revision_status: "pinned",
    case_id: "case_1",
    source_ir_id: "ir_case_1",
    evidence_level: evidenceLevel,
    repeat_id: 1,
    package_id: `pkg_${evidenceLevel}_ir_case_1`,
    source_evidence_id: "evidence_case_1",
    prompt_id: "prompt_1",
    prompt_version: "prompt_v1",
    output_schema_version: "1.0",
    input_package_sha256: "a".repeat(64),
    input_package_hash_verified: true,
    prompt_message_sha256: "b".repeat(64),
    prompt_hash_verified: true,
    runtime_status: usable ? "SUCCESS" : "FAILED",
    finish_reason: usable ? "stop" : "length",
    truncated_response: !usable,
    raw_json_parse_success: usable,
    schema_valid: usable,
    usable,
    usability_reason_codes: usable ? [] : ["truncated_response"],
    source_generation_path: "/tmp/generations.jsonl",
    source_generation_file_sha256: "c".repeat(64),
    source_generation_line: 1,
    source_prompt_path: "/tmp/prompts.jsonl",
    source_prompt_file_sha256: "d".repeat(64),
    source_prompt_line: 1,
    generation_record: {
      generation_id: generationId,
      run_id: "run_1",
      experiment_stage: "evaluation",
      package_id: `pkg_${evidenceLevel}_ir_case_1`,
      source_ir_id: "ir_case_1",
      source_evidence_id: "evidence_case_1",
      evidence_level: evidenceLevel,
      model_id: modelId,
      model_revision: "revision_1",
      prompt_version: "prompt_v1",
      output_schema_version: "1.0",
      repeat_id: 1,
      input_package_sha256: "a".repeat(64),
      prompt_id: "prompt_1",
      prompt_message_sha256: "b".repeat(64),
      runtime_metrics: {
        status: usable ? "SUCCESS" : "FAILED",
        finish_reason: usable ? "stop" : "length",
        retry_count: 0,
        empty_response: false,
        truncated_response: !usable,
      },
      schema_metrics: {
        raw_json_parse_success: usable,
        json_parse_success: usable,
        schema_valid: usable,
      },
      parsed_output: parsedOutput,
      content_metrics: { too_short: false, too_long: false },
      evidence_mention_metrics: {
        selected_feature_mention_rate: 1,
        top1_mention_rate: 1,
        top3_mention_rate: 1,
        top5_mention_rate: 1,
        concept_mention_rate: 1,
      },
    },
  };
}

export function evidencePackage(
  evidenceLevel: EvidenceLevel = "S5",
): EvidencePackageRecord {
  return {
    package_id: `pkg_${evidenceLevel}_ir_case_1`,
    source_ir_id: "ir_case_1",
    source_evidence_id: "evidence_case_1",
    evidence_level: evidenceLevel,
    constraints: {
      allowed_feature_ids: ["feature_a", "feature_b"],
      allowed_concept_ids: ["concept_a", "concept_b"],
    },
    prompt_payload: {
      backend_explanation_skeleton:
        evidenceLevel === "S5"
          ? {
              main_factor_slots: [
                { feature_id: "feature_a" },
                { feature_id: "feature_b" },
              ],
            }
          : null,
    },
  };
}

export function defaultParsedOutput(): JsonObject {
  return {
    prediction_summary: "Mô hình dự đoán mức rủi ro cao.",
    factors: [
      {
        factor_id: "factor_1",
        role: "main",
        factor_name: "Tín hiệu A",
        declared_feature_ids: ["feature_a"],
        declared_concept_ids: ["concept_a"],
        direction: "increase_risk",
        explanation: "Tín hiệu A góp phần làm tăng rủi ro dự đoán của mô hình.",
      },
      {
        factor_id: "factor_2",
        role: "main",
        factor_name: "Tín hiệu B",
        declared_feature_ids: ["feature_b"],
        declared_concept_ids: ["concept_b"],
        direction: "decrease_risk",
        explanation: "Tín hiệu B góp phần làm giảm rủi ro dự đoán của mô hình.",
      },
    ],
    uncertainty_note: "Đây là dự đoán của mô hình, không phải kết luận chắc chắn.",
    distributed_evidence_note: "Bằng chứng có nhiều chiều khác nhau.",
    safe_summary: "Các yếu tố chỉ mô tả đóng góp trong mô hình.",
  };
}

