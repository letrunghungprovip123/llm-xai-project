"""Decision Studio i18n contracts and state-preservation tests."""

from __future__ import annotations

import json
from typing import Any

from plotly.utils import PlotlyJSONEncoder

from research.python.dashboard.callbacks.decision import (
    certified_updates,
    custom_updates,
    decision_figures,
)
from research.python.dashboard.data.repository import get_dashboard_repository
from research.python.dashboard.i18n import localize_component_tree, t
from research.python.dashboard.i18n.plotly_locale import (
    catalog_replacements,
    replace_catalog_text,
)
from research.python.dashboard.pages.decision import layout
from research.python.dashboard.settings import DEFAULT_DECISION_SCENARIO


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        output: list[str] = []
        for item in value:
            output.extend(_strings(item))
        return output
    if hasattr(value, "children"):
        return _strings(value.children)
    return []


def _figure_signature(figure) -> str:
    payload = figure.to_plotly_json()
    for key in ("title", "xaxis", "yaxis", "legend", "annotations"):
        payload.get("layout", {}).pop(key, None)
    for trace in payload.get("data", []):
        for key in (
            "name", "text", "hovertext", "hovertemplate", "texttemplate",
            "x", "y",
        ):
            trace.pop(key, None)
    return json.dumps(payload, cls=PlotlyJSONEncoder, sort_keys=True)


def test_decision_layout_defaults_to_vietnamese_and_can_render_english() -> None:
    vi_text = " ".join(_strings(layout()))
    en_text = " ".join(_strings(layout(locale="en")))
    assert "Không gian quyết định" in vi_text
    assert "Kịch bản đã chứng nhận" in vi_text
    assert "Decision Studio" in en_text
    assert "Certified scenarios" in en_text


def test_component_localizer_preserves_control_values() -> None:
    page = layout(tab="what-if", scenario="QUALITY_FIRST", x="mean_total_token_count_planned")
    localized = localize_component_tree(page, "en", prefixes=("decision.",))
    assert localized.id == page.id
    assert localized.to_plotly_json()["props"]["data-decision-mode"] == "what-if"


def test_certified_updates_translate_copy_without_analytical_drift() -> None:
    vi = certified_updates(DEFAULT_DECISION_SCENARIO, "mean_latency_seconds_planned", "vi")
    en = certified_updates(DEFAULT_DECISION_SCENARIO, "mean_latency_seconds_planned", "en")
    assert vi[0] != en[0]
    assert "Cân bằng" in vi[0] or "Cân bằng" in " ".join(_strings(vi[2]))
    assert _figure_signature(vi[1]) == _figure_signature(en[1])
    assert vi[1].layout.meta == en[1].layout.meta
    assert vi[6][0]["configuration"] == en[6][0]["configuration"]
    assert vi[6][0]["pareto_status"] != en[6][0]["pareto_status"]


def test_custom_what_if_preserves_ranking_and_link_across_locales() -> None:
    repository = get_dashboard_repository()
    weights = {item.criterion_id: item.default_weight * 100 for item in repository.decision_criteria()}
    vi = custom_updates(weights, "vi")
    en = custom_updates(weights, "en")
    assert vi[4] == en[4]
    assert _figure_signature(vi[1]) == _figure_signature(en[1])
    assert [row["rank"] for row in vi[3]] == [row["rank"] for row in en[3]]
    assert vi[3][0]["status"] != en[3][0]["status"]


def test_decision_figures_localize_visible_text_only() -> None:
    vi = decision_figures(locale="vi")
    en = decision_figures(locale="en")
    assert set(vi) == set(en)
    for figure_id in vi:
        assert vi[figure_id].layout.meta == en[figure_id].layout.meta
        assert _figure_signature(vi[figure_id]) == _figure_signature(en[figure_id])



def test_tradeoff_hover_preserves_missing_utility_rank_as_not_applicable() -> None:
    figures = decision_figures(locale="en")
    tradeoff = figures["FIG_DECISION_TRADEOFF_MAP"]
    hover_items = [
        str(item)
        for trace in tradeoff.data
        for item in (
            list(trace.hovertext)
            if getattr(trace, "hovertext", None) is not None
            else []
        )
    ]
    assert any("Utility rank: N/A" in item for item in hover_items)
    assert all("Utility rank: nan" not in item for item in hover_items)


def test_decision_catalog_contains_research_boundaries() -> None:
    assert "không phải xác suất" in t("vi", "decision.boundary_utility")
    assert "not a probability" in t("en", "decision.boundary_utility")
    assert "không xác lập ưu thế" in t("vi", "decision.pareto_boundary")


def test_decision_plotly_copy_is_fully_localized_and_word_safe() -> None:
    vi = decision_figures(locale="vi")
    tradeoff = vi["FIG_DECISION_TRADEOFF_MAP"]
    contribution = vi["FIG_DECISION_CRITERION_CONTRIBUTIONS"]
    comparison = vi["FIG_DECISION_WHAT_IF_CONTRIBUTION_COMPARISON"]

    assert tradeoff.layout.yaxis.title.text == "Độ trung thành vận hành E2E trung bình"
    assert any("bị chi phối" in str(trace.name) for trace in tradeoff.data)
    assert contribution.layout.xaxis.title.text == "Đóng góp có trọng số"
    assert comparison.layout.xaxis.title.text == "Đóng góp có trọng số"
    assert {str(trace.name) for trace in comparison.data} == {"Đã chứng nhận", "Tùy chỉnh"}
    hover_items = [
        item
        for trace in tradeoff.data
        for item in (
            list(trace.hovertext) if getattr(trace, "hovertext", None) is not None else []
        )
    ]
    assert all("True" not in str(item) and "False" not in str(item) for item in hover_items)
    assert any("Tối đa hóa" in str(item) or "Tối thiểu hóa" in str(item) for item in contribution.data[0].hovertext)
    assert all("Mean resolved-error loss" not in str(item) for item in contribution.data[0].y)
    assert all("Strong safe-phrase signal share" not in str(item) for item in contribution.data[0].y)

    assert replace_catalog_text("Not applicable", {"No": "Không"}) == "Not applicable"
