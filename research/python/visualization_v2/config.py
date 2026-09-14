"""Paths and contracts for visualization presentation marts v2."""

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
DATA_MART_DIR = ANALYSIS_ROOT / "data_mart"
BASELINE_DIR = ANALYSIS_ROOT / "baseline_comparison"
STATISTICS_DIR = ANALYSIS_ROOT / "statistical_analysis"
SENSITIVITY_DIR = ANALYSIS_ROOT / "validator_sensitivity"
REPORT_RELEASE_DIR = ANALYSIS_ROOT / "report_release"
OUTPUT_DIR = ANALYSIS_ROOT / "visualization_v2"

GENERATIONS_PATH = DATA_MART_DIR / "generations.csv"
GENERATION_METRICS_PATH = DATA_MART_DIR / "generation_metrics.csv"
CASES_PATH = DATA_MART_DIR / "cases.csv"
CLAIMS_PATH = DATA_MART_DIR / "claims.csv"
EVIDENCE_PACKAGES_PATH = DATA_MART_DIR / "evidence_packages.csv"
EVIDENCE_ITEMS_PATH = DATA_MART_DIR / "evidence_items.csv"
MODELS_PATH = DATA_MART_DIR / "models.csv"
EVIDENCE_LEVELS_PATH = DATA_MART_DIR / "evidence_levels.csv"

STATISTICAL_VALIDATION_PATH = STATISTICS_DIR / "statistical_validation.json"
VALIDATOR_SENSITIVITY_VALIDATION_PATH = (
    SENSITIVITY_DIR / "validator_sensitivity_validation.json"
)
REPORT_READINESS_PATH = REPORT_RELEASE_DIR / "report_readiness_validation.json"
REPORT_MANIFEST_PATH = REPORT_RELEASE_DIR / "report_release_manifest.json"
REPORT_NUMBERS_PATH = REPORT_RELEASE_DIR / "report_numbers.json"
BASELINE_VALIDATION_PATH = BASELINE_DIR / "baseline_comparison_validation.json"
BASELINE_MANIFEST_PATH = BASELINE_DIR / "baseline_comparison_manifest.json"
BASELINE_GENERATION_METRICS_SOURCE_PATH = (
    BASELINE_DIR / "baseline_generation_metrics.csv"
)
BASELINE_OPTION_PERFORMANCE_SOURCE_PATH = (
    BASELINE_DIR / "baseline_option_performance.csv"
)
BASELINE_PAIR_SOURCE_PATH = BASELINE_DIR / "llm_vs_template_case_pairs.csv"
BASELINE_SUMMARY_SOURCE_PATH = BASELINE_DIR / "llm_vs_template_summary.csv"
BASELINE_TEST_SOURCE_PATH = BASELINE_DIR / "llm_vs_template_tests.csv"

DESCRIPTIVE_STATISTICS_SOURCE_PATH = (
    STATISTICS_DIR / "descriptive_statistics.csv"
)
OMNIBUS_TESTS_SOURCE_PATH = STATISTICS_DIR / "omnibus_tests.csv"
PAIRED_TESTS_SOURCE_PATH = STATISTICS_DIR / "paired_tests.csv"
CONDITIONAL_PAIRED_TESTS_SOURCE_PATH = (
    STATISTICS_DIR / "conditional_paired_tests.csv"
)
COMPLETE_CASE_OMNIBUS_SOURCE_PATH = (
    STATISTICS_DIR / "complete_case_omnibus_tests.csv"
)
STATISTICAL_SENSITIVITY_SOURCE_PATH = (
    STATISTICS_DIR / "sensitivity_summary.csv"
)
UNUSABLE_GENERATIONS_SOURCE_PATH = (
    STATISTICS_DIR / "unusable_generations.csv"
)
VALIDATOR_GENERATION_PAIRS_SOURCE_PATH = (
    SENSITIVITY_DIR / "validator_generation_pairs.csv"
)
VALIDATOR_METRIC_SUMMARY_SOURCE_PATH = (
    SENSITIVITY_DIR / "validator_metric_summary.csv"
)
VALIDATOR_SENSITIVITY_TESTS_SOURCE_PATH = (
    SENSITIVITY_DIR / "validator_sensitivity_tests.csv"
)

RQ_CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "research"
    / "visualization_research_questions_v1.json"
)
DASHBOARD_CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "research"
    / "dashboard_contract_v2.json"
)
METRIC_VISIBILITY_PATH = (
    PROJECT_ROOT
    / "config"
    / "research"
    / "visualization_metric_visibility_v1.json"
)

VISUALIZATION_VERSION = "v2.0"
OUTPUT_GATE = "VISUALIZATION_DATA_V2_READY"
INVALID_GATE = "VISUALIZATION_DATA_V2_INVALID"
EXPECTED_COUNTS = {
    "dashboard_kpis": 22,
    "option_performance": 18,
    "mechanism_breakdowns": 203,
    "scenario_options": 90,
    "scenario_criterion_contributions": 504,
    "recommendation_evidence": 85,
    "pipeline_failures": 10,
    "evidence_design_summary": 216,
    "evidence_utilization_summary": 864,
    "narrative_structure_summary": 864,
    "case_heterogeneity_summary": 864,
    "research_question_registry": 6,
    "baseline_generation_metrics": 216,
    "baseline_option_performance": 6,
    "llm_vs_template_case_pairs": 648,
    "llm_vs_template_summary": 24,
    "llm_vs_template_tests": 105,
    "descriptive_statistics": 272,
    "omnibus_tests": 3,
    "paired_tests": 33,
    "conditional_paired_tests": 99,
    "complete_case_omnibus_tests": 3,
    "statistical_sensitivity_summary": 3,
    "unusable_generations": 10,
    "validator_generation_pairs": 648,
    "validator_metric_summary": 112,
    "validator_sensitivity_tests": 40,
    "certified_report_numbers": 18,
    "release_metadata": 1,
}

OUTPUT_FILENAMES = {
    "dashboard_kpis": "dashboard_kpis.csv",
    "option_performance": "option_performance.csv",
    "mechanism_breakdowns": "mechanism_breakdowns.csv",
    "scenario_options": "scenario_options.csv",
    "scenario_criterion_contributions": "scenario_criterion_contributions.csv",
    "recommendation_evidence": "recommendation_evidence.csv",
    "pipeline_failures": "pipeline_failures.csv",
    "evidence_design_summary": "evidence_design_summary.csv",
    "evidence_utilization_summary": "evidence_utilization_summary.csv",
    "narrative_structure_summary": "narrative_structure_summary.csv",
    "case_heterogeneity_summary": "case_heterogeneity_summary.csv",
    "research_question_registry": "research_question_registry.csv",
    "metric_visibility_registry": "metric_visibility_registry.csv",
    "baseline_generation_metrics": "baseline_generation_metrics.csv",
    "baseline_option_performance": "baseline_option_performance.csv",
    "llm_vs_template_case_pairs": "llm_vs_template_case_pairs.csv",
    "llm_vs_template_summary": "llm_vs_template_summary.csv",
    "llm_vs_template_tests": "llm_vs_template_tests.csv",
    "descriptive_statistics": "descriptive_statistics.csv",
    "omnibus_tests": "omnibus_tests.csv",
    "paired_tests": "paired_tests.csv",
    "conditional_paired_tests": "conditional_paired_tests.csv",
    "complete_case_omnibus_tests": "complete_case_omnibus_tests.csv",
    "statistical_sensitivity_summary": "statistical_sensitivity_summary.csv",
    "unusable_generations": "unusable_generations.csv",
    "validator_generation_pairs": "validator_generation_pairs.csv",
    "validator_metric_summary": "validator_metric_summary.csv",
    "validator_sensitivity_tests": "validator_sensitivity_tests.csv",
    "certified_report_numbers": "certified_report_numbers.csv",
    "release_metadata": "release_metadata.csv",
    "visualization_dictionary": "visualization_dictionary.csv",
}
OUTPUT_PATHS = {
    name: OUTPUT_DIR / filename
    for name, filename in OUTPUT_FILENAMES.items()
}
MANIFEST_PATH = OUTPUT_DIR / "visualization_manifest.json"
VALIDATION_PATH = OUTPUT_DIR / "visualization_validation.json"
