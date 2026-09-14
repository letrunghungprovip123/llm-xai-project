"""Frozen paths and contracts for the Template Baseline comparison."""

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
OUTPUT_DIR = ANALYSIS_ROOT / "baseline_comparison"

TEMPLATE_INDEX_PATH = (
    VALIDATION_ROOT
    / "canonicalization"
    / "template_baseline_index.jsonl"
)
CASES_PATH = DATA_MART_DIR / "cases.csv"
EVIDENCE_PACKAGES_PATH = DATA_MART_DIR / "evidence_packages.csv"
EVIDENCE_ITEMS_PATH = DATA_MART_DIR / "evidence_items.csv"
LLM_GENERATIONS_PATH = DATA_MART_DIR / "generations.csv"
LLM_GENERATION_METRICS_PATH = DATA_MART_DIR / "generation_metrics.csv"
MODELS_PATH = DATA_MART_DIR / "models.csv"
EVIDENCE_LEVELS_PATH = DATA_MART_DIR / "evidence_levels.csv"
REPORT_READINESS_PATH = (
    ANALYSIS_ROOT
    / "report_release"
    / "report_readiness_validation.json"
)
REPORT_MANIFEST_PATH = (
    ANALYSIS_ROOT
    / "report_release"
    / "report_release_manifest.json"
)
CLAIM_RELEASE_PATH = (
    PROJECT_ROOT
    / "config"
    / "research"
    / "claim_measurement_release_v1.json"
)
RQ_CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "research"
    / "visualization_research_questions_v1.json"
)

BASELINE_CLAIMS_PATH = OUTPUT_DIR / "baseline_claims.csv"
BASELINE_GENERATION_METRICS_PATH = (
    OUTPUT_DIR / "baseline_generation_metrics.csv"
)
BASELINE_OPTION_PERFORMANCE_PATH = (
    OUTPUT_DIR / "baseline_option_performance.csv"
)
PAIR_PATH = OUTPUT_DIR / "llm_vs_template_case_pairs.csv"
SUMMARY_PATH = OUTPUT_DIR / "llm_vs_template_summary.csv"
TEST_PATH = OUTPUT_DIR / "llm_vs_template_tests.csv"
METRIC_DICTIONARY_PATH = OUTPUT_DIR / "baseline_metric_dictionary.csv"
MANIFEST_PATH = OUTPUT_DIR / "baseline_comparison_manifest.json"
VALIDATION_PATH = OUTPUT_DIR / "baseline_comparison_validation.json"

BASELINE_COMPARISON_VERSION = "v1.0"
STRUCTURED_ADAPTER_VERSION = "structured_template_adapter_v1"
VALIDATION_MODE = "DETERMINISTIC_CONTRACT_REPLAY"
OUTPUT_GATE = "BASELINE_COMPARISON_READY"
INVALID_GATE = "BASELINE_COMPARISON_INVALID"
PARENT_GATE = "REPORT_WRITING_READY"
ALPHA = 0.05
EXPECTED_BASELINE_GENERATIONS = 216
EXPECTED_LLM_GENERATIONS = 648
EXPECTED_CASES = 36
EXPECTED_EVIDENCE_LEVELS = 6
EXPECTED_PAIRS = 648
EXPECTED_SUMMARY_ROWS = 24

TEST_METRICS = {
    "end_to_end_faithfulness_yield": (
        "llm_end_to_end_faithfulness_yield",
        "template_end_to_end_faithfulness_yield",
    ),
    "conservative_faithfulness": (
        "llm_conservative_faithfulness",
        "template_conservative_faithfulness",
    ),
    "supported_claim_count": (
        "llm_supported_count",
        "template_supported_count",
    ),
    "supported_claims_per_100_words": (
        "llm_supported_claims_per_100_words",
        "template_supported_claims_per_100_words",
    ),
    "output_word_count": (
        "llm_output_word_count",
        "template_output_word_count",
    ),
}

OUTPUT_PATHS = {
    "baseline_claims": BASELINE_CLAIMS_PATH,
    "baseline_generation_metrics": BASELINE_GENERATION_METRICS_PATH,
    "baseline_option_performance": BASELINE_OPTION_PERFORMANCE_PATH,
    "llm_vs_template_case_pairs": PAIR_PATH,
    "llm_vs_template_summary": SUMMARY_PATH,
    "llm_vs_template_tests": TEST_PATH,
    "baseline_metric_dictionary": METRIC_DICTIONARY_PATH,
}
