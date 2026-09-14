import path from "node:path";

import type {
  CanonicalGenerationRow,
  JsonObject,
} from "../../../contracts/llm-validation";
import {
  CLAIM_SUBTYPES_BY_TYPE,
  type AtomicClaimRecord,
  type AtomicClaimRecordV3,
  type ClaimSubtype,
  type ClaimType,
} from "../../../contracts/validation-claims";
import { sha256 } from "../common/utils";
import {
  describeArtifact,
  readJsonlStrict,
  writeJsonAtomic,
  writeJsonlAtomic,
} from "../canonicalization/io";
import { buildSemanticSignature } from "../claim_extraction/claimPostprocessor";
import { buildGenerationTextDocument } from "../claim_extraction/generationTextAdapter";
import {
  classifyClaimSemantics,
  classifyClaimSubtype,
} from "./claimSubtype";
import { assertClaimCompatible } from "./claimTypeCompatibility";
import type {
  ClaimSemanticCorrection,
  SemanticCorrectionTarget,
} from "./generateSemanticCorrections";

export const SEMANTIC_CLAIM_FINALIZER_VERSION = "claim_finalizer_v2.0.0";
export const SEMANTIC_FINALIZATION_POLICY_VERSION =
  "claim_finalization_policy_v3";

export type SemanticClaimFinalizationOptions = {
  generationIndexPath: string;
  historicalClaimsPath: string;
  correctionsPath: string;
  claimsOutputPath: string;
  changesOutputPath: string;
  summaryOutputPath: string;
  manifestOutputPath: string;
};

type WorkingV3Claim = Omit<
  AtomicClaimRecord,
  "claim_schema_version" | "claim_type"
> & {
  claim_schema_version: "claims_v3";
  parent_claim_id: string;
  claim_type: ClaimType;
  claim_subtype: ClaimSubtype;
  proposition_status: "COMPLETE";
  source_start: number;
  source_end: number;
  finalizer_version: string;
  finalization_policy_version: string;
};

type SemanticFinalizationChange = {
  change_schema_version: "claim_finalization_change_v2";
  change_id: string;
  generation_id: string;
  action: "ADD" | "UPDATE" | "DROP";
  semantic_operation:
    | ClaimSemanticCorrection["operation"]
    | "MIGRATE_SCHEMA";
  historical_claim_id: string;
  new_claim_id: string | null;
  changed_fields: string[];
  old_claim: AtomicClaimRecord;
  new_claim: AtomicClaimRecordV3 | null;
};

export async function runSemanticClaimFinalization(
  options: SemanticClaimFinalizationOptions,
): Promise<Record<string, unknown>> {
  validateOutputPaths(options);
  const [generationInput, historicalInput, correctionInput] = await Promise.all([
    readJsonlStrict<JsonObject>(options.generationIndexPath),
    readJsonlStrict<AtomicClaimRecord>(options.historicalClaimsPath),
    readJsonlStrict<ClaimSemanticCorrection>(options.correctionsPath),
  ]);
  const generations = generationInput.records.map(
    (record) => record.value as unknown as CanonicalGenerationRow,
  );
  const historicalClaims = historicalInput.records.map((record) => record.value);
  const corrections = correctionInput.records.map((record) => record.value);
  const generationById = uniqueMap(
    generations,
    (row) => row.generation_id,
    "generation",
  );
  const historicalById = uniqueMap(
    historicalClaims,
    (claim) => claim.claim_id,
    "historical claim",
  );
  const correctionById = uniqueMap(
    corrections,
    (correction) => correction.historical_claim_id,
    "semantic correction",
  );
  validateCorrectionFixture(corrections, historicalById);
  validateFragmentReplacements(
    corrections,
    historicalClaims,
    historicalById,
  );

  const finalClaims: AtomicClaimRecordV3[] = [];
  const changes: SemanticFinalizationChange[] = [];
  let splitCount = 0;
  for (const historical of historicalClaims) {
    const correction = correctionById.get(historical.claim_id);
    if (correction?.operation === "DROP_FRAGMENT") {
      changes.push(buildChange(historical, null, "DROP", correction.operation));
      continue;
    }

    const targets = semanticTargets(historical, correction);
    if (targets.length > 1) splitCount += 1;
    targets.forEach((target, index) => {
      const migrated = migrateClaim(historical, target);
      assertClaimCompatible(migrated);
      finalClaims.push(migrated);
      changes.push(buildChange(
        historical,
        migrated,
        index === 0 ? "UPDATE" : "ADD",
        correction?.operation ?? "MIGRATE_SCHEMA",
      ));
    });
  }

  reindexWithinGenerations(finalClaims);
  assertUniqueIds(finalClaims);
  const sourceSpanAudit = auditSourceSpans(finalClaims, generationById);
  const actionCounts = countBy(changes, (change) => change.action);
  const semanticOperationCounts = countBy(
    changes.filter((change) => change.action !== "ADD"),
    (change) => change.semantic_operation,
  );
  const claimsArtifact = await writeAndDescribe(
    options.claimsOutputPath,
    finalClaims,
  );
  const changesArtifact = await writeAndDescribe(
    options.changesOutputPath,
    changes,
  );
  const correctionCaseCounts = countBy(
    corrections,
    (correction) => correction.semantic_case_name,
  );
  const summary = {
    summary_schema_version: "claim_finalization_summary_v2",
    finalizer_version: SEMANTIC_CLAIM_FINALIZER_VERSION,
    finalization_policy_version: SEMANTIC_FINALIZATION_POLICY_VERSION,
    claims_v2_count: historicalClaims.length,
    claims_v3_count: finalClaims.length,
    change_counts: {
      ADD: actionCounts.ADD ?? 0,
      UPDATE: actionCounts.UPDATE ?? 0,
      DROP: actionCounts.DROP ?? 0,
      SPLIT: splitCount,
    },
    reviewed_population: {
      total: corrections.length,
      category_counts: correctionCaseCounts,
      fragments_handled:
        correctionCaseCounts.PREDICTION_SUBSPAN_FRAGMENT ?? 0,
      mistyped_predictions_handled:
        correctionCaseCounts.FACTOR_STATEMENT_MISCLASSIFIED_AS_PREDICTION ?? 0,
      directions_repaired:
        correctionCaseCounts.EXPLICIT_PREDICTION_DIRECTION_NOT_ENCODED ?? 0,
      contradictions_preserved:
        correctionCaseCounts.VALID_OVERALL_PREDICTION_CONTRADICTION ?? 0,
    },
    semantic_operation_counts: semanticOperationCounts,
    source_span_reconstruction: sourceSpanAudit,
    compatibility_matrix_failures: 0,
    output_claims_sha256: claimsArtifact.sha256,
  };
  await writeJsonAtomic(options.summaryOutputPath, summary);
  const summaryArtifact = await describeArtifact(options.summaryOutputPath, 1);

  const manifest = {
    finalization_schema_version: "claim_finalization_manifest_v2",
    finalizer_version: SEMANTIC_CLAIM_FINALIZER_VERSION,
    finalization_policy_version: SEMANTIC_FINALIZATION_POLICY_VERSION,
    deterministic: true,
    provider_calls_made: 0,
    lineage: {
      source_claim_schema_version: "claims_v2",
      output_claim_schema_version: "claims_v3",
      every_output_record_has_parent_claim_id: true,
    },
    inputs: {
      generation_index: loadedDescriptor(generationInput),
      historical_claims: loadedDescriptor(historicalInput),
      semantic_corrections: loadedDescriptor(correctionInput),
    },
    outputs: {
      claims: claimsArtifact,
      changes: changesArtifact,
      summary: projectDescriptor({
        ...summaryArtifact,
        record_count: summaryArtifact.record_count ?? 1,
      }),
    },
    invariants: {
      official_incomplete_fragments: 0,
      source_span_mismatches: sourceSpanAudit.mismatch_count,
      compatibility_matrix_failures: 0,
      unique_claim_ids: true,
    },
  };
  await writeJsonAtomic(options.manifestOutputPath, manifest);
  return summary;
}

function semanticTargets(
  historical: AtomicClaimRecord,
  correction: ClaimSemanticCorrection | undefined,
): SemanticCorrectionTarget[] {
  if (correction?.operation === "SPLIT") {
    if (correction.split_targets.length < 2) {
      throw new Error(`Split correction has fewer than two targets: ${historical.claim_id}.`);
    }
    return correction.split_targets;
  }
  if (
    correction?.operation === "RETYPE"
    || correction?.operation === "UPDATE_DIRECTION"
  ) {
    return [{
      claim_type: correction.target_claim_type,
      claim_subtype: correction.target_claim_subtype,
      subject_type: targetSubjectType(correction.target_claim_type),
      feature_id: correction.target_feature_id,
      concept_id: correction.target_concept_id,
      direction: correction.corrected_direction ?? historical.direction,
      magnitude: correction.target_claim_type === "magnitude"
        ? historical.magnitude
        : null,
    }];
  }
  if (correction?.operation === "PRESERVE_EXPERIMENTAL_ERROR") {
    return [{
      claim_type: historical.claim_type,
      claim_subtype: correction.target_claim_subtype,
      subject_type: normalizedSubjectType(historical),
      feature_id: historical.feature_id,
      concept_id: historical.concept_id,
      direction: historical.direction,
      magnitude: historical.magnitude,
    }];
  }

  const classification = classifyClaimSemantics(historical);
  return [{
    claim_type: classification.claim_type,
    claim_subtype: classification.claim_subtype,
    subject_type: classification.claim_type === historical.claim_type
      ? normalizedSubjectType(historical)
      : targetSubjectType(classification.claim_type),
    feature_id: historical.feature_id,
    concept_id: historical.concept_id,
    direction: historical.direction,
    magnitude: historical.magnitude,
  }];
}

function migrateClaim(
  historical: AtomicClaimRecord,
  target: SemanticCorrectionTarget,
): AtomicClaimRecordV3 {
  const numeric = predictionNumericFact(historical, target);
  const working: WorkingV3Claim = {
    ...historical,
    claim_schema_version: "claims_v3",
    parent_claim_id: historical.claim_id,
    claim_type: target.claim_type,
    claim_subtype: target.claim_subtype,
    proposition_status: "COMPLETE",
    source_start: historical.source_span_start,
    source_end: historical.source_span_end,
    subject_type: target.subject_type,
    feature_id: target.feature_id,
    concept_id: target.concept_id,
    direction: target.direction,
    magnitude: target.magnitude,
    numeric_value: numeric.value,
    numeric_unit: numeric.unit,
    numeric_role: numeric.role,
    model_normalized_claim_key: semanticModelKey(historical, target),
    finalizer_version: SEMANTIC_CLAIM_FINALIZER_VERSION,
    finalization_policy_version: SEMANTIC_FINALIZATION_POLICY_VERSION,
    semantic_signature: "",
    normalized_claim_key: "",
    claim_id: "",
  };
  const baseSignature = buildSemanticSignature(working);
  const signature = `${baseSignature}|subtype:${target.claim_subtype}`;
  working.semantic_signature = signature;
  working.normalized_claim_key = signature;
  working.claim_id = buildClaimId(
    working.generation_id,
    signature,
    working.source_start,
  );
  return narrowV3Claim(working);
}

function predictionNumericFact(
  historical: AtomicClaimRecord,
  target: SemanticCorrectionTarget,
): {
  value: number | null;
  unit: string | null;
  role: AtomicClaimRecord["numeric_role"];
} {
  if (target.claim_type === "numeric") {
    return {
      value: historical.numeric_value,
      unit: historical.numeric_unit,
      role: historical.numeric_role,
    };
  }
  if (target.claim_type !== "prediction") {
    return { value: null, unit: null, role: null };
  }
  const percentage = historical.source_text.match(/(\d+(?:[.,]\d+)?)\s*%/u);
  if (!percentage?.[1]) return { value: null, unit: null, role: null };
  return {
    value: Number(percentage[1].replace(",", ".")) / 100,
    unit: "probability",
    role: "prediction_score",
  };
}

function narrowV3Claim(claim: WorkingV3Claim): AtomicClaimRecordV3 {
  switch (claim.claim_type) {
    case "prediction":
      return narrow(claim, "prediction", CLAIM_SUBTYPES_BY_TYPE.prediction);
    case "feature_presence":
      return narrow(claim, "feature_presence", CLAIM_SUBTYPES_BY_TYPE.feature_presence);
    case "feature_direction":
      return narrow(claim, "feature_direction", CLAIM_SUBTYPES_BY_TYPE.feature_direction);
    case "concept_presence":
      return narrow(claim, "concept_presence", CLAIM_SUBTYPES_BY_TYPE.concept_presence);
    case "concept_direction":
      return narrow(claim, "concept_direction", CLAIM_SUBTYPES_BY_TYPE.concept_direction);
    case "magnitude":
      return narrow(claim, "magnitude", CLAIM_SUBTYPES_BY_TYPE.magnitude);
    case "ranking":
      return narrow(claim, "ranking", CLAIM_SUBTYPES_BY_TYPE.ranking);
    case "numeric":
      return narrow(claim, "numeric", CLAIM_SUBTYPES_BY_TYPE.numeric);
    case "causal":
      return narrow(claim, "causal", CLAIM_SUBTYPES_BY_TYPE.causal);
    case "uncertainty":
      return narrow(claim, "uncertainty", CLAIM_SUBTYPES_BY_TYPE.uncertainty);
    case "distributed_evidence":
      return narrow(
        claim,
        "distributed_evidence",
        CLAIM_SUBTYPES_BY_TYPE.distributed_evidence,
      );
    case "recommendation":
      return narrow(claim, "recommendation", CLAIM_SUBTYPES_BY_TYPE.recommendation);
    case "limitation":
      return narrow(claim, "limitation", CLAIM_SUBTYPES_BY_TYPE.limitation);
  }
}

function narrow<
  Type extends ClaimType,
  Subtypes extends readonly ClaimSubtype[],
>(
  claim: WorkingV3Claim,
  claimType: Type,
  subtypes: Subtypes,
): AtomicClaimRecordV3 {
  if (!subtypes.includes(claim.claim_subtype)) {
    throw new Error(
      `Subtype ${claim.claim_subtype} is incompatible with ${claimType}.`,
    );
  }
  return {
    ...claim,
    claim_type: claimType,
    claim_subtype: claim.claim_subtype,
  } as AtomicClaimRecordV3;
}

function validateCorrectionFixture(
  corrections: readonly ClaimSemanticCorrection[],
  historicalById: ReadonlyMap<string, AtomicClaimRecord>,
): void {
  if (corrections.length !== 260) {
    throw new Error(`Semantic correction fixture must contain 260 rows.`);
  }
  for (const correction of corrections) {
    const historical = historicalById.get(correction.historical_claim_id);
    if (!historical) {
      throw new Error(
        `Correction references absent claim: ${correction.historical_claim_id}.`,
      );
    }
    if (
      correction.generation_id !== historical.generation_id
      || correction.source_section !== historical.source_section
      || correction.source_text_sha256 !== historical.source_text_sha256
    ) {
      throw new Error(
        `Correction technical lineage mismatch: ${correction.historical_claim_id}.`,
      );
    }
  }
}

function validateFragmentReplacements(
  corrections: readonly ClaimSemanticCorrection[],
  historicalClaims: readonly AtomicClaimRecord[],
  historicalById: ReadonlyMap<string, AtomicClaimRecord>,
): void {
  for (const correction of corrections) {
    if (correction.operation !== "DROP_FRAGMENT") continue;
    const fragment = historicalById.get(correction.historical_claim_id);
    if (!fragment) throw new Error("Fragment correction lost its source claim.");
    const completeOverallExists = historicalClaims.some((candidate) =>
      candidate.claim_id !== fragment.claim_id
      && candidate.generation_id === fragment.generation_id
      && candidate.source_section === fragment.source_section
      && candidate.claim_type === "prediction"
      && candidate.direction !== "unknown"
      && candidate.direction !== "neutral"
      && !startsWithConnective(candidate.source_text)
    );
    if (!completeOverallExists) {
      throw new Error(
        `Fragment has no complete overall replacement: ${fragment.claim_id}.`,
      );
    }
  }
}

function auditSourceSpans(
  claims: readonly AtomicClaimRecordV3[],
  generationById: ReadonlyMap<string, CanonicalGenerationRow>,
): { audited_claim_count: number; exact_match_count: number; mismatch_count: number } {
  let exactMatches = 0;
  for (const claim of claims) {
    const row = generationById.get(claim.generation_id);
    if (!row) throw new Error(`Claim cannot join generation: ${claim.claim_id}.`);
    const document = buildGenerationTextDocument(row);
    const reconstructed = document.generation_text.slice(
      claim.source_start,
      claim.source_end,
    );
    if (
      claim.source_start !== claim.source_span_start
      || claim.source_end !== claim.source_span_end
      || reconstructed !== claim.source_text
      || sha256(reconstructed) !== claim.source_text_sha256
      || document.source_input_sha256 !== claim.source_input_sha256
    ) {
      throw new Error(`Source-span reconstruction mismatch: ${claim.claim_id}.`);
    }
    exactMatches += 1;
  }
  return {
    audited_claim_count: claims.length,
    exact_match_count: exactMatches,
    mismatch_count: claims.length - exactMatches,
  };
}

function buildChange(
  oldClaim: AtomicClaimRecord,
  newClaim: AtomicClaimRecordV3 | null,
  action: SemanticFinalizationChange["action"],
  semanticOperation: SemanticFinalizationChange["semantic_operation"],
): SemanticFinalizationChange {
  const changedFields = newClaim
    ? diffFields(oldClaim, newClaim)
    : [];
  const stable = JSON.stringify({
    generation_id: oldClaim.generation_id,
    action,
    semantic_operation: semanticOperation,
    historical_claim_id: oldClaim.claim_id,
    new_claim_id: newClaim?.claim_id ?? null,
  });
  return {
    change_schema_version: "claim_finalization_change_v2",
    change_id: `claim_change_${sha256(stable).slice(0, 32)}`,
    generation_id: oldClaim.generation_id,
    action,
    semantic_operation: semanticOperation,
    historical_claim_id: oldClaim.claim_id,
    new_claim_id: newClaim?.claim_id ?? null,
    changed_fields: changedFields,
    old_claim: oldClaim,
    new_claim: newClaim,
  };
}

function reindexWithinGenerations(claims: AtomicClaimRecordV3[]): void {
  const byGeneration = groupBy(claims, (claim) => claim.generation_id);
  for (const generationClaims of byGeneration.values()) {
    generationClaims.sort((left, right) =>
      left.source_start - right.source_start
      || left.source_end - right.source_end
      || left.claim_id.localeCompare(right.claim_id)
    );
    generationClaims.forEach((claim, index) => {
      claim.local_claim_index = index + 1;
    });
  }
  claims.sort((left, right) =>
    left.generation_id.localeCompare(right.generation_id)
    || left.local_claim_index - right.local_claim_index
  );
}

function normalizedSubjectType(
  claim: AtomicClaimRecord,
): AtomicClaimRecord["subject_type"] {
  switch (claim.claim_type) {
    case "prediction":
      return "prediction";
    case "feature_presence":
    case "feature_direction":
      return "feature";
    case "ranking":
      return claim.concept_id ? "concept" : "feature";
    case "concept_presence":
    case "concept_direction":
      return "concept";
    case "distributed_evidence":
      return "evidence";
    case "recommendation":
    case "limitation":
      return "narrative";
    case "numeric":
      if (claim.concept_id) return "concept";
      if (
        claim.numeric_role === "prediction_score"
        || claim.numeric_role === "decision_threshold"
      ) {
        return "prediction";
      }
      if (
        claim.numeric_role === "feature_value"
        || claim.numeric_role === "rank"
      ) {
        return "feature";
      }
      return "evidence";
    case "magnitude":
      if (claim.feature_id) return "feature";
      if (claim.concept_id) return "concept";
      return "evidence";
    case "causal":
      return claim.subject_type === "none" ? "narrative" : claim.subject_type;
    default:
      return claim.subject_type;
  }
}

function targetSubjectType(
  claimType: ClaimType,
): AtomicClaimRecord["subject_type"] {
  switch (claimType) {
    case "prediction":
      return "prediction";
    case "feature_presence":
    case "feature_direction":
    case "ranking":
      return "feature";
    case "concept_presence":
    case "concept_direction":
      return "concept";
    case "distributed_evidence":
    case "magnitude":
      return "evidence";
    case "recommendation":
    case "limitation":
      return "narrative";
    default:
      return "none";
  }
}

function semanticModelKey(
  historical: AtomicClaimRecord,
  target: SemanticCorrectionTarget,
): string | null {
  if (target.feature_id) return `feature:${target.feature_id}`;
  if (target.concept_id) return `concept:${target.concept_id}`;
  if (
    target.claim_type !== classifyClaimSemantics(historical).claim_type
    || target.claim_subtype !== classifyClaimSubtype(historical)
  ) {
    return `${target.claim_type}:${target.claim_subtype.toLocaleLowerCase("en-US")}`;
  }
  return historical.model_normalized_claim_key;
}

function startsWithConnective(value: string): boolean {
  const normalized = value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase("en-US")
    .trim();
  return /^(?:dua tren|cung voi|nhung|va|do)/u.test(normalized);
}

function buildClaimId(
  generationId: string,
  semanticSignature: string,
  sourceStart: number,
): string {
  return `claim_${sha256(
    `${generationId}|${semanticSignature}|${sourceStart}`,
  ).slice(0, 32)}`;
}

function assertUniqueIds(claims: readonly AtomicClaimRecordV3[]): void {
  const ids = new Set<string>();
  for (const claim of claims) {
    if (ids.has(claim.claim_id)) {
      throw new Error(`Duplicate claims_v3 ID: ${claim.claim_id}.`);
    }
    ids.add(claim.claim_id);
  }
}

function diffFields(
  left: AtomicClaimRecord,
  right: AtomicClaimRecordV3,
): string[] {
  const leftRecord: Record<string, unknown> = left;
  const rightRecord: Record<string, unknown> = right;
  return [...new Set([...Object.keys(leftRecord), ...Object.keys(rightRecord)])]
    .filter((key) =>
      JSON.stringify(leftRecord[key]) !== JSON.stringify(rightRecord[key])
    )
    .sort();
}

async function writeAndDescribe<T>(
  outputPath: string,
  records: readonly T[],
): Promise<{ path: string; sha256: string; byte_count: number; record_count: number }> {
  await writeJsonlAtomic(outputPath, [...records]);
  const descriptor = await describeArtifact(outputPath, records.length);
  return projectDescriptor({
    ...descriptor,
    record_count: descriptor.record_count ?? records.length,
  });
}

function loadedDescriptor(input: {
  path: string;
  sha256: string;
  byte_count: number;
  records: readonly unknown[];
}): { path: string; sha256: string; byte_count: number; record_count: number } {
  return {
    path: projectPath(input.path),
    sha256: input.sha256,
    byte_count: input.byte_count,
    record_count: input.records.length,
  };
}

function projectDescriptor(input: {
  path: string;
  sha256: string;
  byte_count: number;
  record_count: number;
}): { path: string; sha256: string; byte_count: number; record_count: number } {
  return { ...input, path: projectPath(input.path) };
}

function projectPath(value: string): string {
  return path.relative(process.cwd(), path.resolve(value)).split(path.sep).join("/");
}

function validateOutputPaths(options: SemanticClaimFinalizationOptions): void {
  const inputs = [
    options.generationIndexPath,
    options.historicalClaimsPath,
    options.correctionsPath,
  ].map((value) => path.resolve(value));
  const outputs = [
    options.claimsOutputPath,
    options.changesOutputPath,
    options.summaryOutputPath,
    options.manifestOutputPath,
  ].map((value) => path.resolve(value));
  if (new Set(outputs).size !== outputs.length) {
    throw new Error("Semantic finalization output paths must be distinct.");
  }
  if (outputs.some((output) => inputs.includes(output))) {
    throw new Error("Semantic finalization cannot overwrite an input artifact.");
  }
}

function uniqueMap<T>(
  values: readonly T[],
  key: (value: T) => string,
  label: string,
): Map<string, T> {
  const result = new Map<string, T>();
  for (const value of values) {
    const itemKey = key(value);
    if (result.has(itemKey)) throw new Error(`Duplicate ${label}: ${itemKey}.`);
    result.set(itemKey, value);
  }
  return result;
}

function groupBy<T>(
  values: readonly T[],
  key: (value: T) => string,
): Map<string, T[]> {
  const result = new Map<string, T[]>();
  for (const value of values) {
    const itemKey = key(value);
    const group = result.get(itemKey) ?? [];
    group.push(value);
    result.set(itemKey, group);
  }
  return result;
}

function countBy<T>(
  values: readonly T[],
  key: (value: T) => string,
): Record<string, number> {
  const counts = new Map<string, number>();
  for (const value of values) {
    const itemKey = key(value);
    counts.set(itemKey, (counts.get(itemKey) ?? 0) + 1);
  }
  return Object.fromEntries(
    [...counts.entries()].sort(([left], [right]) => left.localeCompare(right)),
  );
}
