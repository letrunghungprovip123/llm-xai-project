"""Shared helpers for structured diagnostic validation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


ValidationChecks = dict[str, dict[str, Any]]


def python_value(value: Any) -> Any:
    """Convert pandas and NumPy values into JSON-safe values."""

    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass

    if isinstance(value, dict):
        return {
            str(key): python_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [python_value(item) for item in value]

    return value


def add_check(
    checks: ValidationChecks,
    name: str,
    expected: Any,
    observed: Any,
    passed: bool,
    details: str | None = None,
) -> None:
    """Add one structured validation check."""

    check = {
        "expected": python_value(expected),
        "observed": python_value(observed),
        "passed": bool(passed),
    }
    if details:
        check["details"] = details
    checks[name] = check


def numeric_rate_out_of_bounds_count(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> int:
    """Count non-null rates outside zero to one."""

    count = 0
    for column in columns:
        values = pd.to_numeric(dataframe[column], errors="coerce")
        invalid = values.notna() & ((values < 0) | (values > 1))
        count += int(invalid.sum())
    return count


def infinity_count(dataframes: list[pd.DataFrame]) -> int:
    """Count positive and negative infinity across numeric outputs."""

    count = 0
    for dataframe in dataframes:
        numeric = dataframe.select_dtypes(include=[np.number])
        count += int(np.isinf(numeric.to_numpy()).sum())
    return count


def dataframe_value_mismatch_count(
    expected: pd.DataFrame,
    observed: pd.DataFrame,
    key_columns: list[str],
    value_columns: list[str],
    *,
    tolerance: float = 1e-12,
) -> tuple[int, int, int]:
    """Compare keyed frames and count missing, extra and changed rows."""

    joined = expected[key_columns + value_columns].merge(
        observed[key_columns + value_columns],
        on=key_columns,
        how="outer",
        validate="one_to_one",
        suffixes=("_expected", "_observed"),
        indicator=True,
    )

    missing_count = int((joined["_merge"] == "left_only").sum())
    extra_count = int((joined["_merge"] == "right_only").sum())
    both = joined.loc[joined["_merge"] == "both"]

    changed_rows = pd.Series(False, index=both.index)
    for column in value_columns:
        expected_values = both[f"{column}_expected"]
        observed_values = both[f"{column}_observed"]

        if pd.api.types.is_numeric_dtype(expected_values) or (
            pd.api.types.is_numeric_dtype(observed_values)
        ):
            matches = np.isclose(
                pd.to_numeric(expected_values, errors="coerce"),
                pd.to_numeric(observed_values, errors="coerce"),
                rtol=0.0,
                atol=tolerance,
                equal_nan=True,
            )
        else:
            expected_text = expected_values.fillna("<NULL>").astype(str)
            observed_text = observed_values.fillna("<NULL>").astype(str)
            matches = expected_text == observed_text

        changed_rows = changed_rows | ~matches

    return missing_count, extra_count, int(changed_rows.sum())
