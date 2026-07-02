// src/server/llm/prompt-builder.ts

import type {
  BuiltPrompt,
  ExplanationIrRecord,
  LlmContractConcept,
  LlmContractFeatureFactor,
  LlmInputContract,
  IrPredictionSummary,
  RiskDirection,
  ContributionStrength,
} from "./explanation-schema";

import { getCustomerId, pickNumber, pickString } from "./explanation-schema";

/**
 * Batch I v1.0 - Prompt Builder
 *
 * Goal:
 * Convert Batch H Explanation IR into a tightly controlled prompt.
 *
 * Critical design rule:
 * The LLM is only a verbalization layer.
 * It must not invent new evidence, hidden features, causal claims, or certainty claims.
 */

export const PROMPT_VERSION = "batch_i_llm_prompt_v1.0";

type NormalizedPrediction = {
  predictedLabel: string;
  probability: number;
  threshold: number;
  thresholdComparison: string;
};

type NormalizedConcept = {
  conceptId: string;
  displayName: string;
  direction: RiskDirection;
  strength: ContributionStrength;
  contributionPercent?: number;
};

type NormalizedFeatureFactor = {
  featureId: string;
  displayName: string;
  value?: unknown;
  valueDisplay?: string;
  shapValue?: number;
  shapValueDisplay?: string;
  direction: RiskDirection;
  strength: ContributionStrength;
  contributionPercent?: number;
  contributionPercentDisplay?: string;
};
/**
 * Main public function.
 */
export function buildExplanationPrompt(
  irRecord: ExplanationIrRecord,
): BuiltPrompt {
  const contract = getLlmInputContractOrThrow(irRecord);

  const safeContract = buildSafePromptContract(irRecord, contract);

  const system = buildSystemPrompt();
  const user = buildUserPrompt(safeContract);

  return {
    system,
    user,
    promptVersion: PROMPT_VERSION,
  };
}

/**
 * We only expose the LLM input contract, not the full IR.
 */
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

/**
 * Build a compact safe object for the LLM.
 *
 * This removes fields that the LLM should not need.
 * The goal is to minimize hallucination risk and avoid exposing hidden/internal data.
 */
function buildSafePromptContract(
  irRecord: ExplanationIrRecord,
  contract: LlmInputContract,
) {
  const prediction = normalizePrediction(
    contract.prediction ?? irRecord.prediction_summary,
  );

  const mainConcepts = normalizeConcepts(
    contract.main_concepts ?? contract.mainConcepts ?? [],
  );

  const riskIncreasingFactors = normalizeFeatureFactors(
    contract.main_risk_increasing_factors ??
      contract.mainRiskIncreasingFactors ??
      [],
  );

  const riskDecreasingFactors = normalizeFeatureFactors(
    contract.main_risk_decreasing_factors ??
      contract.mainRiskDecreasingFactors ??
      [],
  );

  const allowedClaimIds =
    contract.allowed_claim_ids ?? contract.allowedClaimIds ?? [];

  const forbiddenRuleIds =
    contract.forbidden_rule_ids ?? contract.forbiddenRuleIds ?? [];

  const mustInclude = contract.must_include ?? contract.mustInclude ?? [];

  const mustNot = contract.must_not ?? contract.mustNot ?? [];

  const requiredOutputSections = contract.required_output_sections ??
    contract.requiredOutputSections ?? [
      "prediction",
      "main_risk_drivers",
      "risk_reducing_factors",
      "limitations",
    ];

  return {
    task: "Generate a faithful Vietnamese explanation from the provided Explanation IR contract.",
    language: "vi",
    source_ir_id: irRecord.ir_id,
    source_evidence_id: irRecord.source_evidence_id ?? null,
    trace_id: irRecord.trace_id ?? null,
    run_mode: irRecord.run_mode ?? "evaluation",
    has_ground_truth: Boolean(irRecord.has_ground_truth),
    customer_id: getCustomerId(irRecord.customer),

    prediction,

    allowed_content: {
      main_concepts: mainConcepts,
      main_risk_increasing_factors: riskIncreasingFactors,
      main_risk_decreasing_factors: riskDecreasingFactors,
    },

    contract_rules: {
      allowed_claim_ids: allowedClaimIds,
      forbidden_rule_ids: forbiddenRuleIds,
      must_include: mustInclude,
      must_not: mustNot,
      required_output_sections: requiredOutputSections,
    },

    required_json_output_schema: {
      language: "vi",
      sections: {
        prediction: "string",
        main_risk_drivers: "string",
        risk_reducing_factors: "string",
        limitations: "string",
      },
      full_text: "string",
    },
  };
}

/**
 * System prompt: stable instruction for the model.
 */
function buildSystemPrompt(): string {
  return [
    "Bạn là một bộ sinh diễn giải cho hệ thống Machine Learning có khả năng giải thích.",
    "Nhiệm vụ của bạn là diễn đạt Explanation IR thành tiếng Việt dễ hiểu.",
    "",
    "Bạn KHÔNG phải là chuyên gia tín dụng tự suy luận thêm.",
    "Bạn KHÔNG được thêm thông tin ngoài contract được cung cấp.",
    "Bạn KHÔNG được tạo feature, concept, lý do, hoặc khuyến nghị mới.",
    "",
    "Quy tắc bắt buộc:",
    "1. Chỉ dùng thông tin trong JSON contract do người dùng cung cấp.",
    "2. Chỉ mô tả các yếu tố là đóng góp vào dự đoán của mô hình.",
    "3. Trong sections.main_risk_drivers, nếu allowed_content.main_risk_increasing_factors có dữ liệu, phải nêu một số yếu tố cụ thể được phép hiển thị, không chỉ nói nhóm yếu tố chung.",
    "4. Khi nêu yếu tố cụ thể, hãy dùng displayName, direction, strength và nếu có thì dùng valueDisplay, shapValueDisplay hoặc contributionPercentDisplay.",
    "5. Nếu có SHAP/contribution value, diễn đạt là 'đóng góp vào dự đoán của mô hình', không diễn đạt là nguyên nhân ngoài thực tế.",
    "6. Không được nói hoặc ngụ ý quan hệ nhân quả ngoài thực tế.",
    "7. Không được nói khách hàng chắc chắn vỡ nợ hoặc chắc chắn trả nợ.",
    "8. Không được nhắc TARGET, nhãn thật, true label, true positive, false positive, false negative.",
    "9. Không được nhắc feature ẩn, feature nhạy cảm, hoặc bất kỳ thông tin nào không có trong allowed_content.",
    "10. Không được nói đây là quyết định cuối cùng của ngân hàng.",
    "11. Phải có phần giới hạn giải thích trong sections.limitations.",
    "12. Khi nói về high_default_risk, ưu tiên dùng 'rủi ro gặp khó khăn trong thanh toán' hoặc 'rủi ro không trả nợ đúng hạn', hạn chế dùng từ quá mạnh như 'vỡ nợ'.",
    "13. Chỉ trả về JSON hợp lệ, không markdown, không giải thích ngoài JSON.",
    "",
    "Cách diễn đạt nên dùng:",
    "- 'góp phần làm tăng rủi ro dự đoán của mô hình'",
    "- 'góp phần làm giảm rủi ro dự đoán của mô hình'",
    "- 'theo mô hình'",
    "- 'dự đoán xác suất'",
    "",
    "Cách diễn đạt bị cấm:",
    "- 'gây ra rủi ro'",
    "- 'là nguyên nhân khiến khách hàng vỡ nợ'",
    "- 'chắc chắn sẽ không trả nợ'",
    "- 'chứng minh rằng khách hàng không trả được nợ'",
  ].join("\n");
}

/**
 * User prompt: contains the actual safe contract.
 */
function buildUserPrompt(safeContract: unknown): string {
  return [
    "Hãy tạo giải thích tiếng Việt từ JSON contract bên dưới.",
    "",
    "Yêu cầu output:",
    "- Chỉ trả về JSON hợp lệ.",
    "- Không dùng markdown.",
    "- Không bọc JSON trong ```.",
    "- Không thêm text ngoài JSON.",
    "- JSON phải có đúng các field: language, sections, full_text.",
    "- sections phải có: prediction, main_risk_drivers, risk_reducing_factors, limitations.",
    "- sections.main_risk_drivers phải gồm 2 phần: nhóm yếu tố chính và các yếu tố cụ thể được phép hiển thị.",
    "- Nếu contract có main_risk_increasing_factors, hãy nêu 3 đến 6 yếu tố cụ thể quan trọng nhất.",
    "- Không được bỏ qua feature-level factors nếu chúng có trong allowed_content.",
    "",
    "JSON contract:",
    JSON.stringify(safeContract, null, 2),
  ].join("\n");
}

function normalizePrediction(
  prediction: IrPredictionSummary | undefined,
): NormalizedPrediction {
  const predictionObj = prediction as Record<string, unknown> | undefined;

  return {
    predictedLabel: pickString(
      predictionObj,
      ["predicted_label", "predictedLabel"],
      "unknown",
    ),
    probability: pickNumber(
      predictionObj,
      ["probability", "predicted_probability", "predictedProbability"],
      0,
    ),
    threshold: pickNumber(predictionObj, ["threshold"], 0.5),
    thresholdComparison: pickString(
      predictionObj,
      ["threshold_comparison", "thresholdComparison"],
      "unknown",
    ),
  };
}

function normalizeConcepts(
  concepts: LlmContractConcept[],
): NormalizedConcept[] {
  return concepts
    .filter((item) => isVisibleAndClaimable(item))
    .map((item) => {
      const obj = item as Record<string, unknown>;

      return {
        conceptId: pickString(
          obj,
          ["concept_id", "conceptId"],
          "unknown_concept",
        ),
        displayName: pickString(
          obj,
          ["display_name", "displayName"],
          "yếu tố không xác định",
        ),
        direction: normalizeDirection(obj.direction),
        strength: normalizeStrength(obj.strength),
        contributionPercent: optionalNumber(obj, [
          "contribution_percent",
          "contributionPercent",
        ]),
      };
    })
    .filter((item) => item.conceptId !== "unknown_concept");
}

function normalizeFeatureFactors(
  factors: LlmContractFeatureFactor[],
): NormalizedFeatureFactor[] {
  return factors
    .filter((item) => isVisibleAndClaimable(item))
    .map((item) => {
      const obj = item as Record<string, unknown>;

      return {
        featureId: pickString(
          obj,
          ["feature_id", "featureId"],
          "unknown_feature",
        ),
        displayName: pickString(
          obj,
          ["display_name", "displayName"],
          "yếu tố không xác định",
        ),

        value: obj.value,
        valueDisplay: pickString(
          obj,
          [
            "value_display",
            "valueDisplay",
            "formatted_value",
            "formattedValue",
          ],
          "",
        ),

        shapValue: optionalNumber(obj, ["shap_value", "shapValue"]),
        shapValueDisplay: pickString(
          obj,
          [
            "shap_value_display",
            "shapValueDisplay",
            "formatted_shap_value",
            "formattedShapValue",
          ],
          "",
        ),

        direction: normalizeDirection(obj.direction),
        strength: normalizeStrength(obj.strength),

        contributionPercent: optionalNumber(obj, [
          "contribution_percent",
          "contributionPercent",
        ]),
        contributionPercentDisplay: pickString(
          obj,
          [
            "contribution_percent_display",
            "contributionPercentDisplay",
            "formatted_contribution_percent",
            "formattedContributionPercent",
          ],
          "",
        ),
      };
    })
    .filter((item) => item.featureId !== "unknown_feature");
}
/**
 * Extra safety:
 * If Batch H already filtered correctly, this simply keeps allowed items.
 * If not, this avoids exposing items explicitly marked as hidden/unclaimable.
 */
function isVisibleAndClaimable(item: Record<string, unknown>): boolean {
  const llmVisible = item.llm_visible ?? item.llmVisible;
  const claimable = item.claimable;

  if (llmVisible === false) return false;
  if (claimable === false) return false;

  return true;
}

function normalizeDirection(value: unknown): RiskDirection {
  if (
    value === "increases_risk" ||
    value === "decreases_risk" ||
    value === "neutral" ||
    value === "mixed" ||
    value === "unknown"
  ) {
    return value;
  }

  return "unknown";
}

function normalizeStrength(value: unknown): ContributionStrength {
  if (
    value === "strong" ||
    value === "moderate" ||
    value === "weak" ||
    value === "neutral" ||
    value === "unknown"
  ) {
    return value;
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
