"""Static semantic boundaries for the Decision Studio source."""

from __future__ import annotations

from pathlib import Path


PAGE = Path("research/python/dashboard/pages/decision.py")
REPOSITORY = Path("research/python/dashboard/data/repository.py")


def test_decision_page_separates_certified_and_what_if_modes() -> None:
    text = PAGE.read_text(encoding="utf-8")
    assert "Certified scenarios" in text
    assert "What-if studio" in text
    assert "User-specified exploration" not in text or "what_if_warning" in text
    assert "not a probability" in text or "decision_boundaries" in text
    assert "Template" not in text or "Template Reference" in text


def test_what_if_formula_uses_normalized_value_not_old_contribution() -> None:
    text = REPOSITORY.read_text(encoding="utf-8")
    assert 'base["normalized_value"].astype(float)' in text
    assert '* base["custom_weight"].astype(float)' in text
    assert 'base["weighted_contribution"] *' not in text


def test_decision_page_has_no_gauge_or_modebar_contract() -> None:
    text = PAGE.read_text(encoding="utf-8").lower()
    assert "gauge" not in text
    assert "figure id" not in text

def test_what_if_results_precede_weight_controls_and_use_exact_ui_hooks() -> None:
    text = PAGE.read_text(encoding="utf-8")
    chart_position = text.index('class_name="decision-what-if-comparison-card"')
    controls_position = text.index('decision-weight-editor-panel--bottom')
    assert chart_position < controls_position
    assert "decision-what-if-overview-grid" in text
    assert "decision-action-button" in text


def test_decision_css_has_exact_sidebar_and_page_spacing_hooks() -> None:
    css = Path("research/python/dashboard/assets/app.css").read_text(encoding="utf-8")
    assert "PAGE4_DECISION_EXACT_UI_REFINEMENT_START" in css
    assert ".dashboard-nav-link" in css
    assert ".decision-what-if-overview-grid" in css
    assert ".decision-weight-editor-panel--bottom" in css


def test_certified_ranking_explains_pareto_first_and_utility_rank() -> None:
    page = PAGE.read_text(encoding="utf-8")
    assert "Decision rank places eligible, scored Pareto-efficient options first" in page
    assert "Utility rank" in page
    assert "Top certified decision ranks" in page


def test_certified_copy_uses_english_scenario_descriptions() -> None:
    settings = Path("research/python/dashboard/settings.py").read_text(encoding="utf-8")
    assert "Prioritizes end-to-end quality" in settings
    assert "Considers only configurations that complete all planned generations" in settings
    assert "Ưu tiên" not in settings
    assert "Chỉ chấp nhận" not in settings
