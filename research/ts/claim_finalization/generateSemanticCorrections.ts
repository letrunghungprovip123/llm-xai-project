import type {
  AtomicClaimRecord,
  ClaimDirection,
  ClaimMagnitude,
  ClaimSubtype,
  ClaimType,
} from "../../../contracts/validation-claims";
import {
  readCsvStrict,
  readJsonlStrict,
  writeJsonlAtomic,
} from "../canonicalization/io";
import { classifyClaimSubtype } from "./claimSubtype";

type CorrectionOperation =
  | "DROP_FRAGMENT"
  | "RETYPE"
  | "SPLIT"
  | "UPDATE_DIRECTION"
  | "PRESERVE_EXPERIMENTAL_ERROR"
  | "REGRESSION_ONLY";

export type SemanticCorrectionTarget = {
  claim_type: ClaimType;
  claim_subtype: ClaimSubtype;
  subject_type: AtomicClaimRecord["subject_type"];
  feature_id: string | null;
  concept_id: string | null;
  direction: ClaimDirection;
  magnitude: ClaimMagnitude | null;
};

export type ClaimSemanticCorrection = {
  correction_schema_version: "claim_semantic_correction_v1";
  historical_claim_id: string;
  generation_id: string;
  source_section: AtomicClaimRecord["source_section"];
  source_text_sha256: string;
  semantic_case_name: string;
  operation: CorrectionOperation;
  target_claim_type: ClaimType;
  target_claim_subtype: ClaimSubtype;
  corrected_direction: ClaimDirection | null;
  rationale: string;
  source_classification: "MEASUREMENT_BUG" | "VALID_EXPERIMENTAL_ERROR";
  target_feature_id: string | null;
  target_concept_id: string | null;
  split_targets: SemanticCorrectionTarget[];
};

type ManualDecision = {
  operation: "RETYPE" | "SPLIT";
  target: SemanticCorrectionTarget;
  splitTargets?: SemanticCorrectionTarget[];
  rationale: string;
};

const MANUAL_FACTOR_DECISIONS: Record<string, ManualDecision> = {
  claim_0f14d4173aa906d2ddb389d570f0c3ca: retypeConcept(
    "previous_application_behavior",
    "The complete proposition identifies the previous-application concept, not the overall prediction.",
  ),
  claim_a15415a565055c4bf6430a198121dff5: splitDistributedMagnitude(
    "The text asserts direction for multiple weak factors and independently asserts weak aggregate strength.",
  ),
  claim_5182973979838e6479b7787ddd3e2b5e: retypeConcept(
    "installment_repayment_behavior",
    "The named repayment-behavior group resolves to the installment-repayment concept.",
  ),
  claim_5a3358661e68cf6f7a3cb4850ff606e0: {
    operation: "SPLIT",
    target: target("distributed_evidence", "CROSS_SECTION_SYNTHESIS", {
      subjectType: "evidence",
      direction: "increase_risk",
    }),
    splitTargets: [
      target("distributed_evidence", "CROSS_SECTION_SYNTHESIS", {
        subjectType: "evidence",
        direction: "increase_risk",
      }),
      target("magnitude", "OVERALL_BALANCE", {
        subjectType: "evidence",
        magnitude: "weak",
      }),
    ],
    rationale:
      "The complete sentence asserts an unresolved factor direction and separately says its contribution is weak; it is not an overall prediction.",
  },
  claim_30ab8915663af16954f6bdefa7c22c01: retypeFeature(
    "AMT_ANNUITY",
    "The generation factor list resolves 'số tiền trả góp' to AMT_ANNUITY.",
  ),
  claim_7b772619d8709404df4fa3bf5fed6701: retypeFeature(
    "installment_total_paid_amount",
    "The generation factor list identifies total installment paid amount as the sole decreasing feature.",
  ),
  claim_59402371a4f991de18bd2dea3e3c8023: retypeFeature(
    "installment_total_paid_amount",
    "The complete statement refers to the single repayment-behavior feature declared by its factor.",
  ),
  claim_a6bae3b9c2ce0820eecc837ae9820bd5: retypeConcept(
    "installment_repayment_behavior",
    "The statement refers to multiple members of the named installment-repayment concept.",
  ),
  claim_d6f7eee91bd7065e7f4814c8d1b00b45: retypeFeature(
    "annuity_to_credit_ratio",
    "The exact named ratio resolves to annuity_to_credit_ratio.",
  ),
  claim_b1a380737436714d0d8ef99ad321bf31: retypeFeature(
    "annuity_to_credit_ratio",
    "The generation declares annuity_to_credit_ratio as the sole decreasing loan-affordability feature.",
  ),
  claim_af8e4db3e8802db6a16a6aa786671524: retypeDistributed(
    "The text synthesizes installment_total_paid_amount and previous_avg_annuity across multiple evidence groups.",
  ),
  claim_38131a2293b11b3e32cde117a671d12e: retypeDistributed(
    "The proposition enumerates five distinct feature IDs and therefore requires multi-feature evidence validation.",
  ),
  claim_1b20e45a68fb2684f14bc863042eee89: retypeDistributed(
    "The proposition combines installment_total_paid_amount and installment_early_payment_count.",
  ),
  claim_03aa47720782fe70852bb66db0dd0dfc: retypeDistributed(
    "The proposition combines repayment amount, early-payment count, and annuity-to-credit ratio.",
  ),
};

const VALID_CONTRADICTION_IDS = [
  "claim_160f95761ea3ba5c8bce6ae4ae2d651e",
  "claim_3ed39c5f3e2a27198834538bd73058a1",
  "claim_8e6f172d33f47f961407f3610474533e",
] as const;

export async function generateClaimSemanticCorrections(input: {
  findingsCsvPath: string;
  historicalClaimsPath: string;
  outputPath: string;
}): Promise<{ row_count: number; category_counts: Record<string, number> }> {
  const findings = await readCsvStrict(input.findingsCsvPath);
  const historical = await readJsonlStrict<AtomicClaimRecord>(
    input.historicalClaimsPath,
  );
  const claimById = uniqueClaimMap(
    historical.records.map((record) => record.value),
  );
  const rows = findings.rows.slice();
  const findingIds = new Set(rows.map((row) => required(row.claim_id, "claim_id")));

  for (const claimId of VALID_CONTRADICTION_IDS) {
    if (findingIds.has(claimId)) continue;
    const claim = requireClaim(claimById, claimId);
    rows.push({
      classification: "VALID_EXPERIMENTAL_ERROR",
      severity: "BLOCKER",
      category: "VALID_OVERALL_PREDICTION_CONTRADICTION",
      claim_id: claim.claim_id,
      generation_id: claim.generation_id,
      claim_type: claim.claim_type,
      source_section: claim.source_section,
      source_text: claim.source_text,
      current_status: "CONTRADICTED",
      current_reason: "PREDICTION_LABEL_MISMATCH",
      detail:
        "Complete overall low-risk proposition contradicts the exposed high-risk package prediction.",
    });
  }

  const corrections = rows.map((row) =>
    buildCorrection(row, requireClaim(
      claimById,
      required(row.claim_id, "claim_id"),
    ))
  );
  assertReviewedPopulation(corrections);
  await writeJsonlAtomic(input.outputPath, corrections);

  return {
    row_count: corrections.length,
    category_counts: countBy(corrections, (row) => row.semantic_case_name),
  };
}

function buildCorrection(
  row: Record<string, string>,
  claim: AtomicClaimRecord,
): ClaimSemanticCorrection {
  if (required(row.generation_id, "generation_id") !== claim.generation_id) {
    throw new Error(`Generation join mismatch for ${claim.claim_id}.`);
  }
  if (required(row.source_section, "source_section") !== claim.source_section) {
    throw new Error(`Source-section join mismatch for ${claim.claim_id}.`);
  }
  if (required(row.source_text, "source_text") !== claim.source_text) {
    throw new Error(`Source-text join mismatch for ${claim.claim_id}.`);
  }

  const caseName = required(row.category, "category");
  const classification = required(row.classification, "classification");
  if (
    classification !== "MEASUREMENT_BUG"
    && classification !== "VALID_EXPERIMENTAL_ERROR"
  ) {
    throw new Error(`Unsupported classification for ${claim.claim_id}.`);
  }
  const sourceClassification:
    | "MEASUREMENT_BUG"
    | "VALID_EXPERIMENTAL_ERROR" = classification;

  const genericSubtype = classifyClaimSubtype(claim);
  const base = {
    correction_schema_version: "claim_semantic_correction_v1" as const,
    historical_claim_id: claim.claim_id,
    generation_id: claim.generation_id,
    source_section: claim.source_section,
    source_text_sha256: claim.source_text_sha256,
    semantic_case_name: caseName,
    source_classification: sourceClassification,
  };

  switch (caseName) {
    case "PREDICTION_SUBSPAN_FRAGMENT":
      return {
        ...base,
        operation: "DROP_FRAGMENT",
        target_claim_type: "prediction",
        target_claim_subtype: "OVERALL_PREDICTION_SUMMARY",
        corrected_direction: null,
        rationale:
          "Incomplete connective subspan is dropped because its generation already contains a complete overall prediction proposition.",
        target_feature_id: null,
        target_concept_id: null,
        split_targets: [],
      };
    case "EXPLICIT_PREDICTION_DIRECTION_NOT_ENCODED":
      return {
        ...base,
        operation: "UPDATE_DIRECTION",
        target_claim_type: "prediction",
        target_claim_subtype: "OVERALL_LABEL",
        corrected_direction: "decrease_risk",
        rationale:
          "The complete overall proposition explicitly states low credit risk.",
        target_feature_id: null,
        target_concept_id: null,
        split_targets: [],
      };
    case "VALID_OVERALL_PREDICTION_CONTRADICTION":
      return {
        ...base,
        operation: "PRESERVE_EXPERIMENTAL_ERROR",
        target_claim_type: "prediction",
        target_claim_subtype: "OVERALL_LABEL",
        corrected_direction: null,
        rationale:
          "Reviewed complete low-risk proposition must remain measurable against the exposed high-risk prediction.",
        target_feature_id: null,
        target_concept_id: null,
        split_targets: [],
      };
    case "FACTOR_STATEMENT_MISCLASSIFIED_AS_PREDICTION": {
      const decision = MANUAL_FACTOR_DECISIONS[claim.claim_id];
      if (!decision) {
        throw new Error(`Missing manual factor decision: ${claim.claim_id}.`);
      }
      return {
        ...base,
        operation: decision.operation,
        target_claim_type: decision.target.claim_type,
        target_claim_subtype: decision.target.claim_subtype,
        corrected_direction: decision.target.direction,
        rationale: decision.rationale,
        target_feature_id: decision.target.feature_id,
        target_concept_id: decision.target.concept_id,
        split_targets: decision.splitTargets ?? [],
      };
    }
    case "UNCERTAINTY_EXACT_MATCH_MISMATCH":
    case "CONCEPT_DIRECTION_FIRST_MATCH_AMBIGUITY":
      return {
        ...base,
        operation: "REGRESSION_ONLY",
        target_claim_type: claim.claim_type,
        target_claim_subtype: genericSubtype,
        corrected_direction: null,
        rationale:
          "Reviewed case is retained to verify the generic subtype validator; no per-row output patch is permitted.",
        target_feature_id: claim.feature_id,
        target_concept_id: claim.concept_id,
        split_targets: [],
      };
    default:
      throw new Error(`Unsupported reviewed category: ${caseName}.`);
  }
}

function retypeFeature(
  featureId: string,
  rationale: string,
): ManualDecision {
  return {
    operation: "RETYPE",
    target: target("feature_direction", "FEATURE_RISK_DIRECTION", {
      subjectType: "feature",
      featureId,
      direction: "decrease_risk",
    }),
    rationale,
  };
}

function retypeConcept(
  conceptId: string,
  rationale: string,
): ManualDecision {
  return {
    operation: "RETYPE",
    target: target("concept_direction", "CONCEPT_RISK_DIRECTION", {
      subjectType: "concept",
      conceptId,
      direction: "decrease_risk",
    }),
    rationale,
  };
}

function retypeDistributed(rationale: string): ManualDecision {
  return {
    operation: "RETYPE",
    target: target("distributed_evidence", "MULTIPLE_FEATURES", {
      subjectType: "evidence",
      direction: "decrease_risk",
    }),
    rationale,
  };
}

function splitDistributedMagnitude(rationale: string): ManualDecision {
  const targets = [
    target("distributed_evidence", "MULTIPLE_FEATURES", {
      subjectType: "evidence",
      direction: "increase_risk",
    }),
    target("magnitude", "OVERALL_BALANCE", {
      subjectType: "evidence",
      magnitude: "weak",
    }),
  ];
  return {
    operation: "SPLIT",
    target: targets[0],
    splitTargets: targets,
    rationale,
  };
}

function target(
  claimType: ClaimType,
  claimSubtype: ClaimSubtype,
  values: {
    subjectType: AtomicClaimRecord["subject_type"];
    featureId?: string;
    conceptId?: string;
    direction?: ClaimDirection;
    magnitude?: ClaimMagnitude;
  },
): SemanticCorrectionTarget {
  return {
    claim_type: claimType,
    claim_subtype: claimSubtype,
    subject_type: values.subjectType,
    feature_id: values.featureId ?? null,
    concept_id: values.conceptId ?? null,
    direction: values.direction ?? "unknown",
    magnitude: values.magnitude ?? null,
  };
}

function assertReviewedPopulation(
  corrections: readonly ClaimSemanticCorrection[],
): void {
  if (corrections.length !== 260) {
    throw new Error(`Reviewed population must contain 260 rows, found ${corrections.length}.`);
  }
  const expected = {
    UNCERTAINTY_EXACT_MATCH_MISMATCH: 63,
    CONCEPT_DIRECTION_FIRST_MATCH_AMBIGUITY: 161,
    FACTOR_STATEMENT_MISCLASSIFIED_AS_PREDICTION: 14,
    PREDICTION_SUBSPAN_FRAGMENT: 15,
    EXPLICIT_PREDICTION_DIRECTION_NOT_ENCODED: 4,
    VALID_OVERALL_PREDICTION_CONTRADICTION: 3,
  };
  const actual = countBy(corrections, (row) => row.semantic_case_name);
  for (const [category, expectedCount] of Object.entries(expected)) {
    if (actual[category] !== expectedCount) {
      throw new Error(
        `Reviewed category count mismatch for ${category}: `
          + `expected=${expectedCount}; actual=${actual[category] ?? 0}.`,
      );
    }
  }
  if (Object.keys(actual).length !== Object.keys(expected).length) {
    throw new Error(`Unexpected reviewed categories: ${JSON.stringify(actual)}.`);
  }
  const classifications = countBy(
    corrections,
    (row) => row.source_classification,
  );
  if (
    classifications.MEASUREMENT_BUG !== 257
    || classifications.VALID_EXPERIMENTAL_ERROR !== 3
  ) {
    throw new Error(
      `Reviewed classification counts mismatch: ${JSON.stringify(classifications)}.`,
    );
  }
  const ids = corrections.map((row) => row.historical_claim_id);
  if (new Set(ids).size !== ids.length) {
    throw new Error("Reviewed correction fixture contains duplicate claim IDs.");
  }
}

function uniqueClaimMap(
  claims: readonly AtomicClaimRecord[],
): Map<string, AtomicClaimRecord> {
  const result = new Map<string, AtomicClaimRecord>();
  for (const claim of claims) {
    if (result.has(claim.claim_id)) {
      throw new Error(`Duplicate historical claim ID: ${claim.claim_id}.`);
    }
    result.set(claim.claim_id, claim);
  }
  return result;
}

function requireClaim(
  claims: ReadonlyMap<string, AtomicClaimRecord>,
  claimId: string,
): AtomicClaimRecord {
  const claim = claims.get(claimId);
  if (!claim) throw new Error(`Reviewed claim is absent from history: ${claimId}.`);
  return claim;
}

function countBy<T>(
  values: readonly T[],
  key: (value: T) => string,
): Record<string, number> {
  const result: Record<string, number> = {};
  for (const value of values) {
    const itemKey = key(value);
    result[itemKey] = (result[itemKey] ?? 0) + 1;
  }
  return result;
}

function required(value: string | undefined, field: string): string {
  if (!value) throw new Error(`Missing reviewed finding field: ${field}.`);
  return value;
}

async function main(): Promise<void> {
  const args = new Map<string, string>();
  const values = process.argv.slice(2);
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!key?.startsWith("--") || !value) {
      throw new Error(`Invalid argument near ${key ?? "end"}.`);
    }
    args.set(key.slice(2), value);
  }
  const summary = await generateClaimSemanticCorrections({
    findingsCsvPath: required(args.get("findings-csv"), "findings-csv"),
    historicalClaimsPath: required(
      args.get("historical-claims"),
      "historical-claims",
    ),
    outputPath: required(args.get("output"), "output"),
  });
  console.log(JSON.stringify(summary, null, 2));
}

if (require.main === module) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.stack ?? error.message : String(error));
    process.exitCode = 1;
  });
}
