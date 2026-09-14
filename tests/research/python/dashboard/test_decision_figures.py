"""Decision Studio figure contract tests."""

from __future__ import annotations

import pandas as pd

from research.python.dashboard.figures.decision import (
    FIG_DECISION_CRITERION_CONTRIBUTIONS,
    FIG_DECISION_TRADEOFF_MAP,
    FIG_DECISION_WHAT_IF_CONTRIBUTION_COMPARISON,
    build_certified_custom_contribution_comparison,
    build_criterion_contribution_profile,
    build_tradeoff_map,
)
from research.python.dashboard.settings import ANALYSIS_ROOT


def _directory():
    path = ANALYSIS_ROOT / "visualization_v2"
    return path if path.is_dir() else ANALYSIS_ROOT / "visualization"


def _scenario_options() -> pd.DataFrame:
    frame = pd.read_csv(_directory() / "scenario_options.csv")
    return frame.loc[frame["scenario_id"] == "BALANCED"].copy()


def _contributions() -> pd.DataFrame:
    frame = pd.read_csv(
        _directory() / "scenario_criterion_contributions.csv"
    )
    return frame.loc[frame["scenario_id"] == "BALANCED"].copy()


def test_tradeoff_map_contains_18_option_points_and_full_e2e_axis() -> None:
    options = _scenario_options()
    figure = build_tradeoff_map(
        options,
        x_metric="mean_latency_seconds_planned",
        recommended_option_id="deepseek_v4_flash__S2",
        alternative_option_id="qwen3_8b__S1",
    )
    option_points = sum(
        len(trace.x)
        for trace in figure.data
        if trace.hoverinfo != "skip"
    )
    assert option_points == 18
    assert tuple(figure.layout.yaxis.range) == (0, 1)
    assert figure.layout.meta["figure_id"] == FIG_DECISION_TRADEOFF_MAP
    assert not any(getattr(trace, "mode", "") == "lines" for trace in figure.data)
    role_traces = [trace for trace in figure.data if trace.name in {"Recommended", "Alternative"}]
    assert tuple(trace.mode for trace in role_traces) == ("markers", "markers")
    assert all(getattr(trace, "text", None) in (None, ()) for trace in role_traces)
    assert figure.layout.margin.b >= 90


def test_certified_contribution_profile_uses_weighted_contributions() -> None:
    contributions = _contributions()
    profile = contributions.loc[
        contributions["option_id"] == "deepseek_v4_flash__S2"
    ]
    figure = build_criterion_contribution_profile(profile)
    assert len(figure.data) == 1
    assert len(figure.data[0].x) == 8
    assert figure.layout.meta["figure_id"] == FIG_DECISION_CRITERION_CONTRIBUTIONS


def test_certified_custom_comparison_has_two_series() -> None:
    contributions = _contributions()
    profile = contributions.loc[
        contributions["option_id"] == "deepseek_v4_flash__S2"
    ].copy()
    custom = profile[["criterion_id", "normalized_value"]].copy()
    custom["custom_weight"] = 1 / len(custom)
    custom["custom_contribution"] = (
        custom["normalized_value"] * custom["custom_weight"]
    )
    figure = build_certified_custom_contribution_comparison(profile, custom)
    assert tuple(trace.name for trace in figure.data) == ("Certified", "Custom")
    assert (
        figure.layout.meta["figure_id"]
        == FIG_DECISION_WHAT_IF_CONTRIBUTION_COMPARISON
    )
