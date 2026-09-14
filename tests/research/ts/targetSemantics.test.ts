import assert from "node:assert/strict";
import test from "node:test";

import type {
  EvidencePackage,
  ModelConfig,
  TargetSemanticsPayload,
} from "../../../contracts/narrative";
import { buildPrompt } from "../../../research/ts/narrative/promptBuilder";
import { parseClaimValidationEvidence } from "../../../research/ts/claim_validation/evidenceParser";
import { validateClaimDeterministically } from "../../../research/ts/claim_validation/validators";
import { extractCaseId } from "../../../research/ts/canonicalization/contracts";
import { testClaim } from "./claimValidationTestFixtures";

const TARGET: TargetSemanticsPayload = {
  canonical_name: "target",
  semantic_name: "serious_delinquency_within_24_months",
  prediction_horizon: "24_months",
  positive_class: 1,
  negative_class: 0,
  positive_label: "high_serious_delinquency_risk",
  negative_label: "low_serious_delinquency_risk",
  prediction_subject: "rủi ro trễ hạn nghiêm trọng trong 24 tháng",
  positive_display_name: "rủi ro trễ hạn nghiêm trọng trong 24 tháng cao",
  negative_display_name: "rủi ro trễ hạn nghiêm trọng trong 24 tháng thấp",
  positive_direction_phrase: "rủi ro cao",
  negative_direction_phrase: "rủi ro thấp",
};

const MODEL: ModelConfig = {
  id: "template",
  provider: "template",
  family: "template",
  runtime: "template",
  remote_model_id: "template",
  revision: "fixture",
  output_constraint_mode: "json_object",
  enabled: true,
};

function commonPackage(): EvidencePackage {
  return {
    package_id: "pkg::dataset_b::replication_v1::S0::ir-1",
    source_ir_id: "ir::dataset_b::replication_v1::case-1",
    source_evidence_id: "xai::dataset_b::case-1",
    evidence_level: "S0",
    dataset: { dataset_id: "dataset_b", dataset_version: "v1" },
    experiment: { experiment_id: "replication_v1" },
    case: {
      case_id: "case::dataset_b::borrower::1",
      source_entity_id: "1",
      entity_type: "borrower",
      case_type: "top_high_risk",
    },
    target_semantics: TARGET,
    prompt_payload: {
      evidence_level: "S0",
      target_semantics: TARGET,
      prediction: {
        predicted_class: 1,
        predicted_label: TARGET.positive_label,
        probability: 0.82,
        probability_display: "0.8200",
        probability_percent_display: "82.00%",
        threshold: 0.5,
        threshold_display: "0.5000",
        threshold_percent_display: "50.00%",
        threshold_comparison: "above_or_equal_threshold",
        is_above_threshold: true,
      },
      selected_evidence: [],
      concept_evidence: [],
      selection_context: { selected_evidence_count: 0 },
      narrative_policy: { must_include_uncertainty: true },
      constraints: {
        allowed_feature_ids: [],
        allowed_concept_ids: [],
        forbidden_rule_ids: [],
        claim_policy: { allow_prediction_claim: true },
      },
    },
  };
}

test("common narrative prompt is driven by target semantics", () => {
  const prompt = buildPrompt(commonPackage(), MODEL, "target_semantics_test_v1");
  assert.match(prompt.message_text, /TARGET SEMANTICS/);
  assert.match(prompt.message_text, /trễ hạn nghiêm trọng trong 24 tháng/);
  assert.match(prompt.message_text, /rủi ro cao/);
  assert.match(prompt.message_text, /high_serious_delinquency_risk/);
});

test("legacy narrative prompt keeps frozen Home Credit system wording without semantics", () => {
  const packageItem = commonPackage();
  delete packageItem.target_semantics;
  delete packageItem.prompt_payload.target_semantics;
  delete packageItem.dataset;
  delete packageItem.experiment;
  delete packageItem.case;
  packageItem.package_id = "pkg_S0_ir_legacy";
  packageItem.source_ir_id = "ir_legacy";
  packageItem.prompt_payload.prediction.predicted_label = "high_default_risk";

  const prompt = buildPrompt(packageItem, MODEL, "legacy_test_v1");
  assert.doesNotMatch(prompt.message_text, /TARGET SEMANTICS/);
  assert.match(
    prompt.messages[0].content,
    /Không khẳng định chắc chắn khách hàng sẽ hoặc sẽ không gặp khó khăn trả nợ\./,
  );
});

test("deterministic prediction validator uses dataset target labels", () => {
  const parsed = parseClaimValidationEvidence(commonPackage(), "fixture");
  const positive = validateClaimDeterministically(
    testClaim({
      claim_type: "prediction",
      claim_subtype: "OVERALL_LABEL",
      direction: "increase_risk",
    }),
    parsed,
  );
  assert.equal(positive.reasonCode, "EXACT_MATCH");
  assert.equal(positive.expected.prediction_label, TARGET.positive_label);
  assert.equal(positive.observed.prediction_label, TARGET.positive_label);

  const negative = validateClaimDeterministically(
    testClaim({
      claim_type: "prediction",
      claim_subtype: "OVERALL_LABEL",
      direction: "decrease_risk",
    }),
    parsed,
  );
  assert.equal(negative.reasonCode, "PREDICTION_LABEL_MISMATCH");
  assert.equal(negative.expected.prediction_label, TARGET.negative_label);
});

test("canonicalization prefers dataset-aware case_id but preserves legacy fallback", () => {
  assert.equal(
    extractCaseId({ case_metadata: { case_id: "case::dataset_b::borrower::1" } } as never),
    "case::dataset_b::borrower::1",
  );
  assert.equal(
    extractCaseId({ case_metadata: { customer_id: 156227 } } as never),
    "156227",
  );
});
