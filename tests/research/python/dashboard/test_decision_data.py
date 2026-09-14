"""Certified Decision Studio data and What-if identity tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.python.dashboard.data.repository import DashboardRepository
from research.python.dashboard.settings import (
    ANALYSIS_ROOT,
    DECISION_SCENARIO_IDS,
    WHAT_IF_BASE_SCENARIO,
)


def _repository_from_csvs() -> DashboardRepository:
    directory = ANALYSIS_ROOT / "visualization_v2"
    if not directory.is_dir():
        directory = ANALYSIS_ROOT / "visualization"
    frames = {
        "scenario_options": pd.read_csv(directory / "scenario_options.csv"),
        "scenario_criterion_contributions": pd.read_csv(
            directory / "scenario_criterion_contributions.csv"
        ),
        "recommendation_evidence": pd.read_csv(
            directory / "recommendation_evidence.csv"
        ),
    }
    repository = object.__new__(DashboardRepository)
    repository._frame = lambda name: frames[name].copy(deep=True)  # type: ignore[attr-defined]
    return repository


def test_certified_decision_contracts() -> None:
    repository = _repository_from_csvs()
    options = repository.scenario_options()
    scenarios = repository.decision_scenarios()
    criteria = repository.decision_criteria()

    assert len(options) == 90
    assert tuple(item.scenario_id for item in scenarios) == DECISION_SCENARIO_IDS
    assert options.groupby("scenario_id").size().eq(18).all()
    assert not options["model_id"].str.contains("template", case=False).any()
    assert len(criteria) == 8
    assert all(item.label == item.label.strip() for item in scenarios)
    assert all(item.description.isascii() for item in scenarios)
    assert options["utility_rank"].notna().any()
    assert {item.group for item in criteria} == {
        "Quality",
        "Reliability",
        "Efficiency",
        "Measurement robustness",
    }


def test_custom_what_if_uses_normalized_value_times_new_weight() -> None:
    repository = _repository_from_csvs()
    criteria = repository.decision_criteria()
    raw = {item.criterion_id: 1.0 for item in criteria}
    result = repository.custom_what_if(raw)

    assert result.recommended_option_id is not None
    assert pytest.approx(sum(result.normalized_weights.values())) == 1.0
    assert set(result.ranking["option_id"]) == set(
        repository.scenario_ranking(WHAT_IF_BASE_SCENARIO)["option_id"]
    )

    contributions = result.contributions.dropna(
        subset=["custom_contribution"]
    )
    expected = (
        contributions["normalized_value"].astype(float)
        * contributions["custom_weight"].astype(float)
    )
    assert np.allclose(
        expected,
        contributions["custom_contribution"].astype(float),
        atol=1e-12,
    )
    assert result.ranking["custom_rank"].notna().sum() == 16


def test_all_zero_what_if_returns_no_recommendation() -> None:
    repository = _repository_from_csvs()
    raw = {
        item.criterion_id: 0.0
        for item in repository.decision_criteria()
    }
    result = repository.custom_what_if(raw)

    assert result.recommended_option_id is None
    assert result.contributions.empty
    assert result.ranking["custom_utility"].isna().all()
