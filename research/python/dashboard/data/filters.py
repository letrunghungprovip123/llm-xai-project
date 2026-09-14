"""Shared descriptive filtering helpers for later dashboard pages."""

from __future__ import annotations

import pandas as pd


def filter_frame(
    frame: pd.DataFrame,
    **equals: str | int | float | None,
) -> pd.DataFrame:
    """Return a defensive filtered copy without mutating cached data."""

    result = frame.copy(deep=True)
    for column, value in equals.items():
        if value is None:
            continue
        if column not in result.columns:
            raise KeyError(f"Unknown filter column: {column}")
        result = result.loc[result[column] == value]
    return result.reset_index(drop=True)
