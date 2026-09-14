"""Report-release paths and required analytical gates."""

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
ANALYSIS_ROOT = VALIDATION_ROOT / "analysis"
OUTPUT_DIR = ANALYSIS_ROOT / "report_release"

REPORT_NUMBERS_PATH = OUTPUT_DIR / "report_numbers.json"
SOURCE_INDEX_PATH = OUTPUT_DIR / "report_source_index.csv"
MANIFEST_PATH = OUTPUT_DIR / "report_release_manifest.json"
READINESS_PATH = OUTPUT_DIR / "report_readiness_validation.json"

REQUIRED_GATES = {
    "data_mart": (
        ANALYSIS_ROOT / "data_mart" / "data_mart_validation.json",
        "DATA_MART_READY",
    ),
    "metrics": (
        ANALYSIS_ROOT / "data_mart" / "metric_validation.json",
        "ANALYTICAL_MART_READY",
    ),
    "statistics": (
        ANALYSIS_ROOT
        / "statistical_analysis"
        / "statistical_validation.json",
        "STATISTICAL_CORE_READY",
    ),
    "diagnostics": (
        ANALYSIS_ROOT / "diagnostics" / "diagnostic_validation.json",
        "DIAGNOSTICS_READY",
    ),
    "decision_support": (
        ANALYSIS_ROOT
        / "decision_support"
        / "decision_validation.json",
        "DECISION_SUPPORT_READY",
    ),
    "validator_sensitivity": (
        ANALYSIS_ROOT
        / "validator_sensitivity"
        / "validator_sensitivity_validation.json",
        "VALIDATOR_SENSITIVITY_READY",
    ),
}

CERTIFIED_REPORT_FILES = [
    ANALYSIS_ROOT / "data_mart" / "generation_metrics.csv",
    ANALYSIS_ROOT / "data_mart" / "metric_dictionary.csv",
    ANALYSIS_ROOT / "statistical_analysis" / "omnibus_tests.csv",
    ANALYSIS_ROOT / "statistical_analysis" / "paired_tests.csv",
    ANALYSIS_ROOT / "statistical_analysis" / "conditional_paired_tests.csv",
    ANALYSIS_ROOT
    / "statistical_analysis"
    / "complete_case_omnibus_tests.csv",
    ANALYSIS_ROOT / "statistical_analysis" / "sensitivity_summary.csv",
    ANALYSIS_ROOT / "statistical_analysis" / "unusable_generations.csv",
    ANALYSIS_ROOT / "diagnostics" / "pipeline_failures.csv",
    ANALYSIS_ROOT / "decision_support" / "recommendations.csv",
    ANALYSIS_ROOT
    / "validator_sensitivity"
    / "validator_metric_summary.csv",
    ANALYSIS_ROOT
    / "validator_sensitivity"
    / "validator_sensitivity_tests.csv",
]
