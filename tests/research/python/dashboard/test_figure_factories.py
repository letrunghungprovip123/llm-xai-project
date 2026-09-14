"""Contract tests for the two certified Executive Overview figures."""

from __future__ import annotations

import numpy as np

from research.python.dashboard.data.repository import DashboardRepository
from research.python.dashboard.figures.overview import (
    FIG_OVERVIEW_E2E_HEATMAP,
    FIG_OVERVIEW_EVIDENCE_PROFILE,
    build_e2e_option_heatmap,
    build_evidence_profile,
)
from research.python.dashboard.settings import (
    EXPECTED_EVIDENCE_ORDER,
    EXPECTED_MODEL_ORDER,
)


def test_e2e_heatmap_has_exact_certified_matrix() -> None:
    options = DashboardRepository().option_performance()
    figure = build_e2e_option_heatmap(options)

    assert len(figure.data) == 1
    trace = figure.data[0]
    assert trace.type == "heatmap"
    assert np.asarray(trace.z).shape == (3, 6)
    assert tuple(trace.x) == EXPECTED_EVIDENCE_ORDER
    assert len(tuple(trace.y)) == len(EXPECTED_MODEL_ORDER)
    assert figure.layout.meta["figure_id"] == FIG_OVERVIEW_E2E_HEATMAP
    assert figure.layout.meta["template_included"] is False
    assert int(np.asarray(trace.customdata)[:, :, 9].astype(int).sum()) == 10
    assert sum("⚠" in str(item) for item in np.asarray(trace.text).ravel()) == 2


def test_e2e_heatmap_values_match_option_performance() -> None:
    options = DashboardRepository().option_performance()
    figure = build_e2e_option_heatmap(options)

    expected = (
        options.sort_values(["model_order", "evidence_order"])[
            "mean_end_to_end_yield"
        ]
        .to_numpy(dtype=float)
        .reshape(3, 6)
    )
    np.testing.assert_allclose(np.asarray(figure.data[0].z, dtype=float), expected)


def test_evidence_profile_has_three_model_traces_and_full_axis() -> None:
    options = DashboardRepository().option_performance()
    figure = build_evidence_profile(options)

    assert len(figure.data) == 3
    assert tuple(trace.name for trace in figure.data) == tuple(
        options.sort_values("model_order")["model_label"].drop_duplicates()
    )
    for trace in figure.data:
        assert tuple(trace.x) == EXPECTED_EVIDENCE_ORDER
        assert len(trace.y) == 6
    assert tuple(figure.layout.yaxis.range) == (0, 1)
    assert figure.layout.meta["figure_id"] == FIG_OVERVIEW_EVIDENCE_PROFILE
    assert figure.layout.meta["x_semantics"] == "categorical experimental order"
    assert figure.layout.meta["template_included"] is False


def test_overview_figures_contain_reproducibility_metadata() -> None:
    options = DashboardRepository().option_performance()
    figures = (
        build_e2e_option_heatmap(options),
        build_evidence_profile(options),
    )

    for figure in figures:
        metadata = dict(figure.layout.meta)
        assert metadata["source"] == "option_performance.csv"
        assert metadata["metric"] == "mean_end_to_end_yield"
        assert metadata["release"] == "visualization-data-v2"
        assert metadata["grain"] == "model × evidence condition"
