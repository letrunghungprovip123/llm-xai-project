"""Certified data-contract tests for Page 7."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data/reports/llm_validation/validation_v1/analysis/visualization_v2"


def _csv(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name)


def test_methods_release_metadata_is_single_and_scientifically_bounded() -> None:
    frame = _csv("release_metadata.csv")
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["parent_analytical_gate"] == "REPORT_WRITING_READY"
    assert row["statistical_gate"] == "STATISTICAL_CORE_READY"
    assert row["validator_sensitivity_gate"] == "VALIDATOR_SENSITIVITY_READY"
    assert row["baseline_gate"] == "BASELINE_COMPARISON_READY"
    assert bool(row["template_is_fourth_llm"]) is False
    assert bool(row["template_eligible_for_decision_ranking"]) is False
    assert bool(row["human_naturalness_evaluated"]) is False
    assert bool(row["template_latency_measurement_floor_limited"]) is True


def test_methods_research_registry_has_six_unique_questions() -> None:
    frame = _csv("research_question_registry.csv")
    assert len(frame) == 6
    assert frame["rq_id"].nunique() == 6
    assert list(frame.sort_values("rq_order")["rq_id"]) == [f"RQ{i}" for i in range(1, 7)]
    for column in [
        "primary_metrics_json",
        "supporting_metrics_json",
        "primary_sources_json",
        "dashboard_pages_json",
        "interpretation_restrictions_json",
    ]:
        assert frame[column].map(lambda value: isinstance(json.loads(value), list)).all()


def test_methods_visibility_has_four_frozen_tiers() -> None:
    frame = _csv("metric_visibility_registry.csv")
    assert set(frame["visibility_tier"]) == {
        "A_HEADLINE",
        "B_EXPLANATORY",
        "C_INTERNAL_VALIDATION",
        "D_DISABLED_UNTIL_BETTER_DATA",
    }
    assert not frame["metric_id"].duplicated().any()
    disabled = frame.loc[frame["visibility_tier"] == "D_DISABLED_UNTIL_BETTER_DATA"]
    assert (~disabled["dashboard_enabled"].astype(bool)).all()
    assert disabled["requires_additional_data"].astype(bool).all()


def test_methods_dictionary_matches_manifest_field_contract() -> None:
    dictionary = _csv("visualization_dictionary.csv")
    manifest = json.loads((DATA / "visualization_manifest.json").read_text())
    expected = sum(
        int(item["column_count"])
        for item in manifest["output_artifacts"]
        if item["dataset_name"] != "visualization_dictionary"
    )
    assert len(dictionary) == expected
    assert not dictionary.duplicated(["dataset_name", "field_name"]).any()


def test_methods_denominator_ledger_is_frozen() -> None:
    numbers = _csv("certified_report_numbers.csv").set_index("metric_id")
    assert int(numbers.loc["planned_llm_generations", "value"]) == 648
    assert int(numbers.loc["usable_llm_generations", "value"]) == 638
    assert int(numbers.loc["unusable_llm_generations", "value"]) == 10
    assert int(numbers.loc["final_atomic_claims", "value"]) == 14667
    assert int(numbers.loc["applicable_claims", "value"]) == 14655
    assert int(numbers.loc["resolved_claims", "value"]) == 13637


def test_methods_statistical_families_are_frozen() -> None:
    assert len(_csv("omnibus_tests.csv")) == 3
    assert len(_csv("paired_tests.csv")) == 33
    assert len(_csv("conditional_paired_tests.csv")) == 99
    assert len(_csv("validator_sensitivity_tests.csv")) == 40
    assert len(_csv("llm_vs_template_tests.csv")) == 105


def test_methods_complete_case_denominators_reconcile() -> None:
    frame = _csv("case_heterogeneity_summary.csv")
    cases = (
        frame[["case_id", "complete_llm_case"]]
        .drop_duplicates("case_id")
        .sort_values("case_id", kind="stable")
    )
    complete = int(cases["complete_llm_case"].astype(bool).sum())
    incomplete = int(len(cases) - complete)
    assert len(cases) == 36
    assert complete == 27
    assert incomplete == 9
    assert complete + incomplete == 36
