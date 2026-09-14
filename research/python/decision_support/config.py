"""Cấu hình cố định cho Decision Support Core."""

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
DIAGNOSTICS_DIR = VALIDATION_ROOT / "analysis" / "diagnostics"
OUTPUT_DIR = VALIDATION_ROOT / "analysis" / "decision_support"

GENERATION_METRICS_PATH = DATA_MART_DIR / "generation_metrics.csv"
MODELS_PATH = DATA_MART_DIR / "models.csv"
EVIDENCE_LEVELS_PATH = DATA_MART_DIR / "evidence_levels.csv"
METRIC_VALIDATION_PATH = DATA_MART_DIR / "metric_validation.json"

PAIRED_TESTS_PATH = STATISTICAL_DIR / "paired_tests.csv"
STATISTICAL_VALIDATION_PATH = STATISTICAL_DIR / "statistical_validation.json"

GENERATION_DIAGNOSTICS_PATH = DIAGNOSTICS_DIR / "generation_diagnostics.csv"
CLAIM_MECHANISM_SUMMARY_PATH = DIAGNOSTICS_DIR / "claim_mechanism_summary.csv"
GENERATION_MECHANISM_SUMMARY_PATH = (
    DIAGNOSTICS_DIR / "generation_mechanism_summary.csv"
)
DIAGNOSTIC_VALIDATION_PATH = DIAGNOSTICS_DIR / "diagnostic_validation.json"

DECISION_OPTIONS_PATH = OUTPUT_DIR / "decision_options.csv"
SCENARIO_DEFINITIONS_PATH = OUTPUT_DIR / "scenario_definitions.csv"
SCENARIO_CRITERION_SCORES_PATH = (
    OUTPUT_DIR / "scenario_criterion_scores.csv"
)
SCENARIO_RANKINGS_PATH = OUTPUT_DIR / "scenario_rankings.csv"
PARETO_FRONTIER_PATH = OUTPUT_DIR / "pareto_frontier.csv"
RECOMMENDATIONS_PATH = OUTPUT_DIR / "recommendations.csv"
RECOMMENDATION_EVIDENCE_PATH = OUTPUT_DIR / "recommendation_evidence.csv"
DECISION_VALIDATION_PATH = OUTPUT_DIR / "decision_validation.json"

DECISION_VERSION = "v1.1"
REQUIRED_DIAGNOSTIC_VERSION = "v1.1"
METRIC_GATE = "ANALYTICAL_MART_READY"
STATISTICAL_GATE = "STATISTICAL_CORE_READY"
DIAGNOSTIC_GATE = "DIAGNOSTICS_READY"
OUTPUT_GATE = "DECISION_SUPPORT_READY"
INVALID_GATE = "DECISION_SUPPORT_INVALID"

ALPHA = 0.05
FLOAT_TOLERANCE = 1e-12
P10_QUANTILE = 0.10
MAX_RECOMMENDATIONS_PER_SCENARIO = 3

EXPECTED_COUNTS = {
    "options": 18,
    "models": 3,
    "evidence_levels": 6,
    "generations_per_option": 36,
    "scenarios": 5,
    "ranking_rows": 90,
    "primary_recommendations": 5,
    "recommendation_evidence_rows": 85,
}

REQUIRED_GENERATION_DIAGNOSTIC_COLUMNS = {
    "generation_id",
    "case_id",
    "model_id",
    "evidence_level",
    "model_order",
    "evidence_order",
    "usable",
    "end_to_end_faithfulness_yield",
    "pipeline_loss",
    "not_verifiable_loss",
    "unsupported_loss",
    "contradiction_loss",
    "resolved_error_loss",
    "claim_quality_loss",
}

REQUIRED_GENERATION_METRIC_COLUMNS = {
    "generation_id",
    "model_id",
    "evidence_level",
    "usable",
    "is_truncated",
    "is_parse_success",
    "is_schema_valid",
    "latency_seconds",
    "total_token_count",
    "supported_claims_per_1000_total_tokens",
}

REQUIRED_CLAIM_SUMMARY_COLUMNS = {
    "group_type",
    "model_id",
    "evidence_level",
    "claim_count",
    "safe_phrase_exposed_claim_count",
    "safe_phrase_eligible_claim_count",
    "safe_phrase_best_exact_claim_count",
    "safe_phrase_best_contained_claim_count",
    "safe_phrase_best_high_overlap_claim_count",
    "safe_phrase_best_none_claim_count",
}

REQUIRED_GENERATION_SUMMARY_COLUMNS = {
    "group_type",
    "model_id",
    "evidence_level",
    "planned_generation_count",
    "mean_end_to_end_yield",
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

REQUIRED_PAIRED_TEST_COLUMNS = {
    "condition_a_model_id",
    "condition_a_evidence_level",
    "condition_b_model_id",
    "condition_b_evidence_level",
    "mean_difference",
    "rank_biserial_correlation",
    "adjusted_p_value",
    "significant_adjusted",
    "contrast_family",
}

# Mỗi scenario khai báo hard constraints trước và weighted objectives sau.
# Các weights là giả định ra quyết định minh bạch, không phải kết quả thống kê.
SCENARIOS = [
    {
        "scenario_id": "QUALITY_FIRST",
        "scenario_label": "Quality first",
        "scenario_description": (
            "Ưu tiên end-to-end quality và độ vững trên các case yếu hơn."
        ),
        "constraints": [
            {
                "criterion_id": "usability_rate",
                "minimum_value": 0.95,
                "maximum_value": None,
            },
        ],
        "objectives": [
            ("mean_end_to_end_yield", "MAX", 0.40),
            ("p10_end_to_end_yield", "MAX", 0.25),
            ("usability_rate", "MAX", 0.15),
            ("mean_resolved_error_loss", "MIN", 0.10),
            ("mean_not_verifiable_loss", "MIN", 0.10),
        ],
    },
    {
        "scenario_id": "RELIABILITY_FIRST",
        "scenario_label": "Reliability first",
        "scenario_description": (
            "Chỉ chấp nhận option hoàn thành toàn bộ planned generations."
        ),
        "constraints": [
            {
                "criterion_id": "usability_rate",
                "minimum_value": 1.0,
                "maximum_value": None,
            },
            {
                "criterion_id": "truncation_rate",
                "minimum_value": None,
                "maximum_value": 0.0,
            },
        ],
        "objectives": [
            ("p10_end_to_end_yield", "MAX", 0.40),
            ("mean_end_to_end_yield", "MAX", 0.30),
            ("mean_resolved_error_loss", "MIN", 0.15),
            ("mean_latency_seconds_planned", "MIN", 0.15),
        ],
    },
    {
        "scenario_id": "BALANCED",
        "scenario_label": "Balanced",
        "scenario_description": (
            "Cân bằng quality, reliability, efficiency và overlap signal."
        ),
        "constraints": [
            {
                "criterion_id": "usability_rate",
                "minimum_value": 0.95,
                "maximum_value": None,
            },
        ],
        "objectives": [
            ("mean_end_to_end_yield", "MAX", 0.25),
            ("p10_end_to_end_yield", "MAX", 0.15),
            ("usability_rate", "MAX", 0.15),
            ("mean_latency_seconds_planned", "MIN", 0.10),
            ("mean_total_token_count_planned", "MIN", 0.10),
            ("mean_supported_claims_per_1000_tokens", "MAX", 0.10),
            ("mean_resolved_error_loss", "MIN", 0.05),
            (
                "strong_safe_phrase_signal_share_all_claims",
                "MIN",
                0.10,
            ),
        ],
    },
    {
        "scenario_id": "EFFICIENCY_AWARE",
        "scenario_label": "Efficiency aware",
        "scenario_description": (
            "Ưu tiên latency và token efficiency sau khi quality qua ngưỡng."
        ),
        "constraints": [
            {
                "criterion_id": "usability_rate",
                "minimum_value": 0.95,
                "maximum_value": None,
            },
            {
                "criterion_id": "mean_end_to_end_yield",
                "minimum_value": 0.90,
                "maximum_value": None,
            },
        ],
        "objectives": [
            ("mean_supported_claims_per_1000_tokens", "MAX", 0.30),
            ("mean_latency_seconds_planned", "MIN", 0.25),
            ("mean_total_token_count_planned", "MIN", 0.20),
            ("mean_end_to_end_yield", "MAX", 0.15),
            ("p10_end_to_end_yield", "MAX", 0.10),
        ],
    },
    {
        "scenario_id": "INDEPENDENCE_SENSITIVE",
        "scenario_label": "Independence sensitive",
        "scenario_description": (
            "Giữ quality tương đối cao nhưng giảm lexical overlap signal."
        ),
        "constraints": [
            {
                "criterion_id": "usability_rate",
                "minimum_value": 0.95,
                "maximum_value": None,
            },
            {
                "criterion_id": "mean_end_to_end_yield",
                "minimum_value": 0.85,
                "maximum_value": None,
            },
        ],
        "objectives": [
            ("mean_end_to_end_yield", "MAX", 0.30),
            ("p10_end_to_end_yield", "MAX", 0.15),
            (
                "strong_safe_phrase_signal_share_all_claims",
                "MIN",
                0.30,
            ),
            (
                "weak_safe_phrase_signal_share_all_claims",
                "MIN",
                0.10,
            ),
            ("mean_supported_claims_per_1000_tokens", "MAX", 0.10),
            ("mean_latency_seconds_planned", "MIN", 0.05),
        ],
    },
]

KNOWN_CRITERIA = {
    criterion_id
    for scenario in SCENARIOS
    for criterion_id, _, _ in scenario["objectives"]
} | {
    constraint["criterion_id"]
    for scenario in SCENARIOS
    for constraint in scenario["constraints"]
}
