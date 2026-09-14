"""Configuration for the statistical analysis core."""

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
OUTPUT_DIR = VALIDATION_ROOT / "analysis" / "statistical_analysis"

GENERATION_METRICS_PATH = DATA_MART_DIR / "generation_metrics.csv"
METRIC_VALIDATION_PATH = DATA_MART_DIR / "metric_validation.json"
CASES_PATH = DATA_MART_DIR / "cases.csv"
MODELS_PATH = DATA_MART_DIR / "models.csv"
EVIDENCE_LEVELS_PATH = DATA_MART_DIR / "evidence_levels.csv"

ANALYSIS_FRAME_PATH = OUTPUT_DIR / "analysis_frame.csv"
DESCRIPTIVE_STATISTICS_PATH = OUTPUT_DIR / "descriptive_statistics.csv"
OMNIBUS_TESTS_PATH = OUTPUT_DIR / "omnibus_tests.csv"
PAIRED_TESTS_PATH = OUTPUT_DIR / "paired_tests.csv"
STATISTICAL_VALIDATION_PATH = OUTPUT_DIR / "statistical_validation.json"
CONDITIONAL_PAIRED_TESTS_PATH = (
    OUTPUT_DIR / "conditional_paired_tests.csv"
)
COMPLETE_CASE_OMNIBUS_TESTS_PATH = (
    OUTPUT_DIR / "complete_case_omnibus_tests.csv"
)
UNUSABLE_GENERATIONS_PATH = OUTPUT_DIR / "unusable_generations.csv"
SENSITIVITY_SUMMARY_PATH = OUTPUT_DIR / "sensitivity_summary.csv"

STATISTICAL_ANALYSIS_VERSION = "v1.1"
INPUT_EXIT_GATE = "ANALYTICAL_MART_READY"
OUTPUT_EXIT_GATE = "STATISTICAL_CORE_READY"
INVALID_EXIT_GATE = "STATISTICAL_CORE_INVALID"

ALPHA = 0.05
PRIMARY_METRIC = "end_to_end_faithfulness_yield"
SECONDARY_METRICS = [
    "resolved_faithfulness",
    "verifiability",
    "conservative_faithfulness",
]
DESCRIPTIVE_METRICS = [
    PRIMARY_METRIC,
    *SECONDARY_METRICS,
    "usable",
    "latency_seconds",
    "total_token_count",
    "supported_claims_per_1000_total_tokens",
]

EXPECTED_COUNTS = {
    "generation_rows": 648,
    "cases": 36,
    "models": 3,
    "evidence_levels": 6,
    "model_evidence_cells": 18,
    "conditions_per_case": 18,
    "rows_per_model_evidence_cell": 36,
    "omnibus_tests": 3,
    "model_within_evidence_contrasts": 18,
    "evidence_vs_s0_contrasts": 15,
    "paired_tests": 33,
    "conditional_paired_tests": 99,
    "complete_case_omnibus_tests": 3,
    "complete_case_count": 27,
    "unusable_generation_count": 10,
    "sensitivity_summary_rows": 3,
}

REQUIRED_METRIC_COLUMNS = {
    "generation_id",
    "case_id",
    "model_id",
    "evidence_level",
    "package_id",
    "selection_stratum",
    "model_order",
    "evidence_order",
    "case_order",
    "usable",
    "runtime_status",
    "runtime_error_type",
    "runtime_error_message",
    "retry_count",
    "is_unusable",
    "is_truncated",
    "is_parse_success",
    "is_schema_valid",
    "claim_count",
    "supported_count",
    "unsupported_count",
    "contradicted_count",
    "not_verifiable_count",
    "not_applicable_count",
    "resolved_count",
    "applicable_count",
    "resolved_faithfulness",
    "verifiability",
    "conservative_faithfulness",
    "end_to_end_faithfulness_yield",
    "latency_seconds",
    "total_token_count",
    "supported_claims_per_1000_total_tokens",
}

REQUIRED_CASE_COLUMNS = {
    "case_id",
    "selection_stratum",
    "prediction_correct",
    "prediction_outcome",
    "distance_from_threshold",
}

REQUIRED_MODEL_COLUMNS = {
    "model_id",
    "model_order",
    "model_label",
}

REQUIRED_EVIDENCE_COLUMNS = {
    "evidence_level",
    "evidence_order",
    "evidence_label",
    "intended_role",
}

ANALYSIS_FRAME_COLUMNS = [
    "statistical_analysis_version",
    "generation_id",
    "case_id",
    "model_id",
    "model_label",
    "evidence_level",
    "evidence_label",
    "intended_role",
    "selection_stratum",
    "prediction_correct",
    "prediction_outcome",
    "distance_from_threshold",
    "model_order",
    "evidence_order",
    "case_order",
    "package_id",
    "is_primary_analysis_row",
    "is_usable_analysis_row",
    "is_complete_case",
    "has_resolved_metric",
    "has_verifiability_metric",
    "has_conservative_metric",
    "usable",
    "runtime_status",
    "runtime_error_type",
    "runtime_error_message",
    "retry_count",
    "is_unusable",
    "is_truncated",
    "is_parse_success",
    "is_schema_valid",
    "claim_count",
    "supported_count",
    "unsupported_count",
    "contradicted_count",
    "not_verifiable_count",
    "not_applicable_count",
    "resolved_count",
    "applicable_count",
    "resolved_faithfulness",
    "verifiability",
    "conservative_faithfulness",
    "end_to_end_faithfulness_yield",
    "latency_seconds",
    "total_token_count",
    "supported_claims_per_1000_total_tokens",
]

GROUP_TYPES = [
    "overall",
    "model",
    "evidence",
    "model_evidence",
    "stratum",
]

OMNIBUS_EFFECTS = [
    "model",
    "evidence",
    "model:evidence",
]
