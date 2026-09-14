"""Calculate generation-level quality metrics with explicit denominators."""

from __future__ import annotations

import numpy as np
import pandas as pd


def divide_when_positive(
    numerator: pd.Series,
    denominator: pd.Series,
) -> pd.Series:
    """Divide only where the denominator is positive; otherwise return NaN."""

    result = pd.Series(
        np.nan,
        index=numerator.index,
        dtype="float64",
    )
    valid_rows = denominator > 0

    result.loc[valid_rows] = (
        numerator.loc[valid_rows].astype(float)
        / denominator.loc[valid_rows].astype(float)
    )

    return result


def add_quality_metrics(
    generations: pd.DataFrame,
) -> pd.DataFrame:
    """Add quality rates and flags without changing the source frame."""

    metrics = generations.copy()

    usable = metrics["usable"].astype(bool)
    applicable = metrics["applicable_count"]
    resolved = metrics["resolved_count"]
    supported = metrics["supported_count"]
    unsupported = metrics["unsupported_count"]
    contradicted = metrics["contradicted_count"]
    not_verifiable = metrics["not_verifiable_count"]

    metrics["quality_metric_eligible"] = (
        usable & (applicable > 0)
    )

    metrics["resolved_faithfulness"] = divide_when_positive(
        supported,
        resolved,
    ).where(usable)

    metrics["verifiability"] = divide_when_positive(
        resolved,
        applicable,
    ).where(usable)

    metrics["conservative_faithfulness"] = divide_when_positive(
        supported,
        applicable,
    ).where(usable)

    metrics["end_to_end_faithfulness_yield"] = 0.0
    eligible_rows = metrics["quality_metric_eligible"]
    metrics.loc[
        eligible_rows,
        "end_to_end_faithfulness_yield",
    ] = metrics.loc[
        eligible_rows,
        "conservative_faithfulness",
    ]

    metrics["not_verifiable_rate"] = divide_when_positive(
        not_verifiable,
        applicable,
    ).where(usable)

    metrics["unsupported_rate"] = divide_when_positive(
        unsupported,
        applicable,
    ).where(usable)

    metrics["contradiction_rate"] = divide_when_positive(
        contradicted,
        applicable,
    ).where(usable)

    resolved_error_count = unsupported + contradicted
    metrics["resolved_error_rate"] = divide_when_positive(
        resolved_error_count,
        resolved,
    ).where(usable)

    metrics["is_strict_all_supported"] = (
        usable
        & (applicable > 0)
        & (supported == applicable)
    )

    metrics["has_faithfulness_error"] = (
        usable
        & ((unsupported + contradicted) > 0)
    )

    return metrics
