"""Build the materialized generation metric fact table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    GENERATION_METRICS_PATH,
    METRIC_DICTIONARY_PATH,
    METRIC_ENGINEERING_VERSION,
    OUTPUT_COLUMNS,
)
from .efficiency import add_efficiency_metrics
from .metric_dictionary import build_metric_dictionary
from .quality import add_quality_metrics
from .reliability import add_reliability_metrics


def build_generation_metrics(
    generations: pd.DataFrame,
) -> pd.DataFrame:
    """Build one metric row for every planned generation slot."""

    metric_frame = generations.copy()
    metric_frame = add_quality_metrics(metric_frame)
    metric_frame = add_reliability_metrics(metric_frame)
    metric_frame = add_efficiency_metrics(metric_frame)

    metric_frame.insert(
        0,
        "metric_engineering_version",
        METRIC_ENGINEERING_VERSION,
    )

    metric_frame = metric_frame.sort_values(
        [
            "model_order",
            "evidence_order",
            "case_order",
            "generation_id",
        ]
    ).reset_index(drop=True)

    return metric_frame[OUTPUT_COLUMNS].copy()


def build_metric_outputs(
    input_data: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    """Build the two CSV outputs for the analytical relational mart."""

    return {
        "generation_metrics": build_generation_metrics(
            input_data["generations"]
        ),
        "metric_dictionary": build_metric_dictionary(),
    }


def write_metric_outputs(
    outputs: dict[str, pd.DataFrame],
    generation_metrics_path: Path = GENERATION_METRICS_PATH,
    metric_dictionary_path: Path = METRIC_DICTIONARY_PATH,
) -> None:
    """Write deterministic CSV outputs.

    Default paths preserve the historical Home Credit release layout.
    """

    generation_metrics_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    metric_dictionary_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    outputs["generation_metrics"].to_csv(
        generation_metrics_path,
        index=False,
    )
    outputs["metric_dictionary"].to_csv(
        metric_dictionary_path,
        index=False,
    )


def output_paths() -> list[Path]:
    """Return the materialized CSV paths for tests and terminal reporting."""

    return [
        GENERATION_METRICS_PATH,
        METRIC_DICTIONARY_PATH,
    ]
