"""Pure and static checks for Patch 0031 global locale state."""

from __future__ import annotations

from pathlib import Path

from research.python.dashboard.i18n import DEFAULT_LOCALE
from research.python.dashboard.i18n.locale_state import (
    locale_control_state,
    locale_document_language,
    locale_from_trigger,
)
from research.python.dashboard.ids import APP_LOCALE_EN_ID, APP_LOCALE_VI_ID

ROOT = Path(__file__).resolve().parents[4]
SHELL = ROOT / "research/python/dashboard/components/app_shell.py"
CLIENT = ROOT / "research/python/dashboard/assets/clientside.js"
APP = ROOT / "research/python/dashboard/app.py"


def test_first_visit_contract_is_vietnamese() -> None:
    assert DEFAULT_LOCALE == "vi"
    assert locale_document_language(None) == "vi"


def test_language_buttons_use_stable_ids_and_never_display_labels() -> None:
    assert locale_from_trigger(
        APP_LOCALE_VI_ID,
        "en",
        vietnamese_control_id=APP_LOCALE_VI_ID,
        english_control_id=APP_LOCALE_EN_ID,
    ) == "vi"
    assert locale_from_trigger(
        APP_LOCALE_EN_ID,
        "vi",
        vietnamese_control_id=APP_LOCALE_VI_ID,
        english_control_id=APP_LOCALE_EN_ID,
    ) == "en"
    assert locale_from_trigger(
        None,
        "invalid",
        vietnamese_control_id=APP_LOCALE_VI_ID,
        english_control_id=APP_LOCALE_EN_ID,
    ) == "vi"


def test_control_state_is_accessible_and_deterministic() -> None:
    active = locale_control_state("vi", "vi")
    inactive = locale_control_state("vi", "en")
    assert active.active is True
    assert active.aria_pressed == "true"
    assert active.class_name.endswith("--active")
    assert inactive.active is False
    assert inactive.aria_pressed == "false"


def test_shell_uses_browser_local_storage_without_analytical_state_outputs() -> None:
    source = SHELL.read_text(encoding="utf-8")
    assert "APP_LOCALE_STORE_ID" in source
    assert 'storage_type="local"' in source
    assert "data=DEFAULT_LOCALE" in source
    assert '"data-locale-target": "vi"' in source
    assert '"data-locale-target": "en"' in source
    assert "selected_model" not in source
    assert "selected_case" not in source


def test_clientside_adapter_only_updates_language_metadata_and_controls() -> None:
    source = CLIENT.read_text(encoding="utf-8")
    assert "document.documentElement.lang" in source
    assert "data-locale-target" in source
    assert "textContent" not in source
    assert "innerHTML" not in source
    assert "MutationObserver" not in source


def test_dash_loading_title_is_language_neutral() -> None:
    assert 'update_title="…"' in APP.read_text(encoding="utf-8")
