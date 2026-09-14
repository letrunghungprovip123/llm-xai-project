"""Configuration for generation-level metric engineering."""

from __future__ import annotations

from research.python.common.paths import DEFAULT_PATHS


PROJECT_ROOT = DEFAULT_PATHS.project_root
VALIDATION_ROOT = (
    PROJECT_ROOT
    / "data"
    / "reports"
    / "llm_validation"
    / "validation_v1"
)
DATA_MART_DIR = VALIDATION_ROOT / "analysis" / "data_mart"

GENERATIONS_PATH = DATA_MART_DIR / "generations.csv"
CLAIMS_PATH = DATA_MART_DIR / "claims.csv"
DATA_MART_VALIDATION_PATH = DATA_MART_DIR / "data_mart_validation.json"

GENERATION_METRICS_PATH = DATA_MART_DIR / "generation_metrics.csv"
METRIC_DICTIONARY_PATH = DATA_MART_DIR / "metric_dictionary.csv"
METRIC_VALIDATION_PATH = DATA_MART_DIR / "metric_validation.json"

METRIC_ENGINEERING_VERSION = "1.0"
BASE_EXIT_GATE = "DATA_MART_READY"
METRIC_EXIT_GATE = "METRICS_READY"
FINAL_EXIT_GATE = "ANALYTICAL_MART_READY"
INVALID_EXIT_GATE = "METRICS_INVALID"

EXPECTED_COUNTS = {
    "generations": 648,
    "usable_generations": 638,
    "unusable_generations": 10,
    "claims": 14_667,
    "models": 3,
    "evidence_levels": 6,
    "model_evidence_cells": 18,
    "generations_per_model_evidence_cell": 36,
}

REQUIRED_GENERATION_COLUMNS = {
    "generation_id",
    "case_id",
    "model_id",
    "evidence_level",
    "package_id",
    "selection_stratum",
    "model_order",
    "evidence_order",
    "case_order",
    "runtime_status",
    "runtime_error_type",
    "runtime_error_message",
    "truncated_response",
    "raw_json_parse_success",
    "json_parse_success",
    "schema_valid",
    "usable",
    "retry_count",
    "latency_ms",
    "input_token_count",
    "output_token_count",
    "total_token_count",
    "claim_count",
    "supported_count",
    "unsupported_count",
    "contradicted_count",
    "not_verifiable_count",
    "not_applicable_count",
    "resolved_count",
    "applicable_count",
}

REQUIRED_CLAIM_COLUMNS = {
    "claim_id",
    "generation_id",
    "validation_status",
}

IDENTITY_COLUMNS = [
    "generation_id",
    "case_id",
    "model_id",
    "evidence_level",
    "package_id",
    "selection_stratum",
]

SOURCE_COUNT_COLUMNS = [
    "claim_count",
    "supported_count",
    "unsupported_count",
    "contradicted_count",
    "not_verifiable_count",
    "not_applicable_count",
    "resolved_count",
    "applicable_count",
]

SOURCE_RUNTIME_COLUMNS = [
    "usable",
    "runtime_status",
    "runtime_error_type",
    "runtime_error_message",
    "truncated_response",
    "raw_json_parse_success",
    "json_parse_success",
    "schema_valid",
    "retry_count",
    "latency_ms",
    "input_token_count",
    "output_token_count",
    "total_token_count",
]

DERIVED_METRIC_COLUMNS = [
    "quality_metric_eligible",
    "resolved_faithfulness",
    "verifiability",
    "conservative_faithfulness",
    "end_to_end_faithfulness_yield",
    "not_verifiable_rate",
    "unsupported_rate",
    "contradiction_rate",
    "resolved_error_rate",
    "is_strict_all_supported",
    "has_faithfulness_error",
    "is_unusable",
    "is_truncated",
    "is_parse_success",
    "is_schema_valid",
    "is_first_attempt_success",
    "was_retried",
    "is_strict_pipeline_success",
    "latency_seconds",
    "output_tokens_per_second",
    "claims_per_second",
    "supported_claims_per_second",
    "latency_per_supported_claim_seconds",
    "claims_per_1000_total_tokens",
    "supported_claims_per_1000_total_tokens",
    "output_tokens_per_supported_claim",
]

RATE_COLUMNS = [
    "resolved_faithfulness",
    "verifiability",
    "conservative_faithfulness",
    "end_to_end_faithfulness_yield",
    "not_verifiable_rate",
    "unsupported_rate",
    "contradiction_rate",
    "resolved_error_rate",
]

OUTPUT_COLUMNS = (
    ["metric_engineering_version"]
    + IDENTITY_COLUMNS
    + ["model_order", "evidence_order", "case_order"]
    + SOURCE_RUNTIME_COLUMNS
    + SOURCE_COUNT_COLUMNS
    + DERIVED_METRIC_COLUMNS
)
