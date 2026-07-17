import policyJson from "../../../../config/llm-validation/selection_policy_v1.json";
import type { FrozenSelectionPolicy } from "../../../types/validation-selection";

// Policy được import trực tiếp từ file frozen để code và báo cáo luôn dùng cùng một nguồn.
export const FROZEN_SELECTION_POLICY =
  policyJson as unknown as FrozenSelectionPolicy;

export function assertFrozenSelectionPolicy(
  policy: FrozenSelectionPolicy = FROZEN_SELECTION_POLICY,
): void {
  if (policy.status !== "FROZEN_BEFORE_FINAL_VALIDATION") {
    throw new Error("Selection policy is not frozen.");
  }
  if (policy.generation_quality.combination !== "weighted_geometric_mean") {
    throw new Error("Only weighted geometric mean is allowed by policy v1.");
  }
  const weightSum = Object.values(
    policy.generation_quality.soft_metric_weights,
  ).reduce((sum, value) => sum + value, 0);
  if (Math.abs(weightSum - 1) > 1e-9) {
    throw new Error(`Generation quality weights must sum to 1, found ${weightSum}.`);
  }
  if (policy.non_inferiority.margin <= 0) {
    throw new Error("Non-inferiority margin must be positive.");
  }
}

