// q chỉ là quality index; hàm này chỉ nhận hệ số calibration đã fit từ nhãn human.
export function calibratedAcceptProbability(
  generationQuality: number,
  intercept: number,
  slope: number,
): number {
  if (!Number.isFinite(intercept) || !Number.isFinite(slope)) {
    throw new Error("Calibration intercept and slope must be finite.");
  }
  if (generationQuality < 0 || generationQuality > 1) {
    throw new Error("generationQuality must be between 0 and 1.");
  }
  const logit = intercept + slope * generationQuality;
  if (logit >= 0) return 1 / (1 + Math.exp(-logit));
  const exponential = Math.exp(logit);
  return exponential / (1 + exponential);
}

export function shouldAcceptAtRuntime(input: {
  hardGatePass: boolean;
  calibratedAcceptProbability: number;
  threshold?: number;
}): boolean {
  const threshold = input.threshold ?? 0.9;
  if (threshold <= 0 || threshold >= 1) {
    throw new Error("Runtime probability threshold must be between 0 and 1.");
  }
  if (
    !Number.isFinite(input.calibratedAcceptProbability) ||
    input.calibratedAcceptProbability < 0 ||
    input.calibratedAcceptProbability > 1
  ) {
    throw new Error("calibratedAcceptProbability must be between 0 and 1.");
  }
  return (
    input.hardGatePass && input.calibratedAcceptProbability >= threshold
  );
}
