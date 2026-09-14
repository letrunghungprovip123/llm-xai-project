"""Guard against scientifically unsafe wording on Executive Overview."""

from __future__ import annotations

from pathlib import Path

from research.python.dashboard.i18n import t


REPOSITORY_SOURCE = Path("research/python/dashboard/data/repository.py")


def test_overview_copy_preserves_interpretation_boundaries_in_both_locales() -> None:
    english = t("en", "overview.disclaimer")
    vietnamese = t("vi", "overview.disclaimer")

    assert "not human ground truth" in english
    assert "S0–S5 are categorical experimental conditions." in english
    assert "không phải là sự thật chuẩn do con người xác lập" in vietnamese
    assert "S0–S5 là các điều kiện thực nghiệm phân loại" in vietnamese
    assert "accuracy" not in english.lower()
    assert "probability" not in english.lower()


def test_findings_use_observed_not_absolute_superiority_language() -> None:
    text = REPOSITORY_SOURCE.read_text(encoding="utf-8")
    assert "highest " in text
    assert "observed mean E2E score" in text
    assert "definitively the best" not in text.lower()
