"""Certified data contracts for Page 2."""

from __future__ import annotations

import numpy as np

from research.python.dashboard.data.repository import get_dashboard_repository


def test_effectiveness_release_shapes_and_identities() -> None:
    repo = get_dashboard_repository()
    data = repo.effectiveness_data()

    assert len(data.option_performance) == 18
    assert len(data.case_metrics) == 648
    assert len(data.paired_tests) == 33
    assert len(data.conditional_paired_tests) == 99
    assert len(data.complete_case_omnibus_tests) == 3
    assert len(data.sensitivity_summary) == 3
    assert len(data.unusable_generations) == 10

    loss_columns = [
        "mean_end_to_end_yield",
        "mean_pipeline_loss",
        "mean_not_verifiable_loss",
        "mean_unsupported_loss",
        "mean_contradiction_loss",
    ]
    totals = data.option_performance[loss_columns].sum(axis=1)
    assert np.allclose(totals, 1.0, atol=1e-9)


def test_conditional_summaries_keep_missing_values_explicit() -> None:
    repo = get_dashboard_repository()
    for metric_id in (
        "conservative_faithfulness",
        "verifiability",
        "resolved_faithfulness",
    ):
        summary = repo.conditional_option_summary(metric_id)
        assert len(summary) == 18
        assert (
            summary["planned_count"]
            == summary["observed_count"] + summary["missing_count"]
        ).all()
        assert summary["mean"].between(0, 1).all()

    conservative = repo.conditional_option_summary(
        "conservative_faithfulness"
    )
    assert int(conservative["missing_count"].sum()) == 10


def test_focused_option_is_validated_against_certified_matrix() -> None:
    repo = get_dashboard_repository()
    selected = repo.focused_option("deepseek_v4_flash", "S4")
    assert selected is not None
    assert selected.unusable_count == 3
    assert selected.planned_count == 36
    assert repo.focused_option("template_baseline", "S4") is None
    assert repo.focused_option("unknown", "S4") is None
