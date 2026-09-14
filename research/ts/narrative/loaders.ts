import { readTextFile } from "./artifacts";
import type {
  EvidenceLevel,
  EvidencePackage,
  TargetSemanticsPayload,
} from "../../../contracts/narrative";

export async function readJsonl<T>(pathOrS3Uri: string): Promise<T[]> {
  const content = await readTextFile(pathOrS3Uri);
  const records: T[] = [];
  const lines = content.split(/\r?\n/);

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (!line) {
      continue;
    }

    try {
      records.push(JSON.parse(line) as T);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Invalid JSONL at line ${index + 1}: ${message}`);
    }
  }

  return records;
}

export async function loadEvidencePackages(
  pathOrS3Uri: string,
): Promise<EvidencePackage[]> {
  const packages = await readJsonl<EvidencePackage>(pathOrS3Uri);

  for (let index = 0; index < packages.length; index += 1) {
    validateEvidencePackage(packages[index], index + 1);
  }

  return packages;
}

function validateEvidencePackage(
  packageItem: EvidencePackage,
  lineNumber: number,
): void {
  if (!packageItem || typeof packageItem !== "object") {
    throw new Error(`Evidence package line ${lineNumber} is not an object.`);
  }

  if (!packageItem.package_id) {
    throw new Error(
      `Evidence package line ${lineNumber} is missing package_id.`,
    );
  }

  if (!packageItem.source_ir_id) {
    throw new Error(
      `Evidence package ${packageItem.package_id} is missing source_ir_id.`,
    );
  }

  if (!isEvidenceLevel(packageItem.evidence_level)) {
    throw new Error(
      `Evidence package ${packageItem.package_id} has invalid evidence_level.`,
    );
  }

  if (!packageItem.prompt_payload) {
    throw new Error(
      `Evidence package ${packageItem.package_id} is missing prompt_payload.`,
    );
  }

  if (
    packageItem.prompt_payload.evidence_level !== packageItem.evidence_level
  ) {
    throw new Error(
      `Evidence package ${packageItem.package_id} has mismatched prompt_payload level.`,
    );
  }

  const promptSemantics = packageItem.prompt_payload.target_semantics;
  const packageSemantics = packageItem.target_semantics;
  if (promptSemantics) {
    validateTargetSemantics(
      promptSemantics,
      `Evidence package ${packageItem.package_id} prompt target semantics`,
    );
  }
  const completePackageSemantics = isCompleteTargetSemantics(packageSemantics)
    ? packageSemantics
    : undefined;
  if (completePackageSemantics) {
    validateTargetSemantics(
      completePackageSemantics,
      `Evidence package ${packageItem.package_id} target semantics`,
    );
  }
  if (promptSemantics && completePackageSemantics) {
    for (const key of [
      "positive_label",
      "negative_label",
      "prediction_subject",
      "positive_display_name",
      "negative_display_name",
      "positive_direction_phrase",
      "negative_direction_phrase",
    ] as const) {
      if (promptSemantics[key] !== completePackageSemantics[key]) {
        throw new Error(
          `Evidence package ${packageItem.package_id} has conflicting target semantics for ${key}.`,
        );
      }
    }
  }
}

function isCompleteTargetSemantics(
  value: unknown,
): value is TargetSemanticsPayload {
  if (!value || typeof value !== "object") return false;
  const semantics = value as Record<string, unknown>;
  return [
    "positive_label",
    "negative_label",
    "prediction_subject",
    "positive_display_name",
    "negative_display_name",
    "positive_direction_phrase",
    "negative_direction_phrase",
  ].every((key) => typeof semantics[key] === "string" && semantics[key]!.trim());
}

function validateTargetSemantics(
  semantics: TargetSemanticsPayload,
  context: string,
): void {
  for (const key of [
    "positive_label",
    "negative_label",
    "prediction_subject",
    "positive_display_name",
    "negative_display_name",
    "positive_direction_phrase",
    "negative_direction_phrase",
  ] as const) {
    if (typeof semantics[key] !== "string" || !semantics[key].trim()) {
      throw new Error(`${context}.${key} must be a non-empty string.`);
    }
  }
  if (semantics.positive_label === semantics.negative_label) {
    throw new Error(`${context} positive_label and negative_label must differ.`);
  }
}

export function isEvidenceLevel(value: unknown): value is EvidenceLevel {
  return (
    value === "S0" ||
    value === "S1" ||
    value === "S2" ||
    value === "S3" ||
    value === "S4" ||
    value === "S5"
  );
}

export function getOrderedCaseIds(packages: EvidencePackage[]): string[] {
  const result: string[] = [];
  const seen = new Set<string>();

  for (const packageItem of packages) {
    if (!seen.has(packageItem.source_ir_id)) {
      seen.add(packageItem.source_ir_id);
      result.push(packageItem.source_ir_id);
    }
  }

  return result;
}
