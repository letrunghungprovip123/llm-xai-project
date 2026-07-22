import assert from "node:assert/strict";
import test from "node:test";

import type {
  AtomicClaimRecord,
  StoredClaimExtractionAttemptRecord,
} from "../../../contracts/validation-claims";
import { sha256 } from "../../../research/llm/common/utils";
import {
  locateNumericSource,
} from "../../../research/llm/claim_extraction/claimPostprocessor";
import {
  assertCountFactCompleteness,
  extractCountFacts,
  finalizeGenerationClaims,
  isPolicyAbsenceSlot,
} from "../../../research/llm/claim_finalization/claimFinalizationRules";
import {
  validateStoredRawResponseHash,
} from "../../../research/llm/claim_finalization/claimFinalizer";
import type {
  GenerationTextDocument,
} from "../../../research/llm/claim_extraction/generationTextAdapter";

const lineage = {
  claim_schema_version: "claims_v2" as const,
  generation_id: "generation_test",
  model_id: "deepseek_v4_flash",
  source_ir_id: "ir_test",
  case_id: "case_test",
  evidence_level: "S4" as const,
  repeat_id: 1,
  source_input_sha256: "source_hash",
  extractor_provider: "deepseek" as const,
  extractor_model_id: "deepseek-v4-flash",
  extractor_version: "atomic_claim_extractor_v2.1.0",
  extractor_prompt_version: "atomic_claim_extraction_prompt_v3",
  extractor_prompt_sha256:
    "6c571dbe10b12e2f1b933fca366ae5f8b900520a330a9a36111ff9c477fb2553",
  extractor_status: "SUCCESS" as const,
};

function makeDocument(input: {
  prediction?: string;
  factorExplanation?: string;
  uncertainty?: string;
  distributed?: string;
  safeSummary?: string;
}): GenerationTextDocument {
  let text = "";
  const spans: GenerationTextDocument["section_spans"] = [];
  const append = (
    section: GenerationTextDocument["section_spans"][number]["source_section"],
    value: string | undefined,
    factorId: string | null = null,
  ): void => {
    if (!value) return;
    text += factorId ? `[${section}:${factorId}]\n` : `[${section}]\n`;
    const start = text.length;
    text += value;
    const end = text.length;
    text += "\n\n";
    spans.push({
      source_section: section,
      source_factor_id: factorId,
      start,
      end,
    });
  };
  append("prediction_summary", input.prediction);
  append("factor_explanation", input.factorExplanation, "factor_1");
  append("uncertainty_note", input.uncertainty);
  append("distributed_evidence_note", input.distributed);
  append("safe_summary", input.safeSummary);
  return {
    generation_text: text,
    source_input_sha256: sha256(JSON.stringify({ text, spans })),
    section_spans: spans,
    factor_metadata: [{
      source_factor_id: "factor_1",
      declared_feature_ids: ["feature_1"],
      declared_concept_ids: [],
    }],
  };
}

function claim(input: {
  document: GenerationTextDocument;
  sourceSection: AtomicClaimRecord["source_section"];
  sourceText: string;
  sourceFactorId?: string | null;
  claimType?: AtomicClaimRecord["claim_type"];
  subjectType?: AtomicClaimRecord["subject_type"];
  direction?: AtomicClaimRecord["direction"];
  featureId?: string | null;
  numericValue?: number | null;
  numericUnit?: string | null;
  numericRole?: AtomicClaimRecord["numeric_role"];
  modelKey?: string | null;
  origin?: AtomicClaimRecord["claim_origin"];
}): AtomicClaimRecord {
  const sourceFactorId = input.sourceFactorId ?? null;
  const span = input.document.section_spans.find(
    (item) =>
      item.source_section === input.sourceSection
      && item.source_factor_id === sourceFactorId,
  );
  assert.ok(span);
  const localStart = input.document.generation_text.indexOf(
    input.sourceText,
    span.start,
  );
  assert.ok(localStart >= span.start && localStart < span.end);
  return {
    ...lineage,
    source_input_sha256: input.document.source_input_sha256,
    claim_id: `old_${Math.random()}`,
    local_claim_index: 1,
    source_section: input.sourceSection,
    source_factor_id: sourceFactorId,
    source_text: input.sourceText,
    source_span_start: localStart,
    source_span_end: localStart + input.sourceText.length,
    source_text_sha256: sha256(input.sourceText),
    claim_type: input.claimType ?? "prediction",
    subject_type: input.subjectType ?? "prediction",
    feature_id: input.featureId ?? null,
    concept_id: null,
    direction: input.direction ?? "unknown",
    magnitude: null,
    certainty: "deterministic",
    causal_strength: "none",
    numeric_value: input.numericValue ?? null,
    numeric_unit: input.numericUnit ?? null,
    numeric_role: input.numericRole ?? null,
    claim_origin: input.origin ?? "llm",
    model_normalized_claim_key: input.modelKey ?? null,
    semantic_signature: "old_signature",
    normalized_claim_key: "old_signature",
  };
}

test("selected evidence counts are typed and concept-group count is added", () => {
  const prediction =
    "Mô hình dự đoán rủi ro cao dựa trên 16 yếu tố được chọn từ 8 nhóm khái niệm.";
  const document = makeDocument({ prediction });
  const narrative = claim({
    document,
    sourceSection: "prediction_summary",
    sourceText: prediction,
  });
  const count16 = claim({
    document,
    sourceSection: "prediction_summary",
    sourceText: "16",
    claimType: "numeric",
    numericValue: 16,
    numericRole: "other",
    origin: "derived_numeric",
  });

  const first = finalizeGenerationClaims([narrative, count16], document);
  const second = finalizeGenerationClaims([narrative, count16], document);
  assert.deepEqual(first, second);
  assert.equal(first.length, 3);

  const records = first.map((item) => item.record);
  const selectedNarrative = records.find(
    (item) => item.model_normalized_claim_key === "selected_evidence_count"
      && item.claim_type !== "numeric",
  );
  assert.equal(selectedNarrative?.claim_type, "distributed_evidence");
  assert.equal(selectedNarrative?.subject_type, "evidence");

  const selectedCount = records.find((item) => item.numeric_value === 16);
  assert.equal(selectedCount?.numeric_unit, "count");
  assert.equal(selectedCount?.subject_type, "evidence");
  assert.equal(selectedCount?.claim_origin, "derived_numeric");

  const conceptCount = records.find((item) => item.numeric_value === 8);
  assert.equal(conceptCount?.model_normalized_claim_key, "concept_group_count");
  assert.equal(conceptCount?.source_text, "8");
  assert.deepEqual(records.map((item) => item.local_claim_index), [1, 2, 3]);
});

test("non-causal disclaimer becomes a narrative limitation", () => {
  const uncertainty =
    "Các yếu tố chỉ giải thích dự đoán, không khẳng định quan hệ nhân quả thực tế.";
  const document = makeDocument({ uncertainty });
  const source = claim({
    document,
    sourceSection: "uncertainty_note",
    sourceText: uncertainty,
    claimType: "uncertainty",
    subjectType: "none",
    direction: "unknown",
  });

  const [result] = finalizeGenerationClaims([source], document);
  assert.equal(result?.record.claim_type, "limitation");
  assert.equal(result?.record.subject_type, "narrative");
  assert.equal(result?.record.causal_strength, "none");
  assert.equal(
    result?.record.model_normalized_claim_key,
    "non_causal_model_limitation",
  );
});

test("directional quote expands only when the declared factor supplies direction", () => {
  const explanation =
    "Thu nhập thấp góp phần làm tăng rủi ro tín dụng của mô hình.";
  const document = makeDocument({ factorExplanation: explanation });
  const source = claim({
    document,
    sourceSection: "factor_explanation",
    sourceFactorId: "factor_1",
    sourceText: "Thu nhập thấp",
    claimType: "feature_direction",
    subjectType: "feature",
    direction: "increase_risk",
    featureId: "feature_1",
  });

  const [result] = finalizeGenerationClaims([source], document);
  assert.equal(result?.record.source_text, explanation);
  assert.equal(
    result?.record.source_text_sha256,
    sha256(explanation),
  );
});

test("policy-absence distributed-evidence notes are non-claim-bearing", () => {
  assert.equal(
    isPolicyAbsenceSlot(
      "distributed_evidence_note",
      "Không có yêu cầu phân phối bằng chứng.",
    ),
    true,
  );
  assert.equal(
    isPolicyAbsenceSlot(
      "distributed_evidence_note",
      "Không có distributed_evidence_note do policy không yêu cầu.",
    ),
    true,
  );
  assert.equal(
    isPolicyAbsenceSlot("safe_summary", "Không có yêu cầu phân phối bằng chứng."),
    false,
  );
});

test("provider canonicalization resolves explicit high-risk prediction", async () => {
  const { validateAndNormalizeClaimPayload } = await import(
    "../../../research/llm/claim_extraction/atomicClaimSchema"
  );
  const prediction = "Mô hình dự đoán rủi ro tín dụng cao với xác suất 90%.";
  const document = makeDocument({ prediction });
  const payload = validateAndNormalizeClaimPayload({
    claims: [{
      source_section: "prediction_summary",
      source_factor_id: "",
      source_text: prediction,
      claim_type: "prediction",
      subject_type: "prediction",
      feature_id: "",
      concept_id: "",
      direction: "unknown",
      magnitude: "not_applicable",
      certainty: "probabilistic",
      causal_strength: "none",
      numeric_value_text: "90",
      numeric_unit: "percent",
      numeric_role: "prediction_score",
      normalized_claim_key: "high risk prediction",
    }],
  }, document);
  const result = payload.claims.find((item) => item.claim_type === "prediction");
  assert.equal(result?.direction, "increase_risk");
});


test("numeric source minimization keeps four-decimal values atomic", () => {
  const text = "ext_source_mean có giá trị SHAP dương 0.0703.";
  const document = makeDocument({ factorExplanation: text });
  const source = claim({
    document,
    sourceSection: "factor_explanation",
    sourceFactorId: "factor_1",
    sourceText: text,
    claimType: "numeric",
    subjectType: "feature",
    featureId: "feature_1",
    numericValue: 0.0703,
    numericUnit: "shap_value",
    numericRole: "feature_value",
  });

  const located = locateNumericSource(source);
  assert.deepEqual(located, {
    text: "0.0703",
    start: source.source_span_start + text.indexOf("0.0703"),
    end: source.source_span_start + text.indexOf("0.0703") + 6,
  });

  const [result] = finalizeGenerationClaims([source], document);
  assert.equal(result?.record.source_text, "0.0703");
  assert.equal(result?.record.numeric_value, 0.0703);
});

test("policy-absence claims are removed from finalized claims", () => {
  const note = "Không có yêu cầu phân phối bằng chứng.";
  const text = `[distributed_evidence_note]\n${note}\n\n`;
  const start = text.indexOf(note);
  const document: GenerationTextDocument = {
    generation_text: text,
    source_input_sha256: sha256(text),
    section_spans: [{
      source_section: "distributed_evidence_note",
      source_factor_id: null,
      start,
      end: start + note.length,
    }],
    factor_metadata: [],
  };
  const source = claim({
    document,
    sourceSection: "distributed_evidence_note",
    sourceText: note,
    claimType: "distributed_evidence",
    subjectType: "evidence",
  });

  assert.deepEqual(finalizeGenerationClaims([source], document), []);
});


test("stored raw-response hash guard rejects tampering", () => {
  const rawText = '{"claims":[]}';
  const attempt = {
    attempt_id: "attempt_test",
    raw_response_text: rawText,
    raw_response_sha256: sha256(rawText),
  } as StoredClaimExtractionAttemptRecord;

  assert.doesNotThrow(() => validateStoredRawResponseHash(attempt));
  assert.throws(
    () => validateStoredRawResponseHash({
      ...attempt,
      raw_response_text: `${rawText} `,
    }),
    /Stored response hash mismatch/u,
  );
});


test("count canonicalization covers selected evidence and concept groups", () => {
  const prediction =
    "Mô hình dự đoán rủi ro cao dựa trên 20 tín hiệu được chọn từ 8 nhóm khái niệm.";
  const document = makeDocument({ prediction });
  const narrative = claim({
    document,
    sourceSection: "prediction_summary",
    sourceText: prediction,
  });
  const mistyped20 = claim({
    document,
    sourceSection: "prediction_summary",
    sourceText: "20",
    claimType: "numeric",
    subjectType: "prediction",
    numericValue: 20,
    numericRole: "other",
    modelKey: "prediction basis count",
  });

  const records = finalizeGenerationClaims(
    [narrative, mistyped20],
    document,
  ).map((item) => item.record);
  const count20 = records.find((item) => item.numeric_value === 20);
  const count8 = records.find((item) => item.numeric_value === 8);
  assert.equal(count20?.model_normalized_claim_key, "selected_evidence_count");
  assert.equal(count20?.subject_type, "evidence");
  assert.equal(count20?.numeric_unit, "count");
  assert.equal(count8?.model_normalized_claim_key, "concept_group_count");
  assert.doesNotThrow(() => assertCountFactCompleteness(records, document));
});

test("factor-member counts use factor-specific semantic targets", () => {
  const explanation = "Nhóm hành vi trả góp gồm 4 yếu tố làm tăng rủi ro.";
  const document = makeDocument({ factorExplanation: explanation });
  const narrative = claim({
    document,
    sourceSection: "factor_explanation",
    sourceFactorId: "factor_1",
    sourceText: explanation,
    claimType: "distributed_evidence",
    subjectType: "evidence",
  });

  const records = finalizeGenerationClaims([narrative], document)
    .map((item) => item.record);
  const count = records.find((item) => item.numeric_value === 4);
  assert.equal(
    count?.model_normalized_claim_key,
    "factor_member_count:factor_1",
  );
  assert.equal(count?.source_factor_id, "factor_1");
  assert.equal(count?.source_text, "4");
});

test("distributed evidence count facts include selected, concept and mixed groups", () => {
  const distributed =
    "Evidence gồm 20 đặc trưng từ 13 nhóm concept, trong đó có 2 nhóm hỗn hợp.";
  const document = makeDocument({ distributed });
  const narrative = claim({
    document,
    sourceSection: "distributed_evidence_note",
    sourceText: distributed,
    claimType: "distributed_evidence",
    subjectType: "evidence",
  });

  const records = finalizeGenerationClaims([narrative], document)
    .map((item) => item.record);
  const targets = new Map(
    records
      .filter((item) => item.claim_type === "numeric")
      .map((item) => [item.model_normalized_claim_key, item.numeric_value]),
  );
  assert.equal(targets.get("selected_evidence_count"), 20);
  assert.equal(targets.get("concept_group_count"), 13);
  assert.equal(targets.get("mixed_concept_group_count"), 2);
});

test("same count value remains distinct for different semantic targets", () => {
  const prediction =
    "Dự đoán dựa trên 10 đặc trưng được chọn từ 10 nhóm khái niệm.";
  const document = makeDocument({ prediction });
  const narrative = claim({
    document,
    sourceSection: "prediction_summary",
    sourceText: prediction,
  });

  const numeric = finalizeGenerationClaims([narrative], document)
    .map((item) => item.record)
    .filter((item) => item.claim_type === "numeric");
  assert.equal(numeric.length, 2);
  assert.equal(new Set(numeric.map((item) => item.semantic_signature)).size, 2);
  assert.deepEqual(
    new Set(numeric.map((item) => item.model_normalized_claim_key)),
    new Set(["selected_evidence_count", "concept_group_count"]),
  );
});

test("decimal values and percentages are not count facts", () => {
  const prediction = "Xác suất 90.40%, SHAP trung bình 0.0703.";
  const document = makeDocument({ prediction });
  assert.deepEqual(extractCountFacts(document), []);
});

test("repeated count facts across sections canonicalize once", () => {
  const prediction = "Dự đoán dựa trên 10 yếu tố chính.";
  const safeSummary = "Mô hình dự đoán rủi ro cao dựa trên 10 yếu tố.";
  const document = makeDocument({ prediction, safeSummary });
  const claims = [
    claim({
      document,
      sourceSection: "prediction_summary",
      sourceText: prediction,
    }),
    claim({
      document,
      sourceSection: "safe_summary",
      sourceText: safeSummary,
      claimType: "distributed_evidence",
      subjectType: "evidence",
    }),
  ];

  assert.equal(extractCountFacts(document).length, 1);
  const final = finalizeGenerationClaims(claims, document)
    .map((item) => item.record);
  assert.equal(
    final.filter((item) =>
      item.model_normalized_claim_key === "selected_evidence_count"
      && item.claim_type === "numeric"
    ).length,
    1,
  );
});

test("count completeness gate fails on an omitted explicit count", () => {
  const prediction = "Dự đoán dựa trên 10 yếu tố chính.";
  const document = makeDocument({ prediction });
  assert.throws(
    () => assertCountFactCompleteness([], document),
    /Count fact completeness failure/u,
  );
});


test("generic factor-group wording is canonicalized as concept-group count", () => {
  const safeSummary =
    "Mô hình dự đoán rủi ro cao dựa trên 18 tín hiệu thuộc 8 nhóm.";
  const document = makeDocument({ safeSummary });
  const narrative = claim({
    document,
    sourceSection: "safe_summary",
    sourceText: safeSummary,
    claimType: "distributed_evidence",
    subjectType: "evidence",
  });

  const records = finalizeGenerationClaims([narrative], document)
    .map((item) => item.record);
  assert.equal(
    records.find((item) => item.numeric_value === 18)
      ?.model_normalized_claim_key,
    "selected_evidence_count",
  );
  assert.equal(
    records.find((item) => item.numeric_value === 8)
      ?.model_normalized_claim_key,
    "concept_group_count",
  );
});
