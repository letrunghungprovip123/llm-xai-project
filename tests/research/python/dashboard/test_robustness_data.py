"""Certified data contracts for Page 5."""

from __future__ import annotations

import numpy as np

from research.python.dashboard.data.repository import DashboardRepository
from research.python.dashboard.settings import (
    DEFAULT_ROBUSTNESS_METRIC,
    DEFAULT_TEMPLATE_SCOPE,
    EXPECTED_EVIDENCE_ORDER,
    EXPECTED_MODEL_ORDER,
)


def test_robustness_release_counts_and_roles() -> None:
    repository = DashboardRepository()
    data = repository.robustness_data()

    assert len(data.validator_pairs) == 648
    assert len(data.validator_summary) == 112
    assert len(data.validator_tests) == 40
    assert len(data.baseline_generations) == 216
    assert len(data.baseline_options) == 6
    assert len(data.baseline_pairs) == 648
    assert len(data.baseline_summary) == 24
    assert len(data.baseline_tests) == 105
    assert not data.baseline_options["eligible_for_llm_decision_ranking"].any()
    assert not data.baseline_pairs["template_is_fourth_llm"].any()
    assert data.baseline_generations["latency_ms"].max() <= 1
    assert data.baseline_generations["latency_measurement_floor_limited"].mean() > 0.99


def test_measurement_views_preserve_paired_case_contract() -> None:
    repository = DashboardRepository()
    shifts = repository.measurement_shift_summary(DEFAULT_ROBUSTNESS_METRIC)

    assert len(shifts) == 18
    assert tuple(shifts["model_id"].drop_duplicates()) == EXPECTED_MODEL_ORDER
    assert tuple(shifts.loc[shifts["model_id"] == EXPECTED_MODEL_ORDER[0], "evidence_level"]) == EXPECTED_EVIDENCE_ORDER

    focused = shifts.iloc[shifts["mean_delta_v4_minus_candidate"].abs().argmax()]
    cases = repository.measurement_case_deltas(
        DEFAULT_ROBUSTNESS_METRIC,
        str(focused["model_id"]),
        str(focused["evidence_level"]),
    )
    assert len(cases) == 36
    assert np.allclose(
        cases["delta_value"],
        cases["sensitivity_value"] - cases["candidate_value"],
    )


def test_template_primary_scope_aggregates_to_36_cases() -> None:
    repository = DashboardRepository()
    for model_id in EXPECTED_MODEL_ORDER:
        cases = repository.template_case_deltas(
            "end_to_end_faithfulness_yield",
            model_id,
            DEFAULT_TEMPLATE_SCOPE,
        )
        assert len(cases) == 36
        assert cases["case_id"].is_unique

    summary = repository.template_uplift_summary(
        "end_to_end_faithfulness_yield",
        DEFAULT_TEMPLATE_SCOPE,
    )
    assert len(summary) == 3
    assert set(summary["paired_case_count"].astype(int)) == {36}
    assert not repository.llm_vs_template_tests()["claims_used_as_independent_units"].any()
