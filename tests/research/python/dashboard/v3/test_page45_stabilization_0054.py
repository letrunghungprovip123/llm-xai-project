from __future__ import annotations

from pathlib import Path

from dash import dcc

from research.python.dashboard.v3.decision_model import build_decision_model
from research.python.dashboard.v3.pages import decision as decision_page
from research.python.dashboard.v3.pages import robustness as robustness_page
from research.python.dashboard.v3.repository import get_v3_repository
from research.python.dashboard.v3.robustness_model import build_robustness_model


def _walk(component):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for item in component:
            yield from _walk(item)
        return
    yield component
    children = getattr(component, "children", None)
    if children is not None:
        yield from _walk(children)


def _by_id(component, target):
    matches = [item for item in _walk(component) if getattr(item, "id", None) == target]
    assert len(matches) == 1, f"{target}: expected 1 component, found {len(matches)}"
    return matches[0]


def _links(component):
    return [item for item in _walk(component) if isinstance(item, dcc.Link)]


def test_page45_drawer_content_ids_are_portal_safe_and_owned_selectors_exist():
    for page in (decision_page, robustness_page):
        assert page.DETAIL_DRAWER_TITLE_ID != f"{page.DETAIL_DRAWER_ID}-title"
        assert page.DETAIL_DRAWER_BODY_ID != f"{page.DETAIL_DRAWER_ID}-body"
        assert page.DETAIL_DRAWER_TITLE_ID.endswith("-content")
        assert page.DETAIL_DRAWER_BODY_ID.endswith("-content")
    decision_source = Path(decision_page.__file__).read_text(encoding="utf-8")
    robustness_source = Path(robustness_page.__file__).read_text(encoding="utf-8")
    assert 'data-testid": "decision-drawer-content"' in decision_source
    assert 'data-testid": "robustness-drawer-content"' in robustness_source


def test_decision_deep_link_filters_initial_tradeoff_and_preserves_dataset_on_drills():
    model = build_decision_model(
        get_v3_repository(),
        "CROSS_DATASET",
        "vi",
        search="?tab=tradeoffs&dataset=FREDDIE&model=qwen3_8b&evidence=S4&option=qwen3_8b::S4",
    )
    page = decision_page.render(model)
    assert model.initial_tab == "tradeoffs"
    assert model.focus_dataset == "FREDDIE"

    qrel = _by_id(page, decision_page.QUALITY_RELIABILITY_ID)
    qeff = _by_id(page, decision_page.QUALITY_EFFICIENCY_ID)
    assert sum(len(trace.x) for trace in qrel.figure.data) == 1
    assert sum(len(trace.x) for trace in qeff.figure.data) == 1

    panel = _by_id(page, decision_page.TRADEOFF_OPTION_PANEL_ID)
    hrefs = [link.href for link in _links(panel)]
    assert any(href.startswith("/effectiveness?") and "dataset=FREDDIE" in href for href in hrefs)
    assert any(href.startswith("/robustness?") and "dataset=FREDDIE" in href for href in hrefs)
    assert any(href.startswith("/cases?") and "dataset=FREDDIE" in href for href in hrefs)

    store = _by_id(page, decision_page.SELECTED_OPTION_STORE_ID)
    assert store.data == {"option_id": "qwen3_8b::S4"}


def test_decision_scenario_deep_link_is_frozen_and_never_materializes_utility_score():
    model = build_decision_model(
        get_v3_repository(),
        "CROSS_DATASET",
        "vi",
        search="?tab=scenarios&scenario=QUALITY_FIRST",
    )
    page = decision_page.render(model)
    assert model.initial_tab == "scenarios"
    selector = _by_id(page, decision_page.SCENARIO_ID)
    assert selector.value == "QUALITY_FIRST"
    row = next(r for r in model.scenarios if r["scenario_id"] == "QUALITY_FIRST")
    assert row["pool_mode"] == "NONE"
    assert row["scenario_eligible_count"] == 0
    assert row["utility_non_null_count"] == 0


def test_robustness_metric_deep_link_uses_certified_rank_rows_without_reranking():
    model = build_robustness_model(
        get_v3_repository(),
        "CROSS_DATASET",
        "vi",
        search="?tab=metric&dataset=FREDDIE&model=qwen3_8b&evidence=S4&metric=resolved_faithfulness",
    )
    page = robustness_page.render(model)
    assert model.initial_tab == "metric"
    assert model.focus_dataset == "FREDDIE"
    assert model.focus_metric == "resolved_faithfulness"

    heatmap = _by_id(page, robustness_page.RANK_SHIFT_ID)
    # Cross scope keeps both study facets but filtering leaves exactly one certified option/metric row per study.
    assert len(heatmap.figure.data) == 2
    assert all(len(trace.z) == 1 for trace in heatmap.figure.data)
    source = Path(robustness_page.__file__).read_text(encoding="utf-8")
    assert ".rank(" not in source


def test_robustness_margin_deep_link_only_selects_a_frozen_certified_lane():
    model = build_robustness_model(
        get_v3_repository(),
        "CROSS_DATASET",
        "vi",
        search="?tab=decision&margin=0.05",
    )
    page = robustness_page.render(model)
    assert model.initial_tab == "decision"
    assert model.focus_margin == 0.05
    selector = _by_id(page, robustness_page.MARGIN_SELECT_ID)
    assert selector.value == "0.05"
    plot = _by_id(page, robustness_page.MARGIN_PLOT_ID)
    assert list(plot.figure.data[0].x) == [0.02, 0.03, 0.05]
    assert list(plot.figure.data[0].y) == [0, 0, 2]
    lane = next(row for row in model.margin_rows if float(row["margin"]) == 0.05)
    assert lane["analysis_status"] == "SENSITIVITY_ONLY"
    primary = next(row for row in model.margin_rows if float(row["margin"]) == 0.03)
    assert primary["analysis_status"] == "PRIMARY_CERTIFIED"


def test_page45_runtime_source_avoids_known_page23_failure_patterns():
    decision_source = Path(decision_page.__file__).read_text(encoding="utf-8")
    robustness_source = Path(robustness_page.__file__).read_text(encoding="utf-8")
    callbacks_source = Path("research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    source = decision_source + robustness_source

    assert "dmc.Tabs" not in source
    assert 'columnSize="sizeToFit"' not in source
    assert "component=\"a\"" not in source
    assert "dmc.Button" not in source or "href=" not in source
    assert callbacks_source.count('Input(LOCATION, "pathname")') >= 5
    assert callbacks_source.count('Input(LOCATION, "search")') >= 5


def test_app_v3_startup_registers_all_callback_import_contracts():
    # Regression for 0054a: callback registration must resolve every lazily imported page symbol.
    import importlib

    module = importlib.import_module("research.python.dashboard.app_v3")
    assert getattr(module, "app", None) is not None
