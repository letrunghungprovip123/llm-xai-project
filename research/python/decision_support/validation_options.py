"""Validation cho decision_options.csv."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import EXPECTED_COUNTS
from .prepare import build_decision_options
from .validation_common import (
    ValidationChecks,
    add_check,
    dataframe_key_set,
    dataframe_value_mismatch_count,
)


def validate_decision_options(
    checks: ValidationChecks,
    observed: pd.DataFrame,
    input_data: dict[str, Any],
) -> None:
    """Rebuild 18 options từ upstream detail rồi so toàn bộ values."""

    expected = build_decision_options(input_data)
    key_columns = ["option_id"]

    add_check(
        checks,
        "decision_option_row_count",
        EXPECTED_COUNTS["options"],
        len(observed),
        len(observed) == EXPECTED_COUNTS["options"],
    )
    duplicate_count = int(observed["option_id"].duplicated(keep=False).sum())
    add_check(
        checks,
        "duplicate_decision_option_id_count",
        0,
        duplicate_count,
        duplicate_count == 0,
    )

    key_mismatch = len(
        dataframe_key_set(observed, key_columns)
        ^ dataframe_key_set(expected, key_columns)
    )
    add_check(
        checks,
        "decision_option_key_set_mismatch_count",
        0,
        key_mismatch,
        key_mismatch == 0,
    )

    value_mismatch = dataframe_value_mismatch_count(
        observed,
        expected,
        key_columns,
    )
    add_check(
        checks,
        "decision_option_value_mismatch_count",
        0,
        value_mismatch,
        value_mismatch == 0,
    )

    loss_sum = (
        observed["mean_end_to_end_yield"]
        + observed["mean_pipeline_loss"]
        + observed["mean_not_verifiable_loss"]
        + observed["mean_unsupported_loss"]
        + observed["mean_contradiction_loss"]
    )
    loss_mismatch = int(
        (~np.isclose(loss_sum, 1.0, rtol=0.0, atol=1e-12)).sum()
    )
    add_check(
        checks,
        "decision_option_loss_identity_mismatch_count",
        0,
        loss_mismatch,
        loss_mismatch == 0,
    )

    best_partition = (
        observed["safe_phrase_best_exact_claim_count"]
        + observed["safe_phrase_best_contained_claim_count"]
        + observed["safe_phrase_best_high_overlap_claim_count"]
        + observed["safe_phrase_best_none_claim_count"]
    )
    best_mismatch = int(
        (
            best_partition
            != observed["safe_phrase_eligible_claim_count"]
        ).sum()
    )
    add_check(
        checks,
        "decision_option_best_match_partition_mismatch_count",
        0,
        best_mismatch,
        best_mismatch == 0,
    )
