import path from "node:path";

import type {
  CanonicalGenerationRow,
  JsonObject,
} from "../../../contracts/llm-validation";
import type {
  AtomicClaimRecord,
  StoredClaimExtractionAttemptRecord,
  StoredClaimExtractionFailure,
} from "../../../contracts/validation-claims";
import { sha256 } from "../common/utils";
import {
  describeArtifact,
  readJsonlStrict,
  writeJsonAtomic,
  writeJsonlAtomic,
} from "../canonicalization/io";
import {
  ATOMIC_CLAIM_EXTRACTOR_VERSION,
  ATOMIC_CLAIM_PROMPT_VERSION,
  validateAndNormalizeClaimPayload,
} from "../claim_extraction/atomicClaimSchema";
import { buildGenerationTextDocument } from "../claim_extraction/generationTextAdapter";
import {
  CLAIM_FINALIZATION_POLICY_VERSION,
  CLAIM_FINALIZER_VERSION,
  extractCountFacts,
  finalizeGenerationClaims,
  isPolicyAbsenceSlot,
  type ClaimFinalizationRuleCode,
  type TracedClaim,
} from "./claimFinalizationRules";

export type ClaimFinalizationOptions = {
  generationIndexPath: string;
  claimsInputPath: string;
  attemptsInputPath: string;
  failuresInputPath: string;
  claimsOutputPath: string;
  changesOutputPath: string;
  manifestOutputPath: string;
};

export type ClaimFinalizationSummary = {
  canonical_generations: number;
  successful_generations: number;
  unusable_generations: number;
  input_claims: number;
  replayed_claims: number;
  final_claims: number;
  changed_generations: number;
  change_records: number;
  policy_absence_slots: number;
  atomic_count_facts: number;
  claims_output_path: string;
  changes_output_path: string;
  manifest_output_path: string;
  claims_output_sha256: string;
};

type ClaimFinalizationChange = {
  change_schema_version: "claim_finalization_change_v1";
  change_id: string;
  generation_id: string;
  action: "ADD" | "UPDATE" | "DROP";
  old_claim_id: string | null;
  new_claim_id: string | null;
  rule_codes: ClaimFinalizationRuleCode[];
  changed_fields: string[];
  old_claim: AtomicClaimRecord | null;
  new_claim: AtomicClaimRecord | null;
};

const EXPECTED_PROMPT_SHA256 =
  "6c571dbe10b12e2f1b933fca366ae5f8b900520a330a9a36111ff9c477fb2553";

export async function runClaimFinalization(
  options: ClaimFinalizationOptions,
): Promise<ClaimFinalizationSummary> {
  validatePaths(options);

  const generationInput = await readJsonlStrict<JsonObject>(
    options.generationIndexPath,
  );
  const claimsInput = await readJsonlStrict<JsonObject>(
    options.claimsInputPath,
  );
  const attemptsInput = await readJsonlStrict<JsonObject>(
    options.attemptsInputPath,
  );
  const failuresInput = await readJsonlStrict<JsonObject>(
    options.failuresInputPath,
  );

  const rows = generationInput.records.map(
    (item) => item.value as unknown as CanonicalGenerationRow,
  );
  const inputClaims = claimsInput.records.map(
    (item) => item.value as unknown as AtomicClaimRecord,
  );
  const attempts = attemptsInput.records.map(
    (item) => item.value as unknown as StoredClaimExtractionAttemptRecord,
  );
  const failures = failuresInput.records.map(
    (item) => item.value as unknown as StoredClaimExtractionFailure,
  );

  const rowByGeneration = uniqueMap(rows, (row) => row.generation_id, "generation");
  const claimsByGeneration = groupBy(inputClaims, (claim) => claim.generation_id);
  const attemptsByGeneration = groupBy(attempts, (attempt) => attempt.generation_id);
  const failureByGeneration = uniqueMap(
    failures,
    (failure) => failure.generation_id,
    "failure",
  );

  validateCohort(
    rows,
    claimsByGeneration,
    failureByGeneration,
  );

  const finalClaims: AtomicClaimRecord[] = [];
  const tracedByGeneration = new Map<string, TracedClaim[]>();
  const replayAudit: Array<{
    generation_id: string;
    attempt_id: string;
    attempt_number: number;
    attempt_status: string;
    raw_response_sha256: string | null;
    replayed_claim_count: number;
    final_claim_count: number;
  }> = [];
  let atomicCountFacts = 0;
  const policyAbsenceSlots: Array<{
    generation_id: string;
    source_section: string;
    source_factor_id: string | null;
    source_text: string;
    policy: "NON_CLAIM_BEARING_POLICY_ABSENCE";
  }> = [];

  for (const row of rows) {
    if (failureByGeneration.has(row.generation_id)) continue;

    const document = buildGenerationTextDocument(row);
    atomicCountFacts += extractCountFacts(document).length;
    const replay = replayGeneration(
      row,
      document,
      attemptsByGeneration.get(row.generation_id) ?? [],
    );
    const finalized = finalizeGenerationClaims(replay.claims, document);
    assertFinalGeneration(row, document, finalized.map((item) => item.record));

    tracedByGeneration.set(row.generation_id, finalized);
    for (const traced of finalized) {
      finalClaims.push(traced.record);
    }

    for (const span of document.section_spans) {
      const sourceText = document.generation_text.slice(span.start, span.end);
      if (isPolicyAbsenceSlot(span.source_section, sourceText)) {
        policyAbsenceSlots.push({
          generation_id: row.generation_id,
          source_section: span.source_section,
          source_factor_id: span.source_factor_id,
          source_text: sourceText,
          policy: "NON_CLAIM_BEARING_POLICY_ABSENCE",
        });
      }
    }

    replayAudit.push({
      generation_id: row.generation_id,
      attempt_id: replay.attempt.attempt_id,
      attempt_number: replay.attempt.attempt_number,
      attempt_status: replay.attempt.status,
      raw_response_sha256: replay.attempt.raw_response_sha256,
      replayed_claim_count: replay.claims.length,
      final_claim_count: finalized.length,
    });
  }

  assertUniqueClaimIds(finalClaims);
  const changes = buildChanges(
    inputClaims,
    finalClaims,
    tracedByGeneration,
  );
  const actionCounts = countStrings(changes.map((change) => change.action));
  const changeRuleCounts = countStrings(
    changes.flatMap((change) => change.rule_codes),
  );

  await writeJsonlAtomic(options.claimsOutputPath, finalClaims);
  await writeJsonlAtomic(options.changesOutputPath, changes);
  const claimsDescriptor = await describeArtifact(
    options.claimsOutputPath,
    finalClaims.length,
  );
  const changesDescriptor = await describeArtifact(
    options.changesOutputPath,
    changes.length,
  );

  const changedGenerations = new Set(
    changes.map((change) => change.generation_id),
  );
  const manifest = {
    finalization_schema_version: "claim_finalization_manifest_v1",
    finalizer_version: CLAIM_FINALIZER_VERSION,
    policy_version: CLAIM_FINALIZATION_POLICY_VERSION,
    created_at: new Date().toISOString(),
    inputs: {
      generation_index: descriptorFromLoaded(generationInput),
      claims: descriptorFromLoaded(claimsInput),
      attempts: descriptorFromLoaded(attemptsInput),
      failures: descriptorFromLoaded(failuresInput),
    },
    outputs: {
      claims: claimsDescriptor,
      changes: changesDescriptor,
    },
    cohort: {
      canonical_generations: rows.length,
      successful_generations: rows.length - failures.length,
      unusable_generations: failures.length,
      input_claims: inputClaims.length,
      replayed_claims: replayAudit.reduce(
        (sum, item) => sum + item.replayed_claim_count,
        0,
      ),
      final_claims: finalClaims.length,
    },
    lineage: {
      extractor_version: ATOMIC_CLAIM_EXTRACTOR_VERSION,
      prompt_version: ATOMIC_CLAIM_PROMPT_VERSION,
      prompt_sha256: EXPECTED_PROMPT_SHA256,
      claim_schema_version: "claims_v2",
    },
    reproducibility: {
      provider_calls_made: 0,
      replayed_success_generations: replayAudit.length,
      stored_response_replay: replayAudit,
      deterministic_output_sha256: claimsDescriptor.sha256,
    },
    transformations: {
      changed_generations: changedGenerations.size,
      change_records: changes.length,
      action_counts: actionCounts,
      rule_counts: changeRuleCounts,
    },
    atomic_numeric_policy: {
      explicit_count_facts_are_claim_bearing: true,
      detected_count_facts: atomicCountFacts,
      validated_count_facts: atomicCountFacts,
      completeness_failures: 0,
    },
    coverage_policy: {
      policy_absence_slots_are_claim_bearing: false,
      policy_absence_slot_count: policyAbsenceSlots.length,
      policy_absence_slots: policyAbsenceSlots,
    },
  };
  await writeJsonAtomic(options.manifestOutputPath, manifest);

  return {
    canonical_generations: rows.length,
    successful_generations: replayAudit.length,
    unusable_generations: failures.length,
    input_claims: inputClaims.length,
    replayed_claims: replayAudit.reduce(
      (sum, item) => sum + item.replayed_claim_count,
      0,
    ),
    final_claims: finalClaims.length,
    changed_generations: changedGenerations.size,
    change_records: changes.length,
    policy_absence_slots: policyAbsenceSlots.length,
    atomic_count_facts: atomicCountFacts,
    claims_output_path: path.resolve(options.claimsOutputPath),
    changes_output_path: path.resolve(options.changesOutputPath),
    manifest_output_path: path.resolve(options.manifestOutputPath),
    claims_output_sha256: claimsDescriptor.sha256,
  };
}

function replayGeneration(
  row: CanonicalGenerationRow,
  document: ReturnType<typeof buildGenerationTextDocument>,
  attempts: StoredClaimExtractionAttemptRecord[],
): { claims: AtomicClaimRecord[]; attempt: StoredClaimExtractionAttemptRecord } {
  const candidates = attempts
    .filter((attempt) =>
      attempt.raw_response_text
      && attempt.source_input_sha256 === document.source_input_sha256
      && attempt.extractor_provider === "deepseek"
      && attempt.extractor_model_id === "deepseek-v4-flash"
      && attempt.extractor_version === ATOMIC_CLAIM_EXTRACTOR_VERSION
      && attempt.extractor_prompt_version === ATOMIC_CLAIM_PROMPT_VERSION
      && (
        !("extractor_prompt_sha256" in attempt)
        || attempt.extractor_prompt_sha256 === EXPECTED_PROMPT_SHA256
      ),
    )
    .sort((left, right) => right.attempt_number - left.attempt_number);

  const errors: string[] = [];
  for (const attempt of candidates) {
    try {
      validateStoredRawResponseHash(attempt);
      const parsed = parseStoredJsonObject(attempt.raw_response_text);
      const payload = validateAndNormalizeClaimPayload(parsed, document);
      if (payload.postprocess_metrics.llm_claim_count === 0) continue;
      const claims = payload.claims.map((draft): AtomicClaimRecord => ({
        ...draft,
        claim_schema_version: "claims_v2",
        claim_id: buildClaimId(
          row.generation_id,
          draft.semantic_signature,
          draft.source_span_start,
        ),
        generation_id: row.generation_id,
        model_id: row.model_id,
        source_ir_id: row.source_ir_id,
        case_id: row.case_id,
        evidence_level: row.evidence_level,
        repeat_id: row.repeat_id,
        source_input_sha256: document.source_input_sha256,
        source_text_sha256: sha256(draft.source_text),
        extractor_provider: "deepseek",
        extractor_model_id: "deepseek-v4-flash",
        extractor_version: ATOMIC_CLAIM_EXTRACTOR_VERSION,
        extractor_prompt_version: ATOMIC_CLAIM_PROMPT_VERSION,
        extractor_prompt_sha256: EXPECTED_PROMPT_SHA256,
        extractor_status: "SUCCESS",
      }));
      return { claims, attempt };
    } catch (error) {
      errors.push(error instanceof Error ? error.message : String(error));
    }
  }

  throw new Error(
    `No stored raw response can reproduce generation ${row.generation_id}. `
      + `Candidates=${candidates.length}; errors=${errors.join(" | ")}`,
  );
}

export function validateStoredRawResponseHash(
  attempt: StoredClaimExtractionAttemptRecord,
): void {
  const rawText = attempt.raw_response_text;
  const expectedHash = attempt.raw_response_sha256;
  if (!rawText || !expectedHash) {
    throw new Error(
      `Stored response hash metadata is incomplete: ${attempt.attempt_id}`,
    );
  }
  const actualHash = sha256(rawText);
  if (actualHash !== expectedHash) {
    throw new Error(
      `Stored response hash mismatch: ${attempt.attempt_id}; `
        + `expected=${expectedHash}; actual=${actualHash}`,
    );
  }
}

function parseStoredJsonObject(rawText: string | null): unknown {
  const trimmed = rawText?.trim();
  if (!trimmed) throw new Error("Stored response is empty.");

  const candidates = [trimmed];
  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/iu)?.[1];
  if (fenced) candidates.push(fenced);
  const firstBrace = trimmed.indexOf("{");
  const lastBrace = trimmed.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    candidates.push(trimmed.slice(firstBrace, lastBrace + 1));
  }

  for (const candidate of candidates) {
    try {
      const parsed: unknown = JSON.parse(candidate);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed;
      }
    } catch {
      // Continue with the next deterministic candidate.
    }
  }
  throw new Error("Stored response does not contain a JSON object.");
}

function buildChanges(
  inputClaims: AtomicClaimRecord[],
  finalClaims: AtomicClaimRecord[],
  tracedByGeneration: Map<string, TracedClaim[]>,
): ClaimFinalizationChange[] {
  const inputById = new Map(inputClaims.map((claim) => [claim.claim_id, claim]));
  const finalById = new Map(finalClaims.map((claim) => [claim.claim_id, claim]));
  const unmatchedInput = new Set(inputById.keys());
  const changes: ClaimFinalizationChange[] = [];

  for (const finalClaim of finalClaims) {
    const exact = inputById.get(finalClaim.claim_id);
    if (exact && JSON.stringify(exact) === JSON.stringify(finalClaim)) {
      unmatchedInput.delete(finalClaim.claim_id);
      continue;
    }

    const traced = tracedByGeneration
      .get(finalClaim.generation_id)
      ?.find((item) => item.record.claim_id === finalClaim.claim_id);
    const matchedOld = findBestOldClaim(
      finalClaim,
      inputClaims,
      unmatchedInput,
    );
    if (matchedOld) unmatchedInput.delete(matchedOld.claim_id);
    const action = matchedOld ? "UPDATE" : "ADD";
    const changedFields = matchedOld
      ? diffFields(matchedOld, finalClaim)
      : Object.keys(finalClaim).sort();
    const ruleCodes = new Set<ClaimFinalizationRuleCode>(
      traced?.rule_codes ?? [],
    );
    if (
      !matchedOld
      || !traced?.source_claim_ids.includes(matchedOld.claim_id)
    ) {
      ruleCodes.add("STORED_RESPONSE_REPLAY_CANONICALIZATION");
    }
    changes.push(buildChange({
      generationId: finalClaim.generation_id,
      action,
      oldClaim: matchedOld,
      newClaim: finalClaim,
      ruleCodes: [...ruleCodes].sort(),
      changedFields,
    }));
  }

  for (const oldClaimId of [...unmatchedInput].sort()) {
    const oldClaim = inputById.get(oldClaimId);
    if (!oldClaim || finalById.has(oldClaimId)) continue;
    const generationTraces = tracedByGeneration.get(oldClaim.generation_id) ?? [];
    const wasPolicyAbsenceClaim = isPolicyAbsenceSlot(
      oldClaim.source_section,
      oldClaim.source_text,
    );
    const wasFinalizerDeduplication = generationTraces.some((item) =>
      item.rule_codes.has("SEMANTIC_DEDUPLICATION")
    );
    changes.push(buildChange({
      generationId: oldClaim.generation_id,
      action: "DROP",
      oldClaim,
      newClaim: null,
      ruleCodes: wasPolicyAbsenceClaim
        ? ["DROP_POLICY_ABSENCE_CLAIM"]
        : wasFinalizerDeduplication
          ? ["SEMANTIC_DEDUPLICATION"]
          : ["STORED_RESPONSE_REPLAY_CANONICALIZATION"],
      changedFields: [],
    }));
  }

  return changes.sort((left, right) =>
    left.generation_id.localeCompare(right.generation_id)
    || left.action.localeCompare(right.action)
    || (left.old_claim_id ?? "").localeCompare(right.old_claim_id ?? "")
    || (left.new_claim_id ?? "").localeCompare(right.new_claim_id ?? ""),
  );
}

function findBestOldClaim(
  finalClaim: AtomicClaimRecord,
  inputClaims: AtomicClaimRecord[],
  unmatchedInput: Set<string>,
): AtomicClaimRecord | null {
  const candidates = inputClaims.filter((claim) =>
    unmatchedInput.has(claim.claim_id)
    && claim.generation_id === finalClaim.generation_id
    && claim.source_section === finalClaim.source_section
    && claim.source_factor_id === finalClaim.source_factor_id
    && claim.claim_origin === finalClaim.claim_origin
    && claim.model_normalized_claim_key === finalClaim.model_normalized_claim_key
    && claim.feature_id === finalClaim.feature_id
    && claim.concept_id === finalClaim.concept_id
    && claim.numeric_value === finalClaim.numeric_value,
  );
  if (candidates.length === 1) return candidates[0] ?? null;

  const sourceCandidates = inputClaims.filter((claim) =>
    unmatchedInput.has(claim.claim_id)
    && claim.generation_id === finalClaim.generation_id
    && claim.source_section === finalClaim.source_section
    && claim.source_factor_id === finalClaim.source_factor_id
    && claim.source_text === finalClaim.source_text
    && claim.numeric_value === finalClaim.numeric_value,
  );
  return sourceCandidates.length === 1 ? sourceCandidates[0] ?? null : null;
}

function buildChange(input: {
  generationId: string;
  action: ClaimFinalizationChange["action"];
  oldClaim: AtomicClaimRecord | null;
  newClaim: AtomicClaimRecord | null;
  ruleCodes: ClaimFinalizationRuleCode[];
  changedFields: string[];
}): ClaimFinalizationChange {
  const stable = JSON.stringify({
    generation_id: input.generationId,
    action: input.action,
    old_claim_id: input.oldClaim?.claim_id ?? null,
    new_claim_id: input.newClaim?.claim_id ?? null,
    rule_codes: input.ruleCodes,
    changed_fields: input.changedFields,
  });
  return {
    change_schema_version: "claim_finalization_change_v1",
    change_id: `claim_change_${sha256(stable).slice(0, 32)}`,
    generation_id: input.generationId,
    action: input.action,
    old_claim_id: input.oldClaim?.claim_id ?? null,
    new_claim_id: input.newClaim?.claim_id ?? null,
    rule_codes: input.ruleCodes,
    changed_fields: input.changedFields,
    old_claim: input.oldClaim,
    new_claim: input.newClaim,
  };
}

function assertFinalGeneration(
  row: CanonicalGenerationRow,
  document: ReturnType<typeof buildGenerationTextDocument>,
  claims: AtomicClaimRecord[],
): void {
  const ids = new Set<string>();
  const signatures = new Set<string>();
  claims.forEach((claim, index) => {
    if (claim.local_claim_index !== index + 1) {
      throw new Error(`Non-contiguous local indexes: ${row.generation_id}`);
    }
    if (ids.has(claim.claim_id)) {
      throw new Error(`Duplicate claim_id: ${claim.claim_id}`);
    }
    ids.add(claim.claim_id);
    if (signatures.has(claim.semantic_signature)) {
      throw new Error(
        `Duplicate semantic signature in ${row.generation_id}: `
          + claim.semantic_signature,
      );
    }
    signatures.add(claim.semantic_signature);
    if (claim.source_input_sha256 !== document.source_input_sha256) {
      throw new Error(`Source-input hash mismatch: ${claim.claim_id}`);
    }
    const exact = document.generation_text.slice(
      claim.source_span_start,
      claim.source_span_end,
    );
    if (exact !== claim.source_text) {
      throw new Error(`Exact source span mismatch: ${claim.claim_id}`);
    }
    if (claim.source_text_sha256 !== sha256(claim.source_text)) {
      throw new Error(`Source-text hash mismatch: ${claim.claim_id}`);
    }
    const expectedId = buildClaimId(
      claim.generation_id,
      claim.semantic_signature,
      claim.source_span_start,
    );
    if (claim.claim_id !== expectedId) {
      throw new Error(`Claim-ID mismatch: ${claim.claim_id}`);
    }
  });
}

function validateCohort(
  rows: CanonicalGenerationRow[],
  claimsByGeneration: Map<string, AtomicClaimRecord[]>,
  failureByGeneration: Map<string, StoredClaimExtractionFailure>,
): void {
  for (const row of rows) {
    const hasClaims = (claimsByGeneration.get(row.generation_id)?.length ?? 0) > 0;
    const failure = failureByGeneration.get(row.generation_id);
    if (row.usable) {
      if (!hasClaims || failure) {
        throw new Error(
          `Usable generation is not a clean success: ${row.generation_id}`,
        );
      }
    } else {
      if (hasClaims || !failure || failure.attempted) {
        throw new Error(
          `Unusable generation has invalid claim/failure state: ${row.generation_id}`,
        );
      }
    }
  }
  if (claimsByGeneration.size + failureByGeneration.size !== rows.length) {
    throw new Error("Claims and failures do not partition the canonical cohort.");
  }
}

function assertUniqueClaimIds(claims: AtomicClaimRecord[]): void {
  const ids = new Set<string>();
  for (const claim of claims) {
    if (ids.has(claim.claim_id)) {
      throw new Error(`Duplicate final claim_id: ${claim.claim_id}`);
    }
    ids.add(claim.claim_id);
  }
}

function buildClaimId(
  generationId: string,
  semanticSignature: string,
  sourceSpanStart: number,
): string {
  return `claim_${sha256(
    `${generationId}|${semanticSignature}|${sourceSpanStart}`,
  ).slice(0, 32)}`;
}

function diffFields(
  left: AtomicClaimRecord,
  right: AtomicClaimRecord,
): string[] {
  return [...new Set([...Object.keys(left), ...Object.keys(right)])]
    .filter((key) =>
      JSON.stringify(
        (left as unknown as Record<string, unknown>)[key],
      ) !== JSON.stringify(
        (right as unknown as Record<string, unknown>)[key],
      ),
    )
    .sort();
}

function descriptorFromLoaded(input: {
  path: string;
  sha256: string;
  byte_count: number;
  records: unknown[];
}): {
  path: string;
  sha256: string;
  byte_count: number;
  record_count: number;
} {
  return {
    path: input.path,
    sha256: input.sha256,
    byte_count: input.byte_count,
    record_count: input.records.length,
  };
}

function uniqueMap<T>(
  values: T[],
  key: (value: T) => string,
  label: string,
): Map<string, T> {
  const result = new Map<string, T>();
  for (const value of values) {
    const itemKey = key(value);
    if (result.has(itemKey)) {
      throw new Error(`Duplicate ${label} key: ${itemKey}`);
    }
    result.set(itemKey, value);
  }
  return result;
}

function groupBy<T>(
  values: T[],
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

function countStrings(values: string[]): Record<string, number> {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return Object.fromEntries(
    [...counts.entries()].sort(([left], [right]) => left.localeCompare(right)),
  );
}

function validatePaths(options: ClaimFinalizationOptions): void {
  const inputs = [
    options.generationIndexPath,
    options.claimsInputPath,
    options.attemptsInputPath,
    options.failuresInputPath,
  ].map((value) => path.resolve(value));
  const outputs = [
    options.claimsOutputPath,
    options.changesOutputPath,
    options.manifestOutputPath,
  ].map((value) => path.resolve(value));
  if (new Set(outputs).size !== outputs.length) {
    throw new Error("Finalization output paths must be distinct.");
  }
  if (outputs.some((output) => inputs.includes(output))) {
    throw new Error("Finalization must not overwrite an input artifact.");
  }
}
