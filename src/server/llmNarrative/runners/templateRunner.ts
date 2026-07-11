import type {
  ConceptEvidenceItem,
  EvidenceItem,
  EvidencePackage,
  ExplanationFactor,
  ExplanationOutput,
  RunnerResult,
} from "../../../types/types";

export async function runTemplate(
  packageItem: EvidencePackage,
): Promise<RunnerResult> {
  const startedAt = Date.now();
  const output = buildTemplateOutput(packageItem);
  const rawOutput = JSON.stringify(output);

  return {
    status: "SUCCESS",
    raw_output: rawOutput,
    finish_reason: "stop",
    latency_ms: Date.now() - startedAt,
    retry_count: 0,
    input_token_count: null,
    output_token_count: null,
    total_token_count: null,
    provider_request_id: null,
    provider_returned_model_id: "template_baseline",
    provider_api_cost_usd: 0,
    error_type: null,
    error_message: null,
  };
}

function buildTemplateOutput(packageItem: EvidencePackage): ExplanationOutput {
  const payload = packageItem.prompt_payload;
  const predictionText = buildPredictionText(packageItem);

  if (packageItem.evidence_level === "S0") {
    return {
      prediction_summary: predictionText,
      factors: [],
      uncertainty_note:
        "Đây là dự đoán của mô hình và không phải kết luận chắc chắn về khách hàng.",
      distributed_evidence_note: "",
      safe_summary:
        "Không có bằng chứng feature cụ thể được cung cấp nên hệ thống không nêu nguyên nhân cho dự đoán.",
    };
  }

  let factors: ExplanationFactor[] = [];

  if (packageItem.evidence_level === "S4") {
    factors = buildConceptFactors(payload.concept_evidence);
  } else if (packageItem.evidence_level === "S5") {
    factors = buildSkeletonFactors(packageItem);
  } else {
    factors = buildFeatureFactors(payload.selected_evidence);
  }

  const uncertaintyParts = [
    "Các yếu tố trên chỉ mô tả đóng góp vào dự đoán của mô hình, không khẳng định quan hệ nhân quả ngoài đời thực.",
  ];

  if (payload.narrative_policy.must_include_partial_evidence_note) {
    uncertaintyParts.push(
      "Đây chỉ là phần bằng chứng nổi bật được cung cấp, không phải toàn bộ tín hiệu của mô hình.",
    );
  }

  const distributedNote = payload.narrative_policy
    .must_include_distributed_evidence_note
    ? "Đóng góp được phân tán trên nhiều tín hiệu nên không nên quy dự đoán cho một nguyên nhân duy nhất."
    : "";

  return {
    prediction_summary: predictionText,
    factors,
    uncertainty_note: uncertaintyParts.join(" "),
    distributed_evidence_note: distributedNote,
    safe_summary: buildSafeSummary(packageItem, factors),
  };
}

function buildPredictionText(packageItem: EvidencePackage): string {
  const prediction = packageItem.prompt_payload.prediction;
  const probability =
    prediction.probability_percent_display ||
    (typeof prediction.probability === "number"
      ? `${(prediction.probability * 100).toFixed(2)}%`
      : "không xác định");

  return `Mô hình dự đoán nhãn ${prediction.predicted_label || "không xác định"} với xác suất ${probability}.`;
}

function buildFeatureFactors(evidence: EvidenceItem[]): ExplanationFactor[] {
  const selected = evidence.slice(0, Math.min(5, evidence.length));

  return selected.map((item, index) => ({
    factor_id: `factor_${index + 1}`,
    role: index < 3 ? "main" : "supporting",
    factor_name:
      item.display_name ||
      item.feature_name ||
      item.feature_id ||
      `factor ${index + 1}`,
    declared_feature_ids: item.feature_id ? [item.feature_id] : [],
    declared_concept_ids: item.concept ? [item.concept] : [],
    direction: normalizeDirection(item.direction),
    explanation: item.safe_phrase || buildEvidenceSentence(item),
  }));
}

function buildConceptFactors(
  concepts: ConceptEvidenceItem[],
): ExplanationFactor[] {
  const selected = concepts.slice(0, Math.min(5, concepts.length));

  return selected.map((concept, index) => ({
    factor_id: `factor_${index + 1}`,
    role: index < 3 ? "main" : "supporting",
    factor_name:
      concept.concept_display_name || concept.concept || `concept ${index + 1}`,
    declared_feature_ids: concept.selected_feature_ids || [],
    declared_concept_ids: concept.concept ? [concept.concept] : [],
    direction: normalizeDirection(concept.direction),
    explanation: buildConceptSentence(concept),
  }));
}

function buildSkeletonFactors(
  packageItem: EvidencePackage,
): ExplanationFactor[] {
  const slots =
    packageItem.prompt_payload.backend_explanation_skeleton
      ?.main_factor_slots || [];

  return slots.map((slot, index) => ({
    factor_id: `factor_${index + 1}`,
    role: "main",
    factor_name: slot.display_name || slot.feature_id || `factor ${index + 1}`,
    declared_feature_ids: slot.feature_id ? [slot.feature_id] : [],
    declared_concept_ids: slot.concept ? [slot.concept] : [],
    direction: normalizeDirection(slot.direction),
    explanation:
      slot.safe_phrase ||
      `${slot.display_name || slot.feature_id} có đóng góp vào dự đoán của mô hình.`,
  }));
}

function buildEvidenceSentence(item: EvidenceItem): string {
  const name =
    item.display_name || item.feature_name || item.feature_id || "Tín hiệu này";
  const direction = normalizeDirection(item.direction);

  if (direction === "increase_risk") {
    return `${name} góp phần làm tăng rủi ro dự đoán của mô hình.`;
  }

  if (direction === "decrease_risk") {
    return `${name} góp phần làm giảm rủi ro dự đoán của mô hình.`;
  }

  return `${name} có đóng góp vào dự đoán của mô hình.`;
}

function buildConceptSentence(concept: ConceptEvidenceItem): string {
  const name =
    concept.concept_display_name || concept.concept || "Nhóm tín hiệu này";
  const direction = normalizeDirection(concept.direction);

  if (direction === "increase_risk") {
    return `Nhóm ${name} gồm các tín hiệu được chọn và có tổng đóng góp theo hướng làm tăng rủi ro dự đoán.`;
  }

  if (direction === "decrease_risk") {
    return `Nhóm ${name} gồm các tín hiệu được chọn và có tổng đóng góp theo hướng làm giảm rủi ro dự đoán.`;
  }

  return `Nhóm ${name} chứa các tín hiệu có chiều đóng góp khác nhau trong dự đoán.`;
}

function buildSafeSummary(
  packageItem: EvidencePackage,
  factors: ExplanationFactor[],
): string {
  if (factors.length === 0) {
    return "Chỉ có thể tóm tắt kết quả dự đoán vì không có evidence cụ thể được cung cấp.";
  }

  const policy = packageItem.prompt_payload.narrative_policy;
  if (policy.avoid_single_cause_wording) {
    return "Dự đoán được hỗ trợ bởi nhiều tín hiệu đã cung cấp và không nên được hiểu là do một nguyên nhân duy nhất.";
  }

  return "Các factor trên là những tín hiệu nổi bật trong evidence được cung cấp cho lời giải thích.";
}

function normalizeDirection(
  value: string | undefined,
): "increase_risk" | "decrease_risk" | "mixed" | "unknown" {
  if (value === "increases_risk" || value === "increase_risk") {
    return "increase_risk";
  }

  if (value === "decreases_risk" || value === "decrease_risk") {
    return "decrease_risk";
  }

  if (value === "mixed") {
    return "mixed";
  }

  return "unknown";
}
