"""Target viewport acceptance test for Page 1."""
from __future__ import annotations
import os
import pytest
BASE_URL = os.getenv("DASH_E2E_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="Set DASH_E2E_BASE_URL after starting the dashboard server.")
def test_overview_at_1366_by_768(page) -> None:
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(BASE_URL, wait_until="networkidle")
    page.locator("#overview-e2e-heatmap").wait_for()
    assert page.locator("#overview-e2e-heatmap").is_visible()
    assert page.locator("#overview-evidence-profile").is_visible()
