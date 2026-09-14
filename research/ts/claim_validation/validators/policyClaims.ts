import type { AtomicClaimRecordV3 as AtomicClaimRecord } from "../../../../contracts/validation-claims";
import { REASON_CODE } from "../constants";
import { emptyClaimValidationFactValues } from "../types";
import type { SemanticDecision, EvidenceView } from "./shared";
import {
  decision,
  isCertaintyOverclaim,
  isGuaranteeOverclaim,
} from "./shared";

export function validateUncertainty(
  claim: Extract<AtomicClaimRecord, { claim_type: "uncertainty" }>,
  view: EvidenceView,
): SemanticDecision {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.certainty = claim.certainty;
  expected.exposure_status = "EXPOSED";
  if (
    claim.certainty === "deterministic" &&
    isCertaintyOverclaim(claim.source_text)
  ) {
    observed.certainty = "hedged";
    observed.exposure_status = "EXPOSED";
    return decision(
      REASON_CODE.CERTAINTY_OVERCLAIM,
      expected,
      observed,
      "Claim uses prohibited certainty wording.",
      [],
      [],
      { policyStatus: "VIOLATION" },
    );
  }
  const source = uncertaintySource(claim, view);
  if (source === null) {
    observed.exposure_status = "SOURCE_MISSING";
    return decision(
      REASON_CODE.SEMANTIC_SOURCE_UNFROZEN,
      expected,
      observed,
      "Uncertainty subtype has no explicit confidence source or frozen threshold.",
      [],
      [],
      {
        validationCoverage: "SEMANTIC_REQUIRED",
        unresolvedFacts: ["confidence_strength_source"],
      },
    );
  }
  if (!source.grounded) {
    observed.exposure_status = "NOT_EXPOSED";
    return decision(
      REASON_CODE.UNCERTAINTY_NOT_GROUNDED,
      expected,
      observed,
      `No exact exposed source grounds ${claim.claim_subtype}.`,
      [],
      [source.sourceKey],
    );
  }
  observed.exposure_status = "EXPOSED";
  if (claim.claim_subtype === "PROBABILITY_HEDGE") {
    observed.certainty = "hedged";
    if (claim.certainty === "hedged") {
      return decision(
        REASON_CODE.EXACT_MATCH,
        expected,
        observed,
        "Probability hedge exactly matches exposed uncertainty policy.",
        [],
        [source.sourceKey],
      );
    }
    if (claim.certainty === "probabilistic") {
      return decision(
        REASON_CODE.NORMALIZED_MATCH,
        expected,
        observed,
        "Probabilistic certainty normalizes to the exposed hedge requirement.",
        ["probabilistic_to_hedged_uncertainty"],
        [source.sourceKey],
      );
    }
    return decision(
      REASON_CODE.UNCERTAINTY_NOT_GROUNDED,
      expected,
      observed,
      "Claim certainty does not match the exposed probability hedge.",
      [],
      [source.sourceKey],
    );
  }
  observed.certainty = claim.certainty;
  return decision(
    REASON_CODE.EXACT_MATCH,
    expected,
    observed,
    `${claim.claim_subtype} is grounded by its exact exposed policy source.`,
    [],
    [source.sourceKey],
  );
}

export function validateDistributedEvidence(
  claim: Extract<AtomicClaimRecord, { claim_type: "distributed_evidence" }>,
  view: EvidenceView,
): SemanticDecision {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.exposure_status = "EXPOSED";
  const support = distributedEvidenceSupport(claim, view);
  if (support === null) {
    observed.exposure_status = "SOURCE_MISSING";
    return decision(
      REASON_CODE.SEMANTIC_SOURCE_UNFROZEN,
      expected,
      observed,
      `${claim.claim_subtype} requires semantic review or an unfrozen threshold.`,
      [],
      [],
      {
        validationCoverage: "SEMANTIC_REQUIRED",
        unresolvedFacts: ["distributed_evidence_scope"],
      },
    );
  }
  if (support.grounded) {
    observed.exposure_status = "EXPOSED";
    return decision(
      REASON_CODE.EXACT_MATCH,
      expected,
      observed,
      `${claim.claim_subtype} matches its exact exposed evidence source.`,
      [],
      support.sourceKeys,
    );
  }
  observed.exposure_status = "NOT_EXPOSED";
  return decision(
    REASON_CODE.POLICY_RULE_NOT_APPLICABLE,
    expected,
    observed,
    `Exact exposed evidence does not ground ${claim.claim_subtype}.`,
    [],
    support.sourceKeys,
  );
}

export function validateRecommendation(
  claim: Extract<AtomicClaimRecord, { claim_type: "recommendation" }>,
  view: EvidenceView,
): SemanticDecision {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.exposure_status = "EXPOSED";
  observed.exposure_status = "SOURCE_MISSING";
  const prescriptive =
    claim.claim_subtype === "PRESCRIPTIVE_FINANCIAL_ACTION";
  const policyViolation =
    prescriptive &&
    view.package.prompt_payload.constraints.claim_policy
      .allow_financial_advice !== true;
  if (
    claim.certainty === "deterministic" &&
    isGuaranteeOverclaim(claim.source_text)
  ) {
    observed.exposure_status = "NOT_EXPOSED";
    return decision(
      REASON_CODE.GUARANTEE_OVERCLAIM,
      expected,
      observed,
      "Recommendation contains prohibited guarantee wording.",
      [],
      [],
      {
        policyStatus: "VIOLATION",
        additionalReasonCodes: policyViolation
          ? [REASON_CODE.UNSUPPORTED_RECOMMENDATION]
          : [],
      },
    );
  }
  return decision(
    REASON_CODE.SEMANTIC_SOURCE_UNFROZEN,
    expected,
    observed,
    "Recommendation evidence support requires semantic or human review.",
    [],
    ["policy:allow_financial_advice"],
    {
      policyStatus: policyViolation ? "VIOLATION" : "COMPLIANT",
      validationCoverage: "SEMANTIC_REQUIRED",
      unresolvedFacts: ["recommendation_evidence_support"],
      additionalReasonCodes: policyViolation
        ? [REASON_CODE.UNSUPPORTED_RECOMMENDATION]
        : [],
    },
  );
}

export function validateCausal(
  claim: Extract<AtomicClaimRecord, { claim_type: "causal" }>,
  view: EvidenceView,
): SemanticDecision {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.causal_strength = claim.causal_strength;
  expected.exposure_status = "EXPOSED";
  const allowed =
    view.package.prompt_payload.constraints.claim_policy?.allow_causal_claim ===
    true;
  observed.causal_strength = allowed ? claim.causal_strength : "associational";
  observed.exposure_status = allowed ? "EXPOSED" : "NOT_EXPOSED";
  if (claim.causal_strength === "causal" && !allowed) {
    return decision(
      REASON_CODE.CAUSAL_OVERCLAIM,
      expected,
      observed,
      "SHAP evidence does not support real-world causality.",
    );
  }
  return decision(
    allowed ? REASON_CODE.EXACT_MATCH : REASON_CODE.POLICY_RULE_NOT_APPLICABLE,
    expected,
    observed,
    allowed
      ? "Causal claim is explicitly allowed by exposed policy."
      : "No causal claim is applicable under the exposed policy.",
  );
}

export function validateLimitation(
  claim: Extract<AtomicClaimRecord, { claim_type: "limitation" }>,
  view: EvidenceView,
): SemanticDecision {
  const expected = emptyClaimValidationFactValues();
  const observed = emptyClaimValidationFactValues();
  expected.exposure_status = "EXPOSED";
  const support = limitationSupport(claim, view);
  observed.exposure_status = support.grounded ? "EXPOSED" : "NOT_EXPOSED";
  return decision(
    support.grounded
      ? REASON_CODE.EXACT_MATCH
      : REASON_CODE.POLICY_RULE_NOT_APPLICABLE,
    expected,
    observed,
    support.grounded
      ? `${claim.claim_subtype} matches its exact exposed policy source.`
      : `The exact policy source for ${claim.claim_subtype} is absent.`,
    [],
    [support.sourceKey],
  );
}

function uncertaintySource(
  claim: Extract<AtomicClaimRecord, { claim_type: "uncertainty" }>,
  view: EvidenceView,
): { grounded: boolean; sourceKey: string } | null {
  const payload = view.package.prompt_payload;
  switch (claim.claim_subtype) {
    case "PROBABILITY_HEDGE":
      return {
        grounded: payload.narrative_policy.must_include_uncertainty === true,
        sourceKey: "narrative_policy:must_include_uncertainty",
      };
    case "MODEL_PREDICTION_NOT_OUTCOME":
      return {
        grounded: payload.constraints.claim_policy.allow_true_label_claim === false,
        sourceKey: "claim_policy:allow_true_label_claim",
      };
    case "NO_GUARANTEE":
      return {
        grounded:
          payload.constraints.claim_policy.allow_absolute_decision_claim ===
            false ||
          payload.constraints.forbidden_rule_ids.includes(
            "forbid_certainty_wording",
          ),
        sourceKey: "claim_policy:allow_absolute_decision_claim",
      };
    case "EVIDENCE_SCOPE_UNCERTAINTY":
      return {
        grounded:
          payload.narrative_policy.must_include_partial_evidence_note === true ||
          payload.narrative_policy.must_not_claim_evidence_is_complete === true ||
          payload.evidence_level === "S0",
        sourceKey: "narrative_policy:must_include_partial_evidence_note",
      };
    case "CONFIDENCE_STRENGTH":
    case "UNRESOLVED_UNCERTAINTY":
      return null;
  }
}

function distributedEvidenceSupport(
  claim: Extract<AtomicClaimRecord, { claim_type: "distributed_evidence" }>,
  view: EvidenceView,
): { grounded: boolean; sourceKeys: string[] } | null {
  switch (claim.claim_subtype) {
    case "MULTIPLE_FEATURES":
      return {
        grounded: view.exposed_features.length > 1,
        sourceKeys: view.exposed_features.map(
          (feature) => `feature:${feature.feature_id}`,
        ),
      };
    case "MULTIPLE_CONCEPTS":
      return {
        grounded: view.aggregated_concepts.size > 1,
        sourceKeys: [...view.aggregated_concepts.keys()].map(
          (conceptId) => `concept:${conceptId}`,
        ),
      };
    case "MIXED_DIRECTIONS":
      return {
        grounded: hasMixedDirections(view),
        sourceKeys: [...view.aggregated_concepts.values()]
          .filter((concept) => concept.direction === "mixed")
          .flatMap((concept) => concept.source_record_keys),
      };
    case "DISTRIBUTED_SHAP_MASS":
      return {
        grounded:
          view.package.prompt_payload.narrative_policy
            .must_include_distributed_evidence_note === true,
        sourceKeys: ["narrative_policy:must_include_distributed_evidence_note"],
      };
    case "CROSS_SECTION_SYNTHESIS":
    case "UNRESOLVED_DISTRIBUTED_EVIDENCE":
      return null;
  }
}

function hasMixedDirections(view: EvidenceView): boolean {
  if (
    [...view.aggregated_concepts.values()].some(
      (concept) => concept.direction === "mixed",
    )
  ) {
    return true;
  }
  const directions = new Set(
    view.exposed_features.map((feature) =>
      feature.shap_value > 0
        ? "increase_risk"
        : feature.shap_value < 0
          ? "decrease_risk"
          : "neutral"
    ),
  );
  return directions.has("increase_risk") && directions.has("decrease_risk");
}

function limitationSupport(
  claim: Extract<AtomicClaimRecord, { claim_type: "limitation" }>,
  view: EvidenceView,
): { grounded: boolean; sourceKey: string } {
  const payload = view.package.prompt_payload;
  switch (claim.claim_subtype) {
    case "NON_CAUSAL":
      return {
        grounded:
          payload.constraints.claim_policy.allow_causal_claim === false ||
          payload.constraints.forbidden_rule_ids.includes(
            "forbid_real_world_causality",
          ),
        sourceKey: "claim_policy:allow_causal_claim",
      };
    case "NOT_FINANCIAL_ADVICE":
      return {
        grounded:
          payload.constraints.claim_policy.allow_financial_advice === false ||
          payload.constraints.forbidden_rule_ids.includes(
            "forbid_financial_advice",
          ),
        sourceKey: "claim_policy:allow_financial_advice",
      };
    case "NOT_SOLE_DECISION_BASIS":
      return {
        grounded:
          payload.constraints.claim_policy.allow_absolute_decision_claim ===
          false,
        sourceKey: "claim_policy:allow_absolute_decision_claim",
      };
    case "INCOMPLETE_EVIDENCE":
      return {
        grounded:
          payload.narrative_policy.must_include_partial_evidence_note === true ||
          payload.narrative_policy.must_not_claim_evidence_is_complete === true,
        sourceKey: "narrative_policy:must_include_partial_evidence_note",
      };
    case "MODEL_NOT_CERTAIN":
      return {
        grounded: payload.narrative_policy.must_include_uncertainty === true,
        sourceKey: "narrative_policy:must_include_uncertainty",
      };
    case "UNRESOLVED_LIMITATION":
      return {
        grounded: false,
        sourceKey: "claim_subtype:unresolved",
      };
  }
}
