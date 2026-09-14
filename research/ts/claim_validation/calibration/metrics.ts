export const CALIBRATION_STATUSES = [
  "SUPPORTED",
  "UNSUPPORTED",
  "CONTRADICTED",
  "NOT_VERIFIABLE",
] as const;

export type CalibrationStatus = (typeof CALIBRATION_STATUSES)[number];

export type ClassificationMetrics = {
  precision: number;
  recall: number;
  f1: number;
  support: number;
};

export function rawAgreement(
  left: readonly CalibrationStatus[],
  right: readonly CalibrationStatus[],
): number {
  assertParallel(left, right);
  if (left.length === 0) return 0;
  return left.filter((value, index) => value === right[index]).length / left.length;
}

export function cohensKappa(
  left: readonly CalibrationStatus[],
  right: readonly CalibrationStatus[],
): number {
  assertParallel(left, right);
  if (left.length === 0) return 0;
  const observed = rawAgreement(left, right);
  const expected = CALIBRATION_STATUSES.reduce((sum, status) => {
    const leftRate = left.filter((value) => value === status).length / left.length;
    const rightRate = right.filter((value) => value === status).length / right.length;
    return sum + leftRate * rightRate;
  }, 0);
  return expected === 1 ? (observed === 1 ? 1 : 0) : (observed - expected) / (1 - expected);
}

export function classificationReport(
  expected: readonly CalibrationStatus[],
  predicted: readonly CalibrationStatus[],
): {
  per_status: Record<CalibrationStatus, ClassificationMetrics>;
  macro_f1: number;
  false_accept_rate: number;
  false_reject_rate: number;
} {
  assertParallel(expected, predicted);
  const perStatus = Object.fromEntries(
    CALIBRATION_STATUSES.map((status) => {
      const truePositive = expected.filter(
        (value, index) => value === status && predicted[index] === status,
      ).length;
      const falsePositive = expected.filter(
        (value, index) => value !== status && predicted[index] === status,
      ).length;
      const falseNegative = expected.filter(
        (value, index) => value === status && predicted[index] !== status,
      ).length;
      const precision = ratio(truePositive, truePositive + falsePositive);
      const recall = ratio(truePositive, truePositive + falseNegative);
      return [
        status,
        {
          precision,
          recall,
          f1: precision + recall === 0 ? 0 : (2 * precision * recall) / (precision + recall),
          support: expected.filter((value) => value === status).length,
        },
      ];
    }),
  ) as Record<CalibrationStatus, ClassificationMetrics>;
  const macroF1 =
    CALIBRATION_STATUSES.reduce((sum, status) => sum + perStatus[status].f1, 0) /
    CALIBRATION_STATUSES.length;
  const humanUnsupported = expected.map((value) => value !== "SUPPORTED");
  const validatorSupported = predicted.map((value) => value === "SUPPORTED");
  const falseAccepts = humanUnsupported.filter(
    (value, index) => value && validatorSupported[index],
  ).length;
  const humanSupported = expected.map((value) => value === "SUPPORTED");
  const falseRejects = humanSupported.filter(
    (value, index) => value && !validatorSupported[index],
  ).length;
  return {
    per_status: perStatus,
    macro_f1: macroF1,
    false_accept_rate: ratio(falseAccepts, humanUnsupported.filter(Boolean).length),
    false_reject_rate: ratio(falseRejects, humanSupported.filter(Boolean).length),
  };
}

function ratio(numerator: number, denominator: number): number {
  return denominator === 0 ? 0 : numerator / denominator;
}

function assertParallel(left: readonly unknown[], right: readonly unknown[]): void {
  if (left.length !== right.length) {
    throw new Error(`Metric input length mismatch: ${left.length} vs ${right.length}.`);
  }
}
