"""Figure-factory tests for Page 6 Case Explorer."""

from __future__ import annotations

import numpy as np

from research.python.dashboard.data.repository import DashboardRepository
from research.python.dashboard.figures.cases import (
    build_candidate_v4_case_dumbbell,
    build_case_performance_matrix,
    build_claim_composition,
    build_cohort_landscape,
    build_evidence_utilization_profile,
)
from research.python.dashboard.settings import (
    DEFAULT_CASE_EVIDENCE,
    DEFAULT_CASE_MODEL,
    EXPECTED_EVIDENCE_ORDER,
)


def _first_case(repository: DashboardRepository) -> int:
    return int(repository.case_catalog().iloc[0]["case_id"])


def test_cohort_landscape_has_36_cases_and_threshold_reference() -> None:
    repository = DashboardRepository()
    catalog = repository.case_catalog()
    selected_case = int(catalog.iloc[0]["case_id"])
    figure = build_cohort_landscape(catalog, selected_case_id=selected_case)

    point_count = sum(len(trace.x) for trace in figure.data if trace.name != "Selected case")
    assert point_count == 36
    assert any(float(shape.x0) == 0.5 and float(shape.x1) == 0.5 for shape in figure.layout.shapes)
    assert figure.layout.meta["grain"] == "canonical case"
    assert "not performance extremity" in figure.layout.meta["selection_rule"]


def test_case_matrix_contains_four_generators_and_six_conditions() -> None:
    repository = DashboardRepository()
    case_id = _first_case(repository)
    matrix = repository.case_generation_matrix(case_id)
    figure = build_case_performance_matrix(
        matrix,
        metric_id="end_to_end_faithfulness_yield",
        focused_model_id=DEFAULT_CASE_MODEL,
        focused_evidence_level=DEFAULT_CASE_EVIDENCE,
    )

    assert figure.data[0].z.shape == (4, 6)
    assert tuple(figure.layout.xaxis.ticktext) == EXPECTED_EVIDENCE_ORDER
    assert figure.layout.meta["template_is_fourth_llm"] is False
    assert figure.layout.meta["evidence_is_ordinal"] is False
    assert len(figure.layout.shapes) >= 2  # Template separator plus focused-cell outline.


def test_unusable_conditional_matrix_uses_na_not_zero() -> None:
    repository = DashboardRepository()
    case_id = int(
        repository.case_catalog().loc[
            lambda frame: frame["unusable_slot_count"] > 0
        ].iloc[0]["case_id"]
    )
    matrix = repository.case_generation_matrix(case_id, "conservative_faithfulness")
    figure = build_case_performance_matrix(
        matrix,
        metric_id="conservative_faithfulness",
        focused_model_id=DEFAULT_CASE_MODEL,
        focused_evidence_level="S4",
    )

    text = np.asarray(figure.data[0].text, dtype=object)
    assert "N/A" in set(text.ravel())
    assert np.isnan(np.asarray(figure.data[0].z, dtype=float)).any()


def test_utilization_profile_preserves_not_applicable_values() -> None:
    repository = DashboardRepository()
    case_id = _first_case(repository)
    row = repository.case_utilization(case_id, DEFAULT_CASE_MODEL, "S0")
    figure = build_evidence_utilization_profile(
        row,
        model_id=DEFAULT_CASE_MODEL,
        model_label="Qwen3 8B",
        evidence_level="S0",
    )

    assert len(figure.data) == 1
    assert len(figure.data[0].y) == 6
    assert "N/A" in set(figure.data[0].text)
    assert figure.layout.meta["interpretation"] == "descriptive association, not causal mediation"


def test_claim_composition_reconciles_candidate_counts() -> None:
    repository = DashboardRepository()
    case_id = _first_case(repository)
    pair = repository.case_validator_pair(case_id, DEFAULT_CASE_MODEL, DEFAULT_CASE_EVIDENCE)
    figure = build_claim_composition(pair)

    expected = int(pair["candidate_total_claims"])
    observed = sum(int(trace.customdata[0][0]) for trace in figure.data)
    assert observed == expected
    assert figure.layout.meta["measurement_role"] == "Candidate primary artifact"


def test_candidate_v4_dumbbell_keeps_roles_and_four_metrics() -> None:
    repository = DashboardRepository()
    case_id = _first_case(repository)
    pair = repository.case_validator_pair(case_id, DEFAULT_CASE_MODEL, DEFAULT_CASE_EVIDENCE)
    figure = build_candidate_v4_case_dumbbell(
        pair,
        model_label="Qwen3 8B",
        evidence_level=DEFAULT_CASE_EVIDENCE,
    )

    assert len(figure.layout.yaxis.ticktext) == 4
    assert any(trace.name == "Candidate · primary" for trace in figure.data)
    assert any(trace.name == "V4 · sensitivity only" for trace in figure.data)
    assert figure.layout.meta["candidate_role"] == "primary"
    assert figure.layout.meta["v4_role"] == "sensitivity_only"
