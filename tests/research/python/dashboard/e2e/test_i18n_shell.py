"""Live-browser checks for Vietnamese-first shell and persisted locale state."""

from __future__ import annotations

import os

import pytest


BASE_URL = os.getenv("DASH_E2E_BASE_URL")
pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="Start the dashboard and set DASH_E2E_BASE_URL.",
)


def test_shell_defaults_to_vietnamese_and_persists_user_choice(page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.evaluate("window.localStorage.clear()")
    page.reload(wait_until="networkidle")

    page.locator("#app-locale-vi").wait_for()
    assert page.locator("html").get_attribute("lang") == "vi"
    page.get_by_text("Bảng điều khiển nghiên cứu LLM-XAI", exact=True).wait_for()
    assert page.locator("#app-locale-vi").get_attribute("aria-pressed") == "true"

    page.locator("#app-locale-en").click()
    page.get_by_text("LLM-XAI Research Dashboard", exact=True).wait_for()
    assert page.locator("html").get_attribute("lang") == "en"
    assert page.locator("#app-locale-en").get_attribute("aria-pressed") == "true"

    page.reload(wait_until="networkidle")
    page.get_by_text("LLM-XAI Research Dashboard", exact=True).wait_for()
    assert page.locator("html").get_attribute("lang") == "en"

    page.locator("#app-locale-vi").click()
    page.get_by_text("Bảng điều khiển nghiên cứu LLM-XAI", exact=True).wait_for()
    assert page.locator("html").get_attribute("lang") == "vi"


def test_shell_locale_switch_does_not_change_route(page) -> None:
    page.goto(f"{BASE_URL}/methods", wait_until="networkidle")
    original_path = page.evaluate("window.location.pathname")
    page.locator("#app-locale-en").click()
    page.get_by_text("LLM-XAI Research Dashboard", exact=True).wait_for()
    assert page.evaluate("window.location.pathname") == original_path
    page.locator("#app-locale-vi").click()
    page.get_by_text("Bảng điều khiển nghiên cứu LLM-XAI", exact=True).wait_for()
    assert page.evaluate("window.location.pathname") == original_path
