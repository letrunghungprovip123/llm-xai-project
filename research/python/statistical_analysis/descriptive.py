"""Build tidy descriptive statistics from the analysis frame."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from .config import DESCRIPTIVE_METRICS, GROUP_TYPES


GROUP_COLUMNS = {
    "overall": [],
    "model": ["model_id"],
    "evidence": ["evidence_level"],
    "model_evidence": ["model_id", "evidence_level"],
    "stratum": ["selection_stratum"],
}


def analysis_population_for_metric(metric_id: str) -> str:
    """Name the denominator population used by one descriptive metric."""

    if metric_id in {
        "resolved_faithfulness",
        "verifiability",
        "conservative_faithfulness",
    }:
        return "METRIC_AVAILABLE"

    return "PLANNED_648"


def summarize_values(values: pd.Series) -> dict[str, float | int]:
    """Summarize one numeric series while preserving missingness."""

    numeric_values = pd.to_numeric(
        values,
        errors="coerce",
    ).astype("float64")
    observed = numeric_values.dropna()
    planned_count = int(len(numeric_values))
    observed_count = int(len(observed))

    summary: dict[str, float | int] = {
        "planned_count": planned_count,
        "observed_count": observed_count,
        "missing_count": planned_count - observed_count,
        "mean": np.nan,
        "standard_deviation": np.nan,
        "median": np.nan,
        "q1": np.nan,
        "q3": np.nan,
        "minimum": np.nan,
        "maximum": np.nan,
    }

    if observed_count == 0:
        return summary

    summary["mean"] = float(observed.mean())
    summary["median"] = float(observed.median())
    summary["q1"] = float(observed.quantile(0.25))
    summary["q3"] = float(observed.quantile(0.75))
    summary["minimum"] = float(observed.min())
    summary["maximum"] = float(observed.max())

    if observed_count > 1:
        summary["standard_deviation"] = float(
            observed.std(ddof=1)
        )

    return summary


def group_iterator(
    frame: pd.DataFrame,
    group_columns: list[str],
) -> Iterable[tuple[tuple[object, ...], pd.DataFrame]]:
    """Yield a consistent tuple key for grouped and ungrouped data."""

    if not group_columns:
        yield tuple(), frame
        return

    grouped = frame.groupby(
        group_columns,
        sort=False,
        dropna=False,
    )

    for key, group in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        yield key, group


def build_descriptive_statistics(
    analysis_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Create one row per metric and descriptive group."""

    rows: list[dict[str, object]] = []

    for metric_order, metric_id in enumerate(DESCRIPTIVE_METRICS):
        for group_order, group_type in enumerate(GROUP_TYPES):
            group_columns = GROUP_COLUMNS[group_type]

            for key, group in group_iterator(
                analysis_frame,
                group_columns,
            ):
                group_values = dict(zip(group_columns, key))
                summary = summarize_values(group[metric_id])

                rows.append(
                    {
                        "metric_order": metric_order,
                        "group_order": group_order,
                        "analysis_population": (
                            analysis_population_for_metric(metric_id)
                        ),
                        "metric_id": metric_id,
                        "group_type": group_type,
                        "model_id": group_values.get("model_id"),
                        "evidence_level": group_values.get(
                            "evidence_level"
                        ),
                        "selection_stratum": group_values.get(
                            "selection_stratum"
                        ),
                        **summary,
                    }
                )

    output = pd.DataFrame(rows)
    output = output.sort_values(
        [
            "metric_order",
            "group_order",
            "model_id",
            "evidence_level",
            "selection_stratum",
        ],
        kind="stable",
        na_position="first",
    ).reset_index(drop=True)

    return output.drop(
        columns=["metric_order", "group_order"]
    )
