"""Locale contract for the certified dashboard.

Vietnamese is intentionally the first-visit default. A later UI patch will
persist the explicit user choice in browser local storage; this module only
owns validation and normalization of locale codes.
"""

from __future__ import annotations

from .types import LocaleCode


SUPPORTED_LOCALES: tuple[LocaleCode, ...] = ("vi", "en")
DEFAULT_LOCALE: LocaleCode = "vi"


class UnsupportedLocaleError(ValueError):
    """Raised when strict locale validation receives an unsupported value."""


def is_supported_locale(value: object) -> bool:
    """Return whether *value* is one of the frozen dashboard locale codes."""

    return isinstance(value, str) and value.strip().lower() in SUPPORTED_LOCALES


def normalize_locale(
    value: object,
    *,
    strict: bool = False,
    default: LocaleCode = DEFAULT_LOCALE,
) -> LocaleCode:
    """Normalize a locale value without consulting process or browser locale.

    The application contract deliberately does not infer the first-visit
    locale from the operating system. Missing or invalid persisted values use
    Vietnamese unless ``strict=True`` is requested by validation code.
    """

    if isinstance(value, str):
        normalized = value.strip().lower().replace("_", "-")
        base = normalized.split("-", 1)[0]
        if base in SUPPORTED_LOCALES:
            return base  # type: ignore[return-value]

    if strict:
        raise UnsupportedLocaleError(
            f"Unsupported locale {value!r}; expected one of {SUPPORTED_LOCALES}."
        )
    return default


__all__ = [
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "UnsupportedLocaleError",
    "is_supported_locale",
    "normalize_locale",
]
