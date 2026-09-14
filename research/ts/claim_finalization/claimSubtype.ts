import type {
  AtomicClaimRecord,
  ClaimSubtype,
  ClaimType,
} from "../../../contracts/validation-claims";

export type ClaimSemanticClassification = {
  claim_type: ClaimType;
  claim_subtype: ClaimSubtype;
};

export function classifyClaimSemantics(
  claim: AtomicClaimRecord,
): ClaimSemanticClassification {
  const text = normalizeText(claim.source_text);

  switch (claim.claim_type) {
    case "prediction":
      if (mentionsThreshold(text)) {
        return classified("prediction", "THRESHOLD_COMPARISON");
      }
      if (mentionsProbability(text)) {
        return classified(
          "prediction",
          mentionsPredictionLabel(text)
            ? "OVERALL_PREDICTION_SUMMARY"
            : "OVERALL_PROBABILITY",
        );
      }
      if (mentionsPredictionLabel(text)) {
        return classified("prediction", "OVERALL_LABEL");
      }
      return classified("prediction", "UNRESOLVED_PREDICTION");

    case "feature_presence":
      return classified("feature_presence", "FEATURE_MENTION");
    case "feature_direction":
      return classified("feature_direction", "FEATURE_RISK_DIRECTION");
    case "concept_presence":
      return classified("concept_presence", "CONCEPT_MENTION");
    case "concept_direction":
      return classified("concept_direction", "CONCEPT_RISK_DIRECTION");

    case "magnitude":
      if (claim.feature_id) {
        return classified("magnitude", "FEATURE_STRENGTH");
      }
      if (claim.concept_id) {
        return classified("magnitude", "CONCEPT_STRENGTH");
      }
      if (hasAny(text, [
        "so voi",
        "manh hon",
        "yeu hon",
        "manh nhat",
        "yeu nhat",
      ])) {
        return classified("magnitude", "COMPARATIVE_STRENGTH");
      }
      if (hasAny(text, [
        "can bang",
        "tong the",
        "khong yeu to nao noi troi",
        "muc do dong gop tuong doi",
      ])) {
        return classified("magnitude", "OVERALL_BALANCE");
      }
      return classified("magnitude", "UNRESOLVED_MAGNITUDE");

    case "ranking":
      return classified(
        "ranking",
        claim.concept_id ? "CONCEPT_RANK" : "FEATURE_RANK",
      );

    case "numeric":
      switch (claim.numeric_role) {
        case "prediction_score":
          return classified("numeric", "PREDICTION_SCORE");
        case "decision_threshold":
          return classified("numeric", "DECISION_THRESHOLD");
        case "feature_value":
          return classified(
            "numeric",
            claim.concept_id ? "CONCEPT_VALUE" : "FEATURE_VALUE",
          );
        case "rank":
          return classified("numeric", "RANK_VALUE");
        case "other":
          return classified(
            "numeric",
            claim.numeric_unit === "count"
              ? "EVIDENCE_COUNT"
              : "OTHER_NUMERIC",
          );
        default:
          return classified("numeric", "OTHER_NUMERIC");
      }

    case "causal":
      return classified("causal", "CAUSAL_ATTRIBUTION");

    case "uncertainty":
      if (mentionsNonCausalLimitation(text)) {
        return classified("limitation", "NON_CAUSAL");
      }
      if (mentionsModelUncertainty(text)) {
        return classified("limitation", "MODEL_NOT_CERTAIN");
      }
      if (hasAny(text, ["khong dam bao", "khong bao dam", "no guarantee"])) {
        return classified("uncertainty", "NO_GUARANTEE");
      }
      if (hasAny(text, [
        "khong phai ket qua thuc te",
        "khong phan anh ket qua thuc te",
        "du doan cua mo hinh",
        "model prediction",
      ])) {
        return classified("uncertainty", "MODEL_PREDICTION_NOT_OUTCOME");
      }
      if (hasAny(text, [
        "bang chung",
        "du lieu duoc cung cap",
        "thong tin hien co",
        "cac yeu to duoc chon",
        "chi phan anh mot phan",
      ])) {
        return classified("uncertainty", "EVIDENCE_SCOPE_UNCERTAINTY");
      }
      if (hasAny(text, [
        "do tin cay",
        "muc do chac chan",
        "confidence",
      ])) {
        return classified("uncertainty", "CONFIDENCE_STRENGTH");
      }
      if (hasAny(text, [
        "co the",
        "kha nang",
        "xac suat",
        "du kien",
        "khong nhat thiet",
      ])) {
        return classified("uncertainty", "PROBABILITY_HEDGE");
      }
      return classified("uncertainty", "UNRESOLVED_UNCERTAINTY");

    case "distributed_evidence":
      if (claim.direction === "mixed" || hasAny(text, [
        "hai chieu",
        "trai chieu",
        "tang va giam",
      ])) {
        return classified("distributed_evidence", "MIXED_DIRECTIONS");
      }
      if (hasAny(text, ["shap", "phan bo", "tong do lon"])) {
        return classified("distributed_evidence", "DISTRIBUTED_SHAP_MASS");
      }
      if (hasAny(text, ["nhom khai niem", "khai niem", "concept"])) {
        return classified("distributed_evidence", "MULTIPLE_CONCEPTS");
      }
      if (hasAny(text, ["dac trung", "tin hieu", "yeu to", "features"])) {
        return classified("distributed_evidence", "MULTIPLE_FEATURES");
      }
      if (hasAny(text, [
        "tong hop",
        "ket hop cac phan",
        "xuyen suot cac phan",
      ])) {
        return classified("distributed_evidence", "CROSS_SECTION_SYNTHESIS");
      }
      return classified(
        "distributed_evidence",
        "UNRESOLVED_DISTRIBUTED_EVIDENCE",
      );

    case "recommendation":
      if (hasAny(text, [
        "xem xet boi con nguoi",
        "chuyen gia",
        "human review",
        "tham dinh them",
        "kiem tra thu cong",
      ])) {
        return classified("recommendation", "HUMAN_REVIEW");
      }
      if (hasAny(text, [
        "them thong tin",
        "bo sung thong tin",
        "xac minh them",
        "thu thap them",
        "doi chieu them",
      ])) {
        return classified("recommendation", "REQUEST_MORE_INFORMATION");
      }
      if (hasAny(text, [
        "than trong",
        "khong nen chi",
        "khong nen su dung",
        "khong nen dung",
        "khong su dung don le",
        "can ket hop",
        "chi nen tham khao",
        "can can nhac",
      ])) {
        return classified("recommendation", "CAUTION_IN_DECISION_USE");
      }
      if (hasAny(text, [
        "phe duyet khoan vay",
        "tu choi khoan vay",
        "cap tin dung",
        "khong cap tin dung",
        "giai ngan",
        "tang han muc",
        "giam han muc",
      ])) {
        return classified("recommendation", "PRESCRIPTIVE_FINANCIAL_ACTION");
      }
      return classified("recommendation", "UNRESOLVED_RECOMMENDATION");

    case "limitation":
      if (mentionsNonCausalLimitation(text)) {
        return classified("limitation", "NON_CAUSAL");
      }
      if (hasAny(text, [
        "khong phai tu van tai chinh",
        "khong phai loi khuyen tai chinh",
        "khong phai khuyen nghi tai chinh",
        "not financial advice",
      ])) {
        return classified("limitation", "NOT_FINANCIAL_ADVICE");
      }
      if (hasAny(text, [
        "khong nen la co so duy nhat",
        "khong nen la can cu duy nhat",
        "khong duoc dung lam can cu duy nhat",
        "khong phai co so duy nhat",
        "khong phai can cu duy nhat",
        "quyet dinh duy nhat",
        "khong the thay the tham dinh",
      ])) {
        return classified("limitation", "NOT_SOLE_DECISION_BASIS");
      }
      if (hasAny(text, [
        "khong day du",
        "chua day du",
        "han che bang chung",
        "chi dua tren",
        "chi phan anh mot phan",
        "khong bao gom tat ca",
        "cac yeu to duoc chon",
      ])) {
        return classified("limitation", "INCOMPLETE_EVIDENCE");
      }
      if (mentionsModelUncertainty(text)) {
        return classified("limitation", "MODEL_NOT_CERTAIN");
      }
      return classified("limitation", "UNRESOLVED_LIMITATION");
  }
}

export function classifyClaimSubtype(claim: AtomicClaimRecord): ClaimSubtype {
  return classifyClaimSemantics(claim).claim_subtype;
}

function classified(
  claimType: ClaimType,
  claimSubtype: ClaimSubtype,
): ClaimSemanticClassification {
  return {
    claim_type: claimType,
    claim_subtype: claimSubtype,
  };
}

function mentionsNonCausalLimitation(text: string): boolean {
  return hasAny(text, [
    "khong phai quan he nhan qua",
    "khong phan anh quan he nhan qua",
    "khong chung minh quan he nhan qua",
    "khong dong nghia voi nguyen nhan",
    "khong phai nguyen nhan thuc te",
    "not causal",
  ]);
}

function mentionsModelUncertainty(text: string): boolean {
  return hasAny(text, [
    "khong chac chan",
    "khong the chac chan",
    "mo hinh co the sai",
    "mo hinh khong the dam bao",
  ]);
}

function mentionsThreshold(text: string): boolean {
  return hasAny(text, ["nguong", "threshold", "cutoff"]);
}

function mentionsProbability(text: string): boolean {
  return /(?:\d+(?:[.,]\d+)?\s*%|(?:\bxac suat\b|\bprobabilit)[^\d]{0,20}\d)/u
    .test(text);
}

function mentionsPredictionLabel(text: string): boolean {
  return hasAny(text, [
    "rui ro cao",
    "rui ro thap",
    "nguy co cao",
    "nguy co thap",
    "vo no",
    "khong gap kho khan",
  ]);
}

function hasAny(text: string, values: readonly string[]): boolean {
  return values.some((value) => text.includes(value));
}

function normalizeText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase("en-US")
    .replace(/đ/gu, "d");
}
