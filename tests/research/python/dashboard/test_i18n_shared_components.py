"""Strict checks for Patch 0033 shared component localization."""

from __future__ import annotations

from pathlib import Path

from research.python.dashboard.i18n import (
    ag_grid_locale_text,
    t,
    validate_ag_grid_locale_parity,
    validate_catalogs,
)

ROOT = Path(__file__).resolve().parents[4]
COMPONENTS = ROOT / "research/python/dashboard/components"


def test_shared_catalog_and_ag_grid_locale_parity() -> None:
    assert validate_catalogs().passed is True
    validate_ag_grid_locale_parity()
    assert set(ag_grid_locale_text("vi")) == set(ag_grid_locale_text("en"))
    assert len(ag_grid_locale_text("vi")) >= 80


def test_ag_grid_core_controls_are_fully_localized() -> None:
    vi = ag_grid_locale_text("vi")
    en = ag_grid_locale_text("en")
    expected = {
        "contains": ("Chứa", "Contains"),
        "equals": ("Bằng", "Equals"),
        "selectAll": ("Chọn tất cả", "Select all"),
        "noRowsToShow": ("Không có hàng dữ liệu", "No rows to show"),
        "next": ("Tiếp", "Next"),
        "previous": ("Trước", "Previous"),
    }
    for key, values in expected.items():
        assert (vi[key], en[key]) == values


def test_shared_translation_keys_are_strict() -> None:
    assert t("vi", "shared.source") == "Nguồn"
    assert t("en", "shared.source") == "Source"
    assert t("vi", "shared.method_note_for", label="E2E") == (
        "Ghi chú phương pháp cho E2E"
    )


def test_shared_components_use_locale_helpers_for_internal_copy() -> None:
    expectations = {
        "chart_card.py": "shared.stable_export_identifier",
        "source_footer.py": "shared.denominator",
        "page_header.py": "shared.primary_endpoint",
        "loading_state.py": "shared.loading_certified_data",
        "metric_card.py": "shared.method_note_for",
        "data_grid.py": "ag_grid_locale_text",
    }
    for filename, token in expectations.items():
        source = (COMPONENTS / filename).read_text(encoding="utf-8")
        assert token in source


def test_migrated_shared_components_have_no_string_translation_bridge() -> None:
    migrated = [
        "chart_card.py",
        "data_grid.py",
        "loading_state.py",
        "metric_card.py",
        "page_header.py",
        "source_footer.py",
    ]
    source = "\n".join(
        (COMPONENTS / filename).read_text(encoding="utf-8")
        for filename in migrated
    )
    assert "translateText" not in source
    assert ' .replace("_", " ")'.strip() not in source
