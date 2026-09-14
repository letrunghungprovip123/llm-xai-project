"""Architecture checks for Patch 0032 explicit AppShell localization."""

from __future__ import annotations

from pathlib import Path

from research.python.dashboard.callbacks.global_state import (
    _has_user_click,
    _methods_drawer_state,
)
from research.python.dashboard.components.navigation import dashboard_navigation
from research.python.dashboard.i18n import document_metadata, t, validate_catalogs
from research.python.dashboard.ids import (
    APP_LOCALE_EN_ID,
    APP_METHODS_DRAWER_CLOSE_ID,
    APP_METHODS_DRAWER_OPEN_ID,
)
from research.python.dashboard.navigation import NAVIGATION_ITEMS

ROOT = Path(__file__).resolve().parents[4]
SHELL = ROOT / "research/python/dashboard/components/app_shell.py"
CALLBACKS = ROOT / "research/python/dashboard/callbacks/global_state.py"
CLIENT = ROOT / "research/python/dashboard/assets/clientside.js"


def test_catalogs_remain_strict_and_shell_keys_have_both_locales() -> None:
    report = validate_catalogs()
    assert report.passed is True
    for key in [
        "app.title",
        "app.subtitle",
        "app.methodology_title",
        "app.blocked_title",
    ]:
        assert t("vi", key)
        assert t("en", key)
    assert t("vi", "app.release_certified", release_id="visualization-data-v2")
    assert t("en", "app.release_certified", release_id="visualization-data-v2")


def test_navigation_is_locale_neutral_and_complete() -> None:
    assert [item.key for item in NAVIGATION_ITEMS] == [
        "overview",
        "effectiveness",
        "mechanisms",
        "decision",
        "robustness",
        "cases",
        "methods",
    ]
    assert all(item.label_key.startswith("domain.page.") for item in NAVIGATION_ITEMS)
    assert all(
        item.description_key.startswith("navigation.page_description.")
        for item in NAVIGATION_ITEMS
    )


def test_navigation_constructs_with_dash_mantine_2_8_supported_props() -> None:
    """Build every localized NavLink so unsupported component props fail in tests."""

    for locale in ("vi", "en"):
        navigation = dashboard_navigation(locale)
        links = list(navigation.children)
        assert len(links) == len(NAVIGATION_ITEMS)

        for link, item in zip(links, NAVIGATION_ITEMS, strict=True):
            props = link.to_plotly_json()["props"]
            assert props["label"] == t(locale, item.label_key)
            assert props["aria-label"] == t(locale, item.description_key)
            assert props["href"] == item.path
            assert "title" not in props


def test_document_metadata_is_route_and_locale_aware() -> None:
    assert document_metadata("vi", "/methods").title == (
        "Khả năng tái lập & Phương pháp · LLM-XAI"
    )
    assert document_metadata("en", "/effectiveness/").title == (
        "Effectiveness & Reliability · LLM-XAI"
    )
    assert document_metadata("invalid", "/unknown").lang == "vi"


def test_shell_is_rendered_from_semantic_keys_not_dom_replacement() -> None:
    source = SHELL.read_text(encoding="utf-8")
    for key in [
        "app.title",
        "app.subtitle",
        "app.methodology_primary_contract",
        "app.methodology_boundary_detail",
    ]:
        assert key in source
    client = CLIENT.read_text(encoding="utf-8")
    assert "applyDocumentMetadata" in client
    assert "document.title" in client
    assert "MutationObserver" not in client
    assert "translateText" not in client


def test_shell_callback_owns_only_shell_presentation_outputs() -> None:
    source = CALLBACKS.read_text(encoding="utf-8")
    for output_id in [
        "APP_HEADER_CONTENT_ID",
        "APP_NAVIGATION_CONTENT_ID",
        "APP_RELEASE_STRIP_ID",
        "APP_METHODS_DRAWER_CONTENT_ID",
        "APP_DOCUMENT_METADATA_ID",
    ]:
        assert output_id in source
    for analytical_id in [
        "CASES_SELECTED_CASE_ID",
        "DECISION_SCENARIO_ID",
        "ROBUSTNESS_TEMPLATE_METRIC_ID",
    ]:
        assert analytical_id not in source


def test_dynamic_shell_controls_ignore_component_insertion_events() -> None:
    assert _has_user_click(APP_LOCALE_EN_ID, APP_LOCALE_EN_ID, None) is False
    assert _has_user_click(APP_LOCALE_EN_ID, APP_LOCALE_EN_ID, 0) is False
    assert _has_user_click(APP_LOCALE_EN_ID, APP_LOCALE_EN_ID, 1) is True
    assert _has_user_click("another-control", APP_LOCALE_EN_ID, 1) is False

    assert _methods_drawer_state(
        APP_METHODS_DRAWER_OPEN_ID, None, None, False
    ) is False
    assert _methods_drawer_state(
        APP_METHODS_DRAWER_CLOSE_ID, None, None, True
    ) is True
    assert _methods_drawer_state(
        APP_METHODS_DRAWER_OPEN_ID, 1, None, False
    ) is True
    assert _methods_drawer_state(
        APP_METHODS_DRAWER_CLOSE_ID, 1, 1, True
    ) is False
