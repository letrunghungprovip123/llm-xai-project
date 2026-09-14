"""Small deterministic file loaders for dashboard presentation data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


class DashboardDataError(RuntimeError):
    """Raised when a certified dashboard input is missing or malformed."""


def read_json_object(path: Path) -> dict[str, Any]:
    """Read one JSON object and reject missing or non-object content."""

    if not path.is_file():
        raise DashboardDataError(f"Missing JSON input: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DashboardDataError(f"Invalid JSON input: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DashboardDataError(f"Expected JSON object: {path}")
    return value


def read_csv_frame(path: Path) -> pd.DataFrame:
    """Read one CSV into a fresh DataFrame."""

    if not path.is_file():
        raise DashboardDataError(f"Missing CSV input: {path}")
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception as exc:  # pandas exposes several parser exception types.
        raise DashboardDataError(f"Could not read CSV input: {path}: {exc}") from exc


def require_columns(
    frame: pd.DataFrame,
    required: set[str],
    *,
    dataset_name: str,
) -> None:
    """Fail with a readable contract error when columns are missing."""

    missing = sorted(required - set(frame.columns))
    if missing:
        raise DashboardDataError(
            f"{dataset_name} is missing required columns: {missing}"
        )
