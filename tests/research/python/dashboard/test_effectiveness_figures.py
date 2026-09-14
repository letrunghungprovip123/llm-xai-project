"""Pure figure contracts for Page 2."""

from __future__ import annotations

import numpy as np

from research.python.dashboard.data.repository import get_dashboard_repository
from research.python.dashboard.figures.effectiveness import (
    FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP,
    FIG_EFFECTIVENESS_LOSS_DECOMPOSITION,
    FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP,
    FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES,
    FIG_EFFECTIVENESS_RELIABILITY_MAP,
    build_conditional_quality_heatmap,
    build_effect_size_chart,
    build_operational_conditional_gap,
    build_operational_loss_decomposition,
    build_reliability_map,
)


def test_reliability_map_has_18_options_and_fixed_axes() -> None:
    repo = get_dashboard_repository()
    options = repo.option_performance()
    figure = build_reliability_map(options)

    point_count = sum(
        len(trace.x)
        for trace in figure.data
        if trace.name in set(options["model_label"])
    )
    assert point_count == 18
    assert list(figure.layout.xaxis.range) == [0, 1.02]
    assert list(figure.layout.yaxis.range) == [0, 1.02]
    assert figure.layout.meta["figure_id"] == FIG_EFFECTIVENESS_RELIABILITY_MAP


def test_operational_loss_components_sum_to_one() -> None:
    repo = get_dashboard_repository()
    options = repo.option_performance()
    figure = build_operational_loss_decomposition(options)

    assert len(figure.data) == 5
    stacked = np.sum([np.asarray(trace.x, dtype=float) for trace in figure.data], axis=0)
    assert np.allclose(stacked, 1.0, atol=1e-9)
    assert figure.layout.meta["figure_id"] == FIG_EFFECTIVENESS_LOSS_DECOMPOSITION


def test_conditional_figures_keep_observed_and_missing_counts() -> None:
    repo = get_dashboard_repository()
    summary = repo.conditional_option_summary("conservative_faithfulness")
    heatmap = build_conditional_quality_heatmap(
        summary,
        metric_id="conservative_faithfulness",
        metric_label="Conservative faithfulness",
    )
    gap = build_operational_conditional_gap(
        summary,
        metric_id="conservative_faithfulness",
        metric_label="Conservative faithfulness",
    )

    assert np.asarray(heatmap.data[0].z).shape == (3, 6)
    assert int(summary["missing_count"].sum()) == 10
    assert heatmap.layout.meta["figure_id"] == FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP
    assert gap.layout.meta["figure_id"] == FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP
    assert list(gap.layout.xaxis.range) == [0, 1.02]


def test_effect_size_chart_uses_partial_eta_squared() -> None:
    repo = get_dashboard_repository()
    figure = build_effect_size_chart(repo.omnibus_tests())
    assert len(figure.data[0].x) == 3
    assert figure.layout.meta["figure_id"] == FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES
    assert max(figure.data[0].x) <= 1
