"""Load all certified inputs required by visualization v2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from research.python.common.research_release import (
    verify_manifest_artifacts,
    verify_report_release_manifest,
)

from research.python.visualization.load import load_visualization_inputs

from .config import (
    BASELINE_GENERATION_METRICS_SOURCE_PATH,
    BASELINE_MANIFEST_PATH,
    BASELINE_OPTION_PERFORMANCE_SOURCE_PATH,
    BASELINE_PAIR_SOURCE_PATH,
    BASELINE_SUMMARY_SOURCE_PATH,
    BASELINE_TEST_SOURCE_PATH,
    BASELINE_VALIDATION_PATH,
    COMPLETE_CASE_OMNIBUS_SOURCE_PATH,
    CONDITIONAL_PAIRED_TESTS_SOURCE_PATH,
    CASES_PATH,
    DASHBOARD_CONTRACT_PATH,
    DESCRIPTIVE_STATISTICS_SOURCE_PATH,
    CLAIMS_PATH,
    EVIDENCE_ITEMS_PATH,
    EVIDENCE_LEVELS_PATH,
    EVIDENCE_PACKAGES_PATH,
    GENERATIONS_PATH,
    GENERATION_METRICS_PATH,
    OMNIBUS_TESTS_SOURCE_PATH,
    PAIRED_TESTS_SOURCE_PATH,
    METRIC_VISIBILITY_PATH,
    MODELS_PATH,
    REPORT_MANIFEST_PATH,
    REPORT_NUMBERS_PATH,
    REPORT_READINESS_PATH,
    RQ_CONTRACT_PATH,
    STATISTICAL_SENSITIVITY_SOURCE_PATH,
    STATISTICAL_VALIDATION_PATH,
    UNUSABLE_GENERATIONS_SOURCE_PATH,
    VALIDATOR_GENERATION_PAIRS_SOURCE_PATH,
    VALIDATOR_METRIC_SUMMARY_SOURCE_PATH,
    VALIDATOR_SENSITIVITY_TESTS_SOURCE_PATH,
    VALIDATOR_SENSITIVITY_VALIDATION_PATH,
)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path, low_memory=False)


def require_gate(report: dict[str, Any], expected: str, name: str) -> None:
    if not (
        report.get("passed") is True
        and report.get("failed_check_count") == 0
        and report.get("exit_gate") == expected
    ):
        raise ValueError(f"{name} gate is not ready: expected {expected}.")


def load_visualization_v2_inputs() -> dict[str, Any]:
    data: dict[str, Any] = {
        "legacy": load_visualization_inputs(),
        "generations": read_csv(GENERATIONS_PATH),
        "generation_metrics": read_csv(GENERATION_METRICS_PATH),
        "cases": read_csv(CASES_PATH),
        "claims": read_csv(CLAIMS_PATH),
        "evidence_packages": read_csv(EVIDENCE_PACKAGES_PATH),
        "evidence_items": read_csv(EVIDENCE_ITEMS_PATH),
        "models": read_csv(MODELS_PATH),
        "evidence_levels": read_csv(EVIDENCE_LEVELS_PATH),
        "baseline_generation_metrics": read_csv(
            BASELINE_GENERATION_METRICS_SOURCE_PATH
        ),
        "baseline_option_performance": read_csv(
            BASELINE_OPTION_PERFORMANCE_SOURCE_PATH
        ),
        "llm_vs_template_case_pairs": read_csv(BASELINE_PAIR_SOURCE_PATH),
        "llm_vs_template_summary": read_csv(BASELINE_SUMMARY_SOURCE_PATH),
        "llm_vs_template_tests": read_csv(BASELINE_TEST_SOURCE_PATH),
        "descriptive_statistics": read_csv(
            DESCRIPTIVE_STATISTICS_SOURCE_PATH
        ),
        "omnibus_tests": read_csv(OMNIBUS_TESTS_SOURCE_PATH),
        "paired_tests": read_csv(PAIRED_TESTS_SOURCE_PATH),
        "conditional_paired_tests": read_csv(
            CONDITIONAL_PAIRED_TESTS_SOURCE_PATH
        ),
        "complete_case_omnibus_tests": read_csv(
            COMPLETE_CASE_OMNIBUS_SOURCE_PATH
        ),
        "statistical_sensitivity_summary": read_csv(
            STATISTICAL_SENSITIVITY_SOURCE_PATH
        ),
        "unusable_generations": read_csv(
            UNUSABLE_GENERATIONS_SOURCE_PATH
        ),
        "validator_generation_pairs": read_csv(
            VALIDATOR_GENERATION_PAIRS_SOURCE_PATH
        ),
        "validator_metric_summary": read_csv(
            VALIDATOR_METRIC_SUMMARY_SOURCE_PATH
        ),
        "validator_sensitivity_tests": read_csv(
            VALIDATOR_SENSITIVITY_TESTS_SOURCE_PATH
        ),
        "report_readiness": read_json(REPORT_READINESS_PATH),
        "report_manifest": read_json(REPORT_MANIFEST_PATH),
        "report_numbers": read_json(REPORT_NUMBERS_PATH),
        "statistical_validation": read_json(STATISTICAL_VALIDATION_PATH),
        "validator_sensitivity_validation": read_json(
            VALIDATOR_SENSITIVITY_VALIDATION_PATH
        ),
        "baseline_validation": read_json(BASELINE_VALIDATION_PATH),
        "baseline_manifest": read_json(BASELINE_MANIFEST_PATH),
        "rq_contract": read_json(RQ_CONTRACT_PATH),
        "metric_visibility": read_json(METRIC_VISIBILITY_PATH),
        "dashboard_contract": read_json(DASHBOARD_CONTRACT_PATH),
    }
    require_gate(data["report_readiness"], "REPORT_WRITING_READY", "Report release")
    require_gate(data["statistical_validation"], "STATISTICAL_CORE_READY", "Statistics")
    require_gate(
        data["validator_sensitivity_validation"],
        "VALIDATOR_SENSITIVITY_READY",
        "Validator sensitivity",
    )
    require_gate(
        data["baseline_validation"],
        "BASELINE_COMPARISON_READY",
        "Template Baseline",
    )
    data["verified_report_paths"] = verify_report_release_manifest(
        data["report_manifest"]
    )
    data["verified_baseline_paths"] = verify_manifest_artifacts(
        data["baseline_manifest"].get("output_artifacts", []),
        contract_name="Template Baseline comparison",
    )
    return data
