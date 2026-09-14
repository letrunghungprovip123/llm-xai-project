"""Optional Playwright locale and state coverage for Page 5."""

from __future__ import annotations

import os

import pytest


BASE_URL = os.getenv("DASH_E2E_BASE_URL")
pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="Start dashboard and set DASH_E2E_BASE_URL",
)


def test_robustness_tabs_and_locale_round_trip(page) -> None:
    page.goto(f"{BASE_URL.rstrip('/')}/robustness")

    page.locator("#app-locale-vi").click()
    page.get_by_text("Độ vững & Đường cơ sở Template", exact=True).wait_for()
    page.get_by_text("Độ vững đo lường", exact=True).click()
    page.get_by_text(
        "Mức thay đổi kết quả dưới hiện vật độ nhạy",
        exact=True,
    ).wait_for()

    page.get_by_text("Đường cơ sở Template", exact=True).click()
    page.get_by_text(
        "Hồ sơ LLM và Template tất định theo các điều kiện bằng chứng",
        exact=True,
    ).wait_for()

    page.locator("#app-locale-en").click()
    page.get_by_text("Robustness & Template Baseline", exact=True).wait_for()
    page.get_by_text(
        "LLM and deterministic-template profiles across evidence conditions",
        exact=True,
    ).wait_for()

    # Locale changes must preserve the analytical tab value.
    selected = page.locator("#robustness-tabs .tab--selected")
    assert selected.get_by_text("Template baseline", exact=True).count() == 1
