import assert from "node:assert/strict";
import test from "node:test";

import type {
  AtomicClaimRecord,
  ClaimType,
} from "../../../contracts/validation-claims";
import {
  classifyClaimSemantics,
} from "../../../research/ts/claim_finalization/claimSubtype";

test("semantic classifier uses exact recommendation rules and fails closed", () => {
  assert.deepEqual(
    classifyClaimSemantics(claim(
      "recommendation",
      "Cần thẩm định thêm.",
    )),
    {
      claim_type: "recommendation",
      claim_subtype: "HUMAN_REVIEW",
    },
  );
  assert.deepEqual(
    classifyClaimSemantics(claim(
      "recommendation",
      "Không nên sử dụng kết quả này làm quyết định tín dụng duy nhất.",
    )),
    {
      claim_type: "recommendation",
      claim_subtype: "CAUTION_IN_DECISION_USE",
    },
  );
  assert.equal(
    classifyClaimSemantics(claim(
      "recommendation",
      "Cần xem xét thêm.",
    )).claim_subtype,
    "UNRESOLVED_RECOMMENDATION",
  );
});

test("semantic classifier separates limitation meanings", () => {
  assert.equal(
    classifyClaimSemantics(claim(
      "limitation",
      "Đây không phải lời khuyên tài chính.",
    )).claim_subtype,
    "NOT_FINANCIAL_ADVICE",
  );
  assert.equal(
    classifyClaimSemantics(claim(
      "limitation",
      "Kết quả không nên là căn cứ duy nhất.",
    )).claim_subtype,
    "NOT_SOLE_DECISION_BASIS",
  );
  assert.equal(
    classifyClaimSemantics(claim(
      "limitation",
      "Giới hạn này cần được lưu ý.",
    )).claim_subtype,
    "UNRESOLVED_LIMITATION",
  );
});

test("non-causal uncertainty is retyped as a limitation", () => {
  assert.deepEqual(
    classifyClaimSemantics(claim(
      "uncertainty",
      "Đây không phải quan hệ nhân quả thực tế.",
    )),
    {
      claim_type: "limitation",
      claim_subtype: "NON_CAUSAL",
    },
  );
});

test("broad semantic families do not use meaningful catch-all subtypes", () => {
  assert.equal(
    classifyClaimSemantics(claim(
      "prediction",
      "Mô hình đưa ra một đánh giá.",
    )).claim_subtype,
    "UNRESOLVED_PREDICTION",
  );
  assert.equal(
    classifyClaimSemantics(claim(
      "magnitude",
      "Mức ảnh hưởng cần được xem xét.",
    )).claim_subtype,
    "UNRESOLVED_MAGNITUDE",
  );
  assert.equal(
    classifyClaimSemantics(claim(
      "distributed_evidence",
      "Các bằng chứng tạo thành một bức tranh chung.",
    )).claim_subtype,
    "UNRESOLVED_DISTRIBUTED_EVIDENCE",
  );
});

function claim(
  claimType: ClaimType,
  sourceText: string,
): AtomicClaimRecord {
  return {
    claim_type: claimType,
    source_text: sourceText,
    feature_id: null,
    concept_id: null,
    direction: "unknown",
    numeric_role: null,
    numeric_unit: null,
  } as AtomicClaimRecord;
}
