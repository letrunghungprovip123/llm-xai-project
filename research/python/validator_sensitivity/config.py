"""Paths and contracts for validator sensitivity analysis."""

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
OUTPUT_DIR = VALIDATION_ROOT / "analysis" / "validator_sensitivity"

CANDIDATE_SUMMARY_PATH = (
    VALIDATION_ROOT
    / "claim_validation_candidate"
    / "generation_validation_summary.jsonl"
)
V4_SUMMARY_PATH = (
    VALIDATION_ROOT
    / "claim_validation_v4"
    / "generation_validation_summary.jsonl"
)
PAIR_OUTPUT_PATH = OUTPUT_DIR / "validator_generation_pairs.csv"
SUMMARY_OUTPUT_PATH = OUTPUT_DIR / "validator_metric_summary.csv"
TEST_OUTPUT_PATH = OUTPUT_DIR / "validator_sensitivity_tests.csv"
VALIDATION_OUTPUT_PATH = OUTPUT_DIR / "validator_sensitivity_validation.json"

SENSITIVITY_VERSION = "v1.0"
EXPECTED_GENERATIONS = 648
EXPECTED_CASES = 36
METRICS = [
    "end_to_end_faithfulness_yield",
    "conservative_faithfulness",
    "verifiability",
    "resolved_faithfulness",
]
