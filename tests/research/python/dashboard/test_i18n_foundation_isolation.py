"""Staged-rollout guard after global locale state wiring."""

from __future__ import annotations

from pathlib import Path


DASHBOARD_ROOT = Path("research/python/dashboard")


def test_locale_state_is_wired_only_into_global_runtime_modules() -> None:
    expected = {
        DASHBOARD_ROOT / "app.py",
        DASHBOARD_ROOT / "ids.py",
        DASHBOARD_ROOT / "components" / "app_shell.py",
        DASHBOARD_ROOT / "callbacks" / "global_state.py",
        DASHBOARD_ROOT / "assets" / "clientside.js",
    }
    for path in expected:
        assert path.is_file()

    page_sources = [
        path.read_text(encoding="utf-8")
        for path in (DASHBOARD_ROOT / "pages").glob("*.py")
    ]
    assert all("APP_LOCALE_STORE_ID" not in source for source in page_sources)


def test_patch_0031_does_not_introduce_dom_text_replacement() -> None:
    source = (DASHBOARD_ROOT / "assets" / "clientside.js").read_text(
        encoding="utf-8"
    )
    for prohibited in ["MutationObserver", "textContent", "innerHTML", "replaceAll"]:
        assert prohibited not in source
