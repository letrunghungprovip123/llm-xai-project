"""Optional live-browser smoke test for Page 7."""

from __future__ import annotations

import os

import pytest


BASE_URL = os.getenv("DASH_E2E_BASE_URL")
pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="Start dashboard and set DASH_E2E_BASE_URL",
)


def test_methods_page_smoke(page):
    page.goto(f"{BASE_URL}/methods", wait_until="networkidle")
    page.get_by_role("heading", name="Khả năng tái lập & Phương pháp").wait_for()
    page.get_by_text("Lớp trình bày đã chứng nhận", exact=True).wait_for()
    page.get_by_text("Bản phát hành & Xác thực", exact=True).click()
    page.get_by_text("Ma trận cổng xác thực", exact=True).wait_for()
    page.get_by_text("Thiết kế nghiên cứu", exact=True).click()
    page.get_by_text("Bản đồ sáu câu hỏi nghiên cứu", exact=True).wait_for()
    page.get_by_text("Chỉ số & Mẫu số", exact=True).click()
    page.get_by_text("Sổ mẫu số", exact=True).wait_for()
    page.get_by_text("Hồ sơ đủ 18 điều kiện", exact=True).wait_for()
    page.get_by_text("Hồ sơ có thiếu có cấu trúc", exact=True).wait_for()
    page.get_by_text("Chỉ số chính đã chứng nhận", exact=True).first.wait_for()
    page.get_by_text("Giới hạn & Tái lập", exact=True).click()
    page.get_by_text("Sổ giới hạn", exact=True).wait_for()
