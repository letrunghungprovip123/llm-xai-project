import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import type { AtomicClaimRecordV3 } from "../../../../contracts/validation-claims";
import { reasonCodeByName } from "../reasonCodes";
import type { ClaimValidationResult } from "../types";
import { csvCell, readJsonl, stableBlindId } from "./io";

export type CalibrationPreparationOptions = {
  resultsPath: string;
  claimsPath: string;
  outputDirectory: string;
  sampleSize: number;
};

type Candidate = {
  result: ClaimValidationResult;
  claim: AtomicClaimRecordV3;
  blindId: string;
  reasonFamily: string;
  selectionStratum: string;
  priority: number;
  hash: string;
};

export async function prepareCalibrationPackage(
  options: CalibrationPreparationOptions,
): Promise<Record<string, unknown>> {
  if (!Number.isInteger(options.sampleSize) || options.sampleSize < 1) {
    throw new Error("Calibration sample size must be a positive integer.");
  }
  const [results, claims] = await Promise.all([
    readJsonl<ClaimValidationResult>(options.resultsPath),
    readJsonl<AtomicClaimRecordV3>(options.claimsPath),
  ]);
  const claimById = new Map(claims.map((claim) => [claim.claim_id, claim]));
  const candidates = results
    .filter(
      (result): result is Extract<ClaimValidationResult, { execution_status: "SUCCESS" }> =>
        result.execution_status === "SUCCESS" &&
        result.validation_status !== "NOT_APPLICABLE",
    )
    .map((result) => {
      const claim = claimById.get(result.claim_id);
      if (!claim) throw new Error(`Calibration claim join failed: ${result.claim_id}.`);
      const reasonFamily = reasonCodeByName(result.reason_code).family;
      const selectionStratum = [
        result.evidence_level,
        result.claim_type,
        result.claim_subtype,
        result.validation_status,
        reasonFamily,
      ].join("|");
      return {
        result,
        claim,
        blindId: stableBlindId(result.claim_id),
        reasonFamily,
        selectionStratum,
        priority: oversamplePriority(result, reasonFamily),
        hash: createHash("sha256").update(`calibration-v1|${result.claim_id}`).digest("hex"),
      };
    });
  const selected = stratifiedSelection(candidates, Math.min(options.sampleSize, candidates.length));
  await mkdir(options.outputDirectory, { recursive: true });
  const blinded = selected.map(({ result, claim, blindId }) => ({
    schema_version: "human_calibration_blinded_claim_v1",
    blind_id: blindId,
    evidence_level: result.evidence_level,
    claim_type: result.claim_type,
    claim_subtype: result.claim_subtype,
    source_section: claim.source_section,
    source_text: claim.source_text,
    expected_evidence_summary: result.expected,
    observed_evidence_summary: result.observed,
    policy_context: {
      feature_exposure_status: result.feature_exposure_status,
      concept_exposure_status: result.concept_exposure_status,
    },
  }));
  const reference = selected.map(
    ({ result, blindId }) => ({
      blind_id: blindId,
      claim_id: result.claim_id,
    }),
  );
  const template = annotationTemplate(selected.map((item) => item.blindId));
  const manifest = {
    schema_version: "human_calibration_blinding_manifest_v1",
    generated_at: new Date().toISOString(),
    source_results_path: path.resolve(options.resultsPath),
    source_claims_path: path.resolve(options.claimsPath),
    candidate_count: candidates.length,
    requested_sample_size: options.sampleSize,
    selected_count: selected.length,
    selection_algorithm: "priority_stratified_round_robin_sha256_v1",
    blinded_fields: [
      "validator_status",
      "validator_reason_code",
      "model_id",
      "candidate_winner",
    ],
    annotation_schema:
      "contracts/llm-validation/human_calibration.schema.json",
    blind_index_file: "validator_reference.jsonl",
  };
  await Promise.all([
    writeFile(path.join(options.outputDirectory, "blinded_claims.jsonl"), jsonl(blinded)),
    writeFile(path.join(options.outputDirectory, "validator_reference.jsonl"), jsonl(reference)),
    writeFile(path.join(options.outputDirectory, "annotation_template_rater_a.csv"), template),
    writeFile(path.join(options.outputDirectory, "annotation_template_rater_b.csv"), template),
    writeFile(
      path.join(options.outputDirectory, "blinding_manifest.json"),
      `${JSON.stringify(manifest, null, 2)}\n`,
    ),
    writeFile(
      path.join(options.outputDirectory, "calibration_instructions.md"),
      calibrationInstructions(),
    ),
  ]);
  return manifest;
}

function stratifiedSelection(candidates: Candidate[], limit: number): Candidate[] {
  const queues = new Map<string, Candidate[]>();
  for (const candidate of candidates) {
    const key = `${candidate.priority}|${candidate.selectionStratum}`;
    const queue = queues.get(key) ?? [];
    queue.push(candidate);
    queues.set(key, queue);
  }
  for (const queue of queues.values()) queue.sort((a, b) => a.hash.localeCompare(b.hash));
  const keys = [...queues.keys()].sort((a, b) => {
    const priority = Number(b.split("|", 1)[0]) - Number(a.split("|", 1)[0]);
    return priority || a.localeCompare(b);
  });
  const selected: Candidate[] = [];
  while (selected.length < limit) {
    let progressed = false;
    for (const key of keys) {
      const item = queues.get(key)?.shift();
      if (!item) continue;
      selected.push(item);
      progressed = true;
      if (selected.length === limit) break;
    }
    if (!progressed) break;
  }
  return selected.sort((a, b) => a.blindId.localeCompare(b.blindId));
}

function oversamplePriority(
  result: Extract<ClaimValidationResult, { execution_status: "SUCCESS" }>,
  reasonFamily: string,
): number {
  let priority = result.validation_status === "SUPPORTED" ? 0 : 2;
  if (result.policy_status === "VIOLATION") priority += 2;
  if (result.observed.direction === "mixed") priority += 2;
  if (
    result.feature_exposure_status === "EXPOSED_FORBIDDEN" ||
    result.concept_exposure_status === "EXPOSED_FORBIDDEN"
  ) priority += 2;
  if (["CAUSAL", "POLICY", "SEMANTIC"].includes(reasonFamily)) priority += 1;
  return priority;
}

function annotationTemplate(blindIds: string[]): string {
  const header = [
    "blind_id",
    "rater_id",
    "claim_type_correct",
    "claim_complete",
    "evidence_identity_correct",
    "validation_status",
    "reason_family",
    "critical_ambiguity",
    "notes",
  ];
  return [
    header.map(csvCell).join(","),
    ...blindIds.map((blindId) =>
      [blindId, "", "", "", "", "", "", "", ""].map(csvCell).join(","),
    ),
  ].join("\n") + "\n";
}

function calibrationInstructions(): string {
  return `# Human claim-validation calibration

Two independent human raters must annotate every row without consulting
\`validator_reference.jsonl\`. Use only the blinded claim and exposed evidence.
Allowed validation statuses are SUPPORTED, UNSUPPORTED, CONTRADICTED, and
NOT_VERIFIABLE. Preserve both raw ratings and adjudicate every disagreement.
Do not rewrite model text or evidence. Rater identifiers must be pseudonymous.
`;
}

function jsonl(values: readonly unknown[]): string {
  return values.map((value) => JSON.stringify(value)).join("\n") + "\n";
}
