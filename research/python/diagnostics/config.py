"""Configuration for Diagnostics & Mechanisms."""

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
STATISTICAL_DIR = VALIDATION_ROOT / "analysis" / "statistical_analysis"
OUTPUT_DIR = VALIDATION_ROOT / "analysis" / "diagnostics"

CLAIMS_PATH = DATA_MART_DIR / "claims.csv"
GENERATIONS_PATH = DATA_MART_DIR / "generations.csv"
GENERATION_METRICS_PATH = DATA_MART_DIR / "generation_metrics.csv"
CASES_PATH = DATA_MART_DIR / "cases.csv"
MODELS_PATH = DATA_MART_DIR / "models.csv"
EVIDENCE_LEVELS_PATH = DATA_MART_DIR / "evidence_levels.csv"
EVIDENCE_PACKAGES_PATH = DATA_MART_DIR / "evidence_packages.csv"
EVIDENCE_ITEMS_PATH = DATA_MART_DIR / "evidence_items.csv"
DATA_MART_VALIDATION_PATH = DATA_MART_DIR / "data_mart_validation.json"
METRIC_VALIDATION_PATH = DATA_MART_DIR / "metric_validation.json"
STATISTICAL_VALIDATION_PATH = (
    STATISTICAL_DIR / "statistical_validation.json"
)

CLAIM_DIAGNOSTICS_PATH = OUTPUT_DIR / "claim_diagnostics.csv"
GENERATION_DIAGNOSTICS_PATH = OUTPUT_DIR / "generation_diagnostics.csv"
CLAIM_MECHANISM_SUMMARY_PATH = (
    OUTPUT_DIR / "claim_mechanism_summary.csv"
)
GENERATION_MECHANISM_SUMMARY_PATH = (
    OUTPUT_DIR / "generation_mechanism_summary.csv"
)
SAFE_PHRASE_MATCHES_PATH = OUTPUT_DIR / "safe_phrase_matches.csv"
PIPELINE_FAILURES_PATH = OUTPUT_DIR / "pipeline_failures.csv"
DIAGNOSTIC_VALIDATION_PATH = OUTPUT_DIR / "diagnostic_validation.json"

DIAGNOSTIC_VERSION = "v1.1"
DATA_MART_GATE = "DATA_MART_READY"
METRIC_GATE = "ANALYTICAL_MART_READY"
STATISTICAL_GATE = "STATISTICAL_CORE_READY"
OUTPUT_GATE = "DIAGNOSTICS_READY"
INVALID_GATE = "DIAGNOSTICS_INVALID"

EXPECTED_COUNTS = {
    "claims": 14667,
    "generations": 648,
    "usable_generations": 638,
    "unusable_generations": 10,
    "cases": 36,
    "models": 3,
    "evidence_levels": 6,
    "evidence_packages": 216,
    "evidence_items": 2941,
}

VALIDATION_STATUSES = {
    "SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "NOT_VERIFIABLE",
    "NOT_APPLICABLE",
}
RESOLVED_STATUSES = {
    "SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
}
RESOLVED_ERROR_STATUSES = {
    "UNSUPPORTED",
    "CONTRADICTED",
}

MIN_SAFE_PHRASE_TOKENS = 4
HIGH_OVERLAP_THRESHOLD = 0.80
NUMERIC_TOLERANCE = 1e-12

GENERATION_TEXT_COLUMNS = [
    "prediction_summary",
    "uncertainty_note",
    "distributed_evidence_note",
    "safe_summary",
]

CLAIM_TYPE_COUNT_COLUMNS = {
    "prediction": "prediction_claim_count",
    "feature_presence": "feature_presence_claim_count",
    "feature_direction": "feature_direction_claim_count",
    "concept_presence": "concept_presence_claim_count",
    "concept_direction": "concept_direction_claim_count",
    "numeric": "numeric_claim_count",
    "ranking": "ranking_claim_count",
    "magnitude": "magnitude_claim_count",
    "uncertainty": "uncertainty_claim_count",
    "limitation": "limitation_claim_count",
    "distributed_evidence": "distributed_evidence_claim_count",
    "recommendation": "recommendation_claim_count",
}

CLAIM_GROUP_TYPES = [
    "overall",
    "model",
    "evidence",
    "model_evidence",
    "claim_type",
    "model_evidence_claim_type",
    "stratum",
]

GENERATION_GROUP_TYPES = [
    "overall",
    "model",
    "evidence",
    "model_evidence",
    "stratum",
]

REQUIRED_CLAIM_COLUMNS = {
    "claim_id",
    "generation_id",
    "case_id",
    "model_id",
    "evidence_level",
    "source_section",
    "source_text",
    "claim_type",
    "claim_subtype",
    "subject_type",
    "feature_id",
    "concept_id",
    "claim_origin",
    "validation_status",
    "source_start",
    "source_end",
    "numeric_value",
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
    "usable",
    "runtime_status",
    "finish_reason",
    "truncated_response",
    "raw_json_parse_success",
    "json_parse_success",
    "schema_valid",
    "retry_count",
    "latency_ms",
    "input_token_count",
    "output_token_count",
    "total_token_count",
    "runtime_error_type",
    "runtime_error_message",
    "empty_response",
    "cleanup_type",
    "usability_reason_codes_json",
    "prediction_summary",
    "uncertainty_note",
    "distributed_evidence_note",
    "safe_summary",
    "factors_json",
}

REQUIRED_METRIC_COLUMNS = {
    "generation_id",
    "case_id",
    "model_id",
    "evidence_level",
    "package_id",
    "selection_stratum",
    "usable",
    "runtime_status",
    "claim_count",
    "supported_count",
    "unsupported_count",
    "contradicted_count",
    "not_verifiable_count",
    "not_applicable_count",
    "resolved_count",
    "applicable_count",
    "end_to_end_faithfulness_yield",
}

REQUIRED_CASE_COLUMNS = {
    "case_id",
    "selection_stratum",
}

REQUIRED_MODEL_COLUMNS = {
    "model_id",
    "model_order",
    "model_label",
}

REQUIRED_EVIDENCE_LEVEL_COLUMNS = {
    "evidence_level",
    "evidence_order",
    "evidence_label",
    "intended_role",
    "safe_phrase_available",
}

REQUIRED_PACKAGE_COLUMNS = {
    "package_id",
    "case_id",
    "evidence_level",
    "safe_phrase_count",
}

REQUIRED_ITEM_COLUMNS = {
    "evidence_item_id",
    "package_id",
    "case_id",
    "evidence_level",
    "item_type",
    "item_order",
    "feature_id",
    "concept_id",
    "safe_phrase",
}

CLAIM_DIAGNOSTIC_COLUMNS = [
    "diagnostic_version",
    "claim_id",
    "generation_id",
    "case_id",
    "model_id",
    "evidence_level",
    "package_id",
    "selection_stratum",
    "source_section",
    "source_text",
    "claim_type",
    "claim_subtype",
    "subject_type",
    "feature_id",
    "concept_id",
    "claim_origin",
    "validation_status",
    "is_applicable",
    "is_resolved",
    "is_supported",
    "is_not_verifiable",
    "is_unsupported",
    "is_contradicted",
    "is_not_applicable",
    "is_resolved_error",
    "has_feature_reference",
    "has_concept_reference",
    "has_source_anchor",
    "has_numeric_value",
    "safe_phrase_exposed",
    "safe_phrase_item_count",
    "safe_phrase_match_eligible",
    "best_safe_phrase_item_id",
    "best_safe_phrase_match_type",
    "best_safe_phrase_token_coverage",
    "safe_phrase_exact_match",
    "safe_phrase_contained_match",
    "safe_phrase_high_overlap",
    "safe_phrase_any_match",
]

GENERATION_DIAGNOSTIC_BASE_COLUMNS = [
    "diagnostic_version",
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
    "claim_count",
    "supported_count",
    "unsupported_count",
    "contradicted_count",
    "not_verifiable_count",
    "not_applicable_count",
    "resolved_count",
    "applicable_count",
    "end_to_end_faithfulness_yield",
    "supported_yield_component",
    "pipeline_loss",
    "not_verifiable_loss",
    "unsupported_loss",
    "contradiction_loss",
    "resolved_error_loss",
    "claim_quality_loss",
    "total_loss",
    "safe_phrase_exposed",
    "safe_phrase_item_count",
    "safe_phrase_match_eligible",
    "safe_phrase_exposed_claim_count",
    "safe_phrase_eligible_claim_count",
    "safe_phrase_matched_claim_count",
    "safe_phrase_exact_claim_count",
    "safe_phrase_contained_claim_count",
    "safe_phrase_high_overlap_claim_count",
    "safe_phrase_matched_claim_rate",
    "has_safe_phrase_claim_match",
    "narrative_exact_safe_phrase_match",
    "narrative_contained_safe_phrase_match",
    "narrative_high_overlap_safe_phrase_match",
    "narrative_any_safe_phrase_match",
    "narrative_max_safe_phrase_token_coverage",
    "has_any_safe_phrase_match",
    "claim_type_count",
]

GENERATION_DIAGNOSTIC_COLUMNS = [
    *GENERATION_DIAGNOSTIC_BASE_COLUMNS,
    *CLAIM_TYPE_COUNT_COLUMNS.values(),
]
