"""Certified Page-1 headline parity tests."""

from __future__ import annotations

import pytest

from research.python.dashboard.data.repository import DashboardRepository


def test_page_one_headlines_match_certified_report_numbers() -> None:
    repository = DashboardRepository()
    numbers = repository.certified_numbers().set_index("metric_id")
    kpis = {
        item.metric_id: item
        for item in repository.overview_data().kpis
    }

    assert kpis["planned_llm_generations"].value == int(
        numbers.loc["planned_llm_generations", "value"]
    )
    assert kpis["usable_llm_generations"].value == int(
        numbers.loc["usable_llm_generations", "value"]
    )
    assert kpis["usability_rate"].value == pytest.approx(
        numbers.loc["usability_rate", "value"]
    )
    assert kpis["mean_end_to_end_operational_faithfulness"].value == pytest.approx(
        numbers.loc["mean_end_to_end_operational_faithfulness", "value"]
    )
    assert kpis["final_atomic_claims"].value == int(
        numbers.loc["final_atomic_claims", "value"]
    )
