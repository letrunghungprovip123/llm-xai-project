"""Browser smoke and round-trip locale test for Page 2."""

from __future__ import annotations

import os

import pytest


BASE_URL = os.getenv("DASH_E2E_BASE_URL")


@pytest.mark.skipif(not BASE_URL, reason="Start dashboard and set DASH_E2E_BASE_URL")
def test_effectiveness_page_localizes_all_tabs_and_preserves_state(page) -> None:
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{BASE_URL}/effectiveness", wait_until="networkidle")
    page.locator("#app-locale-vi").click()

    page.get_by_role(
        "heading", name="Hiệu quả & Độ tin cậy", exact=True
    ).wait_for()
    assert page.get_by_text("Độ tin cậy vận hành", exact=True).is_visible()
    assert page.get_by_text("Chất lượng có điều kiện", exact=True).is_visible()
    assert page.get_by_text("Bằng chứng thống kê", exact=True).is_visible()
    assert page.locator("#effectiveness-reliability-map").is_visible()

    page.get_by_text("Chất lượng có điều kiện", exact=True).click()
    page.get_by_text("Khả năng kiểm chứng", exact=True).click()
    assert page.locator("#effectiveness-conditional-heatmap").is_visible()

    page.locator("#app-locale-en").click()
    page.get_by_role(
        "heading", name="Effectiveness & Reliability", exact=True
    ).wait_for()
    assert page.get_by_text("Conditional quality", exact=True).is_visible()
    assert page.get_by_text("Verifiability", exact=True).is_visible()

    page.locator("#app-locale-vi").click()
    page.get_by_role(
        "heading", name="Hiệu quả & Độ tin cậy", exact=True
    ).wait_for()
    assert page.get_by_text("Khả năng kiểm chứng", exact=True).is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
