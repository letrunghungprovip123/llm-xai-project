// src/server/llm/prompt-builder.ts

import type {
  BuiltPrompt,
  ContributionStrength,
  DisplayPolicy,
  ExplanationIrRecord,
  IrPredictionSummary,
  LlmAllowedTerm,
  LlmContractFeatureFactor,
  LlmInputContract,
  LlmSupportingFeatureGroup,
  RegenerationFeedback,
  RiskDirection,
} from "./explanation-schema";

import {
  asArray,
  asRecord,
  getCustomerId,
  pickBoolean,
  pickNumber,
  pickString,
} from "./explanation-schema";

/**
 * Batch I v1.2 - Compact Prompt Builder with Optional Validation Feedback
 *
 * Goal:
 * Build a compact but faithful LLM prompt.
 *
 * Design:
 * - Do NOT send a template full_text.
 * - Do NOT send all long rule/claim arrays.
 * - Do NOT send all 213 feature details.
 * - Send only selected evidence needed for natural explanation.
 * - Optionally receive Batch J feedback for controlled regeneration.
 *
 * Faithfulness is protected by:
 * - selected evidence from Batch H
 * - explicit facts/directions/contributions
 * - display_policy
 * - optional validator feedback from Batch J
 * - later Batch J validator
 */

export const PROMPT_VERSION = "batch_i_llm_prompt_v1.2_compact_feedback_ready";

const MAX_PRIMARY_FEATURES = 6;
const MAX_SUPPORTING_GROUPS = 4;
const MAX_RISK_REDUCING_FEATURES = 4;
const MAX_ALLOWED_TERMS = 16;

type SafePrediction = {
  predicted_label: string;
  probability_percent_display: string;
  threshold_percent_display: string;
  threshold_comparison: string;
};

type SafeContributionAccounting = {
  total_feature_count?: number;
  base_value_display?: string;
  model_output_display?: string;
  all_feature_sum_display?: string;
  primary_feature_count?: number;
  supporting_feature_count?: number;
  remaining_feature_count?: number;
  hidden_or_nonclaimable_feature_count?: number;
  explained_abs_coverage_percent?: number;
};

type SafeFeature = {
  id: string;
  mention: string;
  concept: string;
  direction: RiskDirection;
  contribution: string;
  strength: ContributionStrength;
  display_policy: DisplayPolicy;
  note?: string;

  /**
   * Unique label for categorical/one-hot features.
   * Prefer this when display_name is too generic.
   * Example: "loại thu nhập = Working"
   */
  unique_label?: string;
};

type SafeSupportingGroup = {
  id: string;
  concept_id: string;
  name: string;
  feature_count?: number;
  direction: RiskDirection;
  contribution?: string;
};

type SafeTerm = {
  term_id: string;
  term_type: string;
  mention: string;
};

type CompactPromptContract = {
  task: string;
  language: "vi";
  audience: string;
  source_ir_id: string;
  customer_id: string;
  prediction: SafePrediction;
  accounting: SafeContributionAccounting;
  primary_features: SafeFeature[];
  supporting_groups: SafeSupportingGroup[];
  risk_reducing_features: SafeFeature[];
  remaining_summary: {
    count?: number;
    note: string;
  };
  allowed_terms: SafeTerm[];
  output_shape: {
    language: "vi";
    sections: [
      "prediction",
      "contribution_overview",
      "main_risk_drivers",
      "supporting_evidence_groups",
      "risk_reducing_factors",
      "limitations",
    ];
    include_usage_metadata: true;
    no_full_text: true;
  };
};

export function buildExplanationPrompt(
  irRecord: ExplanationIrRecord,
  feedback: RegenerationFeedback | null = null,
): BuiltPrompt {
  const contract = getLlmInputContractOrThrow(irRecord);
  const compactContract = buildCompactPromptContract(irRecord, contract);

  return {
    system: buildSystemPrompt(),
    user: buildUserPrompt(compactContract, feedback),
    promptVersion: feedback
      ? `${PROMPT_VERSION}_with_feedback`
      : PROMPT_VERSION,
  };
}

function getLlmInputContractOrThrow(
  irRecord: ExplanationIrRecord,
): LlmInputContract {
  const contract = irRecord.llm_input_contract;

  if (!contract || typeof contract !== "object") {
    throw new Error(
      `IR record ${irRecord.ir_id} does not contain llm_input_contract.`,
    );
  }

  return contract;
}

function buildCompactPromptContract(
  irRecord: ExplanationIrRecord,
  contract: LlmInputContract,
): CompactPromptContract {
  const featureTiers = asRecord(
    contract.feature_tiers ?? contract.featureTiers,
  );

  const primaryRaw =
    contract.primary_features ??
    contract.primaryFeatures ??
    asArray<LlmContractFeatureFactor>(featureTiers.primary_features) ??
    contract.main_risk_increasing_factors ??
    contract.mainRiskIncreasingFactors ??
    [];

  const riskReducingRaw =
    asArray<LlmContractFeatureFactor>(featureTiers.risk_reducing_features)
      .length > 0
      ? asArray<LlmContractFeatureFactor>(featureTiers.risk_reducing_features)
      : [
          ...asArray<LlmContractFeatureFactor>(primaryRaw).filter(
            (item) => asRecord(item).direction === "decreases_risk",
          ),
          ...asArray<LlmContractFeatureFactor>(
            contract.main_risk_decreasing_factors ??
              contract.mainRiskDecreasingFactors,
          ),
        ];

  const supportingGroupsRaw =
    contract.supporting_feature_groups ??
    contract.supportingFeatureGroups ??
    [];

  const primaryFeatures = asArray<LlmContractFeatureFactor>(primaryRaw)
    .map(normalizeFeature)
    .filter((item) => item.display_policy !== "hidden")
    .filter((item) => item.direction === "increases_risk")
    .slice(0, MAX_PRIMARY_FEATURES);

  const riskReducingFeatures = asArray<LlmContractFeatureFactor>(
    riskReducingRaw,
  )
    .map(normalizeFeature)
    .filter((item) => item.display_policy !== "hidden")
    .filter((item) => item.direction === "decreases_risk")
    .slice(0, MAX_RISK_REDUCING_FEATURES);

  const supportingGroups = asArray<LlmSupportingFeatureGroup>(
    supportingGroupsRaw,
  )
    .map(normalizeSupportingGroup)
    .filter((item) => item.id !== "unknown_group")
    .slice(0, MAX_SUPPORTING_GROUPS);

  const allowedTerms = buildCompactAllowedTerms({
    terms: contract.allowed_terms ?? contract.allowedTerms ?? [],
    primaryFeatures,
    riskReducingFeatures,
    supportingGroups,
  });

  const remainingSummary = normalizeRemainingSummary(
    asRecord(
      contract.remaining_features_summary ?? contract.remainingFeaturesSummary,
    ),
  );

  return {
    task: "Write a natural Vietnamese explanation from selected XAI evidence. Facts are fixed; wording is flexible.",
    language: "vi",
    audience: String(contract.audience ?? "credit_risk_reviewer"),
    source_ir_id: irRecord.ir_id,
    customer_id: getCustomerId(irRecord.customer),
    prediction: normalizePrediction(
      contract.prediction ?? irRecord.prediction_summary,
    ),
    accounting: normalizeContributionAccounting(
      asRecord(
        contract.contribution_accounting ?? contract.contributionAccounting,
      ),
    ),
    primary_features: primaryFeatures,
    supporting_groups: supportingGroups,
    risk_reducing_features: riskReducingFeatures,
    remaining_summary: remainingSummary,
    allowed_terms: allowedTerms,
    output_shape: {
      language: "vi",
      sections: [
        "prediction",
        "contribution_overview",
        "main_risk_drivers",
        "supporting_evidence_groups",
        "risk_reducing_factors",
        "limitations",
      ],
      include_usage_metadata: true,
      no_full_text: true,
    },
  };
}

function buildSystemPrompt(): string {
  return [
    "Bạn là AI viết diễn giải cho hệ thống Machine Learning có khả năng giải thích.",
    "Viết tiếng Việt tự nhiên, mạch lạc, giống người phân tích rủi ro đang giải thích cho người đọc.",
    "",
    "Bạn KHÔNG phải máy chép contract.",
    "Bạn ĐƯỢC sáng tạo trong cách diễn đạt, nối câu, giảm lặp từ và làm đoạn văn dễ đọc.",
    "Nhưng bạn KHÔNG được sáng tạo dữ kiện.",
    "",
    "Ranh giới:",
    "- Được sáng tạo cách nói.",
    "- Không được sáng tạo facts.",
    "",
    "Quy tắc bắt buộc:",
    "1. Chỉ dùng evidence trong JSON contract.",
    "2. Không thêm feature, concept, số liệu, nguyên nhân hoặc khuyến nghị mới.",
    "3. Không đổi xác suất, ngưỡng, contribution hoặc direction.",
    "4. Không nói quan hệ nhân quả ngoài thực tế.",
    "5. Không nói khách hàng chắc chắn sẽ hoặc không sẽ gặp khó khăn thanh toán.",
    "6. Tránh từ 'vỡ nợ'; dùng 'rủi ro gặp khó khăn trong thanh toán'.",
    "7. Không nhắc TARGET, true label, true positive, false positive, false negative.",
    "8. Không dùng raw snake_case hoặc tên feature kỹ thuật.",
    "9. Nếu display_policy là concept_level_only thì chỉ nói ở cấp nhóm.",
    "10. Không nói các yếu tố còn lại là 'không đáng kể' trừ khi contract nói rõ.",
    "11. Với remaining features, chỉ nói chúng vẫn được tính nhưng không trình bày chi tiết.",
    "12. Không trả full_text; server sẽ tự ghép full_text từ sections.",
    "13. Chỉ trả JSON hợp lệ, không markdown, không text ngoài JSON.",
    "14. sections.limitations bắt buộc phải nêu đủ: explanation chỉ mô tả đóng góp vào dự đoán của mô hình, không chứng minh quan hệ nhân quả ngoài thực tế, không phải quyết định tín dụng cuối cùng, và không phải kết luận chắc chắn.",
    "15. Khi nói về all_feature_sum_display hoặc tổng mức tăng/giảm xác suất, phải nói đó là tổng đóng góp của toàn bộ các yếu tố được mô hình tính, không được nói là chỉ của các yếu tố chính/hỗ trợ.",
    "16. Với các case xác suất rất sát threshold, phải nói 'rất sát ngưỡng' và nêu rõ thấp hơn/cao hơn ngưỡng một lượng rất nhỏ; không chỉ nói 'ngang bằng'.",
    "17. Không được dùng cụm raw English technical như 'previous credit to application ratio'; nếu gặp feature khó diễn đạt, hãy dùng 'một tín hiệu thuộc nhóm ...'.",
    "18. Nếu feedback từ validator được cung cấp, phải sửa đúng các lỗi được nêu trong feedback.",
    "19. Không được lặp lại claim đã bị validator đánh dấu FAIL.",
    "20. Nếu một feature là one-hot/categorical hoặc có tên hiển thị mơ hồ, phải nêu rõ category hoặc unique_label nếu được cung cấp.",
    "21. Không được viết tên feature chung chung nếu nhiều feature có cùng display_name nhưng khác direction.",
    "22. Ví dụ sai: 'Loại thu nhập (-0.38 điểm phần trăm)'. Ví dụ đúng: 'Loại thu nhập = Working làm giảm rủi ro khoảng -0.38 điểm phần trăm'.",
    "",
    "Độ dài:",
    "- Mỗi section 1 đến 3 câu.",
    "- Ưu tiên rõ ràng, tự nhiên, không liệt kê quá dài.",
  ].join("\n");
}

function buildUserPrompt(
  contract: CompactPromptContract,
  feedback: RegenerationFeedback | null,
): string {
  return [
    "Hãy viết explanation tiếng Việt tự nhiên từ JSON contract bên dưới.",
    "",
    "Output JSON bắt buộc:",
    "{",
    '  "language": "vi",',
    '  "sections": {',
    '    "prediction": "string",',
    '    "contribution_overview": "string",',
    '    "main_risk_drivers": "string",',
    '    "supporting_evidence_groups": "string",',
    '    "risk_reducing_factors": "string",',
    '    "limitations": "string"',
    "  },",
    '  "referenced_terms": [{"term_id":"string","term_type":"feature|concept","mention":"string"}],',
    '  "evidence_items_used": [{"evidence_id":"string","evidence_type":"feature|concept","direction":"string","usage":"primary|supporting|risk_reducing"}],',
    '  "evidence_groups_used": [{"group_id":"string","concept_id":"string|null","usage":"supporting_group|remaining_summary"}]',
    "}",
    "",
    "Không trả full_text.",
    "Không markdown.",
    "Không bọc JSON trong ```.",
    "",
    "Viết tự nhiên, không máy móc. Có thể gộp ý và nối câu mượt, nhưng không được đổi facts.",
    "",
    buildFeedbackPromptBlock(feedback),
    "",
    "Trong contribution_overview, nếu nói tổng +/− điểm phần trăm, hãy nói đó là tổng đóng góp của toàn bộ feature được mô hình tính.",
    "Với categorical/one-hot feature, nếu contract có unique_label thì ưu tiên dùng unique_label thay vì mention chung.",
    "Không được dùng display_name mơ hồ nếu có thể gây hiểu nhầm direction/contribution.",
    "Trong limitations, bắt buộc nhắc đủ 4 ý: chỉ mô tả đóng góp vào dự đoán, không chứng minh nhân quả, không phải quyết định tín dụng cuối cùng, không phải kết luận chắc chắn.",
    "Không dùng raw English technical feature phrase. Nếu feature name khó diễn giải, dùng concept-level phrase.",
    "Với probability sát threshold, diễn đạt là 'rất sát ngưỡng', không làm người đọc hiểu sai rằng chắc chắn cao/thấp rõ ràng.",
    "",
    "JSON contract:",
    JSON.stringify(contract),
  ].join("\n");
}

function buildFeedbackPromptBlock(
  feedback: RegenerationFeedback | null,
): string {
  if (!feedback) {
    return [
      "VALIDATION FEEDBACK:",
      "- No previous validation feedback.",
      "- This is the first generation attempt.",
    ].join("\n");
  }

  const issues = feedback.issues
    .slice(0, 8)
    .map((issue, index) =>
      [
        `${index + 1}. ${issue.failure_type}`,
        `   Failed claim: ${issue.claim_text}`,
        `   Reason: ${issue.reason}`,
        `   Repair instruction: ${issue.repair_instruction}`,
      ].join("\n"),
    )
    .join("\n");

  const globalInstructions = feedback.global_repair_instructions
    .slice(0, 8)
    .map((item) => `- ${item}`)
    .join("\n");

  return [
    "VALIDATION FEEDBACK FROM BATCH J:",
    `- Feedback ID: ${feedback.feedback_id}`,
    `- Previous explanation ID: ${feedback.explanation_id ?? "unknown"}`,
    `- Attempt: ${feedback.attempt}`,
    `- Status: ${feedback.status}`,
    "",
    "Failed/warning issues to fix:",
    issues || "- No detailed issues provided.",
    "",
    "Global repair instructions:",
    globalInstructions || "- Follow the IR strictly.",
    "",
    "You must regenerate the explanation so that these validator issues are fixed.",
  ].join("\n");
}

function normalizePrediction(
  prediction: IrPredictionSummary | undefined,
): SafePrediction {
  const obj = asRecord(prediction);

  const probability = pickNumber(
    obj,
    ["probability", "predicted_probability", "predictedProbability"],
    0,
  );

  const threshold = pickNumber(obj, ["threshold"], 0.5);

  return {
    predicted_label: pickString(
      obj,
      ["predicted_label", "predictedLabel"],
      "unknown",
    ),
    probability_percent_display:
      pickString(obj, ["probability_percent_display"]) ||
      `${(probability * 100).toFixed(2)}%`,
    threshold_percent_display:
      pickString(obj, ["threshold_percent_display"]) ||
      `${(threshold * 100).toFixed(2)}%`,
    threshold_comparison: pickString(
      obj,
      ["threshold_comparison", "thresholdComparison"],
      "unknown",
    ),
  };
}

function normalizeContributionAccounting(
  accounting: Record<string, unknown>,
): SafeContributionAccounting {
  return {
    total_feature_count: optionalNumber(accounting, ["total_feature_count"]),
    base_value_display: pickString(accounting, ["base_value_display"]),
    model_output_display: pickString(accounting, ["model_output_display"]),
    all_feature_sum_display: pickString(accounting, [
      "all_feature_sum_display",
    ]),
    primary_feature_count: optionalNumber(accounting, [
      "primary_feature_count",
    ]),
    supporting_feature_count: optionalNumber(accounting, [
      "supporting_feature_count",
    ]),
    remaining_feature_count: optionalNumber(accounting, [
      "remaining_feature_count",
    ]),
    hidden_or_nonclaimable_feature_count: optionalNumber(accounting, [
      "hidden_or_nonclaimable_feature_count",
    ]),
    explained_abs_coverage_percent: optionalNumber(accounting, [
      "explained_abs_coverage_percent",
    ]),
  };
}

function normalizeFeature(item: LlmContractFeatureFactor): SafeFeature {
  const obj = asRecord(item);

  const id = pickString(
    obj,
    [
      "feature_name",
      "featureName",
      "feature_id",
      "featureId",
      "factor_id",
      "factorId",
    ],
    "unknown_feature",
  );

  const displayName = pickString(obj, ["display_name", "displayName"], id);

  const categoryValue = pickString(obj, [
    "category_value",
    "categoryValue",
    "category",
    "value_display",
    "valueDisplay",
    "formatted_value",
    "formattedValue",
  ]);

  const uniqueLabel =
    pickString(obj, [
      "feature_label_unique",
      "featureLabelUnique",
      "unique_label",
      "uniqueLabel",
    ]) || buildUniqueFeatureLabel(displayName, id, categoryValue);

  const conceptId = pickString(
    obj,
    ["concept_id", "conceptId", "concept"],
    "unknown_concept",
  );

  const conceptDisplayName = pickString(
    obj,
    ["concept_display_name", "conceptDisplayName"],
    conceptId.replace(/_/g, " "),
  );

  const displayPolicy = inferDisplayPolicy(obj, displayName);

  const mention =
    displayPolicy === "feature_level_allowed"
      ? uniqueLabel || displayName
      : `một tín hiệu thuộc nhóm ${conceptDisplayName}`;

  return {
    id,
    mention,
    concept: conceptDisplayName,
    direction: normalizeDirection(obj.direction),
    contribution: pickString(obj, [
      "contribution_points_display",
      "contributionPointsDisplay",
      "shap_value_display",
      "shapValueDisplay",
      "contribution_percent_display",
      "contributionPercentDisplay",
    ]),
    strength: normalizeStrength(obj.strength),
    display_policy: displayPolicy,
    unique_label: uniqueLabel || undefined,
    note:
      pickString(obj, ["feature_note", "featureNote"]) ||
      (displayPolicy === "concept_level_only"
        ? "Chỉ diễn giải ở cấp nhóm, không nêu tên kỹ thuật của feature."
        : undefined),
  };
}

function normalizeSupportingGroup(
  item: LlmSupportingFeatureGroup,
): SafeSupportingGroup {
  const obj = asRecord(item);

  const conceptId = pickString(
    obj,
    ["concept_id", "conceptId"],
    "unknown_concept",
  );

  const displayName = pickString(
    obj,
    ["display_name", "displayName"],
    conceptId.replace(/_/g, " "),
  );

  return {
    id: pickString(obj, ["group_id", "groupId"], `supporting_${conceptId}`),
    concept_id: conceptId,
    name: displayName,
    feature_count: optionalNumber(obj, ["feature_count", "featureCount"]),
    direction: normalizeDirection(obj.direction),
    contribution: pickString(obj, [
      "net_contribution_points_display",
      "netContributionPointsDisplay",
    ]),
  };
}

function normalizeRemainingSummary(summary: Record<string, unknown>): {
  count?: number;
  note: string;
} {
  const count = optionalNumber(summary, ["count", "feature_count"]);

  return {
    count,
    note: "Các yếu tố còn lại vẫn được tính trong tổng đóng góp của mô hình nhưng không trình bày chi tiết trong explanation.",
  };
}

function buildCompactAllowedTerms(input: {
  terms: LlmAllowedTerm[];
  primaryFeatures: SafeFeature[];
  riskReducingFeatures: SafeFeature[];
  supportingGroups: SafeSupportingGroup[];
}): SafeTerm[] {
  const relevantMentions = new Set<string>();

  for (const item of input.primaryFeatures) {
    relevantMentions.add(item.mention);
    relevantMentions.add(item.concept);

    if (item.unique_label) {
      relevantMentions.add(item.unique_label);
    }
  }

  for (const item of input.riskReducingFeatures) {
    relevantMentions.add(item.mention);
    relevantMentions.add(item.concept);

    if (item.unique_label) {
      relevantMentions.add(item.unique_label);
    }
  }

  for (const item of input.supportingGroups) {
    relevantMentions.add(item.name);
  }

  const normalized = asArray<LlmAllowedTerm>(input.terms)
    .map((item) => {
      const obj = asRecord(item);

      return {
        term_id: pickString(obj, ["term_id", "termId"]),
        term_type: pickString(obj, ["term_type", "termType"]),
        mention: pickString(obj, ["mention", "display_name", "displayName"]),
      };
    })
    .filter(
      (item) =>
        item.term_id.length > 0 &&
        item.term_type.length > 0 &&
        item.mention.length > 0 &&
        !isRawTechnicalText(item.mention),
    )
    .filter((item) => relevantMentions.has(item.mention))
    .slice(0, MAX_ALLOWED_TERMS);

  return normalized;
}

function buildUniqueFeatureLabel(
  displayName: string,
  featureId: string,
  categoryValue: string,
): string {
  if (!displayName) return "";

  if (categoryValue && categoryValue !== displayName) {
    return `${displayName} = ${categoryValue}`;
  }

  const inferredCategory = inferCategoryFromOneHotFeatureId(featureId);

  if (inferredCategory) {
    return `${displayName} = ${inferredCategory}`;
  }

  return displayName;
}

function inferCategoryFromOneHotFeatureId(featureId: string): string {
  if (!featureId.includes("__")) return "";

  const parts = featureId.split("__");
  const category = parts[1];

  if (!category) return "";

  return category.replace(/_/g, " ");
}

function inferDisplayPolicy(
  obj: Record<string, unknown>,
  displayName: string,
): DisplayPolicy {
  const explicit = pickString(obj, ["display_policy", "displayPolicy"]);

  if (explicit) {
    return explicit;
  }

  const llmVisible = obj.llm_visible ?? obj.llmVisible;
  const claimable = obj.claimable;
  const sensitive = pickBoolean(obj, ["sensitive"], false);
  const allowed = obj.allowed_in_user_explanation;

  if (llmVisible === false || claimable === false || allowed === false) {
    return "hidden";
  }

  if (sensitive || allowed === "limited" || isRawTechnicalText(displayName)) {
    return "concept_level_only";
  }

  return "feature_level_allowed";
}

function isRawTechnicalText(text: string): boolean {
  const value = text.trim();

  if (!value) {
    return false;
  }

  const lowered = value.toLowerCase();

  const technicalTokens = [
    "_",
    "__",
    "bureau ",
    "installment ",
    "pos cash ",
    "credit card ",
    " avg ",
    " max ",
    " min ",
    " sum ",
    " std",
    " dpd",
    " def ",
    " xna",
    " cnt",
    " amt",
    "ext_source",
    "ext source",
    "occupation_type",
    "name_income_type",
  ];

  if (technicalTokens.some((token) => lowered.includes(token))) {
    return true;
  }

  if (/^[A-Z0-9_]+$/.test(value) && value.length > 3) {
    return true;
  }

  return false;
}

function normalizeDirection(value: unknown): RiskDirection {
  if (typeof value === "string" && value.trim().length > 0) {
    return value as RiskDirection;
  }

  return "unknown";
}

function normalizeStrength(value: unknown): ContributionStrength {
  if (typeof value === "string" && value.trim().length > 0) {
    return value as ContributionStrength;
  }

  return "unknown";
}

function optionalNumber(
  obj: Record<string, unknown>,
  keys: string[],
): number | undefined {
  for (const key of keys) {
    const value = obj[key];

    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }

    if (typeof value === "string") {
      const parsed = Number(value);

      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }

  return undefined;
}
