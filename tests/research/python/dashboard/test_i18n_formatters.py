"""Deterministic EN/VI number-formatting tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from research.python.dashboard.i18n import (
    format_integer,
    format_missing,
    format_not_applicable,
    format_number,
    format_p_value,
    format_percent,
    format_percentage_points,
)


def test_integer_grouping_is_locale_specific() -> None:
    assert format_integer("vi", 14667) == "14.667"
    assert format_integer("en", 14667) == "14,667"


def test_decimal_separator_and_rounding_are_locale_specific() -> None:
    assert format_number("vi", Decimal("98.315"), decimals=2) == "98,32"
    assert format_number("en", Decimal("98.315"), decimals=2) == "98.32"


def test_percent_formatter_accepts_ratio_input() -> None:
    assert format_percent("vi", 0.9831) == "98,31%"
    assert format_percent("en", 0.9831) == "98.31%"


def test_percentage_point_suffix_is_localized() -> None:
    assert format_percentage_points("vi", 0.0125) == "1,25 điểm %"
    assert format_percentage_points("en", 0.0125) == "1.25 pp"


def test_p_value_formatter_is_locale_specific() -> None:
    assert format_p_value("vi", 0.0002) == "p < 0,001"
    assert format_p_value("en", 0.0002) == "p < 0.001"
    assert format_p_value("vi", 0.042) == "p = 0,042"


def test_missing_and_not_applicable_are_translated() -> None:
    assert format_missing("vi") == "Thiếu"
    assert format_missing("en") == "Missing"
    assert format_not_applicable("vi") == "Không áp dụng"
    assert format_not_applicable("en") == "N/A"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_values_fail_closed(value: float) -> None:
    with pytest.raises(ValueError):
        format_number("vi", value)


def test_integer_formatter_rejects_fractional_values() -> None:
    with pytest.raises(ValueError):
        format_integer("en", 1.5)
