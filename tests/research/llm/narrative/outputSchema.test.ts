import assert from "node:assert/strict";
import test from "node:test";
import {
  EXPLANATION_JSON_SCHEMA,
  buildGenerationId,
  parseExplanationOutput,
} from "../../../../research/llm/narrative/index";

const VALID_OUTPUT = {
  prediction_summary: "Mô hình dự đoán rủi ro cao.",
  factors: [],
  uncertainty_note: "Đây không phải kết luận chắc chắn.",
  distributed_evidence_note: "",
  safe_summary: "Không nêu nguyên nhân khi không có evidence.",
};

test("parser chấp nhận JSON hợp lệ và giữ nguyên schema Batch-I", () => {
  const parsed = parseExplanationOutput(JSON.stringify(VALID_OUTPUT), "S0");

  assert.equal(parsed.raw_json_parse_success, true);
  assert.equal(parsed.json_parse_success, true);
  assert.equal(parsed.schema_valid, true);
  assert.deepEqual(parsed.parsed_output, VALID_OUTPUT);
  assert.deepEqual(EXPLANATION_JSON_SCHEMA.required, [
    "prediction_summary",
    "factors",
    "uncertainty_note",
    "distributed_evidence_note",
    "safe_summary",
  ]);
});

test("parser chỉ áp dụng hai cleanup type lịch sử", () => {
  const fenced = parseExplanationOutput(
    `\`\`\`json\n${JSON.stringify(VALID_OUTPUT)}\n\`\`\``,
    "S0",
  );
  const wrapped = parseExplanationOutput(
    `Kết quả: ${JSON.stringify(VALID_OUTPUT)} hết.`,
    "S0",
  );

  assert.equal(fenced.cleanup_type, "removed_code_fence");
  assert.equal(fenced.schema_valid, true);
  assert.equal(wrapped.cleanup_type, "extracted_json_object");
  assert.equal(wrapped.schema_valid, true);
});

test("parser từ chối output rỗng, non-JSON và factors của S0", () => {
  const empty = parseExplanationOutput("", "S0");
  const nonJson = parseExplanationOutput("không phải JSON", "S0");
  const invalidS0 = parseExplanationOutput(
    JSON.stringify({
      ...VALID_OUTPUT,
      factors: [
        {
          factor_id: "factor_1",
          role: "main",
          factor_name: "Thu nhập",
          declared_feature_ids: ["feature_income"],
          declared_concept_ids: ["income"],
          direction: "increase_risk",
          explanation: "Tín hiệu góp phần vào dự đoán.",
        },
      ],
    }),
    "S0",
  );

  assert.equal(empty.schema_valid, false);
  assert.equal(nonJson.json_parse_success, false);
  assert.equal(invalidS0.schema_valid, false);
  assert.match(invalidS0.validation_errors.join("\n"), /empty factors array/);
});

test("generation ID giữ đúng format và quy tắc sanitize", () => {
  const generationId = buildGenerationId(
    "run template/fixture",
    "template baseline",
    2,
    "pkg:S0/fixture",
  );

  assert.equal(
    generationId,
    "run_template_fixture__template_baseline__r2__pkg_S0_fixture",
  );
});
