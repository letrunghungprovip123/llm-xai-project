"""Validate statistical outputs before they are used in reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import (
    ALPHA,
    EXPECTED_COUNTS,
    INPUT_EXIT_GATE,
    INVALID_EXIT_GATE,
    OMNIBUS_EFFECTS,
    OUTPUT_EXIT_GATE,
    PRIMARY_METRIC,
    STATISTICAL_ANALYSIS_VERSION,
    STATISTICAL_VALIDATION_PATH,
)
from .inference import holm_adjust


ValidationReport = dict[str, Any]


def python_value(value: Any) -> Any:
    """Convert pandas and NumPy values into JSON-safe Python values."""

    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass

    if isinstance(value, dict):
        return {
            str(key): python_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [python_value(item) for item in value]

    return value


def add_check(
    checks: dict[str, dict[str, Any]],
    name: str,
    expected: Any,
    observed: Any,
    passed: bool,
    details: str | None = None,
) -> None:
    """Add one structured gate check."""

    check = {
        "expected": python_value(expected),
        "observed": python_value(observed),
        "passed": bool(passed),
    }
    if details:
        check["details"] = details
    checks[name] = check


def numeric_out_of_bounds_count(
    dataframe: pd.DataFrame,
    columns: list[str],
    minimum: float,
    maximum: float,
) -> int:
    """Count non-null numeric values outside a closed interval."""

    count = 0
    for column in columns:
        values = pd.to_numeric(dataframe[column], errors="coerce")
        invalid = values.notna() & (
            (values < minimum) | (values > maximum)
        )
        count += int(invalid.sum())
    return count


def infinity_count(dataframes: list[pd.DataFrame]) -> int:
    """Count positive and negative infinity across numeric outputs."""

    count = 0
    for dataframe in dataframes:
        numeric = dataframe.select_dtypes(include=[np.number])
        count += int(np.isinf(numeric.to_numpy()).sum())
    return count


def source_identity_mismatch_count(
    analysis_frame: pd.DataFrame,
    generation_metrics: pd.DataFrame,
) -> int:
    """Check that analysis rows still identify the same generation."""

    columns = [
        "generation_id",
        "case_id",
        "model_id",
        "evidence_level",
        "package_id",
    ]
    joined = analysis_frame[columns].merge(
        generation_metrics[columns],
        on="generation_id",
        how="outer",
        validate="one_to_one",
        suffixes=("_analysis", "_source"),
        indicator=True,
    )

    mismatch = joined["_merge"] != "both"
    for column in columns[1:]:
        mismatch = mismatch | (
            joined[f"{column}_analysis"]
            != joined[f"{column}_source"]
        )

    return int(mismatch.sum())


def recalculate_pair_values(
    row: pd.Series,
    analysis_frame: pd.DataFrame,
) -> dict[str, float | int]:
    """Rebuild one pair directly from condition identity columns."""

    condition_a = analysis_frame.loc[
        (analysis_frame["model_id"] == row["condition_a_model_id"])
        & (
            analysis_frame["evidence_level"]
            == row["condition_a_evidence_level"]
        ),
        ["case_id", row["metric_id"]],
    ]
    condition_b = analysis_frame.loc[
        (analysis_frame["model_id"] == row["condition_b_model_id"])
        & (
            analysis_frame["evidence_level"]
            == row["condition_b_evidence_level"]
        ),
        ["case_id", row["metric_id"]],
    ]

    paired = condition_a.merge(
        condition_b,
        on="case_id",
        how="inner",
        validate="one_to_one",
        suffixes=("_a", "_b"),
    ).dropna()

    values_a = paired[f"{row['metric_id']}_a"].to_numpy(dtype=float)
    values_b = paired[f"{row['metric_id']}_b"].to_numpy(dtype=float)
    differences = values_a - values_b

    return {
        "observed_pair_count": int(len(paired)),
        "mean_a": float(values_a.mean()),
        "mean_b": float(values_b.mean()),
        "mean_difference": float(differences.mean()),
        "median_difference": float(np.median(differences)),
    }


def paired_value_mismatch_count(
    paired_tests: pd.DataFrame,
    analysis_frame: pd.DataFrame,
) -> int:
    """Independently verify pair counts and descriptive differences."""

    mismatch_count = 0
    numeric_columns = [
        "mean_a",
        "mean_b",
        "mean_difference",
        "median_difference",
    ]

    for _, row in paired_tests.iterrows():
        expected = recalculate_pair_values(row, analysis_frame)

        if row["observed_pair_count"] != expected[
            "observed_pair_count"
        ]:
            mismatch_count += 1

        for column in numeric_columns:
            if not np.isclose(
                float(row[column]),
                float(expected[column]),
                rtol=0.0,
                atol=1e-12,
            ):
                mismatch_count += 1

    return mismatch_count


def holm_mismatch_count(paired_tests: pd.DataFrame) -> int:
    """Independently recompute Holm adjustment within each family."""

    mismatch_count = 0
    grouped = paired_tests.groupby(
        ["metric_id", "contrast_family"],
        sort=False,
    )

    for _, group in grouped:
        expected = holm_adjust(group["raw_p_value"])
        observed = group["adjusted_p_value"]
        mismatch_count += int(
            (~np.isclose(
                observed.to_numpy(dtype=float),
                expected.to_numpy(dtype=float),
                rtol=0.0,
                atol=1e-12,
            )).sum()
        )

    return mismatch_count


def validate_statistical_outputs(
    outputs: dict[str, pd.DataFrame],
    input_data: dict[str, Any],
    expected_counts: dict[str, int] | None = None,
    expected_unusable_generation_ids: list[str] | None = None,
) -> ValidationReport:
    """Validate cohort preservation, inference structure and p-values.

    ``expected_unusable_generation_ids=None`` retains the historical Home
    Credit S4-topology check.  Replications may provide the exact frozen IDs.
    """

    expected = EXPECTED_COUNTS if expected_counts is None else expected_counts
    analysis_frame = outputs["analysis_frame"]
    descriptive = outputs["descriptive_statistics"]
    omnibus = outputs["omnibus_tests"]
    paired = outputs["paired_tests"]
    conditional_paired = outputs["conditional_paired_tests"]
    complete_case_omnibus = outputs["complete_case_omnibus_tests"]
    unusable_generations = outputs["unusable_generations"]
    sensitivity_summary = outputs["sensitivity_summary"]
    metrics = input_data["generation_metrics"]
    metric_validation = input_data["metric_validation"]

    checks: dict[str, dict[str, Any]] = {}

    input_ready = (
        metric_validation.get("passed") is True
        and metric_validation.get("failed_check_count") == 0
        and metric_validation.get("exit_gate") == INPUT_EXIT_GATE
    )
    add_check(
        checks,
        "input_analytical_mart_gate",
        INPUT_EXIT_GATE,
        metric_validation.get("exit_gate"),
        input_ready,
    )

    add_check(
        checks,
        "analysis_frame_row_count",
        expected["generation_rows"],
        len(analysis_frame),
        len(analysis_frame) == expected["generation_rows"],
    )

    duplicate_generation_count = int(
        analysis_frame["generation_id"].duplicated(keep=False).sum()
    )
    add_check(
        checks,
        "duplicate_analysis_generation_count",
        0,
        duplicate_generation_count,
        duplicate_generation_count == 0,
    )

    identity_mismatch_count = source_identity_mismatch_count(
        analysis_frame,
        metrics,
    )
    add_check(
        checks,
        "analysis_source_identity_mismatch_count",
        0,
        identity_mismatch_count,
        identity_mismatch_count == 0,
    )

    subject_count = int(analysis_frame["case_id"].nunique())
    model_count = int(analysis_frame["model_id"].nunique())
    evidence_count = int(
        analysis_frame["evidence_level"].nunique()
    )
    cell_count = int(
        analysis_frame[["model_id", "evidence_level"]]
        .drop_duplicates()
        .shape[0]
    )

    add_check(
        checks,
        "subject_count",
        expected["cases"],
        subject_count,
        subject_count == expected["cases"],
    )
    add_check(
        checks,
        "model_count",
        expected["models"],
        model_count,
        model_count == expected["models"],
    )
    add_check(
        checks,
        "evidence_level_count",
        expected["evidence_levels"],
        evidence_count,
        evidence_count == expected["evidence_levels"],
    )
    add_check(
        checks,
        "model_evidence_cell_count",
        expected["model_evidence_cells"],
        cell_count,
        cell_count == expected["model_evidence_cells"],
    )

    conditions_per_case = analysis_frame.groupby("case_id").size()
    invalid_case_condition_count = int(
        (
            conditions_per_case
            != expected["conditions_per_case"]
        ).sum()
    )
    add_check(
        checks,
        "invalid_conditions_per_case_count",
        0,
        invalid_case_condition_count,
        invalid_case_condition_count == 0,
    )

    cell_sizes = analysis_frame.groupby(
        ["model_id", "evidence_level"]
    ).size()
    invalid_cell_size_count = int(
        (
            cell_sizes
            != expected["rows_per_model_evidence_cell"]
        ).sum()
    )
    add_check(
        checks,
        "invalid_model_evidence_cell_size_count",
        0,
        invalid_cell_size_count,
        invalid_cell_size_count == 0,
    )

    primary_null_count = int(
        analysis_frame[PRIMARY_METRIC].isna().sum()
    )
    primary_out_of_bounds = numeric_out_of_bounds_count(
        analysis_frame,
        [PRIMARY_METRIC],
        0.0,
        1.0,
    )
    add_check(
        checks,
        "primary_metric_null_count",
        0,
        primary_null_count,
        primary_null_count == 0,
    )
    add_check(
        checks,
        "primary_metric_out_of_bounds_count",
        0,
        primary_out_of_bounds,
        primary_out_of_bounds == 0,
    )

    unusable_nonzero_count = int(
        (
            analysis_frame.loc[
                analysis_frame["is_unusable"].astype(bool),
                PRIMARY_METRIC,
            ]
            != 0
        ).sum()
    )
    add_check(
        checks,
        "unusable_primary_metric_nonzero_count",
        0,
        unusable_nonzero_count,
        unusable_nonzero_count == 0,
    )

    complete_case_count = int(
        analysis_frame.loc[
            analysis_frame["is_complete_case"].astype(bool),
            "case_id",
        ].nunique()
    )
    add_check(
        checks,
        "complete_case_count",
        expected["complete_case_count"],
        complete_case_count,
        complete_case_count == expected["complete_case_count"],
    )

    descriptive_duplicate_count = int(
        descriptive.duplicated(
            subset=[
                "metric_id",
                "group_type",
                "model_id",
                "evidence_level",
                "selection_stratum",
            ],
            keep=False,
        ).sum()
    )
    descriptive_count_mismatch = int(
        (
            descriptive["planned_count"]
            != descriptive["observed_count"]
            + descriptive["missing_count"]
        ).sum()
    )
    add_check(
        checks,
        "duplicate_descriptive_key_count",
        0,
        descriptive_duplicate_count,
        descriptive_duplicate_count == 0,
    )
    add_check(
        checks,
        "descriptive_count_formula_mismatch_count",
        0,
        descriptive_count_mismatch,
        descriptive_count_mismatch == 0,
    )

    add_check(
        checks,
        "omnibus_test_count",
        expected["omnibus_tests"],
        len(omnibus),
        len(omnibus) == expected["omnibus_tests"],
    )
    observed_effects = sorted(omnibus["effect"].tolist())
    expected_effects = sorted(OMNIBUS_EFFECTS)
    add_check(
        checks,
        "omnibus_effect_set",
        expected_effects,
        observed_effects,
        observed_effects == expected_effects,
    )

    omnibus_p_out_of_bounds = numeric_out_of_bounds_count(
        omnibus,
        [
            "p_value_uncorrected",
            "p_value_greenhouse_geisser",
            "p_value_used",
        ],
        0.0,
        1.0,
    )
    omnibus_eta_out_of_bounds = numeric_out_of_bounds_count(
        omnibus,
        ["partial_eta_squared"],
        0.0,
        1.0,
    )
    omnibus_epsilon_out_of_bounds = numeric_out_of_bounds_count(
        omnibus,
        ["greenhouse_geisser_epsilon"],
        0.0,
        1.0,
    )
    invalid_omnibus_df_count = int(
        (
            (omnibus["df_numerator"] <= 0)
            | (omnibus["df_denominator"] <= 0)
            | (omnibus["df_numerator_corrected"] <= 0)
            | (omnibus["df_denominator_corrected"] <= 0)
        ).sum()
    )
    add_check(
        checks,
        "omnibus_p_value_out_of_bounds_count",
        0,
        omnibus_p_out_of_bounds,
        omnibus_p_out_of_bounds == 0,
    )
    add_check(
        checks,
        "omnibus_effect_size_out_of_bounds_count",
        0,
        omnibus_eta_out_of_bounds,
        omnibus_eta_out_of_bounds == 0,
    )
    add_check(
        checks,
        "omnibus_epsilon_out_of_bounds_count",
        0,
        omnibus_epsilon_out_of_bounds,
        omnibus_epsilon_out_of_bounds == 0,
    )
    add_check(
        checks,
        "invalid_omnibus_degrees_freedom_count",
        0,
        invalid_omnibus_df_count,
        invalid_omnibus_df_count == 0,
    )

    add_check(
        checks,
        "paired_test_count",
        expected["paired_tests"],
        len(paired),
        len(paired) == expected["paired_tests"],
    )

    family_counts = paired["contrast_family"].value_counts().to_dict()
    expected_family_counts = {
        "model_within_evidence": expected[
            "model_within_evidence_contrasts"
        ],
        "evidence_vs_s0": expected[
            "evidence_vs_s0_contrasts"
        ],
    }
    add_check(
        checks,
        "paired_contrast_family_counts",
        expected_family_counts,
        family_counts,
        family_counts == expected_family_counts,
    )

    paired_key_columns = [
        "metric_id",
        "contrast_family",
        "condition_a_model_id",
        "condition_a_evidence_level",
        "condition_b_model_id",
        "condition_b_evidence_level",
    ]
    duplicate_paired_count = int(
        paired.duplicated(
            subset=paired_key_columns,
            keep=False,
        ).sum()
    )
    add_check(
        checks,
        "duplicate_paired_contrast_count",
        0,
        duplicate_paired_count,
        duplicate_paired_count == 0,
    )

    invalid_pair_count = int(
        (
            (paired["planned_pair_count"] != expected["cases"])
            | (paired["observed_pair_count"] != expected["cases"])
            | (paired["excluded_pair_count"] != 0)
        ).sum()
    )
    add_check(
        checks,
        "invalid_primary_pair_count",
        0,
        invalid_pair_count,
        invalid_pair_count == 0,
    )

    pair_value_mismatch = paired_value_mismatch_count(
        paired,
        analysis_frame,
    )
    holm_mismatch = holm_mismatch_count(paired)
    add_check(
        checks,
        "paired_descriptive_value_mismatch_count",
        0,
        pair_value_mismatch,
        pair_value_mismatch == 0,
    )
    add_check(
        checks,
        "holm_adjustment_mismatch_count",
        0,
        holm_mismatch,
        holm_mismatch == 0,
    )

    paired_p_out_of_bounds = numeric_out_of_bounds_count(
        paired,
        ["raw_p_value", "adjusted_p_value"],
        0.0,
        1.0,
    )
    paired_effect_out_of_bounds = numeric_out_of_bounds_count(
        paired,
        ["rank_biserial_correlation"],
        -1.0,
        1.0,
    )
    adjusted_smaller_than_raw_count = int(
        (
            paired["adjusted_p_value"]
            + 1e-15
            < paired["raw_p_value"]
        ).sum()
    )
    add_check(
        checks,
        "paired_p_value_out_of_bounds_count",
        0,
        paired_p_out_of_bounds,
        paired_p_out_of_bounds == 0,
    )
    add_check(
        checks,
        "paired_effect_size_out_of_bounds_count",
        0,
        paired_effect_out_of_bounds,
        paired_effect_out_of_bounds == 0,
    )
    add_check(
        checks,
        "adjusted_p_smaller_than_raw_count",
        0,
        adjusted_smaller_than_raw_count,
        adjusted_smaller_than_raw_count == 0,
    )

    significant_flag_mismatch = int(
        (
            paired["significant_adjusted"]
            != (paired["adjusted_p_value"] < ALPHA)
        ).sum()
    )
    add_check(
        checks,
        "paired_significance_flag_mismatch_count",
        0,
        significant_flag_mismatch,
        significant_flag_mismatch == 0,
    )

    add_check(
        checks,
        "conditional_paired_test_count",
        expected["conditional_paired_tests"],
        len(conditional_paired),
        len(conditional_paired)
        == expected["conditional_paired_tests"],
    )
    conditional_invalid_pair_count = int(
        (
            (conditional_paired["observed_pair_count"] <= 0)
            | (conditional_paired["observed_pair_count"] > expected["cases"])
            | (
                conditional_paired["planned_pair_count"]
                != conditional_paired["observed_pair_count"]
                + conditional_paired["excluded_pair_count"]
            )
        ).sum()
    )
    add_check(
        checks,
        "conditional_invalid_pair_count",
        0,
        conditional_invalid_pair_count,
        conditional_invalid_pair_count == 0,
    )
    add_check(
        checks,
        "conditional_pair_value_mismatch_count",
        0,
        paired_value_mismatch_count(
            conditional_paired,
            analysis_frame,
        ),
        paired_value_mismatch_count(
            conditional_paired,
            analysis_frame,
        ) == 0,
    )
    conditional_holm_mismatch = holm_mismatch_count(conditional_paired)
    add_check(
        checks,
        "conditional_holm_mismatch_count",
        0,
        conditional_holm_mismatch,
        conditional_holm_mismatch == 0,
    )

    add_check(
        checks,
        "complete_case_omnibus_test_count",
        expected["complete_case_omnibus_tests"],
        len(complete_case_omnibus),
        len(complete_case_omnibus)
        == expected["complete_case_omnibus_tests"],
    )
    complete_case_subject_values = sorted(
        complete_case_omnibus["subject_count"].unique().tolist()
    )
    add_check(
        checks,
        "complete_case_omnibus_subject_set",
        [expected["complete_case_count"]],
        complete_case_subject_values,
        complete_case_subject_values
        == [expected["complete_case_count"]],
    )

    add_check(
        checks,
        "unusable_generation_output_count",
        expected["unusable_generation_count"],
        len(unusable_generations),
        len(unusable_generations)
        == expected["unusable_generation_count"],
    )
    if expected_unusable_generation_ids is None:
        unusable_non_s4_count = int(
            unusable_generations["evidence_level"].ne("S4").sum()
        )
        add_check(
            checks,
            "unusable_generation_non_s4_count",
            0,
            unusable_non_s4_count,
            unusable_non_s4_count == 0,
            details="Legacy Home Credit missingness is concentrated in S4.",
        )
    else:
        expected_unusable_ids = sorted(str(value) for value in expected_unusable_generation_ids)
        observed_unusable_ids = sorted(
            unusable_generations["generation_id"].astype(str).tolist()
        )
        add_check(
            checks,
            "unusable_generation_identity_set",
            expected_unusable_ids,
            observed_unusable_ids,
            observed_unusable_ids == expected_unusable_ids,
            details="Replication missingness must match the frozen M21 usability topology exactly.",
        )

    add_check(
        checks,
        "sensitivity_summary_row_count",
        expected["sensitivity_summary_rows"],
        len(sensitivity_summary),
        len(sensitivity_summary)
        == expected["sensitivity_summary_rows"],
    )

    version_values = sorted(
        analysis_frame["statistical_analysis_version"]
        .astype(str)
        .unique()
        .tolist()
    )
    add_check(
        checks,
        "statistical_analysis_version_set",
        [STATISTICAL_ANALYSIS_VERSION],
        version_values,
        version_values == [STATISTICAL_ANALYSIS_VERSION],
    )

    infinite_values = infinity_count(
        [
            analysis_frame,
            descriptive,
            omnibus,
            paired,
            conditional_paired,
            complete_case_omnibus,
            unusable_generations,
            sensitivity_summary,
        ]
    )
    add_check(
        checks,
        "infinite_output_value_count",
        0,
        infinite_values,
        infinite_values == 0,
    )

    failed_check_count = sum(
        1 for check in checks.values() if not check["passed"]
    )
    passed = failed_check_count == 0

    return {
        "statistical_analysis_version": STATISTICAL_ANALYSIS_VERSION,
        "input_gate": INPUT_EXIT_GATE,
        "alpha": ALPHA,
        "check_count": len(checks),
        "failed_check_count": failed_check_count,
        "passed": passed,
        "exit_gate": (
            OUTPUT_EXIT_GATE if passed else INVALID_EXIT_GATE
        ),
        "checks": checks,
    }


def write_validation_report(
    validation_report: ValidationReport,
    output_path: Path = STATISTICAL_VALIDATION_PATH,
) -> None:
    """Write deterministic, human-readable validation JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            validation_report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def print_validation_summary(
    validation_report: ValidationReport,
    outputs: dict[str, pd.DataFrame],
) -> None:
    """Print the small release summary expected after every run."""

    analysis_frame = outputs["analysis_frame"]
    omnibus = outputs["omnibus_tests"]
    paired = outputs["paired_tests"]
    conditional_paired = outputs["conditional_paired_tests"]
    complete_case = outputs["complete_case_omnibus_tests"]

    print("Statistical analysis validation")
    print(f"- Analysis rows: {len(analysis_frame)}")
    print(f"- Subjects: {analysis_frame['case_id'].nunique()}")
    print(f"- Omnibus tests: {len(omnibus)}")
    print(f"- Paired tests: {len(paired)}")
    print(f"- Conditional paired tests: {len(conditional_paired)}")
    print(
        "- Complete-case subjects: "
        f"{int(complete_case['subject_count'].iloc[0])}"
    )
    print(f"- Checks: {validation_report['check_count']}")
    print(f"- Failed checks: {validation_report['failed_check_count']}")
    print(f"- Exit gate: {validation_report['exit_gate']}")
