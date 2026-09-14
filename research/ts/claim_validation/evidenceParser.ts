import type {
  ClaimValidationConstraints,
  ClaimValidationEvidencePackage,
  ClaimValidationPrediction,
  ClaimValidationPromptPayload,
  ClaimValidationTargetSemantics,
} from "./runtimeTypes";
import {
  requireBoolean,
  requireEvidenceLevel,
  requireFiniteNumber,
  requireObject,
  requireString,
  requireStringArray,
} from "./parseHelpers";
import {
  parseConceptEvidence,
  parseFeatureEvidence,
} from "./evidenceItemParser";
import {
  parseClaimPolicy,
  parseNarrativePolicy,
  parseSelectionContext,
} from "./evidencePolicyParser";

/** Parses every Evidence Package field consumed by deterministic validation. */
export function parseClaimValidationEvidence(
  value: unknown,
  context: string,
): ClaimValidationEvidencePackage {
  const item = requireObject(value, context);
  const packageId = requireString(item.package_id, `${context}.package_id`);
  const sourceIrId = requireString(item.source_ir_id, `${context}.source_ir_id`);
  const sourceEvidenceId = requireString(
    item.source_evidence_id,
    `${context}.source_evidence_id`,
  );
  const evidenceLevel = requireEvidenceLevel(
    item.evidence_level,
    `${context}.evidence_level`,
  );
  const prompt = requireObject(item.prompt_payload, `${context}.prompt_payload`);
  const promptPayload = parsePromptPayload(prompt, evidenceLevel, context);
  const packageTargetSemantics = hasCompleteTargetSemantics(item.target_semantics)
    ? parseTargetSemantics(
        item.target_semantics,
        `${context}.target_semantics`,
      )
    : undefined;
  const promptTargetSemantics = promptPayload.target_semantics;
  if (packageTargetSemantics && promptTargetSemantics) {
    assertTargetSemanticsMatch(
      packageTargetSemantics,
      promptTargetSemantics,
      context,
    );
  }
  return {
    package_id: packageId,
    source_ir_id: sourceIrId,
    source_evidence_id: sourceEvidenceId,
    evidence_level: evidenceLevel,
    ...(packageTargetSemantics
      ? { target_semantics: packageTargetSemantics }
      : {}),
    prompt_payload: promptPayload,
  };
}

function parsePromptPayload(
  prompt: Record<string, unknown>,
  evidenceLevel: ClaimValidationEvidencePackage["evidence_level"],
  context: string,
): ClaimValidationPromptPayload {
  const promptLevel = requireEvidenceLevel(
    prompt.evidence_level,
    `${context}.prompt_payload.evidence_level`,
  );
  if (promptLevel !== evidenceLevel) {
    throw new Error(`${context}.prompt_payload.evidence_level conflicts with package.`);
  }
  if (!Array.isArray(prompt.selected_evidence)) {
    throw new Error(`${context}.prompt_payload.selected_evidence must be an array.`);
  }
  if (!Array.isArray(prompt.concept_evidence)) {
    throw new Error(`${context}.prompt_payload.concept_evidence must be an array.`);
  }
  const constraints = requireObject(
    prompt.constraints,
    `${context}.prompt_payload.constraints`,
  );
  return {
    evidence_level: evidenceLevel,
    prediction: parsePrediction(
      prompt.prediction,
      `${context}.prompt_payload.prediction`,
    ),
    ...(prompt.target_semantics === undefined
      ? {}
      : {
          target_semantics: parseTargetSemantics(
            prompt.target_semantics,
            `${context}.prompt_payload.target_semantics`,
          ),
        }),
    selected_evidence: prompt.selected_evidence.map((feature, index) =>
      parseFeatureEvidence(
        feature,
        `${context}.prompt_payload.selected_evidence[${index}]`,
      ),
    ),
    concept_evidence: prompt.concept_evidence.map((concept, index) =>
      parseConceptEvidence(
        concept,
        `${context}.prompt_payload.concept_evidence[${index}]`,
      ),
    ),
    selection_context: parseSelectionContext(
      prompt.selection_context,
      `${context}.prompt_payload.selection_context`,
    ),
    narrative_policy: parseNarrativePolicy(
      prompt.narrative_policy,
      `${context}.prompt_payload.narrative_policy`,
    ),
    constraints: parseConstraints(constraints, context),
  };
}

function parseConstraints(
  constraints: Record<string, unknown>,
  context: string,
): ClaimValidationConstraints {
  const prefix = `${context}.prompt_payload.constraints`;
  return {
    allowed_feature_ids: requireStringArray(
      constraints.allowed_feature_ids,
      `${prefix}.allowed_feature_ids`,
    ),
    allowed_concept_ids: requireStringArray(
      constraints.allowed_concept_ids,
      `${prefix}.allowed_concept_ids`,
    ),
    forbidden_rule_ids: requireStringArray(
      constraints.forbidden_rule_ids,
      `${prefix}.forbidden_rule_ids`,
    ),
    claim_policy: parseClaimPolicy(
      constraints.claim_policy,
      `${prefix}.claim_policy`,
    ),
  };
}

function hasCompleteTargetSemantics(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const semantics = value as Record<string, unknown>;
  return [
    "positive_label",
    "negative_label",
    "prediction_subject",
    "positive_display_name",
    "negative_display_name",
    "positive_direction_phrase",
    "negative_direction_phrase",
  ].every((key) => typeof semantics[key] === "string" && semantics[key]!.trim());
}

function parseTargetSemantics(
  value: unknown,
  context: string,
): ClaimValidationTargetSemantics {
  const semantics = requireObject(value, context);
  const result: ClaimValidationTargetSemantics = {
    positive_label: requireString(
      semantics.positive_label,
      `${context}.positive_label`,
    ),
    negative_label: requireString(
      semantics.negative_label,
      `${context}.negative_label`,
    ),
    prediction_subject: requireString(
      semantics.prediction_subject,
      `${context}.prediction_subject`,
    ),
    positive_display_name: requireString(
      semantics.positive_display_name,
      `${context}.positive_display_name`,
    ),
    negative_display_name: requireString(
      semantics.negative_display_name,
      `${context}.negative_display_name`,
    ),
    positive_direction_phrase: requireString(
      semantics.positive_direction_phrase,
      `${context}.positive_direction_phrase`,
    ),
    negative_direction_phrase: requireString(
      semantics.negative_direction_phrase,
      `${context}.negative_direction_phrase`,
    ),
  };
  if (result.positive_label === result.negative_label) {
    throw new Error(`${context} positive_label and negative_label must differ.`);
  }
  const optionalStringFields = ["canonical_name", "semantic_name"] as const;
  for (const key of optionalStringFields) {
    if (semantics[key] !== undefined) {
      result[key] = requireString(semantics[key], `${context}.${key}`);
    }
  }
  if (semantics.prediction_horizon !== undefined) {
    if (semantics.prediction_horizon === null) {
      result.prediction_horizon = null;
    } else {
      result.prediction_horizon = requireString(
        semantics.prediction_horizon,
        `${context}.prediction_horizon`,
      );
    }
  }
  if (semantics.positive_class !== undefined) {
    result.positive_class = requireFiniteNumber(
      semantics.positive_class,
      `${context}.positive_class`,
    );
  }
  if (semantics.negative_class !== undefined) {
    result.negative_class = requireFiniteNumber(
      semantics.negative_class,
      `${context}.negative_class`,
    );
  }
  return result;
}

function assertTargetSemanticsMatch(
  left: ClaimValidationTargetSemantics,
  right: ClaimValidationTargetSemantics,
  context: string,
): void {
  for (const key of [
    "positive_label",
    "negative_label",
    "prediction_subject",
    "positive_display_name",
    "negative_display_name",
    "positive_direction_phrase",
    "negative_direction_phrase",
  ] as const) {
    if (left[key] !== right[key]) {
      throw new Error(`${context} target semantics conflict for ${key}.`);
    }
  }
}

function parsePrediction(
  value: unknown,
  context: string,
): ClaimValidationPrediction {
  const prediction = requireObject(value, context);
  const probability = requireFiniteNumber(
    prediction.probability,
    `${context}.probability`,
  );
  const threshold = requireFiniteNumber(
    prediction.threshold,
    `${context}.threshold`,
  );
  if (probability < 0 || probability > 1) {
    throw new Error(`${context}.probability must be within [0, 1].`);
  }
  if (threshold < 0 || threshold > 1) {
    throw new Error(`${context}.threshold must be within [0, 1].`);
  }
  return {
    predicted_label: requireString(
      prediction.predicted_label,
      `${context}.predicted_label`,
    ),
    probability,
    threshold,
    probability_display: requireString(
      prediction.probability_display,
      `${context}.probability_display`,
    ),
    probability_percent_display: requireString(
      prediction.probability_percent_display,
      `${context}.probability_percent_display`,
    ),
    threshold_display: requireString(
      prediction.threshold_display,
      `${context}.threshold_display`,
    ),
    threshold_percent_display: requireString(
      prediction.threshold_percent_display,
      `${context}.threshold_percent_display`,
    ),
    threshold_comparison: requireString(
      prediction.threshold_comparison,
      `${context}.threshold_comparison`,
    ),
    is_above_threshold: requireBoolean(
      prediction.is_above_threshold,
      `${context}.is_above_threshold`,
    ),
  };
}
