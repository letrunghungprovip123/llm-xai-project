import { access, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import thresholds from "../../../../config/research/ts-validation/claim_validation_test_thresholds_v1.json";
import { reasonCodeByName } from "../reasonCodes";
import {
  CALIBRATION_STATUSES,
  type CalibrationStatus,
  classificationReport,
  cohensKappa,
  rawAgreement,
} from "./metrics";
import { parseCsv, readJsonl } from "./io";

type Reference = {
  blind_id: string;
  claim_id: string;
  model_id: string;
  evidence_level: string;
  claim_type: string;
  claim_subtype: string;
  validator_status: CalibrationStatus;
  hard_safety: boolean;
};

type BlindIndex = {
  blind_id: string;
  claim_id: string;
};

type ValidatorResult = {
  claim_id: string;
  model_id: string;
  evidence_level: string;
  claim_type: string;
  claim_subtype: string;
  validation_status: CalibrationStatus | "NOT_APPLICABLE" | null;
  reason_code: string;
};

type Rating = {
  blindId: string;
  raterId: string;
  validationStatus: CalibrationStatus;
};

export type CalibrationEvaluationOptions = {
  packageDirectory: string;
  raterAPath: string;
  raterBPath: string;
  adjudicationPath?: string;
  outputPath: string;
};

export async function evaluateCalibration(
  options: CalibrationEvaluationOptions,
): Promise<Record<string, unknown>> {
  const manifest = JSON.parse(
    await readFile(
      path.join(options.packageDirectory, "blinding_manifest.json"),
      "utf8",
    ),
  ) as { source_results_path: string };
  const [blindIndex, validatorResults] = await Promise.all([
    readJsonl<BlindIndex>(
      path.join(options.packageDirectory, "validator_reference.jsonl"),
    ),
    readJsonl<ValidatorResult>(manifest.source_results_path),
  ]);
  const resultByClaimId = new Map(
    validatorResults.map((result) => [result.claim_id, result]),
  );
  const references = blindIndex.map(({ blind_id, claim_id }) => {
    const result = resultByClaimId.get(claim_id);
    if (!result || !result.validation_status) {
      throw new Error(`Missing validator result for blinded claim ${blind_id}.`);
    }
    return {
      blind_id,
      claim_id,
      model_id: result.model_id,
      evidence_level: result.evidence_level,
      claim_type: result.claim_type,
      claim_subtype: result.claim_subtype,
      validator_status: result.validation_status as CalibrationStatus,
      hard_safety: reasonCodeByName(result.reason_code).is_hard_safety_failure,
    };
  });
  const [ratingsA, ratingsB] = await Promise.all([
    loadRatings(options.raterAPath),
    loadRatings(options.raterBPath),
  ]);
  const adjudications =
    options.adjudicationPath && (await exists(options.adjudicationPath))
      ? await loadRatings(options.adjudicationPath)
      : [];
  const aById = new Map(ratingsA.map((rating) => [rating.blindId, rating]));
  const bById = new Map(ratingsB.map((rating) => [rating.blindId, rating]));
  const adjudicatedById = new Map(
    adjudications.map((rating) => [rating.blindId, rating]),
  );
  const doubleRated = references.filter(
    (reference) => aById.has(reference.blind_id) && bById.has(reference.blind_id),
  );
  const disagreements = doubleRated.filter(
    (reference) =>
      aById.get(reference.blind_id)?.validationStatus !==
      bById.get(reference.blind_id)?.validationStatus,
  );
  const unresolvedDisagreements = disagreements.filter(
    (reference) => !adjudicatedById.has(reference.blind_id),
  );
  const completed = doubleRated.filter(
    (reference) =>
      !disagreements.includes(reference) ||
      adjudicatedById.has(reference.blind_id),
  );
  const humanStatuses = completed.map((reference) =>
    adjudicatedById.get(reference.blind_id)?.validationStatus ??
    aById.get(reference.blind_id)!.validationStatus,
  );
  const validatorStatuses = completed.map((reference) => reference.validator_status);
  const agreementA = doubleRated.map(
    (reference) => aById.get(reference.blind_id)!.validationStatus,
  );
  const agreementB = doubleRated.map(
    (reference) => bById.get(reference.blind_id)!.validationStatus,
  );
  const agreement = {
    raw_agreement: rawAgreement(agreementA, agreementB),
    cohens_kappa: cohensKappa(agreementA, agreementB),
  };
  const classifier = classificationReport(humanStatuses, validatorStatuses);
  const breakdowns = {
    by_model: groupedMetrics(completed, humanStatuses, validatorStatuses, (row) => row.model_id),
    by_level: groupedMetrics(completed, humanStatuses, validatorStatuses, (row) => row.evidence_level),
    by_claim_type: groupedMetrics(completed, humanStatuses, validatorStatuses, (row) => row.claim_type),
    by_claim_subtype: groupedMetrics(completed, humanStatuses, validatorStatuses, (row) => row.claim_subtype),
  };
  const hardSafetyFalseNegatives = completed.filter(
    (reference, index) =>
      reference.hard_safety &&
      humanStatuses[index] !== "SUPPORTED" &&
      validatorStatuses[index] === "SUPPORTED",
  ).length;
  const gates = {
    required_sample_completed:
      doubleRated.length >= thresholds.calibration.minimum_double_rated &&
      doubleRated.length === references.length,
    all_disagreements_adjudicated: unresolvedDisagreements.length === 0,
    raw_agreement:
      agreement.raw_agreement >= thresholds.calibration.minimum_raw_agreement,
    overall_kappa:
      agreement.cohens_kappa >= thresholds.calibration.minimum_overall_kappa,
    overall_macro_f1:
      classifier.macro_f1 >= thresholds.calibration.minimum_macro_f1,
    supported_precision:
      classifier.per_status.SUPPORTED.precision >=
      thresholds.calibration.minimum_supported_precision,
    contradicted_precision:
      classifier.per_status.CONTRADICTED.precision >=
      thresholds.calibration.minimum_contradicted_precision,
    not_verifiable_precision:
      classifier.per_status.NOT_VERIFIABLE.precision >=
      thresholds.calibration.minimum_not_verifiable_precision,
    hard_safety_false_negatives:
      hardSafetyFalseNegatives <=
      thresholds.calibration.maximum_hard_safety_false_negatives,
  };
  const report = {
    schema_version: "human_calibration_report_v1",
    generated_at: new Date().toISOString(),
    status: Object.values(gates).every(Boolean) ? "COMPLETE_PASS" : "INCOMPLETE_OR_FAIL",
    reference_count: references.length,
    rater_a_completed_count: ratingsA.length,
    rater_b_completed_count: ratingsB.length,
    double_rated_count: doubleRated.length,
    disagreement_count: disagreements.length,
    adjudication_count: adjudications.length,
    unresolved_disagreement_count: unresolvedDisagreements.length,
    agreement,
    validator_vs_human: {
      ...classifier,
      hard_safety_false_negative_count: hardSafetyFalseNegatives,
    },
    breakdowns,
    thresholds: thresholds.calibration,
    gates,
    c6_pass: Object.values(gates).every(Boolean),
  };
  await writeFile(options.outputPath, `${JSON.stringify(report, null, 2)}\n`);
  return report;
}

async function loadRatings(filePath: string): Promise<Rating[]> {
  const rows = parseCsv(await readFile(filePath, "utf8"));
  return rows
    .filter((row) => row.validation_status?.trim().length > 0)
    .map((row) => {
      const status = row.validation_status.trim();
      if (!CALIBRATION_STATUSES.includes(status as CalibrationStatus)) {
        throw new Error(`Invalid human validation status for ${row.blind_id}.`);
      }
      if (!row.rater_id?.trim()) {
        throw new Error(`Missing pseudonymous rater_id for ${row.blind_id}.`);
      }
      return {
        blindId: row.blind_id,
        raterId: row.rater_id,
        validationStatus: status as CalibrationStatus,
      };
    });
}

function groupedMetrics(
  rows: Reference[],
  expected: CalibrationStatus[],
  predicted: CalibrationStatus[],
  key: (row: Reference) => string,
): Record<string, unknown> {
  const indexes = new Map<string, number[]>();
  rows.forEach((row, index) => {
    const group = indexes.get(key(row)) ?? [];
    group.push(index);
    indexes.set(key(row), group);
  });
  return Object.fromEntries(
    [...indexes.entries()].sort(([left], [right]) => left.localeCompare(right)).map(
      ([name, group]) => [
        name,
        {
          count: group.length,
          ...classificationReport(
            group.map((index) => expected[index]),
            group.map((index) => predicted[index]),
          ),
        },
      ],
    ),
  );
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}
