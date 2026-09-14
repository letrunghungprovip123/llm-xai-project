import type {
  EvidencePackage,
  GenerationRecord,
  RunOptions,
} from "../../../contracts/narrative";
import { sanitizeFilePart } from "../common/utils";
import { getOrderedCaseIds } from "./loaders";

export function isGenerationUsable(record: GenerationRecord): boolean {
  const runtime = record.runtime_metrics;
  const schema = record.schema_metrics;

  return (
    runtime.status === "SUCCESS" &&
    runtime.empty_response !== true &&
    runtime.truncated_response !== true &&
    runtime.finish_reason !== "length" &&
    schema.raw_json_parse_success === true &&
    schema.schema_valid === true &&
    schema.missing_required_field_count === 0 &&
    schema.validation_error_count === 0 &&
    record.parsed_output !== null
  );
}

export function buildGenerationId(
  runId: string,
  modelId: string,
  repeatId: number,
  packageId: string,
): string {
  return [
    sanitizeFilePart(runId),
    sanitizeFilePart(modelId),
    `r${repeatId}`,
    sanitizeFilePart(packageId),
  ].join("__");
}

export function selectPackages(
  packages: EvidencePackage[],
  options: RunOptions,
): EvidencePackage[] {
  let caseIds = getOrderedCaseIds(packages);

  if (options.chunk_start > 0 || options.chunk_size !== undefined) {
    const end =
      options.chunk_size === undefined
        ? undefined
        : options.chunk_start + options.chunk_size;
    caseIds = caseIds.slice(options.chunk_start, end);
  }

  if (options.limit_cases !== undefined) {
    caseIds = caseIds.slice(0, options.limit_cases);
  }

  const selectedCaseIds = new Set(caseIds);
  const selectedLevels = new Set(options.levels);

  return packages.filter((packageItem) => {
    return (
      selectedCaseIds.has(packageItem.source_ir_id) &&
      selectedLevels.has(packageItem.evidence_level)
    );
  });
}
