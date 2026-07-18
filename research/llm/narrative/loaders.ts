import { readTextFile } from "./artifacts";
import type { EvidenceLevel, EvidencePackage } from "../../../contracts/narrative";

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
