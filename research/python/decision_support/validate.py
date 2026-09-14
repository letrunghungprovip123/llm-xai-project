"""Orchestrate Decision Support validation và phát release gate."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .config import (
    DECISION_VALIDATION_PATH,
    DECISION_VERSION,
    DIAGNOSTIC_GATE,
    INVALID_GATE,
    METRIC_GATE,
    OUTPUT_GATE,
    REQUIRED_DIAGNOSTIC_VERSION,
    STATISTICAL_GATE,
)
from .load import gate_is_ready
from .validation_common import (
    ValidationChecks,
    add_check,
    infinity_count,
)
from .validation_options import validate_decision_options
from .validation_scenarios import (
    validate_scenario_definitions,
    validate_scenario_outputs,
)


ValidationReport = dict[str, Any]

EXPECTED_CORE_CHECK_NAMES = {
    "input_metric_gate",
    "input_statistical_gate",
    "input_diagnostic_gate",
    "input_diagnostic_version",
    "decision_option_row_count",
    "duplicate_decision_option_id_count",
    "decision_option_key_set_mismatch_count",
    "decision_option_value_mismatch_count",
    "decision_option_loss_identity_mismatch_count",
    "decision_option_best_match_partition_mismatch_count",
    "scenario_count",
    "duplicate_scenario_rule_count",
    "scenario_definition_key_set_mismatch_count",
    "scenario_definition_value_mismatch_count",
    "scenario_weight_sum_mismatch_count",
    "unknown_scenario_criteria",
    "invalid_scenario_direction_count",
    "criterion_score_key_set_mismatch_count",
    "criterion_score_value_mismatch_count",
    "pareto_key_set_mismatch_count",
    "pareto_value_mismatch_count",
    "ranking_key_set_mismatch_count",
    "ranking_value_mismatch_count",
    "recommendation_key_set_mismatch_count",
    "recommendation_value_mismatch_count",
    "recommendation_evidence_key_set_mismatch_count",
    "recommendation_evidence_value_mismatch_count",
    "scenario_ranking_row_count",
    "utility_rank_state_mismatch_count",
    "recommendation_reason_code_mismatch_count",
    "primary_recommendation_count",
    "recommendation_evidence_row_count",
    "normalized_value_out_of_bounds_count",
    "ineligible_nonnull_utility_count",
    "non_pareto_recommendation_count",
    "utility_score_out_of_bounds_count",
    "infinite_output_value_count",
}


def validate_input_gates(
    checks: ValidationChecks,
    input_data: dict[str, Any],
) -> None:
    """Kiểm ba upstream gates và Diagnostics v1.1."""

    gate_inputs = [
        ("input_metric_gate", input_data["metric_validation"], METRIC_GATE),
        (
            "input_statistical_gate",
            input_data["statistical_validation"],
            STATISTICAL_GATE,
        ),
        (
            "input_diagnostic_gate",
            input_data["diagnostic_validation"],
            DIAGNOSTIC_GATE,
        ),
    ]
    for name, report, expected_gate in gate_inputs:
        add_check(
            checks,
            name,
            expected_gate,
            report.get("exit_gate"),
            gate_is_ready(report, expected_gate),
        )

    observed_version = input_data["diagnostic_validation"].get(
        "diagnostic_version"
    )
    add_check(
        checks,
        "input_diagnostic_version",
        REQUIRED_DIAGNOSTIC_VERSION,
        observed_version,
        observed_version == REQUIRED_DIAGNOSTIC_VERSION,
    )


def validate_numeric_safety(
    checks: ValidationChecks,
    outputs: dict[str, pd.DataFrame],
) -> None:
    """Kiểm utility range và không có infinity."""

    utilities = outputs["scenario_rankings"]["utility_score"]
    invalid_utility = int(
        (
            utilities.notna()
            & ((utilities < 0.0) | (utilities > 1.0))
        ).sum()
    )
    add_check(
        checks,
        "utility_score_out_of_bounds_count",
        0,
        invalid_utility,
        invalid_utility == 0,
    )

    infinite_values = infinity_count(list(outputs.values()))
    add_check(
        checks,
        "infinite_output_value_count",
        0,
        infinite_values,
        infinite_values == 0,
    )


def validate_decision_outputs(
    outputs: dict[str, pd.DataFrame],
    input_data: dict[str, Any],
) -> ValidationReport:
    """Chạy validation theo đúng data flow và fail closed."""

    checks: ValidationChecks = {}
    validate_input_gates(checks, input_data)
    validate_decision_options(
        checks,
        outputs["decision_options"],
        input_data,
    )
    validate_scenario_definitions(
        checks,
        outputs["scenario_definitions"],
    )
    validate_scenario_outputs(checks, outputs, input_data)
    validate_numeric_safety(checks, outputs)

    observed_names = set(checks)
    missing_names = sorted(EXPECTED_CORE_CHECK_NAMES - observed_names)
    extra_names = sorted(observed_names - EXPECTED_CORE_CHECK_NAMES)
    add_check(
        checks,
        "missing_validation_check_names",
        [],
        missing_names,
        missing_names == [],
    )
    add_check(
        checks,
        "extra_validation_check_names",
        [],
        extra_names,
        extra_names == [],
    )

    failed_check_count = sum(
        1 for check in checks.values() if not check["passed"]
    )
    passed = failed_check_count == 0
    return {
        "decision_version": DECISION_VERSION,
        "input_gates": {
            "metric_engineering": METRIC_GATE,
            "statistical_analysis": STATISTICAL_GATE,
            "diagnostics": DIAGNOSTIC_GATE,
        },
        "check_count": len(checks),
        "checks": checks,
        "failed_check_count": failed_check_count,
        "passed": passed,
        "exit_gate": OUTPUT_GATE if passed else INVALID_GATE,
    }


def write_validation_report(report: ValidationReport) -> None:
    """Ghi release gate dạng JSON dễ audit."""

    DECISION_VALIDATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISION_VALIDATION_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def print_validation_summary(
    report: ValidationReport,
    outputs: dict[str, pd.DataFrame],
) -> None:
    """In đúng các counts quan trọng lên terminal."""

    primary_count = int(
        (
            outputs["recommendations"]["recommendation_role"]
            == "PRIMARY"
        ).sum()
    )
    print("Decision support validation")
    print(f"- Decision options: {len(outputs['decision_options'])}")
    print(
        "- Scenarios: "
        f"{outputs['scenario_definitions']['scenario_id'].nunique()}"
    )
    print(f"- Scenario rankings: {len(outputs['scenario_rankings'])}")
    print(f"- Primary recommendations: {primary_count}")
    print(
        "- Recommendation evidence rows: "
        f"{len(outputs['recommendation_evidence'])}"
    )
    print(f"- Checks: {report['check_count']}")
    print(f"- Failed checks: {report['failed_check_count']}")
    print(f"- Exit gate: {report['exit_gate']}")
