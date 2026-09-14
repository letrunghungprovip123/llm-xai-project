"""Final runtime certification for complete EN/VI presentation coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dash import html

from research.python.dashboard.i18n import (
    DEFAULT_LOCALE,
    certify_dashboard_locales,
    localize_component_tree,
    visible_strings,
)
from research.python.dashboard.i18n.certify import write_certification
from research.python.dashboard.pages.methods import layout as methods_layout


@pytest.fixture(scope="module")
def certification():
    return certify_dashboard_locales()


def test_vietnamese_is_the_certified_first_visit_default() -> None:
    assert DEFAULT_LOCALE == "vi"


def test_all_pages_and_exports_pass_bilingual_runtime_certification(certification) -> None:
    assert certification.passed
    assert len(certification.pages) == 14
    assert len(certification.exports) == 14
    assert {item.page_id for item in certification.pages} == {
        "overview",
        "effectiveness",
        "mechanisms",
        "decision",
        "robustness",
        "cases",
        "methods",
    }
    assert all(item.title_present for item in certification.pages)
    assert all(not item.opposite_locale_leaks for item in certification.pages)
    assert all(not item.heuristic_language_leaks for item in certification.pages)
    assert all(item.passed for item in certification.exports)


def test_component_localizer_preserves_embedded_release_identifiers() -> None:
    source = html.Div("Visualization release: visualization-data-v2")
    localized = localize_component_tree(source, "vi", prefixes=("methods.", "shared.", "common."))
    strings = visible_strings(localized)
    assert any("Bản phát hành trực quan hóa" in item for item in strings)
    assert any("visualization-data-v2" in item for item in strings)
    assert all("visualization-dữ liệu-v2" not in item for item in strings)


def test_methods_uses_vietnamese_number_formatting_and_stable_release_ids() -> None:
    strings = visible_strings(methods_layout(locale="vi"))
    assert "14.667" in strings
    assert "14.655" in strings
    assert "13.637" in strings
    assert "visualization-data-v2" in strings
    assert all("visualization-dữ liệu-v2" not in item for item in strings)


def test_certification_cli_writes_machine_readable_artifacts(tmp_path: Path, certification) -> None:
    payload = write_certification(tmp_path)
    assert payload["passed"] is True
    required = {
        "i18n_catalog_parity.json",
        "i18n_page_coverage.json",
        "i18n_export_coverage.json",
        "i18n_untranslated_strings.csv",
        "i18n_certification_summary.json",
    }
    assert required <= {path.name for path in tmp_path.iterdir()}
    summary = json.loads((tmp_path / "i18n_certification_summary.json").read_text())
    assert summary["passed"] is True
    untranslated = (tmp_path / "i18n_untranslated_strings.csv").read_text()
    assert untranslated.splitlines() == [
        "page_id,route,locale,leak_type,text"
    ]
