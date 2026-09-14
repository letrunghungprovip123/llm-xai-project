"""Fail-closed validation for claim and generation summaries."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import EXPECTED_COUNTS, NUMERIC_TOLERANCE
from .summarize import (
    build_claim_mechanism_summary,
    build_generation_mechanism_summary,
)
from .validation_common import (
    ValidationChecks,
    add_check,
    dataframe_value_mismatch_count,
)


def validate_claim_summary(
    checks: ValidationChecks,
    summary: pd.DataFrame,
    claim_diagnostics: pd.DataFrame,
) -> None:
    """Rebuild and validate every claim-summary key and value."""

    key_columns = [
        "group_type",
        "model_id",
        "evidence_level",
        "claim_type",
        "selection_stratum",
    ]
    duplicate_count = int(
        summary.duplicated(subset=key_columns, keep=False).sum()
    )
    add_check(
        checks,
        "duplicate_claim_summary_key_count",
        0,
        duplicate_count,
        duplicate_count == 0,
    )

    expected = build_claim_mechanism_summary(claim_diagnostics)
    value_columns = [
        column for column in expected.columns if column not in key_columns
    ]
    missing, extra, changed = dataframe_value_mismatch_count(
        expected,
        summary,
        key_columns,
        value_columns,
        tolerance=NUMERIC_TOLERANCE,
    )
    add_check(
        checks,
        "claim_summary_key_set_mismatch_count",
        0,
        missing + extra,
        missing + extra == 0,
    )
    add_check(
        checks,
        "claim_summary_value_mismatch_count",
        0,
        changed,
        changed == 0,
    )

    exclusive_counts = summary[
        [
            "safe_phrase_best_exact_claim_count",
            "safe_phrase_best_contained_claim_count",
            "safe_phrase_best_high_overlap_claim_count",
            "safe_phrase_best_none_claim_count",
        ]
    ].sum(axis=1)
    exclusive_partition_mismatch = int(
        (
            exclusive_counts
            != summary["safe_phrase_eligible_claim_count"]
        ).sum()
    )
    add_check(
        checks,
        "claim_summary_best_match_partition_mismatch_count",
        0,
        exclusive_partition_mismatch,
        exclusive_partition_mismatch == 0,
    )

    overall = summary.loc[summary["group_type"] == "overall"]
    overall_claim_count = (
        int(overall.iloc[0]["claim_count"])
        if len(overall) == 1
        else -1
    )
    add_check(
        checks,
        "claim_summary_overall_count",
        EXPECTED_COUNTS["claims"],
        overall_claim_count,
        overall_claim_count == EXPECTED_COUNTS["claims"],
    )


def validate_generation_summary(
    checks: ValidationChecks,
    summary: pd.DataFrame,
    generation_diagnostics: pd.DataFrame,
) -> None:
    """Rebuild and validate every generation-summary key and value."""

    key_columns = [
        "group_type",
        "model_id",
        "evidence_level",
        "selection_stratum",
    ]
    duplicate_count = int(
        summary.duplicated(subset=key_columns, keep=False).sum()
    )
    add_check(
        checks,
        "duplicate_generation_summary_key_count",
        0,
        duplicate_count,
        duplicate_count == 0,
    )

    expected = build_generation_mechanism_summary(
        generation_diagnostics
    )
    value_columns = [
        column for column in expected.columns if column not in key_columns
    ]
    missing, extra, changed = dataframe_value_mismatch_count(
        expected,
        summary,
        key_columns,
        value_columns,
        tolerance=NUMERIC_TOLERANCE,
    )
    add_check(
        checks,
        "generation_summary_key_set_mismatch_count",
        0,
        missing + extra,
        missing + extra == 0,
    )
    add_check(
        checks,
        "generation_summary_value_mismatch_count",
        0,
        changed,
        changed == 0,
    )

    component_sum = summary[
        [
            "mean_end_to_end_yield",
            "mean_pipeline_loss",
            "mean_not_verifiable_loss",
            "mean_unsupported_loss",
            "mean_contradiction_loss",
        ]
    ].sum(axis=1)
    identity_mismatch = int(
        (~np.isclose(
            component_sum,
            1.0,
            rtol=0.0,
            atol=NUMERIC_TOLERANCE,
        )).sum()
    )
    add_check(
        checks,
        "generation_summary_loss_identity_mismatch_count",
        0,
        identity_mismatch,
        identity_mismatch == 0,
    )

    overall = summary.loc[summary["group_type"] == "overall"]
    overall_count = (
        int(overall.iloc[0]["planned_generation_count"])
        if len(overall) == 1
        else -1
    )
    add_check(
        checks,
        "generation_summary_overall_count",
        EXPECTED_COUNTS["generations"],
        overall_count,
        overall_count == EXPECTED_COUNTS["generations"],
    )
