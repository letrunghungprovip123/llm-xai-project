"""Research-boundary and progressive-disclosure tests for Page 3."""

from pathlib import Path

from research.python.dashboard.i18n import t


PAGE = Path("research/python/dashboard/pages/mechanisms.py")


def test_page3_copy_preserves_mechanism_boundaries_in_both_locales() -> None:
    english = " ".join(
        [
            t("en", "mechanisms.panel.categorical"),
            t("en", "mechanisms.utilization.disclaimer"),
            t("en", "mechanisms.utilization.narrative_note"),
            t("en", "mechanisms.claims.lexical_disclaimer"),
        ]
    )
    vietnamese = " ".join(
        [
            t("vi", "mechanisms.panel.categorical"),
            t("vi", "mechanisms.utilization.disclaimer"),
            t("vi", "mechanisms.utilization.narrative_note"),
            t("vi", "mechanisms.claims.lexical_disclaimer"),
        ]
    )
    assert "categorical experimental conditions" in english
    assert "association, not causal impact" in english
    assert "not human naturalness" in english
    assert "does not establish copying" in english
    assert "điều kiện thực nghiệm phân loại" in vietnamese
    assert "không phải tác động nhân quả" in vietnamese
    assert "không phải là thước đo độ tự nhiên" in vietnamese
    assert "không chứng minh việc sao chép" in vietnamese


def test_page3_uses_progressive_disclosure_and_excludes_template() -> None:
    text = PAGE.read_text(encoding="utf-8")
    assert text.count("html.Details(") >= 6
    assert "Template" not in text
    assert "Figure ID" not in text
    assert "REPORT_WRITING_READY" not in text
