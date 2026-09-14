"""Load the audited relational data mart for metric calculation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    BASE_EXIT_GATE,
    CLAIMS_PATH,
    DATA_MART_VALIDATION_PATH,
    GENERATIONS_PATH,
    REQUIRED_CLAIM_COLUMNS,
    REQUIRED_GENERATION_COLUMNS,
)


LoadedInputs = dict[str, Any]


def check_input_file(file_path: Path) -> None:
    """Fail with a clear path when a required input is unavailable."""

    if not file_path.exists():
        raise FileNotFoundError(
            f"Required metric input does not exist: {file_path}"
        )

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Required metric input is not a file: {file_path}"
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
    """Read one CSV without changing source values."""

    check_input_file(file_path)
    return pd.read_csv(file_path, low_memory=False)


def require_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    table_name: str,
) -> None:
    """Require the exact source fields used by metric formulas."""

    missing_columns = sorted(
        required_columns - set(dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            f"{table_name} is missing required columns: "
            f"{missing_columns}"
        )


def require_ready_data_mart(
    validation_report: dict[str, Any],
) -> None:
    """Stop before calculating metrics from an invalid base mart."""

    passed = validation_report.get("passed") is True
    failed_checks = validation_report.get("failed_check_count")
    exit_gate = validation_report.get("exit_gate")

    if not passed or failed_checks != 0 or exit_gate != BASE_EXIT_GATE:
        raise ValueError(
            "Metric engineering requires a passed DATA_MART_READY gate. "
            f"Observed passed={passed}, "
            f"failed_check_count={failed_checks}, "
            f"exit_gate={exit_gate}."
        )


def load_metric_inputs(
    input_paths: dict[str, Path] | None = None,
) -> LoadedInputs:
    """Load and minimally validate the two analytical fact tables.

    ``input_paths=None`` preserves the historical Home Credit paths.
    """

    paths = (
        {
            "data_mart_validation": DATA_MART_VALIDATION_PATH,
            "generations": GENERATIONS_PATH,
            "claims": CLAIMS_PATH,
        }
        if input_paths is None
        else input_paths
    )

    data_mart_validation = read_json_file(
        paths["data_mart_validation"]
    )
    require_ready_data_mart(data_mart_validation)

    generations = read_csv_file(paths["generations"])
    claims = read_csv_file(paths["claims"])

    require_columns(
        generations,
        REQUIRED_GENERATION_COLUMNS,
        "generations.csv",
    )
    require_columns(
        claims,
        REQUIRED_CLAIM_COLUMNS,
        "claims.csv",
    )

    return {
        "data_mart_validation": data_mart_validation,
        "generations": generations,
        "claims": claims,
    }
