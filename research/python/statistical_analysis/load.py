"""Load the approved analytical mart for statistical analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    CASES_PATH,
    EVIDENCE_LEVELS_PATH,
    GENERATION_METRICS_PATH,
    INPUT_EXIT_GATE,
    METRIC_VALIDATION_PATH,
    MODELS_PATH,
    REQUIRED_CASE_COLUMNS,
    REQUIRED_EVIDENCE_COLUMNS,
    REQUIRED_METRIC_COLUMNS,
    REQUIRED_MODEL_COLUMNS,
)


LoadedInputs = dict[str, Any]


def check_input_file(file_path: Path) -> None:
    """Require one readable file and report its full path on failure."""

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Required statistical input does not exist: {file_path}"
        )


def read_json_file(file_path: Path) -> dict[str, Any]:
    """Read one JSON object from disk."""

    check_input_file(file_path)

    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON in {file_path}: {error}"
        ) from error

    if not isinstance(value, dict):
        raise ValueError(
            f"Expected one JSON object in {file_path}."
        )

    return value


def read_csv_file(file_path: Path) -> pd.DataFrame:
    """Read one CSV without silently changing source values."""

    check_input_file(file_path)
    return pd.read_csv(file_path, low_memory=False)


def require_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    table_name: str,
) -> None:
    """Require only the columns used by this analysis batch."""

    missing_columns = sorted(
        required_columns - set(dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            f"{table_name} is missing required columns: "
            f"{missing_columns}"
        )


def require_ready_analytical_mart(
    validation_report: dict[str, Any],
) -> None:
    """Stop before inference when Metric Engineering did not pass."""

    passed = validation_report.get("passed") is True
    failed_checks = validation_report.get("failed_check_count")
    exit_gate = validation_report.get("exit_gate")

    if (
        not passed
        or failed_checks != 0
        or exit_gate != INPUT_EXIT_GATE
    ):
        raise ValueError(
            "Statistical analysis requires an approved "
            "ANALYTICAL_MART_READY gate. "
            f"Observed passed={passed}, "
            f"failed_check_count={failed_checks}, "
            f"exit_gate={exit_gate}."
        )


def load_statistical_inputs(
    input_paths: dict[str, Path] | None = None,
) -> LoadedInputs:
    """Load the metric fact and the three small dimension tables.

    ``input_paths=None`` preserves the historical Home Credit paths.
    """

    paths = (
        {
            "metric_validation": METRIC_VALIDATION_PATH,
            "generation_metrics": GENERATION_METRICS_PATH,
            "cases": CASES_PATH,
            "models": MODELS_PATH,
            "evidence_levels": EVIDENCE_LEVELS_PATH,
        }
        if input_paths is None
        else input_paths
    )

    metric_validation = read_json_file(
        paths["metric_validation"]
    )
    require_ready_analytical_mart(metric_validation)

    generation_metrics = read_csv_file(
        paths["generation_metrics"]
    )
    cases = read_csv_file(paths["cases"])
    models = read_csv_file(paths["models"])
    evidence_levels = read_csv_file(paths["evidence_levels"])

    require_columns(
        generation_metrics,
        REQUIRED_METRIC_COLUMNS,
        "generation_metrics.csv",
    )
    require_columns(
        cases,
        REQUIRED_CASE_COLUMNS,
        "cases.csv",
    )
    require_columns(
        models,
        REQUIRED_MODEL_COLUMNS,
        "models.csv",
    )
    require_columns(
        evidence_levels,
        REQUIRED_EVIDENCE_COLUMNS,
        "evidence_levels.csv",
    )

    return {
        "metric_validation": metric_validation,
        "generation_metrics": generation_metrics,
        "cases": cases,
        "models": models,
        "evidence_levels": evidence_levels,
    }
