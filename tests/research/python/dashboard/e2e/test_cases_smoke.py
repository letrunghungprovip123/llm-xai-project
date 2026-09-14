"""Optional Playwright smoke and locale-state coverage for Page 6."""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import expect


BASE_URL = os.getenv("DASH_E2E_BASE_URL")
pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="Start dashboard and set DASH_E2E_BASE_URL",
)


def test_case_explorer_renders_and_preserves_state_across_locales(page) -> None:
    page.goto(f"{BASE_URL.rstrip('/')}/cases")
    page.locator("#app-locale-vi").click()
    page.get_by_role("heading", name="Khám phá hồ sơ", exact=True).wait_for()
    page.get_by_text("Toàn cảnh đoàn hệ chuẩn hóa", exact=True).wait_for()
    page.get_by_text("Ma trận hiệu năng theo hồ sơ", exact=True).wait_for()
    page.get_by_text("Chẩn đoán LLM đang tập trung", exact=True).wait_for()

    evidence = page.locator("#cases-evidence-condition")
    evidence.click()
    page.get_by_role("option", name="S4", exact=True).click()
    expect(evidence).to_contain_text("S4")

    model_before = page.locator("#cases-focused-model").inner_text().strip()
    case_before = page.locator("#cases-selected-case").inner_text().strip()
    case_number_before = "".join(character for character in case_before if character.isdigit())
    metric_before = page.locator("#cases-matrix-metric input:checked").get_attribute("value")

    page.locator("#app-locale-en").click()
    page.get_by_role("heading", name="Case Explorer", exact=True).wait_for()
    page.get_by_text("Canonical cohort landscape", exact=True).wait_for()
    expect(evidence).to_contain_text("S4")
    assert page.locator("#cases-focused-model").inner_text().strip() == model_before
    case_after = page.locator("#cases-selected-case").inner_text().strip()
    assert "".join(character for character in case_after if character.isdigit()) == case_number_before
    assert page.locator("#cases-matrix-metric input:checked").get_attribute("value") == metric_before
