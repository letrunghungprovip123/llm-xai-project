"""Optional Playwright smoke test against a separately running Dash server."""

from __future__ import annotations

import os

import pytest


BASE_URL = os.getenv("DASH_E2E_BASE_URL")
pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="Set DASH_E2E_BASE_URL after starting the dashboard server.",
)


def test_overview_renders_without_horizontal_overflow(page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.get_by_role("heading", name="Tổng quan điều hành").wait_for()
    assert page.locator(".metric-card").count() == 6
    assert page.locator(".chart-card").count() == 2
    overflow = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth"
    )
    assert overflow is False
