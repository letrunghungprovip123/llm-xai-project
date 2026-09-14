"""Playwright localization and state smoke coverage for Page 3."""

import os
import pytest

BASE_URL = os.getenv("DASH_E2E_BASE_URL")
pytestmark = pytest.mark.skipif(
    not BASE_URL, reason="Start dashboard and set DASH_E2E_BASE_URL"
)


def test_mechanisms_page_round_trip_locale_preserves_selected_view(page) -> None:
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{BASE_URL}/mechanisms", wait_until="networkidle")
    page.locator("#app-locale-vi").click()

    page.get_by_role(
        "heading", name="Bằng chứng, Cơ chế & Chẩn đoán", exact=True
    ).wait_for()
    assert page.get_by_text("Thiết kế bằng chứng", exact=True).is_visible()
    page.get_by_text("Mức sử dụng bằng chứng", exact=True).click()
    page.get_by_text("Mức sử dụng khái niệm", exact=True).click()
    assert page.locator("#mechanisms-utilization-matrix").is_visible()

    page.locator("#app-locale-en").click()
    page.get_by_role(
        "heading", name="Evidence, Mechanisms & Diagnostics", exact=True
    ).wait_for()
    assert page.get_by_text("Evidence utilization", exact=True).is_visible()
    assert (
        page.locator("#mechanisms-utilization-metric")
        .get_by_text("Concept use", exact=True)
        .is_visible()
    )
    assert page.locator("#mechanisms-utilization-matrix").is_visible()

    page.locator("#app-locale-vi").click()
    page.get_by_role(
        "heading", name="Bằng chứng, Cơ chế & Chẩn đoán", exact=True
    ).wait_for()
    assert (
        page.locator("#mechanisms-utilization-metric")
        .get_by_text("Mức sử dụng khái niệm", exact=True)
        .is_visible()
    )
    assert page.locator("body").evaluate("el => el.scrollWidth <= el.clientWidth")
