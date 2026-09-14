"""Live-browser bilingual smoke coverage for every dashboard route."""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import expect


BASE_URL = os.getenv("DASH_E2E_BASE_URL")
pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="Start the dashboard and set DASH_E2E_BASE_URL.",
)

ROUTES = (
    ("/", "Tổng quan điều hành", "Executive Overview"),
    ("/effectiveness", "Hiệu quả & Độ tin cậy", "Effectiveness & Reliability"),
    ("/mechanisms", "Bằng chứng, Cơ chế & Chẩn đoán", "Evidence, Mechanisms & Diagnostics"),
    ("/decision", "Không gian quyết định", "Decision Studio"),
    ("/robustness", "Độ vững & Đường cơ sở Template", "Robustness & Template Baseline"),
    ("/cases", "Khám phá hồ sơ", "Case Explorer"),
    ("/methods", "Khả năng tái lập & Phương pháp", "Reproducibility & Methods"),
)


def _assert_no_horizontal_overflow(page) -> None:
    overflow = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth + 2"
    )
    assert overflow is False


def _select_locale(page, locale: str, expected_title: str) -> None:
    button = page.locator(f"#app-locale-{locale}")
    button.click()
    expect(button).to_have_attribute("aria-pressed", "true")
    expect(page.locator("html")).to_have_attribute("lang", locale)
    expect(
        page.get_by_role("heading", name=expected_title, exact=True)
    ).to_be_visible()


def test_every_route_round_trips_vi_en_without_route_or_layout_drift(page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.evaluate("window.localStorage.clear()")

    for route, vietnamese_title, english_title in ROUTES:
        page.goto(f"{BASE_URL}{route}", wait_until="networkidle")
        _select_locale(page, "vi", vietnamese_title)
        original_path = page.evaluate("window.location.pathname")
        _assert_no_horizontal_overflow(page)

        _select_locale(page, "en", english_title)
        assert page.evaluate("window.location.pathname") == original_path
        _assert_no_horizontal_overflow(page)

        _select_locale(page, "vi", vietnamese_title)
        assert page.evaluate("window.location.pathname") == original_path
