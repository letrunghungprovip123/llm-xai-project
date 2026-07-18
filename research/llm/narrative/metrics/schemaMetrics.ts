import type { ParseResult, SchemaMetrics } from "../../../../contracts/narrative";

export function buildSchemaMetrics(parseResult: ParseResult): SchemaMetrics {
  return {
    raw_json_parse_success: parseResult.raw_json_parse_success,
    json_parse_success: parseResult.json_parse_success,
    schema_valid: parseResult.schema_valid,
    missing_required_field_count: parseResult.missing_required_fields.length,
    validation_error_count: parseResult.validation_errors.length,
    cleanup_type: parseResult.cleanup_type,
  };
}
