"""Locale contract tests for the dashboard i18n foundation."""

from __future__ import annotations

import pytest

from research.python.dashboard.i18n import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    UnsupportedLocaleError,
    is_supported_locale,
    normalize_locale,
)


def test_vietnamese_is_the_first_visit_default() -> None:
    assert DEFAULT_LOCALE == "vi"
    assert SUPPORTED_LOCALES == ("vi", "en")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("vi", "vi"),
        ("VI", "vi"),
        ("vi-VN", "vi"),
        ("vi_VN", "vi"),
        ("en", "en"),
        ("EN-us", "en"),
        (" en_GB ", "en"),
        (None, "vi"),
        ("", "vi"),
        ("fr", "vi"),
    ],
)
def test_normalize_locale_uses_stable_codes(value: object, expected: str) -> None:
    assert normalize_locale(value) == expected


def test_strict_locale_validation_rejects_unknown_values() -> None:
    with pytest.raises(UnsupportedLocaleError):
        normalize_locale("fr", strict=True)


def test_supported_locale_detection_is_explicit() -> None:
    assert is_supported_locale("vi")
    assert is_supported_locale("EN")
    assert not is_supported_locale("en-US")
    assert not is_supported_locale(None)
