import { EXPLANATION_JSON_SCHEMA } from "./outputSchema";
import type {
  BackendExplanationSkeleton,
  ConceptEvidenceItem,
  EvidenceItem,
  EvidencePackage,
  ModelConfig,
  PromptBuildResult,
  PromptMessage,
  PromptSectionFlags,
} from "../../types/types";
import { sha256, stableStringify } from "../../utils/llmNarrative/utils";

export function buildPrompt(
  packageItem: EvidencePackage,
  model: ModelConfig,
  promptVersion: string,
): PromptBuildResult {
  const payload = packageItem.prompt_payload;
  const systemMessage = buildSystemMessage();
  const userMessage = buildUserMessage(packageItem);
  const messages: PromptMessage[] = [
    {
      role: "system",
      content: systemMessage,
    },
    {
      role: "user",
      content: userMessage,
    },
  ];

  const messageText = messages
    .map((message) => `${message.role.toUpperCase()}:\n${message.content}`)
    .join("\n\n");

  const messageSha256 = sha256(stableStringify(messages));
  const promptId = `prompt_${sha256(
    [promptVersion, model.id, packageItem.package_id, messageSha256].join("|"),
  )}`;

  return {
    prompt_id: promptId,
    prompt_version: promptVersion,
    model_id: model.id,
    package_id: packageItem.package_id,
    messages,
    message_text: messageText,
    message_sha256: messageSha256,
    section_flags: buildSectionFlags(packageItem),
  };
}

function buildSystemMessage(): string {
  return [
    "Bạn là hệ thống sinh lời giải thích dự đoán rủi ro tín dụng bằng tiếng Việt.",
    "Mục tiêu quan trọng nhất là trung thực với bằng chứng được cung cấp.",
    "Chỉ sử dụng dữ liệu nằm trong prompt. Không tự bổ sung thông tin về khách hàng.",
    "Không diễn đạt SHAP như quan hệ nhân quả ngoài đời thực.",
    "Không khẳng định chắc chắn khách hàng sẽ hoặc sẽ không gặp khó khăn trả nợ.",
    "Không đưa lời khuyên tài chính cá nhân.",
    "Phải trả về đúng một JSON object hợp lệ, không Markdown, không code fence, không văn bản bên ngoài JSON.",
  ].join("\n");
}

function buildUserMessage(packageItem: EvidencePackage): string {
  const payload = packageItem.prompt_payload;
  const sections: string[] = [];

  sections.push(buildTaskSection(packageItem));
  sections.push(buildPredictionSection(packageItem));
  sections.push(buildEvidenceSection(packageItem));

  if (payload.concept_evidence.length > 0) {
    sections.push(buildConceptSection(payload.concept_evidence));
  }

  sections.push(buildSelectionContextSection(packageItem));
  sections.push(buildPolicySection(packageItem));

  if (payload.backend_explanation_skeleton) {
    sections.push(
      buildBackendSkeletonSection(payload.backend_explanation_skeleton),
    );
  }

  sections.push(buildOutputSchemaSection(packageItem));

  return sections.join("\n\n");
}

function buildTaskSection(packageItem: EvidencePackage): string {
  const level = packageItem.evidence_level;

  const descriptions: Record<string, string> = {
    S0: "Chỉ tóm tắt dự đoán. Không được nêu bất kỳ lý do feature hoặc concept cụ thể nào.",
    S1: "Giải thích bằng raw SHAP feature top-10. Giữ nguyên tên kỹ thuật khi cần tham chiếu feature.",
    S2: "Giải thích bằng cùng top-10 SHAP của S1 nhưng có semantic metadata dễ hiểu hơn.",
    S3: "Giải thích bằng tập SHAP adaptive compact và tuân thủ trạng thái coverage.",
    S4: "Giải thích bằng evidence adaptive, entropy policy và concept-direction grouping.",
    S5: "Tuân thủ backend skeleton. Không thêm factor ngoài các slot được backend cho phép.",
  };

  return [
    "## TASK",
    `Evidence level: ${level}`,
    descriptions[level],
    "Viết lời giải thích ngắn, rõ, có cấu trúc và chỉ dựa trên evidence được cung cấp.",
  ].join("\n");
}

function buildPredictionSection(packageItem: EvidencePackage): string {
  const prediction = packageItem.prompt_payload.prediction;

  return [
    "## PREDICTION",
    JSON.stringify(
      {
        predicted_class: prediction.predicted_class,
        predicted_label: prediction.predicted_label,
        probability: prediction.probability,
        probability_percent_display: prediction.probability_percent_display,
        threshold: prediction.threshold,
        threshold_percent_display: prediction.threshold_percent_display,
        threshold_comparison: prediction.threshold_comparison,
      },
      null,
      2,
    ),
  ].join("\n");
}

function buildEvidenceSection(packageItem: EvidencePackage): string {
  const payload = packageItem.prompt_payload;

  if (packageItem.evidence_level === "S0") {
    return [
      "## EVIDENCE",
      "Không có feature evidence hoặc concept evidence được cung cấp.",
      "factors trong output bắt buộc phải là mảng rỗng.",
    ].join("\n");
  }

  const evidence = payload.selected_evidence.map((item) => {
    if (packageItem.evidence_level === "S1") {
      return buildRawEvidenceView(item);
    }

    return buildSemanticEvidenceView(item);
  });

  return ["## SELECTED EVIDENCE", JSON.stringify(evidence, null, 2)].join("\n");
}

function buildRawEvidenceView(item: EvidenceItem): Record<string, unknown> {
  return {
    rank: item.rank,
    feature_id: item.feature_id,
    feature_name: item.feature_name,
    shap_value: item.shap_value,
    abs_shap_value: item.abs_shap_value,
    direction: normalizeDirection(item.direction),
  };
}

function buildSemanticEvidenceView(
  item: EvidenceItem,
): Record<string, unknown> {
  return {
    rank: item.rank,
    feature_id: item.feature_id,
    display_name: item.display_name,
    concept_id: item.concept,
    concept_display_name: item.concept_display_name,
    direction: normalizeDirection(item.direction),
    strength: item.strength,
    shap_value: item.shap_value,
    abs_shap_value: item.abs_shap_value,
    safe_phrase: item.safe_phrase,
  };
}

function buildConceptSection(concepts: ConceptEvidenceItem[]): string {
  const compactConcepts = concepts.map((concept) => ({
    concept_id: concept.concept,
    concept_display_name: concept.concept_display_name,
    direction: normalizeDirection(concept.direction),
    representative_feature_id: concept.representative_feature?.feature_id,
    representative_display_name: concept.representative_feature?.display_name,
    supporting_feature_ids: (concept.supporting_features || [])
      .map((item) => item.feature_id)
      .filter(Boolean),
    selected_feature_ids: concept.selected_feature_ids || [],
    feature_count: concept.feature_count,
    selected_abs_shap_sum: concept.selected_abs_shap_sum,
  }));

  return [
    "## CONCEPT GROUPS",
    "Mỗi group được tạo từ các feature đã chọn có cùng concept và cùng direction.",
    JSON.stringify(compactConcepts, null, 2),
  ].join("\n");
}

function buildSelectionContextSection(packageItem: EvidencePackage): string {
  const context = packageItem.prompt_payload.selection_context;

  return ["## SELECTION CONTEXT", JSON.stringify(context, null, 2)].join("\n");
}

function buildPolicySection(packageItem: EvidencePackage): string {
  const payload = packageItem.prompt_payload;
  const rules: string[] = [];
  const policy = payload.narrative_policy;
  const constraints = payload.constraints;

  rules.push("Chỉ tham chiếu feature_id nằm trong allowed_feature_ids.");
  rules.push("Chỉ tham chiếu concept_id nằm trong allowed_concept_ids.");
  rules.push(
    "Không nói feature gây ra kết quả ngoài đời; chỉ nói feature góp phần vào dự đoán của mô hình.",
  );
  rules.push("Không đảo chiều tăng/giảm rủi ro của evidence.");
  rules.push("Không đưa lời khuyên tài chính hoặc quyết định tín dụng.");

  if (policy.must_include_uncertainty) {
    rules.push("uncertainty_note bắt buộc phải có nội dung thận trọng.");
  }

  if (policy.must_include_distributed_evidence_note) {
    rules.push(
      "distributed_evidence_note bắt buộc nói rằng evidence phân tán trên nhiều tín hiệu.",
    );
  }

  if (policy.must_include_partial_evidence_note) {
    rules.push(
      "uncertainty_note phải nói đây chỉ là phần evidence nổi bật được cung cấp, không phải toàn bộ evidence.",
    );
  }

  if (policy.must_not_claim_evidence_is_complete) {
    rules.push("Không được khẳng định danh sách evidence là đầy đủ tuyệt đối.");
  }

  if (policy.avoid_single_cause_wording) {
    rules.push(
      "Tránh các cụm như nguyên nhân duy nhất, lý do duy nhất hoặc chỉ do một yếu tố.",
    );
  }

  if (!policy.allow_main_reason_wording) {
    rules.push("Không gọi một factor là nguyên nhân chính duy nhất.");
  }

  if (policy.must_not_give_specific_feature_reason) {
    rules.push("Không nêu bất kỳ feature hoặc concept cụ thể nào.");
  }

  return [
    "## CONSTRAINTS",
    ...rules.map((rule, index) => `${index + 1}. ${rule}`),
    "Allowed feature IDs:",
    JSON.stringify(constraints.allowed_feature_ids || []),
    "Allowed concept IDs:",
    JSON.stringify(constraints.allowed_concept_ids || []),
    "Forbidden rule IDs:",
    JSON.stringify(constraints.forbidden_rule_ids || []),
  ].join("\n");
}

function buildBackendSkeletonSection(
  skeleton: BackendExplanationSkeleton,
): string {
  const factorSlots = (skeleton.main_factor_slots || []).map((slot, index) => ({
    order: index + 1,
    feature_id: slot.feature_id,
    display_name: slot.display_name,
    concept_id: slot.concept,
    concept_display_name: slot.concept_display_name,
    direction: normalizeDirection(slot.direction),
    safe_phrase: slot.safe_phrase,
  }));

  return [
    "## BACKEND SKELETON",
    "Tạo factors theo đúng thứ tự dưới đây. Mỗi slot trở thành một factor role=main.",
    "Không thêm factor ngoài danh sách này.",
    JSON.stringify(
      {
        main_factor_slots: factorSlots,
        required_uncertainty_note: skeleton.required_uncertainty_note,
        must_follow_factor_order: skeleton.must_follow_factor_order,
        must_not_add_factor_outside_skeleton:
          skeleton.must_not_add_factor_outside_skeleton,
        forbidden_wording: skeleton.forbidden_wording || [],
      },
      null,
      2,
    ),
  ].join("\n");
}

function buildOutputSchemaSection(packageItem: EvidencePackage): string {
  const levelRules =
    packageItem.evidence_level === "S0"
      ? ["S0 rule: factors must be []."]
      : [
          "factor_id phải duy nhất trong output.",
          "declared_feature_ids và declared_concept_ids chỉ chứa ID được cung cấp.",
          "role chỉ nhận main hoặc supporting.",
        ];

  return [
    "## OUTPUT JSON SCHEMA",
    ...levelRules,
    "distributed_evidence_note có thể là chuỗi rỗng khi policy không yêu cầu.",
    JSON.stringify(EXPLANATION_JSON_SCHEMA, null, 2),
  ].join("\n");
}

function buildSectionFlags(packageItem: EvidencePackage): PromptSectionFlags {
  const payload = packageItem.prompt_payload;

  return {
    has_prediction_section: Boolean(payload.prediction),
    has_evidence_section:
      packageItem.evidence_level === "S0" ||
      payload.selected_evidence.length > 0,
    has_constraints_section: Boolean(payload.constraints),
    has_output_schema_section: true,
    has_entropy_policy_section:
      payload.selection_context.entropy_level !== undefined,
    has_concept_grouping_section: payload.concept_evidence.length > 0,
    has_backend_skeleton_section: Boolean(payload.backend_explanation_skeleton),
  };
}

function normalizeDirection(value: string | undefined): string {
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
