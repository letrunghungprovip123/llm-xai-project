from __future__ import annotations

from dash import dcc

from research.python.dashboard.v3.cases_model import parse_cases_search
from research.python.dashboard.v3.effectiveness_model import build_effectiveness_model
from research.python.dashboard.v3.mechanisms_model import build_mechanisms_model
from research.python.dashboard.v3.pages import effectiveness as effectiveness_page
from research.python.dashboard.v3.pages import mechanisms as mechanisms_page
from research.python.dashboard.v3.pages import overview as overview_page
from research.python.dashboard.v3.repository import get_v3_repository


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


def test_drawer_content_ids_do_not_collide_with_mantine_generated_ids():
    for page in (overview_page, effectiveness_page, mechanisms_page):
        assert page.DETAIL_DRAWER_TITLE_ID != f"{page.DETAIL_DRAWER_ID}-title"
        assert page.DETAIL_DRAWER_BODY_ID != f"{page.DETAIL_DRAWER_ID}-body"
        assert page.DETAIL_DRAWER_TITLE_ID.endswith("-content")
        assert page.DETAIL_DRAWER_BODY_ID.endswith("-content")


def test_effectiveness_deep_link_filters_initial_figures_and_preserves_dataset_identity():
    repo = get_v3_repository()
    model = build_effectiveness_model(
        repo,
        "CROSS_DATASET",
        "vi",
        search="?tab=primary&dataset=FREDDIE&model=qwen3_8b&evidence=S1",
    )
    assert model.focus_dataset == "FREDDIE"
    visible = effectiveness_page.filter_option_rows(
        model.option_rows, model.focus_model, model.focus_evidence
    )
    assert len(visible) == 2
    assert effectiveness_page.best_option_row(visible, model.focus_dataset)["dataset_scope"] == "FREDDIE"

    page = effectiveness_page.render(model)
    graph = _by_id(page, effectiveness_page.RELIABILITY_ID)
    assert sum(len(trace.x) for trace in graph.figure.data) == 2

    grid = _by_id(page, effectiveness_page.CONTRAST_GRID_ID)
    # Evidence-vs-S0 + Qwen + S1 => one planned contrast per study.
    assert len(grid.rowData) == 2

    panel = _by_id(page, effectiveness_page.OPTION_PANEL_ID)
    hrefs = [link.href for link in _links(panel)]
    assert any("dataset=FREDDIE" in href and href.startswith("/mechanisms?") for href in hrefs)
    assert any("dataset=FREDDIE" in href and href.startswith("/cases?") for href in hrefs)


def test_mechanisms_deep_link_filters_initial_quality_and_preserves_dataset_identity():
    repo = get_v3_repository()
    model = build_mechanisms_model(
        repo,
        "CROSS_DATASET",
        "vi",
        search="?tab=quality&dataset=FREDDIE&model=qwen3_8b&evidence=S1",
    )
    assert model.initial_tab == "quality"
    assert model.focus_dataset == "FREDDIE"
    visible = mechanisms_page.filter_quality_rows(
        model.quality_rows, model.focus_model, model.focus_evidence
    )
    assert len(visible) == 2
    assert mechanisms_page.best_quality_row(visible, model.focus_dataset)["dataset_scope"] == "FREDDIE"

    page = mechanisms_page.render(model)
    graph = _by_id(page, mechanisms_page.QUALITY_MAP_ID)
    assert sum(len(trace.x) for trace in graph.figure.data) == 2

    panel = _by_id(page, mechanisms_page.QUALITY_PANEL_ID)
    hrefs = [link.href for link in _links(panel)]
    assert any("dataset=FREDDIE" in href and href.startswith("/effectiveness?") for href in hrefs)
    assert any("dataset=FREDDIE" in href and href.startswith("/cases?") for href in hrefs)


def test_cases_query_parser_accepts_page23_drill_through_identity():
    assert parse_cases_search(
        "?dataset=FREDDIE&model=qwen3_8b&evidence=S1"
    ) == ("FREDDIE", None, "qwen3_8b", "S1")
    assert parse_cases_search(
        "?dataset=HOME_CREDIT&case_id=HC_001&model=phi4_mini_instruct&evidence=S5"
    ) == ("HOME_CREDIT", "HC_001", "phi4_mini_instruct", "S5")
    assert parse_cases_search(
        "?dataset=BAD&model=BAD&evidence=S99"
    ) == (None, None, None, None)


def test_hidden_tab_grids_do_not_use_size_to_fit():
    effect_source = effectiveness_page.__file__
    mech_source = mechanisms_page.__file__
    from pathlib import Path
    assert 'columnSize="sizeToFit"' not in Path(effect_source).read_text(encoding="utf-8")
    assert 'columnSize="sizeToFit"' not in Path(mech_source).read_text(encoding="utf-8")


def test_page_render_callbacks_listen_to_both_pathname_and_search():
    from pathlib import Path
    import research.python.dashboard.v3.callbacks as callbacks

    source = Path(callbacks.__file__).read_text(encoding="utf-8")
    assert source.count('Input(LOCATION, "pathname")') >= 3
    assert source.count('Input(LOCATION, "search")') >= 3
