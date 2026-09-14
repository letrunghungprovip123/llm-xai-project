"""Central settings and contracts for the certified dashboard."""

from __future__ import annotations

from pathlib import Path

from research.python.common.paths import DEFAULT_PATHS


APP_TITLE = "LLM-XAI Research Dashboard"
APP_SUBTITLE = "Model × Evidence × Faithfulness Evaluation"

ANALYTICAL_RELEASE_ID = "thesis-report-v1"
VISUALIZATION_RELEASE_ID = "visualization-data-v2"
VISUALIZATION_VERSION = "v2.0"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8050

PRIMARY_VIEWPORT = (1440, 900)
MINIMUM_ACCEPTED_VIEWPORT = (1366, 768)

PROJECT_ROOT = DEFAULT_PATHS.project_root
VALIDATION_ROOT = (
    PROJECT_ROOT
    / "data"
    / "reports"
    / "llm_validation"
    / "validation_v1"
)
ANALYSIS_ROOT = VALIDATION_ROOT / "analysis"
VISUALIZATION_DATA_DIR = ANALYSIS_ROOT / "visualization_v2"
VISUALIZATION_MANIFEST_PATH = (
    VISUALIZATION_DATA_DIR / "visualization_manifest.json"
)
VISUALIZATION_VALIDATION_PATH = (
    VISUALIZATION_DATA_DIR / "visualization_validation.json"
)

REQUIRED_GATES = (
    "REPORT_WRITING_READY",
    "BASELINE_COMPARISON_READY",
    "VISUALIZATION_DATA_V2_READY",
)

OFFICIAL_PAGE_ORDER = (
    "overview",
    "effectiveness",
    "mechanisms",
    "decision",
    "robustness",
    "cases",
    "methods",
)

OFFICIAL_PAGE_PATHS = {
    "overview": "/",
    "effectiveness": "/effectiveness",
    "mechanisms": "/mechanisms",
    "decision": "/decision",
    "robustness": "/robustness",
    "cases": "/cases",
    "methods": "/methods",
}

EXPECTED_MODEL_ORDER = (
    "qwen3_8b",
    "deepseek_v4_flash",
    "phi4_mini_instruct",
)
EXPECTED_EVIDENCE_ORDER = ("S0", "S1", "S2", "S3", "S4", "S5")
EXPECTED_OPTION_COUNT = 18
EXPECTED_TEMPLATE_GENERATION_COUNT = 216
EXPECTED_VISUALIZATION_DATASET_COUNT = 31
EXPECTED_VISUALIZATION_CHECK_COUNT = 54

OVERVIEW_REQUIRED_DATASETS = (
    "certified_report_numbers",
    "option_performance",
    "omnibus_tests",
    "unusable_generations",
    "validator_metric_summary",
    "baseline_generation_metrics",
    "release_metadata",
)

OVERVIEW_REQUIRED_CERTIFIED_METRICS = (
    "planned_llm_generations",
    "usable_llm_generations",
    "unusable_llm_generations",
    "usability_rate",
    "mean_end_to_end_operational_faithfulness",
    "final_atomic_claims",
)

# Only these files are loaded by Page 1. Other pages add their own contracts.
OVERVIEW_DATASET_FILES = {
    "certified_report_numbers": "certified_report_numbers.csv",
    "option_performance": "option_performance.csv",
    "omnibus_tests": "omnibus_tests.csv",
    "unusable_generations": "unusable_generations.csv",
    "validator_metric_summary": "validator_metric_summary.csv",
    "baseline_generation_metrics": "baseline_generation_metrics.csv",
    "release_metadata": "release_metadata.csv",
}


CONDITIONAL_METRIC_LABELS = {
    "conservative_faithfulness": "Conservative faithfulness",
    "verifiability": "Verifiability",
    "resolved_faithfulness": "Resolved faithfulness",
}
DEFAULT_CONDITIONAL_METRIC = "conservative_faithfulness"

EFFECTIVENESS_REQUIRED_DATASETS = (
    "option_performance",
    "descriptive_statistics",
    "omnibus_tests",
    "paired_tests",
    "conditional_paired_tests",
    "complete_case_omnibus_tests",
    "statistical_sensitivity_summary",
    "unusable_generations",
    "case_heterogeneity_summary",
)


def visualization_path(filename: str) -> Path:
    """Resolve a visualization-v2 dataset without depending on module depth."""

    return VISUALIZATION_DATA_DIR / filename

DASHBOARD_PACKAGE_DIR = PROJECT_ROOT / "research" / "python" / "dashboard"
DASHBOARD_ASSETS_DIR = DASHBOARD_PACKAGE_DIR / "assets"
DASHBOARD_RELEASE_DIR = PROJECT_ROOT / "release" / "thesis_dashboard_v1"


MECHANISMS_REQUIRED_DATASETS = (
    "evidence_design_summary",
    "evidence_utilization_summary",
    "narrative_structure_summary",
    "mechanism_breakdowns",
    "pipeline_failures",
)

UTILIZATION_METRIC_LABELS = {
    "feature_use": "Feature use",
    "concept_use": "Concept use",
    "supported_claim_yield": "Supported-claim yield",
}
DEFAULT_UTILIZATION_METRIC = "feature_use"

CLAIM_DIFFICULTY_METRICS = (
    "not_verifiable",
    "unsupported",
    "contradicted",
)

DECISION_REQUIRED_DATASETS = (
    "scenario_options",
    "scenario_criterion_contributions",
    "recommendation_evidence",
)

DECISION_SCENARIO_IDS = (
    "QUALITY_FIRST",
    "RELIABILITY_FIRST",
    "BALANCED",
    "EFFICIENCY_AWARE",
    "INDEPENDENCE_SENSITIVE",
)
DECISION_SCENARIO_LABELS = {
    "QUALITY_FIRST": "Quality First",
    "RELIABILITY_FIRST": "Reliability First",
    "BALANCED": "Balanced",
    "EFFICIENCY_AWARE": "Efficiency Aware",
    "INDEPENDENCE_SENSITIVE": "Independence Sensitive",
}
DECISION_SCENARIO_DESCRIPTIONS = {
    "QUALITY_FIRST": (
        "Prioritizes end-to-end quality and performance on weaker cases."
    ),
    "RELIABILITY_FIRST": (
        "Considers only configurations that complete all planned generations."
    ),
    "BALANCED": (
        "Balances average quality, lower-tail reliability and deployment efficiency."
    ),
    "EFFICIENCY_AWARE": (
        "Favors lower latency and token use while preserving certified quality constraints."
    ),
    "INDEPENDENCE_SENSITIVE": (
        "Maintains relatively high quality while reducing lexical-overlap signal."
    ),
}
DEFAULT_DECISION_SCENARIO = "BALANCED"
WHAT_IF_BASE_SCENARIO = "BALANCED"

DECISION_X_AXIS_LABELS = {
    "mean_latency_seconds_planned": "Mean latency",
    "mean_total_token_count_planned": "Mean total tokens",
    "mean_supported_claims_per_1000_tokens": "Supported claims / 1,000 tokens",
}
DEFAULT_DECISION_X_AXIS = "mean_latency_seconds_planned"

DECISION_CRITERION_GROUPS = {
    "mean_end_to_end_yield": "Quality",
    "p10_end_to_end_yield": "Reliability",
    "usability_rate": "Reliability",
    "mean_latency_seconds_planned": "Efficiency",
    "mean_total_token_count_planned": "Efficiency",
    "mean_supported_claims_per_1000_tokens": "Efficiency",
    "mean_resolved_error_loss": "Quality",
    "strong_safe_phrase_signal_share_all_claims": "Measurement robustness",
}

DECISION_CONTRIBUTION_LABELS = {
    "mean_end_to_end_yield": "Mean end-to-end yield",
    "p10_end_to_end_yield": "P10 end-to-end yield",
    "usability_rate": "Usability rate",
    "mean_latency_seconds_planned": "Latency efficiency",
    "mean_total_token_count_planned": "Token efficiency",
    "mean_supported_claims_per_1000_tokens": "Supported claims per 1,000 tokens",
    "mean_resolved_error_loss": "Low resolved-error loss",
    "strong_safe_phrase_signal_share_all_claims": "Low strong lexical-signal share",
}


ROBUSTNESS_REQUIRED_DATASETS = (
    "validator_generation_pairs",
    "validator_metric_summary",
    "validator_sensitivity_tests",
    "baseline_generation_metrics",
    "baseline_option_performance",
    "llm_vs_template_case_pairs",
    "llm_vs_template_summary",
    "llm_vs_template_tests",
)

EXPECTED_VALIDATOR_PAIR_COUNT = 648
EXPECTED_VALIDATOR_SUMMARY_COUNT = 112
EXPECTED_VALIDATOR_TEST_COUNT = 40
EXPECTED_BASELINE_OPTION_COUNT = 6
EXPECTED_BASELINE_PAIR_COUNT = 648
EXPECTED_BASELINE_SUMMARY_COUNT = 24
EXPECTED_BASELINE_TEST_COUNT = 105

ROBUSTNESS_MODEL_LABELS = {
    "qwen3_8b": "Qwen3 8B",
    "deepseek_v4_flash": "DeepSeek V4 Flash",
    "phi4_mini_instruct": "Phi-4 Mini Instruct",
}

ROBUSTNESS_METRIC_LABELS = {
    "end_to_end_faithfulness_yield": "End-to-end yield",
    "conservative_faithfulness": "Conservative faithfulness",
    "verifiability": "Verifiability",
    "resolved_faithfulness": "Resolved faithfulness",
}
DEFAULT_ROBUSTNESS_METRIC = "end_to_end_faithfulness_yield"

TEMPLATE_METRIC_LABELS = {
    "end_to_end_faithfulness_yield": "End-to-end yield",
    "conservative_faithfulness": "Conservative faithfulness",
    "supported_claim_count": "Supported claims",
    "supported_claims_per_100_words": "Supported claims / 100 words",
    "output_word_count": "Output words",
}
DEFAULT_TEMPLATE_METRIC = "end_to_end_faithfulness_yield"

TEMPLATE_SCOPE_LABELS = {
    "S1-S4_CASE_MEAN": "S1–S4 primary",
    "S0": "S0",
    "S1": "S1",
    "S2": "S2",
    "S3": "S3",
    "S4": "S4",
    "S5": "S5",
}
DEFAULT_TEMPLATE_SCOPE = "S1-S4_CASE_MEAN"

VALIDATOR_METRIC_COLUMNS = {
    metric_id: {
        "candidate": f"candidate_{metric_id}",
        "sensitivity": f"v4_{metric_id}",
        "delta": f"delta_{metric_id}",
    }
    for metric_id in ROBUSTNESS_METRIC_LABELS
}

BASELINE_PAIR_METRIC_COLUMNS = {
    "end_to_end_faithfulness_yield": {
        "llm": "llm_end_to_end_faithfulness_yield",
        "template": "template_end_to_end_faithfulness_yield",
        "delta": "delta_end_to_end_faithfulness_yield_llm_minus_template",
    },
    "conservative_faithfulness": {
        "llm": "llm_conservative_faithfulness",
        "template": "template_conservative_faithfulness",
        "delta": "delta_conservative_faithfulness_llm_minus_template",
    },
    "supported_claim_count": {
        "llm": "llm_supported_count",
        "template": "template_supported_count",
        "delta": "delta_supported_count_llm_minus_template",
    },
    "supported_claims_per_100_words": {
        "llm": "llm_supported_claims_per_100_words",
        "template": "template_supported_claims_per_100_words",
        "delta": "delta_supported_claims_per_100_words_llm_minus_template",
    },
    "output_word_count": {
        "llm": "llm_output_word_count",
        "template": "template_output_word_count",
        "delta": "delta_output_word_count_llm_minus_template",
    },
}

BASELINE_OPTION_METRIC_COLUMNS = {
    "end_to_end_faithfulness_yield": "mean_end_to_end_yield",
    "conservative_faithfulness": "mean_conservative_faithfulness",
    "supported_claim_count": "mean_supported_claim_count",
    "supported_claims_per_100_words": "mean_supported_claims_per_100_words",
    "output_word_count": "mean_output_word_count",
}

LLM_OPTION_METRIC_COLUMNS = {
    "end_to_end_faithfulness_yield": "llm_mean_end_to_end_yield",
    "conservative_faithfulness": "llm_mean_conservative_faithfulness",
    "supported_claim_count": "llm_mean_supported_count",
    "supported_claims_per_100_words": "llm_mean_supported_claims_per_100_words",
    "output_word_count": "llm_mean_output_word_count",
}


# Page 6 — privacy-preserving canonical-case exploration.
CASE_EXPLORER_REQUIRED_DATASETS = (
    "case_heterogeneity_summary",
    "evidence_design_summary",
    "evidence_utilization_summary",
    "narrative_structure_summary",
    "validator_generation_pairs",
    "llm_vs_template_case_pairs",
)

EXPECTED_CANONICAL_CASE_COUNT = 36
EXPECTED_CASE_GENERATION_COUNT = 24
EXPECTED_CASE_LLM_GENERATION_COUNT = 18
EXPECTED_CASE_TEMPLATE_GENERATION_COUNT = 6
EXPECTED_CASE_EVIDENCE_PACKAGE_COUNT = 6
EXPECTED_COMPLETE_LLM_CASE_COUNT = 27
EXPECTED_INCOMPLETE_LLM_CASE_COUNT = 9

CASE_STRATUM_LABELS = {
    "low_risk": "Low risk",
    "true_positive": "True positive",
    "false_positive": "False positive",
    "false_negative": "False negative",
    "top_high_risk": "Top high risk",
    "near_threshold": "Near threshold",
}
CASE_STRATUM_ORDER = tuple(CASE_STRATUM_LABELS)
CASE_OUTCOME_LABELS = {
    "TN": "True negative",
    "TP": "True positive",
    "FP": "False positive",
    "FN": "False negative",
}
CASE_COMPLETENESS_LABELS = {
    "ALL": "All cases",
    "COMPLETE": "Complete 18-condition cases",
    "INCOMPLETE": "Cases with structured failures",
}

CASE_MATRIX_METRIC_LABELS = {
    "end_to_end_faithfulness_yield": "End-to-end yield",
    "conservative_faithfulness": "Conservative faithfulness",
    "verifiability": "Verifiability",
    "supported_count": "Supported claims",
    "output_word_count": "Output words",
}
DEFAULT_CASE_MATRIX_METRIC = "end_to_end_faithfulness_yield"
DEFAULT_CASE_MODEL = EXPECTED_MODEL_ORDER[0]
DEFAULT_CASE_EVIDENCE = "S1"

CASE_RATE_METRICS = {
    "end_to_end_faithfulness_yield",
    "conservative_faithfulness",
    "verifiability",
    "resolved_faithfulness",
}

CASE_VALIDATOR_METRICS = (
    "end_to_end_faithfulness_yield",
    "conservative_faithfulness",
    "verifiability",
    "resolved_faithfulness",
)

# Page 7 — Reproducibility & Methods.
METHODS_REQUIRED_DATASETS = (
    "release_metadata",
    "certified_report_numbers",
    "visualization_dictionary",
    "metric_visibility_registry",
    "research_question_registry",
    "omnibus_tests",
    "paired_tests",
    "conditional_paired_tests",
    "validator_sensitivity_tests",
    "llm_vs_template_tests",
)

METHODS_TAB_RELEASE = "release"
METHODS_TAB_RESEARCH = "research"
METHODS_TAB_METRICS = "metrics"
METHODS_TAB_LIMITATIONS = "limitations"
METHODS_DEFAULT_TAB = METHODS_TAB_RELEASE
METHODS_TAB_LABELS = {
    METHODS_TAB_RELEASE: "Release & Validation",
    METHODS_TAB_RESEARCH: "Research Design",
    METHODS_TAB_METRICS: "Metrics & Denominators",
    METHODS_TAB_LIMITATIONS: "Limitations & Reproduction",
}

METHODS_VISIBILITY_TIER_ORDER = (
    "A_HEADLINE",
    "B_EXPLANATORY",
    "C_INTERNAL_VALIDATION",
    "D_DISABLED_UNTIL_BETTER_DATA",
)
METHODS_VISIBILITY_TIER_LABELS = {
    "A_HEADLINE": "Headline",
    "B_EXPLANATORY": "Explanatory",
    "C_INTERNAL_VALIDATION": "Internal validation",
    "D_DISABLED_UNTIL_BETTER_DATA": "Disabled pending better data",
}
METHODS_VISIBILITY_TIER_DESCRIPTIONS = {
    "A_HEADLINE": "Report-facing metrics allowed in primary dashboard views.",
    "B_EXPLANATORY": "Supporting metrics used to explain observed performance.",
    "C_INTERNAL_VALIDATION": "Audit and engineering fields not promoted as findings.",
    "D_DISABLED_UNTIL_BETTER_DATA": "Metrics unavailable for current conclusions.",
}

METHODS_RQ_ALL = "ALL"
METHODS_REPORT_SECTION_ALL = "ALL"
METHODS_DICTIONARY_TIER_ALL = "ALL"
METHODS_DICTIONARY_DATASET_ALL = "ALL"
METHODS_DICTIONARY_ROLE_ALL = "ALL"

METHODS_REPRODUCTION_COMMANDS = (
    (
        "Build certified visualization marts",
        "python3 -m research.python.visualization_v2.main",
    ),
    (
        "Run dashboard tests",
        "python3 -m pytest -q tests/research/python/dashboard",
    ),
    (
        "Start the Dash application",
        "python3 -m research.python.dashboard.app",
    ),
    (
        "Run browser E2E tests",
        'DASH_E2E_BASE_URL="http://127.0.0.1:8050" python3 -m pytest -q tests/research/python/dashboard/e2e',
    ),
)
