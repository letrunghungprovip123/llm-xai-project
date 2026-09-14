"""Orchestrate validation and write the Diagnostics release gate."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .config import (
    DATA_MART_GATE,
    DIAGNOSTIC_VALIDATION_PATH,
    DIAGNOSTIC_VERSION,
    INVALID_GATE,
    METRIC_GATE,
    OUTPUT_GATE,
    STATISTICAL_GATE,
)
from .validation_claims import validate_claim_diagnostics
from .validation_safe_phrase import validate_safe_phrase_matches
from .validation_common import (
    ValidationChecks,
    add_check,
    infinity_count,
    numeric_rate_out_of_bounds_count,
)
from .validation_generations import (
    validate_generation_diagnostics,
    validate_pipeline_failures,
)
from .validation_summaries import (
    validate_claim_summary,
    validate_generation_summary,
)


ValidationReport = dict[str, Any]


EXPECTED_CORE_CHECK_NAMES = {
    "input_data_mart_gate",
    "input_metric_gate",
    "input_statistical_gate",
    "claim_diagnostic_row_count",
    "duplicate_claim_diagnostic_id_count",
    "claim_source_identity_mismatch_count",
    "unknown_validation_statuses",
    "claim_status_flag_mismatch_count",
    "claim_status_partition_mismatch_count",
    "safe_phrase_eligibility_mismatch_count",
    "safe_phrase_exposure_mismatch_count",
    "safe_phrase_match_without_exposure_count",
    "safe_phrase_match_without_eligibility_count",
    "claim_diagnostic_version_set",
    "duplicate_claim_safe_phrase_pair_count",
    "expected_safe_phrase_match_pair_count",
    "missing_safe_phrase_match_pair_count",
    "extra_safe_phrase_match_pair_count",
    "safe_phrase_match_source_text_mismatch_count",
    "safe_phrase_match_item_metadata_mismatch_count",
    "safe_phrase_rule_mismatch_count",
    "claim_best_match_reconciliation_mismatch_count",
    "exact_match_not_contained_count",
    "high_overlap_below_threshold_count",
    "generation_diagnostic_row_count",
    "duplicate_generation_diagnostic_id_count",
    "generation_source_identity_mismatch_count",
    "generation_claim_count_mismatch_count",
    "supported_yield_formula_mismatch_count",
    "pipeline_loss_formula_mismatch_count",
    "not_verifiable_loss_formula_mismatch_count",
    "unsupported_loss_formula_mismatch_count",
    "contradiction_loss_formula_mismatch_count",
    "resolved_error_loss_formula_mismatch_count",
    "claim_quality_loss_formula_mismatch_count",
    "total_loss_formula_mismatch_count",
    "generation_loss_decomposition_mismatch_count",
    "supported_yield_metric_mismatch_count",
    "unusable_loss_rule_mismatch_count",
    "generation_claim_type_partition_mismatch_count",
    "generation_safe_phrase_state_mismatch_count",
    "usable_generation_count",
    "unusable_generation_count",
    "duplicate_claim_summary_key_count",
    "claim_summary_key_set_mismatch_count",
    "claim_summary_value_mismatch_count",
    "claim_summary_best_match_partition_mismatch_count",
    "claim_summary_overall_count",
    "duplicate_generation_summary_key_count",
    "generation_summary_key_set_mismatch_count",
    "generation_summary_value_mismatch_count",
    "generation_summary_loss_identity_mismatch_count",
    "generation_summary_overall_count",
    "pipeline_failure_row_count",
    "duplicate_pipeline_failure_generation_count",
    "pipeline_failure_generation_set",
    "pipeline_failure_category_mismatch_count",
    "pipeline_failure_non_s4_count",
    "pipeline_failure_model_counts",
    "diagnostic_rate_out_of_bounds_count",
    "infinite_output_value_count",
}


def gate_is_ready(report: dict[str, Any], expected_gate: str) -> bool:
    """Return whether one upstream report is fully approved."""

    return (
        report.get("passed") is True
        and report.get("failed_check_count") == 0
        and report.get("exit_gate") == expected_gate
    )


def validate_input_gates(
    checks: ValidationChecks,
    input_data: dict[str, Any],
) -> None:
    """Validate all three upstream release gates."""

    gate_inputs = [
        (
            "input_data_mart_gate",
            input_data["data_mart_validation"],
            DATA_MART_GATE,
        ),
        (
            "input_metric_gate",
            input_data["metric_validation"],
            METRIC_GATE,
        ),
        (
            "input_statistical_gate",
            input_data["statistical_validation"],
            STATISTICAL_GATE,
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


def validate_numeric_safety(
    checks: ValidationChecks,
    outputs: dict[str, pd.DataFrame],
) -> None:
    """Validate rates, loss components and numeric finiteness."""

    claim_rates = ["best_safe_phrase_token_coverage"]
    generation_rates = [
        "end_to_end_faithfulness_yield",
        "supported_yield_component",
        "pipeline_loss",
        "not_verifiable_loss",
        "unsupported_loss",
        "contradiction_loss",
        "resolved_error_loss",
        "claim_quality_loss",
        "total_loss",
        "safe_phrase_matched_claim_rate",
        "narrative_max_safe_phrase_token_coverage",
    ]

    out_of_bounds = numeric_rate_out_of_bounds_count(
        outputs["claim_diagnostics"],
        claim_rates,
    ) + numeric_rate_out_of_bounds_count(
        outputs["generation_diagnostics"],
        generation_rates,
    )
    add_check(
        checks,
        "diagnostic_rate_out_of_bounds_count",
        0,
        out_of_bounds,
        out_of_bounds == 0,
    )

    infinite_values = infinity_count(list(outputs.values()))
    add_check(
        checks,
        "infinite_output_value_count",
        0,
        infinite_values,
        infinite_values == 0,
    )


def validate_diagnostic_outputs(
    outputs: dict[str, pd.DataFrame],
    input_data: dict[str, Any],
) -> ValidationReport:
    """Run each validation group in the same order as the data flow."""

    checks: ValidationChecks = {}

    validate_input_gates(checks, input_data)
    validate_claim_diagnostics(
        checks,
        outputs["claim_diagnostics"],
        input_data,
    )
    validate_safe_phrase_matches(
        checks,
        outputs["safe_phrase_matches"],
        outputs["claim_diagnostics"],
        input_data,
    )
    validate_generation_diagnostics(
        checks,
        outputs["generation_diagnostics"],
        outputs["claim_diagnostics"],
        input_data,
    )
    validate_claim_summary(
        checks,
        outputs["claim_mechanism_summary"],
        outputs["claim_diagnostics"],
    )
    validate_generation_summary(
        checks,
        outputs["generation_mechanism_summary"],
        outputs["generation_diagnostics"],
    )
    validate_pipeline_failures(
        checks,
        outputs["pipeline_failures"],
        input_data,
    )
    validate_numeric_safety(checks, outputs)

    observed_check_names = set(checks)
    missing_check_names = sorted(
        EXPECTED_CORE_CHECK_NAMES - observed_check_names
    )
    extra_check_names = sorted(
        observed_check_names - EXPECTED_CORE_CHECK_NAMES
    )
    add_check(
        checks,
        "missing_validation_check_names",
        [],
        missing_check_names,
        missing_check_names == [],
    )
    add_check(
        checks,
        "extra_validation_check_names",
        [],
        extra_check_names,
        extra_check_names == [],
    )

    failed_check_count = sum(
        1 for check in checks.values() if not check["passed"]
    )
    passed = failed_check_count == 0

    return {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "input_gates": {
            "data_mart": DATA_MART_GATE,
            "metric_engineering": METRIC_GATE,
            "statistical_analysis": STATISTICAL_GATE,
        },
        "check_count": len(checks),
        "checks": checks,
        "failed_check_count": failed_check_count,
        "passed": passed,
        "exit_gate": OUTPUT_GATE if passed else INVALID_GATE,
    }


def write_validation_report(report: ValidationReport) -> None:
    """Write the diagnostics gate as formatted JSON."""

    DIAGNOSTIC_VALIDATION_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    DIAGNOSTIC_VALIDATION_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def print_validation_summary(
    report: ValidationReport,
    outputs: dict[str, pd.DataFrame],
) -> None:
    """Print a compact terminal summary."""

    print("Diagnostics validation")
    print(f"- Claim rows: {len(outputs['claim_diagnostics'])}")
    print(
        "- Generation rows: "
        f"{len(outputs['generation_diagnostics'])}"
    )
    print(
        "- Pipeline failures: "
        f"{len(outputs['pipeline_failures'])}"
    )
    print(
        "- Safe phrase matches: "
        f"{len(outputs['safe_phrase_matches'])}"
    )
    print(f"- Checks: {report['check_count']}")
    print(f"- Failed checks: {report['failed_check_count']}")
    print(f"- Exit gate: {report['exit_gate']}")
