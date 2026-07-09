// src/server/validator/faithfulness-validator.ts

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const DEFAULT_CLAIM_EXTRACTIONS_PATH =
  "data/reports/faithfulness_validation/evaluation/llm_api/claim_extractions.jsonl";

const DEFAULT_EXPLANATION_IR_PATH =
  "data/reports/explanation_ir/evaluation/explanation_ir.jsonl";

const DEFAULT_OUTPUT_DIR =
  "data/reports/faithfulness_validation/evaluation/llm_api";

type ValidationStatus = "PASS" | "PASS_WITH_WARN" | "FAIL";

type ClaimValidationStatus = "PASS" | "WARN" | "FAIL";

type ClaimSeverity = "info" | "warning" | "error";

type AnyRecord = Record<string, unknown>;

type ClaimExtractionArtifact = {
  claim_extraction_id?: string;
  created_at?: string;
  ir_id?: string;
  explanation_id?: string;
  customer_id?: string | null;
  generator_type?: string;
  source_input_hash?: string;
  claim_extraction?: {
    claims?: ExtractedClaim[];
    claim_count?: number;
  };
};

type ExtractedClaim = {
  claim_id?: string;
  section?: string;
  claim_type?: string;
  text?: string;
  direction?: string | null;
  value_mentioned?: unknown;
  evidence_refs?: unknown[];
  confidence?: string;
};

type IrFeature = {
  feature_id: string;
  display_name: string;
  concept_id: string | null;
  contribution_value: number | null;
  contribution_direction:
    | "increases_risk"
    | "decreases_risk"
    | "neutral"
    | "unknown";
  rank: number | null;
  aliases: string[];
};

type IrSummary = {
  ir_id: string;
  source_record_index: number;
  customer_id: string | null;
  prediction_label: string | null;
  prediction_probability: number | null;
  prediction_probability_percent: number | null;
  threshold: number | null;
  features: IrFeature[];
  concept_ids: string[];
  concept_names: string[];
  raw: AnyRecord;
};

type ClaimCheck = {
  rule_id: string;
  status: ClaimValidationStatus;
  severity: ClaimSeverity;
  message: string;
  evidence?: Record<string, unknown>;
};

type ClaimValidationResult = {
  claim_id: string;
  claim_type: string;
  section: string | null;
  text: string;
  status: ClaimValidationStatus;
  checks: ClaimCheck[];
  matched_features: Array<{
    feature_id: string;
    display_name: string;
    contribution_value: number | null;
    contribution_direction: string;
    rank: number | null;
  }>;
};

type RecordValidationResult = {
  validation_id: string;
  created_at: string;
  ir_id: string;
  explanation_id: string;
  claim_extraction_id: string | null;
  customer_id: string | null;
  status: ValidationStatus;
  summary: {
    total_claims: number;
    pass_claims: number;
    warn_claims: number;
    fail_claims: number;
    total_checks: number;
    pass_checks: number;
    warn_checks: number;
    fail_checks: number;
  };
  join: {
    claim_ir_id: string;
    ir_found: boolean;
    ir_source_record_index: number | null;
  };
  validation_rules: {
    validator_version: string;
    mode: "rule_based_ir_faithfulness";
    llm_as_judge: false;
  };
  claim_results: ClaimValidationResult[];
};

type J2Summary = {
  report_name: string;
  created_at: string;
  status: ValidationStatus;
  input_paths: {
    claim_extractions_path: string;
    explanation_ir_path: string;
  };
  output_paths: {
    validation_jsonl_path: string;
    summary_json_path: string;
    failures_json_path: string;
    report_md_path: string;
  };
  counts: {
    claim_extraction_records: number;
    explanation_ir_records: number;
    validated_records: number;
    pass_records: number;
    pass_with_warn_records: number;
    fail_records: number;
    total_claims: number;
    pass_claims: number;
    warn_claims: number;
    fail_claims: number;
  };
  join_quality: {
    joined_records: number;
    missing_ir_records: number;
    missing_ir_ids: string[];
  };
  validator: {
    validator_version: string;
    mode: "rule_based_ir_faithfulness";
    llm_as_judge: false;
  };
};

const VALIDATOR_VERSION = "batch_j2_faithfulness_validator_v1.1";

export async function runJ2FaithfulnessValidation(): Promise<J2Summary> {
  const options = resolveOptions();

  await mkdir(options.outputDir, { recursive: true });

  const validationJsonlPath = path.join(
    options.outputDir,
    "faithfulness_validation.jsonl",
  );

  const summaryJsonPath = path.join(
    options.outputDir,
    "faithfulness_validation_summary.json",
  );

  const failuresJsonPath = path.join(
    options.outputDir,
    "faithfulness_validation_failures.json",
  );

  const reportMdPath = path.join(
    options.outputDir,
    "faithfulness_validation_report.md",
  );

  console.log("Running Batch J.2 Faithfulness Validation...");
  console.log("Claim extractions:", options.claimExtractionsPath);
  console.log("Explanation IR:", options.explanationIrPath);
  console.log("Output dir:", options.outputDir);
  console.log("Validator:", VALIDATOR_VERSION);
  console.log("LLM-as-judge: false");

  const claimArtifacts = await readJsonl<ClaimExtractionArtifact>(
    options.claimExtractionsPath,
  );

  const irRecords = await readJsonl<AnyRecord>(options.explanationIrPath);
  const irSummaries = irRecords.map((record, index) =>
    buildIrSummary(record, index),
  );

  const irById = new Map<string, IrSummary>();

  for (const ir of irSummaries) {
    if (ir.ir_id) {
      irById.set(ir.ir_id, ir);
    }
  }

  const validationResults: RecordValidationResult[] = [];

  for (let index = 0; index < claimArtifacts.length; index++) {
    const artifact = claimArtifacts[index];
    const claimIrId = getString(artifact.ir_id);
    const explanationId = getString(artifact.explanation_id);
    const claimExtractionId = getString(artifact.claim_extraction_id) || null;
    const customerId = getNullableString(artifact.customer_id);

    const ir = irById.get(claimIrId) ?? null;

    const claims = Array.isArray(artifact.claim_extraction?.claims)
      ? artifact.claim_extraction.claims
      : [];

    const claimResults = claims.map((claim, claimIndex) =>
      validateClaim({
        claim,
        claimIndex,
        ir,
      }),
    );

    const summary = summarizeClaimResults(claimResults);

    const recordStatus = determineRecordStatus({
      irFound: Boolean(ir),
      summary,
    });

    const result: RecordValidationResult = {
      validation_id: buildValidationId(explanationId, claimIrId, index),
      created_at: new Date().toISOString(),
      ir_id: claimIrId,
      explanation_id: explanationId,
      claim_extraction_id: claimExtractionId,
      customer_id: customerId,
      status: recordStatus,
      summary,
      join: {
        claim_ir_id: claimIrId,
        ir_found: Boolean(ir),
        ir_source_record_index: ir?.source_record_index ?? null,
      },
      validation_rules: {
        validator_version: VALIDATOR_VERSION,
        mode: "rule_based_ir_faithfulness",
        llm_as_judge: false,
      },
      claim_results: claimResults,
    };

    validationResults.push(result);

    console.log(
      `[${index + 1}/${claimArtifacts.length}] ${recordStatus} ${explanationId}`,
    );
  }

  const failures = validationResults.filter(
    (result) => result.status === "FAIL",
  );

  const summary = buildJ2Summary({
    options,
    claimArtifacts,
    irRecords,
    validationResults,
    validationJsonlPath,
    summaryJsonPath,
    failuresJsonPath,
    reportMdPath,
  });

  await writeJsonl(validationJsonlPath, validationResults);
  await writeFile(summaryJsonPath, JSON.stringify(summary, null, 2), "utf8");
  await writeFile(failuresJsonPath, JSON.stringify(failures, null, 2), "utf8");
  await writeFile(
    reportMdPath,
    buildMarkdownReport(summary, validationResults),
    "utf8",
  );

  console.log("\nBatch J.2 finished.");
  console.log(JSON.stringify(summary, null, 2));

  if (summary.status === "FAIL") {
    process.exitCode = 1;
  }

  return summary;
}

function resolveOptions(): {
  claimExtractionsPath: string;
  explanationIrPath: string;
  outputDir: string;
} {
  return {
    claimExtractionsPath:
      process.env.J2_CLAIM_EXTRACTIONS_PATH ?? DEFAULT_CLAIM_EXTRACTIONS_PATH,
    explanationIrPath:
      process.env.J2_EXPLANATION_IR_PATH ?? DEFAULT_EXPLANATION_IR_PATH,
    outputDir: process.env.J2_OUTPUT_DIR ?? DEFAULT_OUTPUT_DIR,
  };
}

function validateClaim(input: {
  claim: ExtractedClaim;
  claimIndex: number;
  ir: IrSummary | null;
}): ClaimValidationResult {
  const { claim, claimIndex, ir } = input;

  const claimId = getString(claim.claim_id) || `claim_${claimIndex + 1}`;
  const claimType = getString(claim.claim_type) || "unknown";
  const section = getNullableString(claim.section);
  const text = getString(claim.text);
  const direction = normalizeDirection(getNullableString(claim.direction));

  const checks: ClaimCheck[] = [];

  if (!text) {
    checks.push({
      rule_id: "J2_SCHEMA_CLAIM_TEXT_REQUIRED",
      status: "FAIL",
      severity: "error",
      message: "Claim text is missing.",
    });
  } else {
    checks.push({
      rule_id: "J2_SCHEMA_CLAIM_TEXT_REQUIRED",
      status: "PASS",
      severity: "info",
      message: "Claim text is present.",
    });
  }

  if (!ir) {
    checks.push({
      rule_id: "J2_JOIN_IR_REQUIRED",
      status: "FAIL",
      severity: "error",
      message:
        "Cannot validate this claim because matching Explanation IR was not found.",
    });

    return {
      claim_id: claimId,
      claim_type: claimType,
      section,
      text,
      status: determineClaimStatus(checks),
      checks,
      matched_features: [],
    };
  }

  const matchedFeatures = matchFeaturesForClaim(claim, text, ir.features);

  if (isPredictionClaim(claimType)) {
    checks.push(...validatePredictionClaim(text, ir));
  }

  if (isFeatureOrContributionClaim(claimType)) {
    checks.push(...validateFeatureGroundingClaim(text, matchedFeatures, ir));

    if (direction !== "unknown" && matchedFeatures.length > 0) {
      checks.push(...validateDirectionClaim(direction, matchedFeatures));
    }
  }

  if (isConceptClaim(claimType)) {
    checks.push(...validateConceptClaim(text, ir));
  }

  if (isLimitationClaim(claimType)) {
    checks.push(...validateLimitationClaim(text));
  }

  if (!isKnownClaimType(claimType)) {
    checks.push({
      rule_id: "J2_CLAIM_TYPE_UNKNOWN",
      status: "WARN",
      severity: "warning",
      message: `Unknown claim_type "${claimType}". The claim is kept but only generic checks were applied.`,
      evidence: { claim_type: claimType },
    });
  }

  return {
    claim_id: claimId,
    claim_type: claimType,
    section,
    text,
    status: determineClaimStatus(checks),
    checks,
    matched_features: matchedFeatures.map((feature) => ({
      feature_id: feature.feature_id,
      display_name: feature.display_name,
      contribution_value: feature.contribution_value,
      contribution_direction: feature.contribution_direction,
      rank: feature.rank,
    })),
  };
}

function validatePredictionClaim(text: string, ir: IrSummary): ClaimCheck[] {
  const checks: ClaimCheck[] = [];

  if (ir.prediction_probability_percent === null) {
    checks.push({
      rule_id: "J2_PREDICTION_PROBABILITY_AVAILABLE_IN_IR",
      status: "WARN",
      severity: "warning",
      message:
        "Prediction claim found, but IR probability could not be extracted. Probability consistency was not checked.",
    });

    return checks;
  }

  const numbers = extractNumbers(text);

  if (numbers.length === 0) {
    checks.push({
      rule_id: "J2_PREDICTION_VALUE_MENTIONED",
      status: "WARN",
      severity: "warning",
      message:
        "Prediction claim does not mention a numeric probability. Cannot compare exact value against IR.",
      evidence: {
        ir_probability_percent: ir.prediction_probability_percent,
      },
    });

    return checks;
  }

  const closest = findClosestNumber(numbers, ir.prediction_probability_percent);
  const diff = Math.abs(closest - ir.prediction_probability_percent);

  if (diff <= 0.75) {
    checks.push({
      rule_id: "J2_PREDICTION_PROBABILITY_MATCH",
      status: "PASS",
      severity: "info",
      message:
        "Prediction probability mentioned in claim is consistent with IR.",
      evidence: {
        claim_number: closest,
        ir_probability_percent: ir.prediction_probability_percent,
        abs_diff: round(diff),
      },
    });
  } else {
    checks.push({
      rule_id: "J2_PREDICTION_PROBABILITY_MATCH",
      status: "FAIL",
      severity: "error",
      message: "Prediction probability mentioned in claim does not match IR.",
      evidence: {
        claim_number: closest,
        ir_probability_percent: ir.prediction_probability_percent,
        abs_diff: round(diff),
      },
    });
  }

  return checks;
}

function validateFeatureGroundingClaim(
  text: string,
  matchedFeatures: IrFeature[],
  ir: IrSummary,
): ClaimCheck[] {
  const checks: ClaimCheck[] = [];

  if (ir.features.length === 0) {
    checks.push({
      rule_id: "J2_IR_FEATURES_AVAILABLE",
      status: "WARN",
      severity: "warning",
      message:
        "Feature-related claim found, but no feature list could be extracted from IR.",
    });

    return checks;
  }

  if (matchedFeatures.length > 0) {
    checks.push({
      rule_id: "J2_FEATURE_MENTION_GROUNDED_IN_IR",
      status: "PASS",
      severity: "info",
      message:
        "Feature-related claim mentions at least one feature available in IR.",
      evidence: {
        matched_features: matchedFeatures.map(
          (feature) => feature.display_name,
        ),
        matched_feature_ids: matchedFeatures.map(
          (feature) => feature.feature_id,
        ),
      },
    });
  } else {
    checks.push({
      rule_id: "J2_FEATURE_MENTION_GROUNDED_IN_IR",
      status: "WARN",
      severity: "warning",
      message:
        "Feature-related claim did not directly match known IR feature names. This may be paraphrasing or an unsupported feature mention.",
      evidence: {
        claim_text: text,
        available_feature_count: ir.features.length,
      },
    });
  }

  return checks;
}

function validateDirectionClaim(
  claimDirection: string,
  matchedFeatures: IrFeature[],
): ClaimCheck[] {
  const checks: ClaimCheck[] = [];

  for (const feature of matchedFeatures) {
    if (feature.contribution_direction === "unknown") {
      checks.push({
        rule_id: "J2_DIRECTION_AVAILABLE_IN_IR",
        status: "WARN",
        severity: "warning",
        message: `Matched feature "${feature.display_name}" has unknown contribution direction in IR.`,
        evidence: {
          feature_id: feature.feature_id,
          display_name: feature.display_name,
        },
      });

      continue;
    }

    if (claimDirection === feature.contribution_direction) {
      checks.push({
        rule_id: "J2_DIRECTION_MATCH",
        status: "PASS",
        severity: "info",
        message: `Claim direction matches IR for feature "${feature.display_name}".`,
        evidence: {
          feature_id: feature.feature_id,
          display_name: feature.display_name,
          claim_direction: claimDirection,
          ir_direction: feature.contribution_direction,
          contribution_value: feature.contribution_value,
        },
      });
    } else {
      checks.push({
        rule_id: "J2_DIRECTION_MATCH",
        status: "FAIL",
        severity: "error",
        message: `Claim direction does not match IR for feature "${feature.display_name}".`,
        evidence: {
          feature_id: feature.feature_id,
          display_name: feature.display_name,
          claim_direction: claimDirection,
          ir_direction: feature.contribution_direction,
          contribution_value: feature.contribution_value,
        },
      });
    }
  }

  return checks;
}

function validateConceptClaim(text: string, ir: IrSummary): ClaimCheck[] {
  if (ir.concept_names.length === 0 && ir.concept_ids.length === 0) {
    return [
      {
        rule_id: "J2_CONCEPTS_AVAILABLE_IN_IR",
        status: "WARN",
        severity: "warning",
        message:
          "Concept claim found, but concept list could not be extracted from IR.",
      },
    ];
  }

  const normalizedText = normalizeText(text);

  const matchedConcepts = [...ir.concept_names, ...ir.concept_ids].filter(
    (concept) => concept && normalizedText.includes(normalizeText(concept)),
  );

  if (matchedConcepts.length > 0) {
    return [
      {
        rule_id: "J2_CONCEPT_MENTION_GROUNDED_IN_IR",
        status: "PASS",
        severity: "info",
        message: "Concept claim mentions at least one concept available in IR.",
        evidence: {
          matched_concepts: matchedConcepts,
        },
      },
    ];
  }

  return [
    {
      rule_id: "J2_CONCEPT_MENTION_GROUNDED_IN_IR",
      status: "WARN",
      severity: "warning",
      message:
        "Concept claim did not directly match known concept names/ids in IR. This may be paraphrasing.",
      evidence: {
        claim_text: text,
      },
    },
  ];
}

function validateLimitationClaim(text: string): ClaimCheck[] {
  const normalized = normalizeText(text);

  const hasCautionMarker =
    normalized.includes("not") ||
    normalized.includes("cannot") ||
    normalized.includes("khong") ||
    normalized.includes("không") ||
    normalized.includes("may") ||
    normalized.includes("might") ||
    normalized.includes("could") ||
    normalized.includes("có thể") ||
    normalized.includes("khả năng") ||
    normalized.includes("probability") ||
    normalized.includes("xác suất") ||
    normalized.includes("final decision") ||
    normalized.includes("quyết định cuối");

  if (hasCautionMarker) {
    return [
      {
        rule_id: "J2_LIMITATION_CAUTIOUS_LANGUAGE",
        status: "PASS",
        severity: "info",
        message: "Limitation claim uses cautious/non-final language.",
      },
    ];
  }

  return [
    {
      rule_id: "J2_LIMITATION_CAUTIOUS_LANGUAGE",
      status: "WARN",
      severity: "warning",
      message:
        "Limitation claim was detected, but cautious/non-final language is weak.",
      evidence: {
        claim_text: text,
      },
    },
  ];
}

function buildIrSummary(record: AnyRecord, index: number): IrSummary {
  const irId =
    getDeepString(record, ["ir_id"]) ||
    getDeepString(record, ["metadata", "ir_id"]) ||
    getDeepString(record, ["source", "ir_id"]) ||
    `missing_ir_id_row_${String(index + 1).padStart(4, "0")}`;

  const customerId =
    getDeepString(record, ["customer_id"]) ||
    getDeepString(record, ["source", "customer_id"]) ||
    getDeepString(record, ["source", "SK_ID_CURR"]) ||
    getDeepString(record, ["input", "customer_id"]) ||
    null;

  const probability = extractProbability(record);
  const threshold = extractThreshold(record);
  const features = extractFeatures(record);
  const conceptIds = uniqueStrings(
    features.map((feature) => feature.concept_id).filter(Boolean) as string[],
  );

  const conceptNames = extractConceptNames(record);

  return {
    ir_id: irId,
    source_record_index: index,
    customer_id: customerId,
    prediction_label:
      getDeepString(record, ["prediction", "label"]) ||
      getDeepString(record, ["prediction_label"]) ||
      getDeepString(record, ["predicted_label"]) ||
      null,
    prediction_probability: probability,
    prediction_probability_percent:
      probability === null
        ? null
        : probability <= 1
          ? probability * 100
          : probability,
    threshold,
    features,
    concept_ids: conceptIds,
    concept_names: conceptNames,
    raw: record,
  };
}

function extractProbability(record: AnyRecord): number | null {
  const candidates = [
    getDeepNumber(record, ["prediction", "probability"]),
    getDeepNumber(record, ["prediction", "probability_default"]),
    getDeepNumber(record, ["prediction", "risk_probability"]),
    getDeepNumber(record, ["prediction_probability"]),
    getDeepNumber(record, ["predicted_probability"]),
    getDeepNumber(record, ["probability"]),
    getDeepNumber(record, ["probability_default"]),
    getDeepNumber(record, ["risk_probability"]),
    getDeepNumber(record, ["model_output", "probability"]),
    getDeepNumber(record, ["model_output", "predicted_probability"]),
  ];

  for (const value of candidates) {
    if (value !== null) return value;
  }

  return findFirstNumberByKey(record, [
    "prediction_probability",
    "predicted_probability",
    "probability_default",
    "risk_probability",
    "probability",
  ]);
}

function extractThreshold(record: AnyRecord): number | null {
  const candidates = [
    getDeepNumber(record, ["prediction", "threshold"]),
    getDeepNumber(record, ["threshold"]),
    getDeepNumber(record, ["model_output", "threshold"]),
  ];

  for (const value of candidates) {
    if (value !== null) return value;
  }

  return findFirstNumberByKey(record, ["threshold"]);
}

function extractFeatures(record: AnyRecord): IrFeature[] {
  const rawFeatureObjects = collectFeatureLikeObjects(record);

  const features = rawFeatureObjects
    .map((item, index) => normalizeFeature(item, index))
    .filter((feature): feature is IrFeature => Boolean(feature));

  const byKey = new Map<string, IrFeature>();

  for (const feature of features) {
    const key = feature.feature_id || feature.display_name;

    if (!byKey.has(key)) {
      byKey.set(key, feature);
    }
  }

  return Array.from(byKey.values());
}

function collectFeatureLikeObjects(value: unknown): AnyRecord[] {
  const results: AnyRecord[] = [];

  walk(value, (node) => {
    if (!isPlainObject(node)) return;

    const hasFeatureIdentity =
      typeof node.feature_id === "string" ||
      typeof node.feature_name === "string" ||
      typeof node.display_name === "string" ||
      typeof node.name === "string";

    const hasContribution =
      typeof node.contribution === "number" ||
      typeof node.contribution_value === "number" ||
      typeof node.shap_value === "number" ||
      typeof node.value === "number" ||
      typeof node.local_contribution === "number";

    const hasRank = typeof node.rank === "number";

    if (hasFeatureIdentity && (hasContribution || hasRank)) {
      results.push(node);
    }
  });

  return results;
}

function normalizeFeature(item: AnyRecord, index: number): IrFeature | null {
  const featureId =
    getString(item.feature_id) ||
    getString(item.feature_name) ||
    getString(item.name) ||
    getString(item.display_name);

  const displayName =
    getString(item.display_name) ||
    getString(item.feature_name) ||
    getString(item.name) ||
    featureId;

  if (!featureId && !displayName) return null;

  const contributionValue =
    getNumber(item.contribution_value) ??
    getNumber(item.contribution) ??
    getNumber(item.shap_value) ??
    getNumber(item.value) ??
    getNumber(item.local_contribution);

  const rawDirection =
    getString(item.contribution_direction) ||
    getString(item.direction) ||
    getString(item.polarity);

  const contributionDirection = normalizeContributionDirection(
    rawDirection,
    contributionValue,
  );

  const rank = getNumber(item.rank) ?? index + 1;

  const conceptId =
    getString(item.concept_id) ||
    getString(item.concept) ||
    getString(item.group_id) ||
    null;

  const aliases = uniqueStrings([
    featureId,
    displayName,
    snakeToWords(featureId),
    snakeToWords(displayName),
  ]);

  return {
    feature_id: featureId || displayName,
    display_name: displayName || featureId,
    concept_id: conceptId,
    contribution_value: contributionValue,
    contribution_direction: contributionDirection,
    rank,
    aliases,
  };
}

function extractConceptNames(record: AnyRecord): string[] {
  const concepts: string[] = [];

  walk(record, (node) => {
    if (!isPlainObject(node)) return;

    const conceptId = getString(node.concept_id);
    const conceptName =
      getString(node.concept_name) ||
      getString(node.display_name) ||
      getString(node.name);

    if (conceptId && isLikelyConceptId(conceptId)) {
      concepts.push(conceptId);
    }

    if (conceptName && isLikelyConceptName(conceptName)) {
      concepts.push(conceptName);
    }
  });

  return uniqueStrings(concepts);
}

function matchFeaturesForClaim(
  claim: ExtractedClaim,
  text: string,
  features: IrFeature[],
): IrFeature[] {
  const evidenceMatched = matchFeaturesFromEvidenceRefs(
    claim.evidence_refs,
    features,
  );

  if (evidenceMatched.length > 0) {
    return evidenceMatched;
  }

  return matchFeaturesFromText(text, features);
}

function matchFeaturesFromEvidenceRefs(
  evidenceRefs: unknown[] | undefined,
  features: IrFeature[],
): IrFeature[] {
  if (!Array.isArray(evidenceRefs) || evidenceRefs.length === 0) {
    return [];
  }

  const normalizedRefs = evidenceRefs
    .map((ref) => String(ref ?? "").trim())
    .filter(Boolean);

  if (normalizedRefs.length === 0) {
    return [];
  }

  const matched: IrFeature[] = [];

  for (const ref of normalizedRefs) {
    const normalizedRef = normalizeText(ref);

    const exact = features.find(
      (feature) =>
        normalizeText(feature.feature_id) === normalizedRef ||
        feature.aliases.some((alias) => normalizeText(alias) === normalizedRef),
    );

    if (exact) {
      matched.push(exact);
      continue;
    }

    const loose = features.find((feature) => {
      const normalizedFeatureId = normalizeText(feature.feature_id);

      return (
        normalizedFeatureId.length >= 3 &&
        (normalizedFeatureId.includes(normalizedRef) ||
          normalizedRef.includes(normalizedFeatureId))
      );
    });

    if (loose) {
      matched.push(loose);
    }
  }

  return dedupeFeatures(matched);
}

function matchFeaturesFromText(
  text: string,
  features: IrFeature[],
): IrFeature[] {
  const normalizedText = normalizeText(text);
  const matched: IrFeature[] = [];

  for (const feature of features) {
    if (isCategoricalOneHotFeature(feature)) {
      if (matchesCategoricalOneHotFeature(normalizedText, feature)) {
        matched.push(feature);
      }

      continue;
    }

    const aliases = feature.aliases
      .map((alias) => normalizeText(alias))
      .filter((alias) => alias.length >= 3);

    const isMatched = aliases.some((alias) => normalizedText.includes(alias));

    if (isMatched) {
      matched.push(feature);
    }
  }

  return dedupeFeatures(matched);
}

function isCategoricalOneHotFeature(feature: IrFeature): boolean {
  return feature.feature_id.includes("__");
}

function matchesCategoricalOneHotFeature(
  normalizedText: string,
  feature: IrFeature,
): boolean {
  const [rawBase, rawCategory] = feature.feature_id.split("__", 2);

  if (!rawBase || !rawCategory) {
    return false;
  }

  const baseWords = normalizeText(snakeToWords(rawBase));
  const categoryWords = normalizeText(snakeToWords(rawCategory));
  const displayName = normalizeText(feature.display_name);

  if (!categoryWords || categoryWords.length < 2) {
    return false;
  }

  const mentionsCategory = normalizedText.includes(categoryWords);

  if (!mentionsCategory) {
    return false;
  }

  const mentionsBase =
    (baseWords.length >= 3 && normalizedText.includes(baseWords)) ||
    (displayName.length >= 3 && normalizedText.includes(displayName));

  return mentionsBase;
}

function dedupeFeatures(features: IrFeature[]): IrFeature[] {
  const byId = new Map<string, IrFeature>();

  for (const feature of features) {
    if (!byId.has(feature.feature_id)) {
      byId.set(feature.feature_id, feature);
    }
  }

  return Array.from(byId.values());
}

function summarizeClaimResults(
  claimResults: ClaimValidationResult[],
): RecordValidationResult["summary"] {
  const passClaims = claimResults.filter(
    (claim) => claim.status === "PASS",
  ).length;
  const warnClaims = claimResults.filter(
    (claim) => claim.status === "WARN",
  ).length;
  const failClaims = claimResults.filter(
    (claim) => claim.status === "FAIL",
  ).length;

  const checks = claimResults.flatMap((claim) => claim.checks);

  return {
    total_claims: claimResults.length,
    pass_claims: passClaims,
    warn_claims: warnClaims,
    fail_claims: failClaims,
    total_checks: checks.length,
    pass_checks: checks.filter((check) => check.status === "PASS").length,
    warn_checks: checks.filter((check) => check.status === "WARN").length,
    fail_checks: checks.filter((check) => check.status === "FAIL").length,
  };
}

function determineRecordStatus(input: {
  irFound: boolean;
  summary: RecordValidationResult["summary"];
}): ValidationStatus {
  if (!input.irFound) return "FAIL";
  if (input.summary.fail_claims > 0) return "FAIL";
  if (input.summary.warn_claims > 0) return "PASS_WITH_WARN";
  return "PASS";
}

function determineClaimStatus(checks: ClaimCheck[]): ClaimValidationStatus {
  if (checks.some((check) => check.status === "FAIL")) return "FAIL";
  if (checks.some((check) => check.status === "WARN")) return "WARN";
  return "PASS";
}

function buildJ2Summary(input: {
  options: {
    claimExtractionsPath: string;
    explanationIrPath: string;
    outputDir: string;
  };
  claimArtifacts: ClaimExtractionArtifact[];
  irRecords: AnyRecord[];
  validationResults: RecordValidationResult[];
  validationJsonlPath: string;
  summaryJsonPath: string;
  failuresJsonPath: string;
  reportMdPath: string;
}): J2Summary {
  const {
    options,
    claimArtifacts,
    irRecords,
    validationResults,
    validationJsonlPath,
    summaryJsonPath,
    failuresJsonPath,
    reportMdPath,
  } = input;

  const passRecords = validationResults.filter(
    (record) => record.status === "PASS",
  ).length;

  const passWithWarnRecords = validationResults.filter(
    (record) => record.status === "PASS_WITH_WARN",
  ).length;

  const failRecords = validationResults.filter(
    (record) => record.status === "FAIL",
  ).length;

  const totalClaims = validationResults.reduce(
    (sum, record) => sum + record.summary.total_claims,
    0,
  );

  const passClaims = validationResults.reduce(
    (sum, record) => sum + record.summary.pass_claims,
    0,
  );

  const warnClaims = validationResults.reduce(
    (sum, record) => sum + record.summary.warn_claims,
    0,
  );

  const failClaims = validationResults.reduce(
    (sum, record) => sum + record.summary.fail_claims,
    0,
  );

  const missingIrIds = validationResults
    .filter((record) => !record.join.ir_found)
    .map((record) => record.ir_id);

  const status: ValidationStatus =
    failRecords > 0
      ? "FAIL"
      : passWithWarnRecords > 0
        ? "PASS_WITH_WARN"
        : "PASS";

  return {
    report_name: "Batch J.2 Faithfulness Validation Summary",
    created_at: new Date().toISOString(),
    status,
    input_paths: {
      claim_extractions_path: options.claimExtractionsPath,
      explanation_ir_path: options.explanationIrPath,
    },
    output_paths: {
      validation_jsonl_path: validationJsonlPath,
      summary_json_path: summaryJsonPath,
      failures_json_path: failuresJsonPath,
      report_md_path: reportMdPath,
    },
    counts: {
      claim_extraction_records: claimArtifacts.length,
      explanation_ir_records: irRecords.length,
      validated_records: validationResults.length,
      pass_records: passRecords,
      pass_with_warn_records: passWithWarnRecords,
      fail_records: failRecords,
      total_claims: totalClaims,
      pass_claims: passClaims,
      warn_claims: warnClaims,
      fail_claims: failClaims,
    },
    join_quality: {
      joined_records: validationResults.length - missingIrIds.length,
      missing_ir_records: missingIrIds.length,
      missing_ir_ids: missingIrIds,
    },
    validator: {
      validator_version: VALIDATOR_VERSION,
      mode: "rule_based_ir_faithfulness",
      llm_as_judge: false,
    },
  };
}

function buildMarkdownReport(
  summary: J2Summary,
  records: RecordValidationResult[],
): string {
  const lines: string[] = [];

  lines.push("# Batch J.2 Faithfulness Validation Report");
  lines.push("");
  lines.push(`Created at: ${summary.created_at}`);
  lines.push(`Status: **${summary.status}**`);
  lines.push("");
  lines.push("## Inputs");
  lines.push("");
  lines.push(
    `- Claim extractions: \`${summary.input_paths.claim_extractions_path}\``,
  );
  lines.push(
    `- Explanation IR: \`${summary.input_paths.explanation_ir_path}\``,
  );
  lines.push("");
  lines.push("## Summary");
  lines.push("");
  lines.push(`- Validated records: ${summary.counts.validated_records}`);
  lines.push(`- PASS records: ${summary.counts.pass_records}`);
  lines.push(
    `- PASS_WITH_WARN records: ${summary.counts.pass_with_warn_records}`,
  );
  lines.push(`- FAIL records: ${summary.counts.fail_records}`);
  lines.push(`- Total claims: ${summary.counts.total_claims}`);
  lines.push(`- PASS claims: ${summary.counts.pass_claims}`);
  lines.push(`- WARN claims: ${summary.counts.warn_claims}`);
  lines.push(`- FAIL claims: ${summary.counts.fail_claims}`);
  lines.push("");
  lines.push("## Join Quality");
  lines.push("");
  lines.push(`- Joined records: ${summary.join_quality.joined_records}`);
  lines.push(
    `- Missing IR records: ${summary.join_quality.missing_ir_records}`,
  );
  lines.push("");
  lines.push("## Per-record Results");
  lines.push("");
  lines.push(
    "| # | Status | IR ID | Explanation ID | Claims | Pass | Warn | Fail |",
  );
  lines.push("|---:|---|---|---|---:|---:|---:|---:|");

  records.forEach((record, index) => {
    lines.push(
      `| ${index + 1} | ${record.status} | \`${record.ir_id}\` | \`${record.explanation_id}\` | ${record.summary.total_claims} | ${record.summary.pass_claims} | ${record.summary.warn_claims} | ${record.summary.fail_claims} |`,
    );
  });

  lines.push("");
  lines.push("## Validator");
  lines.push("");
  lines.push(`- Version: \`${summary.validator.validator_version}\``);
  lines.push(`- Mode: \`${summary.validator.mode}\``);
  lines.push(`- LLM-as-judge: \`${summary.validator.llm_as_judge}\``);
  lines.push("");

  return lines.join("\n");
}

async function readJsonl<T>(filePath: string): Promise<T[]> {
  const raw = await readFile(filePath, "utf8");

  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      try {
        return JSON.parse(line) as T;
      } catch (error) {
        throw new Error(
          `Invalid JSONL at ${filePath}, line ${index + 1}: ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      }
    });
}

async function writeJsonl(filePath: string, records: unknown[]): Promise<void> {
  const content = records.map((record) => JSON.stringify(record)).join("\n");
  await writeFile(filePath, content + (content ? "\n" : ""), "utf8");
}

function isPredictionClaim(claimType: string): boolean {
  return normalizeText(claimType).includes("prediction");
}

function isFeatureOrContributionClaim(claimType: string): boolean {
  const normalized = normalizeText(claimType);

  return (
    normalized.includes("feature") ||
    normalized.includes("contribution") ||
    normalized.includes("direction") ||
    normalized.includes("driver") ||
    normalized.includes("risk_factor")
  );
}

function isConceptClaim(claimType: string): boolean {
  return normalizeText(claimType).includes("concept");
}

function isLimitationClaim(claimType: string): boolean {
  return normalizeText(claimType).includes("limitation");
}

function isKnownClaimType(claimType: string): boolean {
  const normalized = normalizeClaimType(claimType);

  return [
    "prediction",
    "contribution_accounting",
    "feature_mention",
    "concept_mention",
    "direction",
    "contribution_value",
    "referenced_term",
    "limitation",
    "forbidden_wording",
    "raw_technical_leakage",
    "unsupported_customer_claim",
    "remaining_summary",
    "unknown",
  ].includes(normalized);
}

function normalizeClaimType(value: string): string {
  return value.trim().toLowerCase();
}

function normalizeDirection(value: string | null): string {
  const normalized = normalizeText(value ?? "");

  if (
    normalized.includes("increase") ||
    normalized.includes("higher") ||
    normalized.includes("raise") ||
    normalized.includes("positive") ||
    normalized.includes("increases_risk")
  ) {
    return "increases_risk";
  }

  if (
    normalized.includes("decrease") ||
    normalized.includes("lower") ||
    normalized.includes("reduce") ||
    normalized.includes("negative") ||
    normalized.includes("decreases_risk")
  ) {
    return "decreases_risk";
  }

  if (normalized.includes("neutral")) {
    return "neutral";
  }

  return "unknown";
}

function normalizeContributionDirection(
  rawDirection: string,
  contributionValue: number | null,
): IrFeature["contribution_direction"] {
  const normalized = normalizeDirection(rawDirection);

  if (
    normalized === "increases_risk" ||
    normalized === "decreases_risk" ||
    normalized === "neutral"
  ) {
    return normalized;
  }

  if (typeof contributionValue === "number") {
    if (contributionValue > 0) return "increases_risk";
    if (contributionValue < 0) return "decreases_risk";
    return "neutral";
  }

  return "unknown";
}

function extractNumbers(text: string): number[] {
  const matches = text.match(/-?\d+(?:\.\d+)?/g) ?? [];
  return matches.map(Number).filter((value) => Number.isFinite(value));
}

function findClosestNumber(values: number[], target: number): number {
  return values.reduce((best, current) => {
    return Math.abs(current - target) < Math.abs(best - target)
      ? current
      : best;
  }, values[0]);
}

function buildValidationId(
  explanationId: string,
  irId: string,
  index: number,
): string {
  const base = explanationId || irId || `row_${index + 1}`;
  return `val_${safeId(base)}`;
}

function safeId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 120);
}

function walk(value: unknown, visit: (node: unknown) => void): void {
  visit(value);

  if (Array.isArray(value)) {
    for (const item of value) {
      walk(item, visit);
    }

    return;
  }

  if (isPlainObject(value)) {
    for (const item of Object.values(value)) {
      walk(item, visit);
    }
  }
}

function findFirstNumberByKey(
  value: unknown,
  targetKeys: string[],
): number | null {
  let found: number | null = null;
  const normalizedTargets = targetKeys.map(normalizeText);

  walk(value, (node) => {
    if (found !== null || !isPlainObject(node)) return;

    for (const [key, rawValue] of Object.entries(node)) {
      if (normalizedTargets.includes(normalizeText(key))) {
        const numberValue = getNumber(rawValue);

        if (numberValue !== null) {
          found = numberValue;
          return;
        }
      }
    }
  });

  return found;
}

function getDeepString(record: AnyRecord, pathParts: string[]): string {
  const value = getDeepValue(record, pathParts);
  return getString(value);
}

function getDeepNumber(record: AnyRecord, pathParts: string[]): number | null {
  const value = getDeepValue(record, pathParts);
  return getNumber(value);
}

function getDeepValue(record: AnyRecord, pathParts: string[]): unknown {
  let current: unknown = record;

  for (const part of pathParts) {
    if (!isPlainObject(current)) return undefined;
    current = current[part];
  }

  return current;
}

function getString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function getNullableString(value: unknown): string | null {
  const result = getString(value);
  return result || null;
}

function getNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;

  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);

    if (Number.isFinite(parsed)) return parsed;
  }

  return null;
}

function normalizeText(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[_\-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function snakeToWords(value: string): string {
  return value.replace(/[_\-]+/g, " ");
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(
    new Set(values.map((value) => value.trim()).filter(Boolean)),
  );
}

function isPlainObject(value: unknown): value is AnyRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function round(value: number): number {
  return Math.round(value * 10000) / 10000;
}

function isLikelyConceptId(value: string): boolean {
  const normalized = normalizeText(value);

  return (
    normalized.includes("loan") ||
    normalized.includes("credit") ||
    normalized.includes("risk") ||
    normalized.includes("payment") ||
    normalized.includes("repayment") ||
    normalized.includes("income") ||
    normalized.includes("bureau") ||
    normalized.includes("external") ||
    normalized.includes("application") ||
    normalized.includes("profile") ||
    normalized.includes("behavior")
  );
}

function isLikelyConceptName(value: string): boolean {
  const normalized = normalizeText(value);

  return (
    normalized.includes("loan") ||
    normalized.includes("credit") ||
    normalized.includes("risk") ||
    normalized.includes("payment") ||
    normalized.includes("repayment") ||
    normalized.includes("income") ||
    normalized.includes("bureau") ||
    normalized.includes("external") ||
    normalized.includes("application") ||
    normalized.includes("profile") ||
    normalized.includes("behavior")
  );
}
