from __future__ import annotations

from pathlib import Path

from research.python.dashboard.v3.decision_model import SCENARIO_ORDER, build_decision_model
from research.python.dashboard.v3.figures import (
    decision_noninferiority_plot,
    decision_quality_efficiency_plot,
    decision_quality_reliability_plot,
    robustness_contrast_stability_map,
    robustness_effect_dumbbell,
    robustness_margin_sensitivity_plot,
    robustness_rank_shift_heatmap,
)
from research.python.dashboard.v3.repository import get_v3_repository
from research.python.dashboard.v3.robustness_model import build_robustness_model


def test_decision_redesign_preserves_certified_selection_path():
    model = build_decision_model(get_v3_repository(), "CROSS_DATASET", "vi")
    assert model.primary_margin == 0.03
    assert model.robust_status == "NO_ROBUST_RECOMMENDATION"
    assert model.decision_counts == {
        "total": 18,
        "home_credit_hard_gate": 15,
        "freddie_hard_gate": 16,
        "both_hard_gate": 14,
        "home_credit_ni": 2,
        "freddie_ni": 2,
        "robust_ni": 0,
        "robust_eligible": 0,
    }
    recommendations = {r["recommendation_scope"]: r for r in model.dataset_recommendations}
    assert recommendations["HOME_CREDIT_PRIMARY"]["option_id"] == "qwen3_8b::S1"
    assert recommendations["FREDDIE_PRIMARY"]["option_id"] == "qwen3_8b::S4"
    assert tuple(r["scenario_id"] for r in model.scenarios) == SCENARIO_ORDER
    assert all(r["pool_mode"] == "NONE" for r in model.scenarios)
    assert all(r["scenario_eligible_count"] == 0 for r in model.scenarios)
    assert all(r["utility_non_null_count"] == 0 for r in model.scenarios)


def test_decision_deep_link_state_is_sanitized_and_identity_preserved():
    repo = get_v3_repository()
    model = build_decision_model(
        repo,
        "CROSS_DATASET",
        "vi",
        search="?tab=tradeoffs&dataset=FREDDIE&model=qwen3_8b&evidence=S4&option=qwen3_8b::S4&scenario=QUALITY_FIRST",
    )
    assert model.initial_tab == "tradeoffs"
    assert model.focus_dataset == "FREDDIE"
    assert model.focus_model == "qwen3_8b"
    assert model.focus_evidence == "S4"
    assert model.focus_option == "qwen3_8b::S4"
    assert model.focus_scenario == "QUALITY_FIRST"
    invalid = build_decision_model(repo, "CROSS_DATASET", "vi", search="?tab=bad&model=bad&evidence=S9&scenario=BAD")
    assert invalid.initial_tab == "certified"
    assert invalid.focus_model is None and invalid.focus_evidence is None
    assert invalid.focus_scenario == "BALANCED"


def test_decision_figures_use_certified_rows_without_new_frontier():
    model = build_decision_model(get_v3_repository(), "CROSS_DATASET", "vi")
    ni = decision_noninferiority_plot(model.ni_rows, cross_dataset=True)
    quality = decision_quality_reliability_plot(model.options, selected_option="qwen3_8b::S1")
    efficiency = decision_quality_efficiency_plot(model.options, selected_option="qwen3_8b::S1")
    assert len(model.ni_rows) == 30
    assert len(ni.data) == 60
    assert tuple(quality.layout.xaxis.range) == (0, 1.02)
    assert tuple(quality.layout.yaxis.range) == (0, 1.02)
    assert len(quality.data) == 3 and len(efficiency.data) == 3
    assert all(not bool(row["is_pareto_optimal"]) for row in model.options)


def test_robustness_redesign_preserves_primary_and_sensitivity_boundaries():
    model = build_robustness_model(get_v3_repository(), "CROSS_DATASET", "vi")
    assert len(model.population_effects) == 6
    assert len(model.population_contrasts) == 66
    assert len(model.metric_rows) == 144
    assert sum(bool(r["direction_stable"]) for r in model.population_contrasts) == 60
    assert sum(bool(r["significance_conclusion_stable"]) for r in model.population_contrasts) == 64
    lanes = {round(float(r["margin"]), 2): r for r in model.margin_rows}
    assert set(lanes) == {0.02, 0.03, 0.05}
    assert lanes[0.03]["analysis_status"] == "PRIMARY_CERTIFIED"
    assert lanes[0.02]["analysis_status"] == lanes[0.05]["analysis_status"] == "SENSITIVITY_ONLY"
    assert int(lanes[0.03]["robust_primary_candidate_count"]) == 0
    assert int(lanes[0.05]["robust_primary_candidate_count"]) == 2
    assert model.validator_status == "NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3"
    assert model.template_status == "NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3"


def test_metric_rank_shifts_remain_certified_not_reranked():
    model = build_robustness_model(get_v3_repository(), "CROSS_DATASET", "vi")
    rows = list(model.metric_rows)
    by_key = {}
    for row in rows:
        by_key.setdefault((row["dataset_scope"], row["metric_id"]), []).append(abs(int(row["rank_shift_vs_primary"])))
    assert max(by_key[("HOME_CREDIT", "resolved_faithfulness")]) == 16
    assert max(by_key[("FREDDIE", "resolved_faithfulness")]) == 17
    assert max(by_key[("FREDDIE", "conservative_faithfulness")]) == 1


def test_robustness_figures_have_comparable_scales_and_primary_margin_marker():
    model = build_robustness_model(get_v3_repository(), "CROSS_DATASET", "vi")
    effect = robustness_effect_dumbbell(model.population_effects, cross_dataset=True)
    contrast = robustness_contrast_stability_map(model.population_contrasts, cross_dataset=True)
    heatmap = robustness_rank_shift_heatmap(model.metric_rows, cross_dataset=True)
    margin = robustness_margin_sensitivity_plot(model.margin_rows, selected_margin=0.03)
    assert tuple(effect.layout.xaxis.range) == (0, 1)
    assert tuple(effect.layout.xaxis2.range) == (0, 1)
    assert len(contrast.data) >= 2
    assert len(heatmap.data) == 2
    assert all(float(trace.zmin) == -18 and float(trace.zmax) == 18 for trace in heatmap.data)
    assert list(margin.data[0].x) == [0.02, 0.03, 0.05]
    assert list(margin.data[0].y) == [0, 0, 2]


def test_page45_source_isolation_and_runtime_contracts():
    paths = [
        Path("research/python/dashboard/v3/decision_model.py"),
        Path("research/python/dashboard/v3/robustness_model.py"),
        Path("research/python/dashboard/v3/pages/decision.py"),
        Path("research/python/dashboard/v3/pages/robustness.py"),
        Path("research/python/dashboard/v3/callbacks.py"),
    ]
    sources = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for forbidden in (
        "import scipy",
        "from scipy",
        "statsmodels",
        "wilcoxon(",
        "multipletests(",
        "visualization_v2",
        "get_dashboard_repository",
        "decision_support",
        "idxmax(",
        "argmax(",
    ):
        assert forbidden not in sources
    decision_page = Path("research/python/dashboard/v3/pages/decision.py").read_text(encoding="utf-8")
    robustness_page = Path("research/python/dashboard/v3/pages/robustness.py").read_text(encoding="utf-8")
    callbacks = Path("research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    assert "dmc.Tabs" not in decision_page + robustness_page
    assert "decision-detail-drawer-body-content" in decision_page
    assert "robustness-detail-drawer-body-content" in robustness_page
    assert "data-testid" in decision_page and "data-testid" in robustness_page
    assert callbacks.count('Input(LOCATION, "pathname")') >= 5
    assert callbacks.count('Input(LOCATION, "search")') >= 5
