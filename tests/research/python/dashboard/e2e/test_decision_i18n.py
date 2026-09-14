"""Optional Playwright locale and state coverage for Decision Studio."""

from __future__ import annotations

import os

import pytest


BASE_URL = os.getenv("DASH_E2E_BASE_URL")
pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="Start dashboard and set DASH_E2E_BASE_URL",
)


def test_decision_studio_preserves_tab_and_scenario_across_locales(page) -> None:
    page.goto(f"{BASE_URL.rstrip('/')}/decision")
    page.locator("#app-locale-vi").click()
    page.get_by_text("Không gian quyết định", exact=True).wait_for()
    page.get_by_text("Kịch bản đã chứng nhận", exact=True).wait_for()

    scenario_before = page.locator(
        "#decision-scenario input:checked"
    ).get_attribute("value")
    page.get_by_text("Không gian What-if", exact=True).click()
    page.get_by_text("Trọng số tùy chỉnh không định nghĩa lại", exact=False).wait_for()

    page.locator("#app-locale-en").click()
    page.get_by_text("Decision Studio", exact=True).wait_for()
    page.get_by_text("What-if studio", exact=True).wait_for()

    page.get_by_text("Certified scenarios", exact=True).click()
    assert page.locator(
        "#decision-scenario input:checked"
    ).get_attribute("value") == scenario_before
