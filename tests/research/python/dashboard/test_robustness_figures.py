"""Figure contracts for Page 5."""

from __future__ import annotations

import numpy as np

from research.python.dashboard.data.repository import DashboardRepository
from research.python.dashboard.figures.robustness import (
    build_candidate_v4_delta_distribution,
    build_candidate_v4_dumbbell,
    build_template_coverage_scatter,
    build_template_delta_distribution,
    build_template_evidence_progression,
    build_template_uplift_matrix,
)
from research.python.dashboard.settings import (
    DEFAULT_ROBUSTNESS_METRIC,
    DEFAULT_TEMPLATE_SCOPE,
    EXPECTED_EVIDENCE_ORDER,
    EXPECTED_MODEL_ORDER,
)


def test_measurement_dumbbell_preserves_18_configurations_and_roles() -> None:
    repository = DashboardRepository()
    summary = repository.measurement_shift_summary(DEFAULT_ROBUSTNESS_METRIC)
    figure = build_candidate_v4_dumbbell(summary, metric_id=DEFAULT_ROBUSTNESS_METRIC)

    assert figure.layout.meta["candidate_role"] == "primary"
    assert figure.layout.meta["v4_role"] == "sensitivity_only"
    assert tuple(figure.layout.xaxis.range) == (0, 1.035)
    assert len(summary) == 18
    assert len(figure.data) == 1 + 2 * len(EXPECTED_MODEL_ORDER)
    assert any(trace.marker.symbol == "circle-open" for trace in figure.data if hasattr(trace, "marker"))


def test_measurement_delta_distribution_uses_zero_reference_and_36_cases() -> None:
    repository = DashboardRepository()
    cases = repository.measurement_case_deltas(
        DEFAULT_ROBUSTNESS_METRIC,
        EXPECTED_MODEL_ORDER[0],
        "S1",
    )
    figure = build_candidate_v4_delta_distribution(
        cases,
        metric_id=DEFAULT_ROBUSTNESS_METRIC,
        focus_label="Qwen3 8B · S1",
    )

    assert len(cases) == 36
    assert figure.layout.meta["grain"] == "paired canonical case"
    assert "Candidate primary" in figure.data[0].hovertemplate
    assert "V4 sensitivity" in figure.data[0].hovertemplate
    assert any(float(shape.x0) == 0 and float(shape.x1) == 0 for shape in figure.layout.shapes)


def test_template_progression_has_three_llms_and_dashed_template() -> None:
    repository = DashboardRepository()
    figure = build_template_evidence_progression(
        repository.llm_vs_template_summary(),
        repository.baseline_option_performance(),
        metric_id="end_to_end_faithfulness_yield",
    )

    assert len(figure.data) == 4
    assert tuple(trace.name for trace in figure.data[:3]) == (
        "Qwen3 8B",
        "DeepSeek V4 Flash",
        "Phi-4 Mini Instruct",
    )
    assert tuple(figure.data[0].x) == EXPECTED_EVIDENCE_ORDER
    assert figure.data[-1].line.dash == "dash"
    assert figure.data[-1].marker.symbol == "diamond"
    assert figure.layout.meta["template_is_fourth_llm"] is False


def test_template_matrix_and_distribution_preserve_case_paired_inference() -> None:
    repository = DashboardRepository()
    tests = repository.llm_vs_template_tests().copy()
    tests["model_label"] = tests["model_id"].map({
        "qwen3_8b": "Qwen3 8B",
        "deepseek_v4_flash": "DeepSeek V4 Flash",
        "phi4_mini_instruct": "Phi-4 Mini Instruct",
    })
    tests["model_order"] = tests["model_id"].map({
        "qwen3_8b": 1,
        "deepseek_v4_flash": 2,
        "phi4_mini_instruct": 3,
    })
    matrix = build_template_uplift_matrix(tests, evidence_scope=DEFAULT_TEMPLATE_SCOPE)
    assert matrix.data[0].z.shape == (3, 5)
    assert matrix.layout.meta["denominator"] == "36 paired canonical cases per model and scope"

    cases = repository.template_case_deltas(
        "end_to_end_faithfulness_yield",
        EXPECTED_MODEL_ORDER[0],
        DEFAULT_TEMPLATE_SCOPE,
    )
    distribution = build_template_delta_distribution(
        cases,
        metric_id="end_to_end_faithfulness_yield",
        focus_label="Qwen3 8B · S1–S4 primary",
    )
    assert len(cases) == 36
    assert np.isfinite(cases["delta_value"]).all()
    assert "LLM narrative" in distribution.data[0].hovertemplate
    assert "Deterministic Template" in distribution.data[0].hovertemplate
    assert any(float(shape.x0) == 0 and float(shape.x1) == 0 for shape in distribution.layout.shapes)


def test_template_coverage_scatter_keeps_template_separate() -> None:
    repository = DashboardRepository()
    figure = build_template_coverage_scatter(
        repository.llm_vs_template_summary(),
        repository.baseline_option_performance(),
    )
    assert len(figure.data) == 4
    assert figure.data[-1].name == "Deterministic Template Baseline"
    assert figure.data[-1].marker.symbol == "diamond"
    assert len(figure.data[-1].x) == 6


def test_measurement_dumbbell_supports_single_model_display_scope() -> None:
    repository = DashboardRepository()
    summary = repository.measurement_shift_summary(
        DEFAULT_ROBUSTNESS_METRIC,
        EXPECTED_MODEL_ORDER[0],
    )
    figure = build_candidate_v4_dumbbell(
        summary,
        metric_id=DEFAULT_ROBUSTNESS_METRIC,
    )

    assert len(summary) == 6
    assert len(figure.data) == 3
    assert tuple(trace.name for trace in figure.data[1:]) == (
        "Qwen3 8B · Candidate",
        "Qwen3 8B · V4",
    )
    assert int(figure.layout.height) < 570


def test_template_matrix_uses_wrapped_labels_and_observed_pair_counts() -> None:
    repository = DashboardRepository()
    tests = repository.llm_vs_template_tests().copy()
    tests["model_label"] = tests["model_id"].map({
        "qwen3_8b": "Qwen3 8B",
        "deepseek_v4_flash": "DeepSeek V4 Flash",
        "phi4_mini_instruct": "Phi-4 Mini Instruct",
    })
    tests["model_order"] = tests["model_id"].map({
        "qwen3_8b": 1,
        "deepseek_v4_flash": 2,
        "phi4_mini_instruct": 3,
    })
    matrix = build_template_uplift_matrix(tests, evidence_scope="S4")

    assert all("<br>" in str(label) for label in matrix.layout.xaxis.ticktext)
    observed = set(matrix.data[0].customdata[:, :, 1].astype(int).ravel())
    assert observed.issuperset({29, 33, 36})
