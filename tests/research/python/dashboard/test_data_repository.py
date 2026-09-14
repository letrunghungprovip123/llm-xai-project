"""Repository and Page-1 view-model tests."""

from __future__ import annotations

import pytest

from research.python.dashboard.data.repository import DashboardRepository


@pytest.fixture(scope="module")
def overview_data():
    return DashboardRepository().overview_data()


def test_overview_has_six_certified_kpis(overview_data) -> None:
    assert len(overview_data.kpis) == 6
    values = {item.metric_id: item.value for item in overview_data.kpis}
    assert values == {
        "planned_llm_generations": 648,
        "usable_llm_generations": 638,
        "usability_rate": pytest.approx(638 / 648),
        "mean_end_to_end_operational_faithfulness": pytest.approx(0.877132),
        "final_atomic_claims": 14667,
        "template_reference_generations": 216,
    }


def test_overview_option_matrix_is_exactly_three_by_six(overview_data) -> None:
    frame = overview_data.option_performance
    assert len(frame) == 18
    assert frame["model_id"].nunique() == 3
    assert frame["evidence_level"].nunique() == 6
    assert not frame["model_id"].str.contains("template", case=False).any()
    assert frame["option_id"].is_unique


def test_operational_denominators_and_failures_are_consistent(overview_data) -> None:
    frame = overview_data.option_performance
    failures = overview_data.unusable_generations
    assert frame["planned_generation_count"].sum() == 648
    assert frame["usable_generation_count"].sum() == 638
    assert frame["unusable_generation_count"].sum() == 10
    assert len(failures) == 10
    assert set(failures["evidence_level"]) == {"S4"}
    assert set(failures["end_to_end_faithfulness_yield"]) == {0.0}


def test_findings_are_deterministic_and_cautious(overview_data) -> None:
    assert len(overview_data.findings) == 4
    statements = " ".join(item.statement for item in overview_data.findings)
    assert "statistically significant" in statements
    assert "highest observed" in statements
    assert "structured concentration" in statements
    assert "requires sensitivity analysis" in statements
    assert "+6.13 pp" in statements
    assert "definitively best" not in statements.lower()
    assert "human ground truth" not in statements.lower()
