"""Catalog parity and placeholder contract tests."""

from __future__ import annotations

from research.python.dashboard.i18n import require_valid_catalogs, validate_catalogs


def test_en_vi_catalogs_have_exact_key_and_placeholder_parity() -> None:
    report = require_valid_catalogs()
    assert report.passed
    assert report.locales == ("vi", "en")
    assert report.key_count >= 100
    assert report.missing_by_locale == {"vi": [], "en": []}
    assert report.extra_by_locale == {"vi": [], "en": []}
    assert report.blank_by_locale == {"vi": [], "en": []}
    assert report.placeholder_mismatches == {}


def test_validation_report_is_json_serializable() -> None:
    report = validate_catalogs().to_dict()
    assert report["passed"] is True
    assert report["key_count"] >= 100
