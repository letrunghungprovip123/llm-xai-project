"""Build and write all Statistical Analysis Core outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    ANALYSIS_FRAME_PATH,
    COMPLETE_CASE_OMNIBUS_TESTS_PATH,
    CONDITIONAL_PAIRED_TESTS_PATH,
    DESCRIPTIVE_STATISTICS_PATH,
    OMNIBUS_TESTS_PATH,
    OUTPUT_DIR,
    PAIRED_TESTS_PATH,
    SENSITIVITY_SUMMARY_PATH,
    UNUSABLE_GENERATIONS_PATH,
)
from .descriptive import build_descriptive_statistics
from .inference import (
    build_complete_case_omnibus_tests,
    build_conditional_paired_tests,
    build_paired_tests,
    run_repeated_measures_anova,
)
from .prepare import build_analysis_frame


def build_unusable_generation_analysis(
    analysis_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Materialize structured pipeline failures for reporting."""

    columns = [
        "generation_id",
        "case_id",
        "model_id",
        "model_label",
        "evidence_level",
        "evidence_label",
        "runtime_status",
        "runtime_error_type",
        "runtime_error_message",
        "retry_count",
        "is_truncated",
        "is_parse_success",
        "is_schema_valid",
        "latency_seconds",
        "total_token_count",
        "conservative_faithfulness",
        "end_to_end_faithfulness_yield",
    ]
    failures = analysis_frame.loc[
        analysis_frame["is_unusable"].astype(bool),
        columns,
    ].copy()
    failures["missingness_class"] = "STRUCTURED_PIPELINE_FAILURE"
    failures["primary_endpoint_handling"] = "ZERO_OPERATIONAL_PENALTY"
    failures["conditional_endpoint_handling"] = "MISSING_NOT_IMPUTED"
    return failures.reset_index(drop=True)


def build_sensitivity_summary(
    primary_omnibus: pd.DataFrame,
    complete_case_omnibus: pd.DataFrame,
) -> pd.DataFrame:
    """Compare primary and complete-case conclusions effect by effect."""

    primary = primary_omnibus[
        [
            "effect",
            "subject_count",
            "p_value_used",
            "partial_eta_squared",
            "significant",
        ]
    ].rename(
        columns={
            "subject_count": "primary_subject_count",
            "p_value_used": "primary_p_value",
            "partial_eta_squared": "primary_partial_eta_squared",
            "significant": "primary_significant",
        }
    )
    sensitivity = complete_case_omnibus[
        [
            "effect",
            "subject_count",
            "p_value_used",
            "partial_eta_squared",
            "significant",
        ]
    ].rename(
        columns={
            "subject_count": "sensitivity_subject_count",
            "p_value_used": "sensitivity_p_value",
            "partial_eta_squared": "sensitivity_partial_eta_squared",
            "significant": "sensitivity_significant",
        }
    )
    summary = primary.merge(
        sensitivity,
        on="effect",
        how="inner",
        validate="one_to_one",
    )
    summary["significance_conclusion_stable"] = (
        summary["primary_significant"]
        == summary["sensitivity_significant"]
    )
    summary["interpretation"] = summary[
        "significance_conclusion_stable"
    ].map(
        {
            True: "Primary and complete-case significance conclusions agree.",
            False: "Primary and complete-case conclusions differ; report both.",
        }
    )
    return summary


def build_statistical_outputs(
    input_data: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    """Run the statistical core in a clear, sequential order."""

    analysis_frame = build_analysis_frame(input_data)
    descriptive_statistics = build_descriptive_statistics(
        analysis_frame
    )
    omnibus_tests = run_repeated_measures_anova(analysis_frame)
    paired_tests = build_paired_tests(analysis_frame)
    conditional_paired_tests = build_conditional_paired_tests(
        analysis_frame
    )
    complete_case_omnibus_tests = build_complete_case_omnibus_tests(
        analysis_frame
    )
    unusable_generations = build_unusable_generation_analysis(
        analysis_frame
    )
    sensitivity_summary = build_sensitivity_summary(
        omnibus_tests,
        complete_case_omnibus_tests,
    )

    return {
        "analysis_frame": analysis_frame,
        "descriptive_statistics": descriptive_statistics,
        "omnibus_tests": omnibus_tests,
        "paired_tests": paired_tests,
        "conditional_paired_tests": conditional_paired_tests,
        "complete_case_omnibus_tests": complete_case_omnibus_tests,
        "unusable_generations": unusable_generations,
        "sensitivity_summary": sensitivity_summary,
    }


def write_statistical_outputs(
    outputs: dict[str, pd.DataFrame],
) -> None:
    """Write the four deterministic CSV outputs."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    outputs["analysis_frame"].to_csv(
        ANALYSIS_FRAME_PATH,
        index=False,
    )
    outputs["descriptive_statistics"].to_csv(
        DESCRIPTIVE_STATISTICS_PATH,
        index=False,
    )
    outputs["omnibus_tests"].to_csv(
        OMNIBUS_TESTS_PATH,
        index=False,
    )
    outputs["paired_tests"].to_csv(
        PAIRED_TESTS_PATH,
        index=False,
    )
    outputs["conditional_paired_tests"].to_csv(
        CONDITIONAL_PAIRED_TESTS_PATH,
        index=False,
    )
    outputs["complete_case_omnibus_tests"].to_csv(
        COMPLETE_CASE_OMNIBUS_TESTS_PATH,
        index=False,
    )
    outputs["unusable_generations"].to_csv(
        UNUSABLE_GENERATIONS_PATH,
        index=False,
    )
    outputs["sensitivity_summary"].to_csv(
        SENSITIVITY_SUMMARY_PATH,
        index=False,
    )


def output_paths() -> list[Path]:
    """Return generated CSV paths for tests and terminal checks."""

    return [
        ANALYSIS_FRAME_PATH,
        DESCRIPTIVE_STATISTICS_PATH,
        OMNIBUS_TESTS_PATH,
        PAIRED_TESTS_PATH,
        CONDITIONAL_PAIRED_TESTS_PATH,
        COMPLETE_CASE_OMNIBUS_TESTS_PATH,
        UNUSABLE_GENERATIONS_PATH,
        SENSITIVITY_SUMMARY_PATH,
    ]
