"""Certified data-contract tests for Page 6 Case Explorer."""

from __future__ import annotations

import pandas as pd

from research.python.dashboard.data.repository import DashboardRepository
from research.python.dashboard.settings import (
    DEFAULT_CASE_EVIDENCE,
    DEFAULT_CASE_MODEL,
    EXPECTED_CANONICAL_CASE_COUNT,
    EXPECTED_CASE_EVIDENCE_PACKAGE_COUNT,
    EXPECTED_CASE_GENERATION_COUNT,
    EXPECTED_COMPLETE_LLM_CASE_COUNT,
)


def _first_case(repository: DashboardRepository) -> int:
    return int(repository.case_catalog().iloc[0]["case_id"])


def test_case_catalog_preserves_the_frozen_36_case_cohort() -> None:
    repository = DashboardRepository()
    catalog = repository.case_catalog()

    assert len(catalog) == EXPECTED_CANONICAL_CASE_COUNT
    assert catalog["case_id"].is_unique
    assert int(catalog["complete_llm_case"].sum()) == EXPECTED_COMPLETE_LLM_CASE_COUNT
    assert int((~catalog["complete_llm_case"]).sum()) == 9
    assert int(catalog["unusable_slot_count"].sum()) == 10
    assert set(catalog["unusable_slot_count"]) == {0, 1, 2}


def test_each_case_has_18_llm_and_6_template_slots() -> None:
    repository = DashboardRepository()
    case_id = _first_case(repository)
    generations = repository.case_generations(case_id)

    assert len(generations) == EXPECTED_CASE_GENERATION_COUNT
    assert (generations["generator_family"] == "LLM").sum() == 18
    assert (generations["generator_family"] == "TEMPLATE").sum() == 6
    assert generations[["generator_id", "evidence_level"]].duplicated().sum() == 0


def test_case_evidence_package_is_generator_independent_and_complete() -> None:
    repository = DashboardRepository()
    case_id = _first_case(repository)
    packages = repository.case_evidence_packages(case_id)

    assert len(packages) == EXPECTED_CASE_EVIDENCE_PACKAGE_COUNT
    assert tuple(packages["evidence_level"]) == ("S0", "S1", "S2", "S3", "S4", "S5")
    assert packages["evidence_condition_is_ordinal"].eq(False).all()


def test_focused_case_data_keeps_primary_and_reference_roles_separate() -> None:
    repository = DashboardRepository()
    case_id = _first_case(repository)
    focused = repository.focused_case_data(
        case_id,
        DEFAULT_CASE_MODEL,
        DEFAULT_CASE_EVIDENCE,
    )

    assert focused.case_summary.case_id == case_id
    assert focused.utilization["generator_family"] == "LLM"
    assert focused.narrative_structure["human_naturalness_measured"] is False or bool(
        focused.narrative_structure["human_naturalness_measured"]
    ) is False
    assert bool(focused.template_pair["template_is_fourth_llm"]) is False
    assert bool(focused.template_pair["eligible_for_decision_ranking"]) is False


def test_unusable_conditional_cells_remain_missing_not_zero() -> None:
    repository = DashboardRepository()
    catalog = repository.case_catalog()
    case_id = int(catalog.loc[catalog["unusable_slot_count"] > 0].iloc[0]["case_id"])
    matrix = repository.case_generation_matrix(case_id, "conservative_faithfulness")
    unusable = matrix.loc[matrix["is_unusable"].astype(bool)]

    assert not unusable.empty
    assert unusable["metric_value"].isna().all()
    assert unusable["end_to_end_faithfulness_yield"].eq(0).all()
