import assert from "node:assert/strict";
import test from "node:test";

import { parseClaimValidationEvidence } from "../../../research/ts/claim_validation/evidenceParser";
import { parseClaimValidationGeneration } from "../../../research/ts/claim_validation/generationParser";

test("generation boundary parses all validation and aggregation fields", () => {
  const parsed = parseClaimValidationGeneration(validGeneration(), "generation");
  assert.equal(parsed.generation_id, "generation_001");
  assert.equal(parsed.generation_record.package_id, "package_001");
});

test("generation boundary rejects malformed fields before validation", async (t) => {
  const cases: Array<[string, (value: Record<string, unknown>) => void]> = [
    ["missing generation_id", (value) => delete value.generation_id],
    ["empty package_id", (value) => { value.package_id = ""; }],
    ["invalid evidence level", (value) => { value.evidence_level = "S7"; }],
    ["invalid repeat_id", (value) => { value.repeat_id = 0; }],
    ["missing nested record", (value) => delete value.generation_record],
    ["nested identity conflict", (value) => {
      const nested = value.generation_record;
      if (isRecord(nested)) nested.package_id = "different_package";
    }],
    ["malformed unusable metadata", (value) => {
      value.usable = false;
      value.usability_reason_codes = [];
    }],
    ["non-boolean schema flag", (value) => { value.schema_valid = "true"; }],
  ];
  for (const [name, mutate] of cases) {
    await t.test(name, () => {
      const value = validGeneration();
      mutate(value);
      assert.throws(() => parseClaimValidationGeneration(value, "generation"));
    });
  }
});

test("evidence boundary parses every nested field used by validators", () => {
  const parsed = parseClaimValidationEvidence(validEvidence(), "evidence");
  assert.equal(parsed.prompt_payload.prediction.probability, 0.8);
  assert.equal(parsed.prompt_payload.selected_evidence[0]?.feature_id, "feature_a");
  assert.equal(parsed.prompt_payload.concept_evidence[0]?.concept, "concept_a");
});

test("evidence boundary rejects malformed nested fields before validation", async (t) => {
  const cases: Array<[string, (value: Record<string, unknown>) => void]> = [
    ["missing prompt_payload", (value) => delete value.prompt_payload],
    ["missing prediction object", (value) => {
      const prompt = objectField(value, "prompt_payload");
      delete prompt.prediction;
    }],
    ["non-finite probability", (value) => {
      const prediction = nestedObject(value, "prompt_payload", "prediction");
      prediction.probability = Number.NaN;
    }],
    ["invalid threshold", (value) => {
      const prediction = nestedObject(value, "prompt_payload", "prediction");
      prediction.threshold = 2;
    }],
    ["selected_evidence not array", (value) => {
      objectField(value, "prompt_payload").selected_evidence = {};
    }],
    ["malformed selected feature", (value) => {
      objectField(value, "prompt_payload").selected_evidence = [{ feature_id: "" }];
    }],
    ["concept_evidence not array", (value) => {
      objectField(value, "prompt_payload").concept_evidence = {};
    }],
    ["malformed concept", (value) => {
      objectField(value, "prompt_payload").concept_evidence = [{ concept: "" }];
    }],
    ["allowed_feature_ids not string array", (value) => {
      nestedObject(value, "prompt_payload", "constraints").allowed_feature_ids = [1];
    }],
    ["allowed_concept_ids not string array", (value) => {
      nestedObject(value, "prompt_payload", "constraints").allowed_concept_ids = [null];
    }],
    ["invalid direction", (value) => {
      const prompt = objectField(value, "prompt_payload");
      const features = prompt.selected_evidence;
      if (Array.isArray(features) && isRecord(features[0])) {
        features[0].direction = "sideways";
      }
    }],
    ["non-finite shap_value", (value) => {
      const prompt = objectField(value, "prompt_payload");
      const features = prompt.selected_evidence;
      if (Array.isArray(features) && isRecord(features[0])) {
        features[0].shap_value = Number.POSITIVE_INFINITY;
      }
    }],
    ["invalid rank", (value) => {
      const prompt = objectField(value, "prompt_payload");
      const features = prompt.selected_evidence;
      if (Array.isArray(features) && isRecord(features[0])) {
        features[0].rank = 1.5;
      }
    }],
  ];
  for (const [name, mutate] of cases) {
    await t.test(name, () => {
      const value = validEvidence();
      mutate(value);
      assert.throws(() => parseClaimValidationEvidence(value, "evidence"));
    });
  }
});

function validGeneration(): Record<string, unknown> {
  return {
    canonical_schema_version: "generation_index_v1",
    generation_id: "generation_001",
    package_id: "package_001",
    source_evidence_id: "evidence_001",
    source_ir_id: "ir_001",
    model_id: "model_001",
    case_id: "case_001",
    repeat_id: 1,
    evidence_level: "S3",
    usable: true,
    runtime_status: "SUCCESS",
    finish_reason: "stop",
    truncated_response: false,
    raw_json_parse_success: true,
    schema_valid: true,
    usability_reason_codes: [],
    generation_record: {
      generation_id: "generation_001",
      package_id: "package_001",
      source_evidence_id: "evidence_001",
      source_ir_id: "ir_001",
      model_id: "model_001",
      repeat_id: 1,
      evidence_level: "S3",
    },
  };
}

function validEvidence(): Record<string, unknown> {
  const feature = validFeature();
  return {
    package_id: "package_001",
    source_ir_id: "ir_001",
    source_evidence_id: "evidence_001",
    evidence_level: "S3",
    prompt_payload: {
      evidence_level: "S3",
      prediction: {
        predicted_label: "high_default_risk",
        probability: 0.8,
        threshold: 0.5,
        probability_display: "0.8000",
        probability_percent_display: "80.00%",
        threshold_display: "0.5000",
        threshold_percent_display: "50.00%",
        threshold_comparison: "above_or_equal_threshold",
        is_above_threshold: true,
      },
      selected_evidence: [feature],
      concept_evidence: [{
        concept: "concept_a",
        direction: "increases_risk",
        representative_feature: feature,
        supporting_features: [feature],
        selected_feature_ids: ["feature_a"],
        feature_count: 1,
        selected_abs_shap_sum: 0.2,
      }],
      selection_context: {
        selected_evidence_count: 1,
        concept_group_count: 1,
      },
      narrative_policy: { must_include_uncertainty: true },
      constraints: {
        allowed_feature_ids: ["feature_a"],
        allowed_concept_ids: ["concept_a"],
        forbidden_rule_ids: ["forbid_real_world_causality"],
        claim_policy: {
          allow_prediction_claim: true,
          allow_feature_claim: true,
          allow_concept_claim: true,
        },
      },
    },
  };
}

function validFeature(): Record<string, unknown> {
  return {
    feature_id: "feature_a",
    shap_value: 0.2,
    abs_shap_value: 0.2,
    direction: "increases_risk",
    rank: 1,
    strength: "moderate",
    value: 2,
  };
}

function objectField(
  value: Record<string, unknown>,
  field: string,
): Record<string, unknown> {
  const item = value[field];
  if (!isRecord(item)) throw new Error(`Fixture field ${field} is not an object.`);
  return item;
}

function nestedObject(
  value: Record<string, unknown>,
  outer: string,
  inner: string,
): Record<string, unknown> {
  return objectField(objectField(value, outer), inner);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
