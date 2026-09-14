"""Helper nhỏ dùng chung cho Decision Support validation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


ValidationChecks = dict[str, dict[str, Any]]


def python_value(value: Any) -> Any:
    """Đổi NumPy/Pandas scalar thành giá trị JSON-safe."""

    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, dict):
        return {str(key): python_value(item) for key, item in value.items()}
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
    """Ghi một release-gate check có cấu trúc."""

    value = {
        "expected": python_value(expected),
        "observed": python_value(observed),
        "passed": bool(passed),
    }
    if details:
        value["details"] = details
    checks[name] = value


def dataframe_key_set(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> set[tuple[str, ...]]:
    """So key set ổn định, kể cả khi một key value là null."""

    normalized = dataframe[columns].fillna("<NULL>").astype(str)
    return set(map(tuple, normalized.to_numpy()))


def dataframe_value_mismatch_count(
    observed: pd.DataFrame,
    expected: pd.DataFrame,
    key_columns: list[str],
    ignored_columns: set[str] | None = None,
) -> int:
    """So sánh toàn bộ shared values sau khi merge theo primary key."""

    ignored_columns = ignored_columns or set()
    shared = [
        column
        for column in expected.columns
        if column in observed.columns
        and column not in key_columns
        and column not in ignored_columns
    ]
    joined = expected[key_columns + shared].merge(
        observed[key_columns + shared],
        on=key_columns,
        how="outer",
        validate="one_to_one",
        suffixes=("_expected", "_observed"),
        indicator=True,
    )
    mismatch = joined["_merge"] != "both"

    for column in shared:
        left = joined[f"{column}_expected"]
        right = joined[f"{column}_observed"]
        left_numeric = pd.to_numeric(left, errors="coerce")
        right_numeric = pd.to_numeric(right, errors="coerce")
        both_numeric_or_null = (
            (left_numeric.notna() | left.isna())
            & (right_numeric.notna() | right.isna())
        )
        numeric_equal = np.isclose(
            left_numeric.to_numpy(dtype=float),
            right_numeric.to_numpy(dtype=float),
            rtol=0.0,
            atol=1e-12,
            equal_nan=True,
        )
        left_text = left.astype("object").where(left.notna(), "<NULL>").astype(str)
        right_text = right.astype("object").where(right.notna(), "<NULL>").astype(str)
        text_equal = left_text == right_text
        equal = np.where(both_numeric_or_null, numeric_equal, text_equal)
        mismatch = mismatch | ~equal

    return int(mismatch.sum())


def infinity_count(dataframes: list[pd.DataFrame]) -> int:
    """Đếm inf/-inf trên mọi numeric output."""

    count = 0
    for dataframe in dataframes:
        numeric = dataframe.select_dtypes(include=[np.number, "boolean"])
        for column in numeric.columns:
            values = pd.to_numeric(numeric[column], errors="coerce").astype(float)
            count += int(np.isinf(values.to_numpy()).sum())
    return count
