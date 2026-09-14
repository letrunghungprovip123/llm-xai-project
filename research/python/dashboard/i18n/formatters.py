"""Deterministic locale-aware display formatting without global locale state."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .locale import normalize_locale
from .translator import t
from .types import LocaleCode


_GROUP_SEPARATOR: dict[LocaleCode, str] = {"vi": ".", "en": ","}
_DECIMAL_SEPARATOR: dict[LocaleCode, str] = {"vi": ",", "en": "."}


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise TypeError("Boolean values are not valid dashboard numbers.")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite numeric values cannot be formatted.")
        number = Decimal(str(value))
    else:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as error:
            raise TypeError(f"Unsupported numeric value: {value!r}.") from error
    if not number.is_finite():
        raise ValueError("Non-finite numeric values cannot be formatted.")
    return number


def _group_integer(digits: str, separator: str) -> str:
    sign = ""
    if digits.startswith("-"):
        sign, digits = "-", digits[1:]
    groups: list[str] = []
    while digits:
        groups.append(digits[-3:])
        digits = digits[:-3]
    return sign + separator.join(reversed(groups or ["0"]))


def format_number(
    locale: LocaleCode | str,
    value: object,
    *,
    decimals: int = 2,
    trim_trailing_zeros: bool = True,
    use_grouping: bool = True,
) -> str:
    """Format a finite decimal using dashboard-specific EN/VI separators."""

    if decimals < 0:
        raise ValueError("decimals must be non-negative.")
    normalized = normalize_locale(locale, strict=True)
    number = _decimal(value)
    quantum = Decimal(1).scaleb(-decimals)
    rounded = number.quantize(quantum, rounding=ROUND_HALF_UP)
    rendered = f"{rounded:.{decimals}f}"
    integer_part, _, fraction = rendered.partition(".")
    if use_grouping:
        integer_part = _group_integer(integer_part, _GROUP_SEPARATOR[normalized])
    if decimals == 0:
        return integer_part
    if trim_trailing_zeros:
        fraction = fraction.rstrip("0")
    if not fraction:
        return integer_part
    return integer_part + _DECIMAL_SEPARATOR[normalized] + fraction


def format_integer(locale: LocaleCode | str, value: object) -> str:
    number = _decimal(value)
    if number != number.to_integral_value():
        raise ValueError(f"Expected an integer-compatible value, got {value!r}.")
    return format_number(locale, number, decimals=0)


def format_percent(
    locale: LocaleCode | str,
    value: object,
    *,
    decimals: int = 2,
    input_is_ratio: bool = True,
) -> str:
    number = _decimal(value)
    if input_is_ratio:
        number *= Decimal(100)
    rendered = format_number(locale, number, decimals=decimals)
    return f"{rendered}%"


def format_percentage_points(
    locale: LocaleCode | str,
    value: object,
    *,
    decimals: int = 2,
    input_is_ratio: bool = True,
) -> str:
    number = _decimal(value)
    if input_is_ratio:
        number *= Decimal(100)
    rendered = format_number(locale, number, decimals=decimals)
    return t(locale, "format.percentage_points", value=rendered)


def format_p_value(
    locale: LocaleCode | str,
    value: object,
    *,
    decimals: int = 3,
    minimum: object | None = None,
) -> str:
    number = _decimal(value)
    if number < 0 or number > 1:
        raise ValueError("p-values must be within [0, 1].")
    threshold = _decimal(minimum) if minimum is not None else Decimal(1).scaleb(-decimals)
    if number != 0 and number < threshold:
        rendered = format_number(locale, threshold, decimals=decimals, trim_trailing_zeros=False)
        return t(locale, "format.p_value_less_than", value=rendered)
    rendered = format_number(locale, number, decimals=decimals, trim_trailing_zeros=False)
    return t(locale, "format.p_value", value=rendered)


def format_missing(locale: LocaleCode | str) -> str:
    return t(locale, "common.missing")


def format_not_applicable(locale: LocaleCode | str) -> str:
    return t(locale, "common.not_applicable")


__all__ = [
    "format_integer",
    "format_missing",
    "format_not_applicable",
    "format_number",
    "format_p_value",
    "format_percent",
    "format_percentage_points",
]
