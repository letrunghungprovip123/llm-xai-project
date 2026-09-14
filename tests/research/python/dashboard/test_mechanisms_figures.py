"""Pure figure-contract tests for Page 3."""

import numpy as np

from research.python.dashboard.data.repository import DashboardRepository
from research.python.dashboard.figures.mechanisms import (
    build_claim_difficulty_matrix,
    build_claim_status_small_multiples,
    build_coverage_diversity_scatter,
    build_evidence_composition_chart,
    build_failure_matrix,
    build_pipeline_completion_chart,
    build_utilization_matrix,
    build_utilization_quality_scatter,
)


def test_evidence_design_figures_preserve_six_categorical_conditions() -> None:
    repository = DashboardRepository()
    data = repository.mechanisms_data()
    composition = build_evidence_composition_chart(data.evidence_design)
    assert len(composition.data) == 2
    assert tuple(composition.data[0].x) == ("S0", "S1", "S2", "S3", "S4", "S5")
    scatter = build_coverage_diversity_scatter(data.evidence_design)
    assert all(tuple(trace.x) for trace in scatter.data)
    x_min, x_max = map(float, scatter.layout.xaxis.range)

    # Coverage remains a normalized 0–1 metric, while the presentation
    # viewport may zoom into the observed range to reduce empty space.
    assert 0.0 <= x_min < x_max <= 1.0

    for trace in scatter.data:
        assert all(
            x_min <= float(value) <= x_max
            for value in trace.x
        )
    y_min, y_max = map(float, scatter.layout.yaxis.range)

    # Diversity also remains normalized to 0–1, while the chart may zoom
    # into the observed region to improve readability.
    assert 0.0 <= y_min < y_max <= 1.0

    for trace in scatter.data:
        assert all(
            y_min <= float(value) <= y_max
            for value in trace.y
        )


def test_utilization_figures_exclude_template_and_keep_full_axes() -> None:
    repository = DashboardRepository()
    summary = repository.utilization_option_summary("feature_use")
    matrix = build_utilization_matrix(
        summary, metric_label="Feature use", metric_id="feature_use"
    )
    assert len(matrix.data[0].x) == 18
    assert matrix.layout.meta["metric"] == "feature_use"
    assert not any("template" in str(value).lower() for value in matrix.data[0].customdata[:, 0])
    scatter = build_utilization_quality_scatter(repository.evidence_utilization_summary(), metric_id="feature_use", metric_label="Feature use")
    assert len(scatter.data) == 3
    assert tuple(scatter.layout.xaxis.range) == (0, 1)
    assert tuple(scatter.layout.yaxis.range) == (0, 1)


def test_claim_and_pipeline_figures_reconcile_certified_counts() -> None:
    data = DashboardRepository().mechanisms_data()
    shares = data.claim_status_by_option[["supported_share", "not_verifiable_share", "unsupported_share", "contradicted_share", "not_applicable_share"]].sum(axis=1)
    assert np.allclose(shares, 1.0)
    claim = build_claim_status_small_multiples(data.claim_status_by_option)
    assert len(claim.data) == 15
    difficulty = build_claim_difficulty_matrix(data.claim_difficulty_by_type)
    assert difficulty.data[0].z.shape == (12, 3)
    pipeline = build_pipeline_completion_chart(data.pipeline_stage_summary)
    assert len(pipeline.data) == 3
    failure = build_failure_matrix(data.failure_matrix)
    assert int(np.asarray(failure.data[0].z).sum()) == 10
