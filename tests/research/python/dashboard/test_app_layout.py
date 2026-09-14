"""Dash/DMC smoke tests for the certified AppShell and Page 1."""

from __future__ import annotations

import dash

from research.python.dashboard.app import app
from research.python.dashboard.ids import OVERVIEW_PAGE_ID


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "to_plotly_json"):
                yield from _walk(child)
    elif hasattr(children, "to_plotly_json"):
        yield from _walk(children)


def test_app_registers_exactly_seven_official_pages() -> None:
    registered_paths = {
        page["path"]
        for page in dash.page_registry.values()
        if page["module"].startswith("llm_xai_dashboard.")
    }
    assert registered_paths == {
        "/",
        "/effectiveness",
        "/mechanisms",
        "/decision",
        "/robustness",
        "/cases",
        "/methods",
    }


def test_overview_layout_contains_six_kpis_and_two_graphs() -> None:
    page = dash.page_registry["llm_xai_dashboard.overview"]
    layout = page["layout"]()
    components = list(_walk(layout))
    assert any(getattr(item, "id", None) == OVERVIEW_PAGE_ID for item in components)
    metric_cards = [
        item
        for item in components
        if "metric-card"
        in str(getattr(item, "className", "")).split()
    ]
    graphs = [item for item in components if item.__class__.__name__ == "Graph"]
    assert len(metric_cards) == 6
    assert len(graphs) == 2
