"""Strict translator behavior tests."""

from __future__ import annotations

import pytest

from research.python.dashboard.i18n import (
    MissingTranslationError,
    TranslationInterpolationError,
    catalog,
    t,
)


def test_translator_reads_both_locales() -> None:
    assert t("vi", "common.export") == "Xuất"
    assert t("en", "common.export") == "Export"


def test_translator_interpolates_named_parameters() -> None:
    assert (
        t("vi", "common.validation_check_count", passed=54, total=54)
        == "54/54 kiểm tra xác thực đã đạt"
    )
    assert (
        t("en", "common.validation_check_count", passed=54, total=54)
        == "54/54 validation checks passed"
    )


def test_missing_translation_never_falls_back_to_english() -> None:
    with pytest.raises(MissingTranslationError):
        t("vi", "does.not.exist")


def test_missing_interpolation_parameter_fails_closed() -> None:
    with pytest.raises(TranslationInterpolationError, match="missing"):
        t("vi", "common.dataset_count")


def test_unexpected_interpolation_parameter_fails_closed() -> None:
    with pytest.raises(TranslationInterpolationError, match="unexpected"):
        t("en", "common.export", count=1)


def test_catalog_returns_a_defensive_copy() -> None:
    first = catalog("vi")
    first["common.export"] = "MUTATED"
    assert catalog("vi")["common.export"] == "Xuất"
