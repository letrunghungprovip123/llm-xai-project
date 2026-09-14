from __future__ import annotations

from urllib.parse import urlencode

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from research.python.dashboard.theme import PLOTLY_CONFIG

from ..effectiveness_model import EffectivenessModelV3, MODEL_LABELS
from ..figures import (
    effectiveness_contrast_plot,
    effectiveness_effect_size_plot,
    effectiveness_evidence_profiles,
    effectiveness_metric_matrix,
    effectiveness_reliability_map,
)

CONTENT_ID = "v3-effectiveness-content"
TABS_ID = "effectiveness-tabs"
PRIMARY_PANEL_ID = "effectiveness-tab-primary-panel"
SECONDARY_PANEL_ID = "effectiveness-tab-secondary-panel"
STATISTICS_PANEL_ID = "effectiveness-tab-statistics-panel"
MODEL_FILTER_ID = "effectiveness-model-filter"
EVIDENCE_FILTER_ID = "effectiveness-evidence-filter"
RELIABILITY_ID = "effectiveness-reliability-map"
EVIDENCE_PROFILE_ID = "effectiveness-evidence-response-profiles"
METRIC_MATRIX_ID = "effectiveness-metric-matrix"
EFFECT_SIZE_ID = "effectiveness-major-effects"
CONTRAST_FAMILY_ID = "effectiveness-contrast-family"
CONTRAST_PLOT_ID = "effectiveness-contrast-effect-plot"
CONTRAST_GRID_ID = "effectiveness-contrast-grid"
OPTION_PANEL_ID = "effectiveness-selected-option"
DETAIL_DRAWER_ID = "effectiveness-detail-drawer"
DETAIL_DRAWER_TITLE_ID = "effectiveness-detail-drawer-title-content"
DETAIL_DRAWER_BODY_ID = "effectiveness-detail-drawer-body-content"


def register_page() -> None:
    dash.register_page(
        "llm_xai_dashboard_v3.effectiveness",
        path="/effectiveness",
        name="Effectiveness",
        title="Effectiveness · LLM–XAI Research Dashboard",
        order=1,
        layout=layout,
    )


def _provenance(label: str):
    return dmc.Tooltip(
        dmc.ActionIcon(
            DashIconify(icon="solar:info-circle-linear", width=17),
            variant="subtle",
            color="gray",
            size="sm",
            radius="xl",
            **{"aria-label": "Xem provenance"},
        ),
        label=label,
        multiline=True,
        w=340,
        position="left",
        withArrow=True,
    )


def _chart_panel(*, graph_id: str, title: str, subtitle: str, source: str, figure, class_name: str = ""):
    classes = "effectiveness-chart"
    if class_name:
        classes += f" {class_name}"
    height = int(figure.layout.height or 360)
    return html.Section(
        [
            html.Div(
                [
                    html.Div([html.H2(title, className="analysis-chart__title"), html.P(subtitle, className="analysis-chart__subtitle")]),
                    _provenance(source),
                ],
                className="analysis-chart__header",
            ),
            dcc.Graph(
                id=graph_id,
                figure=figure,
                config=PLOTLY_CONFIG,
                responsive=True,
                clear_on_unhover=False,
                className="analysis-chart__graph",
                style={"height": f"{height}px", "minHeight": f"{height}px"},
            ),
        ],
        className=classes,
    )


def _filters(model: EffectivenessModelV3):
    model_data = [{"value": "ALL", "label": "Tất cả model"}] + [
        {"value": model_id, "label": label} for model_id, label in MODEL_LABELS.items()
    ]
    evidence_data = [{"value": "ALL", "label": "Tất cả Evidence"}] + [
        {"value": f"S{i}", "label": f"S{i}"} for i in range(6)
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Bộ lọc descriptive", className="analysis-filter-bar__label"),
                    dmc.Select(id=MODEL_FILTER_ID, data=model_data, value=model.focus_model or "ALL", allowDeselect=False, w=210, size="sm"),
                    dmc.Select(id=EVIDENCE_FILTER_ID, data=evidence_data, value=model.focus_evidence or "ALL", allowDeselect=False, w=185, size="sm"),
                ],
                className="analysis-filter-bar__controls",
            ),
            html.Div(
                [DashIconify(icon="solar:info-circle-linear", width=15), html.Span("Major Effects vẫn là full-study tests; filter không tái tính F, p hoặc Partial η².")],
                className="analysis-filter-bar__note",
            ),
        ],
        className="analysis-filter-bar",
    )


def _find_initial_option(model: EffectivenessModelV3):
    rows = list(model.option_rows)
    if model.focus_model or model.focus_evidence:
        focused = [
            row for row in rows
            if (not model.focus_model or str(row["model_id"]) == model.focus_model)
            and (not model.focus_evidence or str(row["evidence_level"]) == model.focus_evidence)
        ]
        if focused:
            rows = focused
    return min(rows, key=lambda row: (int(row.get("quality_rank", 999)), str(row.get("dataset_scope")))) if rows else None


def option_panel(row: dict | None):
    if not row:
        return html.Div(
            [html.Span("Selected option", className="analysis-eyebrow"), html.H3("Chọn một điểm trên Reliability Map", className="analysis-side-panel__title"), html.P("Click một option để xem exact certified values và drill-through.", className="analysis-side-panel__text")],
            className="analysis-side-panel__empty",
        )
    dataset = str(row.get("dataset_label") or row.get("dataset_scope") or "")
    model_label = str(row.get("model_label") or row.get("model_id") or "")
    evidence = str(row.get("evidence_level") or "")
    query = urlencode({"dataset": row.get("dataset_scope"), "model": row.get("model_id"), "evidence": evidence})
    metrics = (
        ("Mean E2E", row.get("mean_e2e_display") or f"{float(row.get('mean_e2e', 0)):.2%}"),
        ("P10 E2E", row.get("p10_e2e_display") or f"{float(row.get('p10_e2e', 0)):.2%}"),
        ("Median", row.get("median_e2e_display") or f"{float(row.get('median_e2e', 0)):.2%}"),
        ("Usability", row.get("usability_rate_display") or row.get("usability_display") or f"{float(row.get('usability_rate', 0)):.2%}"),
    )
    return html.Div(
        [
            html.Span("Selected option", className="analysis-eyebrow"),
            html.H3(f"{model_label} × {evidence}", className="analysis-side-panel__title"),
            html.Div(dataset, className="analysis-side-panel__dataset"),
            html.Div([html.Div([html.Span(label), html.Strong(str(value))], className="analysis-side-panel__metric") for label, value in metrics], className="analysis-side-panel__metrics"),
            html.Div(
                [
                    html.Span(f"Rank #{int(row.get('quality_rank', 0))}"),
                    html.Span(str(row.get("option_role", ""))),
                    html.Span(f"Usable {int(row.get('usable_generation_count', 0))}/{int(row.get('planned_generation_count', 0))}"),
                ],
                className="analysis-side-panel__chips",
            ),
            html.P("Primary performance được đọc trực tiếp từ certified option_performance; dashboard không recompute metric.", className="analysis-side-panel__text"),
            html.Div(
                [
                    dcc.Link("Mở Mechanisms", href=f"/mechanisms?tab=quality&{query}", className="analysis-link-button analysis-link-button--filled"),
                    dcc.Link("Mở Case Explorer", href=f"/cases?{query}", className="analysis-link-button analysis-link-button--light"),
                ],
                className="analysis-side-panel__actions",
            ),
        ],
        className="analysis-side-panel__body",
    )


def _metric_context(model: EffectivenessModelV3):
    dictionary = {str(row["metric_id"]): row for row in model.metric_dictionary_rows}
    items = [
        ("End-to-End Faithfulness", "end_to_end_faithfulness_yield", "PRIMARY"),
        ("Resolved Faithfulness", "resolved_faithfulness", "SECONDARY"),
        ("Verifiability", "verifiability", "SECONDARY"),
        ("Conservative Faithfulness", "conservative_faithfulness", "SECONDARY"),
    ]
    cards = []
    for label, metric_id, role in items:
        meta = dictionary.get(metric_id, {})
        cards.append(html.Div([html.Div([html.Strong(label), html.Span(role, className=f"metric-role metric-role--{role.lower()}")], className="metric-context__head"), html.Div([html.Span(str(meta.get("family", "—"))), html.Span(str(meta.get("unit", "—")))], className="metric-context__meta")], className="metric-context__item"))
    return html.Div(cards, className="metric-context-grid")


def _contrast_rows(model: EffectivenessModelV3):
    return [dict(row) for row in model.contrast_rows]


def filter_option_rows(rows, model_id: str | None = None, evidence: str | None = None) -> list[dict]:
    selected = [dict(row) for row in rows]
    if model_id and model_id != "ALL":
        selected = [row for row in selected if str(row.get("model_id")) == str(model_id)]
    if evidence and evidence != "ALL":
        selected = [row for row in selected if str(row.get("evidence_level")) == str(evidence)]
    return selected


def filter_metric_rows(rows, model_id: str | None = None, evidence: str | None = None) -> list[dict]:
    selected = [dict(row) for row in rows]
    if model_id and model_id != "ALL":
        selected = [row for row in selected if str(row.get("model_id")) == str(model_id)]
    if evidence and evidence != "ALL":
        selected = [row for row in selected if str(row.get("evidence_level")) == str(evidence)]
    return selected


def filter_contrast_rows(
    rows,
    family: str = "evidence_vs_s0",
    model_id: str | None = None,
    evidence: str | None = None,
) -> list[dict]:
    selected = [dict(row) for row in rows]
    if family != "all":
        selected = [row for row in selected if str(row.get("contrast_family")) == str(family)]
    if model_id and model_id != "ALL":
        selected = [
            row for row in selected
            if str(row.get("condition_a_model_id")) == str(model_id)
            or str(row.get("condition_b_model_id")) == str(model_id)
            or str(row.get("context_model_id")) == str(model_id)
        ]
    if evidence and evidence != "ALL":
        selected = [
            row for row in selected
            if str(row.get("condition_a_evidence_level")) == str(evidence)
            or str(row.get("condition_b_evidence_level")) == str(evidence)
            or str(row.get("context_evidence_level")) == str(evidence)
        ]
    return selected


def best_option_row(rows, dataset_scope: str | None = None) -> dict | None:
    selected = [dict(row) for row in rows]
    if dataset_scope in {"HOME_CREDIT", "FREDDIE"}:
        focused = [row for row in selected if str(row.get("dataset_scope")) == dataset_scope]
        if focused:
            selected = focused
    if not selected:
        return None
    return min(
        selected,
        key=lambda row: (
            int(row.get("quality_rank", 999)),
            str(row.get("dataset_scope", "")),
            str(row.get("model_id", "")),
            str(row.get("evidence_level", "")),
        ),
    )


def contrast_grid_records(rows: list[dict]) -> list[dict]:
    clean = []
    for row in rows:
        clean.append({
            "dataset": row.get("dataset_label"),
            "family": row.get("contrast_family"),
            "contrast": row.get("contrast_label"),
            "mean_difference": row.get("mean_difference"),
            "adjusted_p": row.get("adjusted_p_value"),
            "rank_biserial": row.get("rank_biserial_correlation"),
            "planned": row.get("planned_pair_count"),
            "observed": row.get("observed_pair_count"),
            "excluded": row.get("excluded_pair_count"),
            "significant": bool(row.get("significant_adjusted")),
        })
    return clean


def contrast_grid(rows: list[dict]):
    return dag.AgGrid(
        id=CONTRAST_GRID_ID,
        rowData=contrast_grid_records(rows),
        columnDefs=[
            {"field": "dataset", "headerName": "Dataset", "minWidth": 115},
            {"field": "family", "headerName": "Contrast family", "minWidth": 155},
            {"field": "contrast", "headerName": "Planned contrast", "minWidth": 260, "flex": 2},
            {"field": "mean_difference", "headerName": "Mean Δ", "valueFormatter": {"function": "params.value == null ? '—' : Number(params.value).toFixed(4)"}},
            {"field": "adjusted_p", "headerName": "Holm p", "valueFormatter": {"function": "params.value == null ? '—' : (Number(params.value) < 0.0001 ? '<0.0001' : Number(params.value).toFixed(4))"}},
            {"field": "rank_biserial", "headerName": "Rank-biserial", "valueFormatter": {"function": "params.value == null ? '—' : Number(params.value).toFixed(3)"}},
            {"field": "observed", "headerName": "Observed"},
            {"field": "excluded", "headerName": "Excluded"},
            {"field": "significant", "headerName": "Holm significant"},
        ],
        defaultColDef={"sortable": True, "filter": True, "resizable": True, "minWidth": 95},
        dashGridOptions={"pagination": True, "paginationPageSize": 12, "paginationPageSizeSelector": False, "animateRows": False, "suppressCellFocus": True},
        className="ag-theme-quartz research-data-grid",
        style={"height": "420px", "width": "100%"},
    )


def _page_header(model: EffectivenessModelV3):
    scope_label = "Cross-dataset" if model.scope == "CROSS_DATASET" else ("Home Credit" if model.scope == "HOME_CREDIT" else "Freddie Mac")
    return html.Header(
        [
            html.Div(
                [
                    html.Div([html.Span("RQ · Effectiveness", className="analysis-eyebrow"), html.Span("PRIMARY: End-to-End Faithfulness", className="analysis-lane-badge")], className="analysis-page-header__eyebrow"),
                    html.H1("Effectiveness", className="analysis-page-header__title"),
                    html.P("Model × Evidence configuration nào tạo explanation tốt hơn, lower-tail reliability có đi cùng average performance hay không, và certified statistical evidence mạnh đến mức nào?", className="analysis-page-header__subtitle"),
                ]
            ),
            html.Div(
                [
                    html.Div([html.Span("Phạm vi"), html.Strong(scope_label)], className="analysis-context-pill"),
                    html.Div([html.Span("Experiment"), html.Strong("3 models × S0–S5")], className="analysis-context-pill"),
                    html.Div([html.Span("Statistics"), html.Strong("3 effects · 33 contrasts/study")], className="analysis-context-pill"),
                ],
                className="analysis-page-header__context",
            ),
        ],
        className="analysis-page-header",
    )


def tab_panel_style(active_tab: str | None, panel: str) -> dict[str, str]:
    active = active_tab if active_tab in {"primary", "secondary", "statistics"} else "primary"
    return {"display": "block" if active == panel else "none", "width": "100%"}


def render(model: EffectivenessModelV3):
    cross = model.scope == "CROSS_DATASET"
    visible_options = filter_option_rows(model.option_rows, model.focus_model, model.focus_evidence)
    visible_metrics = filter_metric_rows(model.secondary_metric_rows, model.focus_model, model.focus_evidence)
    visible_contrasts = filter_contrast_rows(
        model.contrast_rows,
        "evidence_vs_s0",
        model.focus_model,
        model.focus_evidence,
    )
    reliability = effectiveness_reliability_map(visible_options, cross_dataset=cross)
    profiles = effectiveness_evidence_profiles(visible_options, cross_dataset=cross)
    matrix = effectiveness_metric_matrix(visible_metrics, cross_dataset=cross)
    effects = effectiveness_effect_size_plot(model.effect_rows, cross_dataset=cross)
    contrasts = effectiveness_contrast_plot(visible_contrasts, cross_dataset=cross, family="all")
    initial = best_option_row(visible_options, model.focus_dataset)

    return html.Main(
        [
            _page_header(model),
            _filters(model),
            html.Div(
                [
                    dmc.SegmentedControl(
                        id=TABS_ID,
                        value=model.initial_tab,
                        data=[
                            {"value": "primary", "label": "Primary performance"},
                            {"value": "secondary", "label": "Secondary metrics"},
                            {"value": "statistics", "label": "Statistical evidence"},
                        ],
                        radius="xl",
                        size="sm",
                        className="analysis-tab-switcher__control",
                        **{"aria-label": "Effectiveness analytical section"},
                    )
                ],
                className="analysis-tab-switcher",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            _chart_panel(graph_id=RELIABILITY_ID, title="Reliability Map", subtitle="Mean E2E × P10 E2E; góc trên-phải đồng thời tốt về average performance và lower-tail reliability.", source="Certified table: option_performance", figure=reliability, class_name="effectiveness-chart--reliability"),
                            html.Aside(option_panel(initial), id=OPTION_PANEL_ID, className="analysis-side-panel"),
                        ],
                        className="effectiveness-primary-grid",
                    ),
                    _chart_panel(graph_id=EVIDENCE_PROFILE_ID, title="Evidence Response Profiles", subtitle="S0–S5 là categorical evidence conditions; đường nối chỉ giúp theo dõi visual pattern. Error bars là certified bootstrap CI.", source="Certified table: option_performance", figure=profiles, class_name="effectiveness-chart--profiles"),
                ],
                id=PRIMARY_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "primary"),
            ),
            html.Div(
                [
                    _chart_panel(graph_id=METRIC_MATRIX_ID, title="Option × Metric matrix", subtitle="E2E là primary endpoint; Resolved Faithfulness, Verifiability và Conservative Faithfulness là secondary analytical lenses.", source="Certified table: metric_sensitivity", figure=matrix, class_name="effectiveness-chart--matrix"),
                    _metric_context(model),
                ],
                id=SECONDARY_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "secondary"),
            ),
            html.Div(
                [
                    html.Div(
                        [
                            _chart_panel(graph_id=EFFECT_SIZE_ID, title="Major Effects", subtitle="Partial η² từ certified repeated-measures omnibus analysis. Filter descriptive phía trên không thay đổi chart này.", source="Certified table: omnibus_effects", figure=effects, class_name="effectiveness-chart--effects"),
                            html.Section(
                                [
                                    html.Span("Statistical protocol", className="analysis-eyebrow"),
                                    html.H3("Full-study inference", className="analysis-side-panel__title"),
                                    html.P("Model, Evidence và Model × Evidence được đọc nguyên trạng từ omnibus_effects. Dashboard không chạy ANOVA, Greenhouse–Geisser hay multiple-testing correction.", className="analysis-side-panel__text"),
                                    html.Div([html.Strong("33"), html.Span("planned contrasts / study")], className="analysis-protocol-stat"),
                                    html.Div([html.Strong("Holm"), html.Span("adjustment đã chứng nhận")], className="analysis-protocol-stat"),
                                ],
                                className="analysis-side-panel analysis-protocol-panel",
                            ),
                        ],
                        className="effectiveness-stat-grid",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div([html.H2("Contrast Effect Plot", className="analysis-chart__title"), html.P("Filled = significant sau Holm; hollow = not significant. Mean Δ = condition A − condition B.", className="analysis-chart__subtitle")]),
                                    dmc.SegmentedControl(
                                        id=CONTRAST_FAMILY_ID,
                                        value="evidence_vs_s0",
                                        data=[
                                            {"value": "evidence_vs_s0", "label": "Evidence vs S0"},
                                            {"value": "model_within_evidence", "label": "Model within Evidence"},
                                            {"value": "all", "label": "Tất cả"},
                                        ],
                                        size="xs",
                                        radius="xl",
                                    ),
                                ],
                                className="analysis-chart__header analysis-chart__header--controls",
                            ),
                            dcc.Graph(id=CONTRAST_PLOT_ID, figure=contrasts, config=PLOTLY_CONFIG, responsive=True, clear_on_unhover=False, className="analysis-chart__graph", style={"height": f"{int(contrasts.layout.height or 420)}px", "minHeight": f"{int(contrasts.layout.height or 420)}px"}),
                            html.Details([html.Summary("Xem exact planned contrasts"), html.Div(contrast_grid(visible_contrasts), className="analysis-grid-wrap")], className="analysis-details"),
                        ],
                        className="effectiveness-chart effectiveness-chart--contrasts",
                    ),
                ],
                id=STATISTICS_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "statistics"),
            ),
            html.Div([DashIconify(icon="solar:shield-check-linear", width=16), html.Span("Certified presentation source · Không recompute science trong UI")], className="analysis-certified-footer"),
            dmc.Drawer(
                html.Div(id=DETAIL_DRAWER_BODY_ID),
                id=DETAIL_DRAWER_ID,
                title=html.Div(id=DETAIL_DRAWER_TITLE_ID),
                opened=False,
                position="right",
                size="md",
                padding="xl",
                overlayProps={"backgroundOpacity": 0.25, "blur": 2},
            ),
        ],
        className=f"research-page analysis-page effectiveness-page--redesign analysis-page--{'cross' if cross else 'study'}",
    )


def option_from_reliability_click(click_data: dict | None) -> dict | None:
    if not click_data or not click_data.get("points"):
        return None
    point = click_data["points"][0]
    custom = list(point.get("customdata") or [])
    if len(custom) < 13:
        return None
    return {
        "dataset_scope": str(custom[0]),
        "dataset_label": "Home Credit" if str(custom[0]) == "HOME_CREDIT" else "Freddie Mac",
        "model_id": str(custom[1]),
        "model_label": str(custom[2]),
        "evidence_level": str(custom[3]),
        "mean_e2e": float(point.get("x", 0)),
        "p10_e2e": float(point.get("y", 0)),
        "median_e2e": float(custom[4]),
        "bootstrap_ci_lower": float(custom[5]),
        "bootstrap_ci_upper": float(custom[6]),
        "usability_rate": float(custom[7]),
        "quality_rank": int(custom[8]),
        "option_role": str(custom[9]),
        "planned_generation_count": int(custom[10]),
        "usable_generation_count": int(custom[11]),
        "mean_e2e_report_number_id": str(custom[12]),
    }


def option_drawer(row: dict):
    query = urlencode({"dataset": row["dataset_scope"], "model": row["model_id"], "evidence": row["evidence_level"]})
    title = f"{row['model_label']} × {row['evidence_level']}"
    body = html.Div(
        [
            html.Div(row["dataset_label"], className="overview-drawer__dataset"),
            html.Div([html.Span("Mean E2E"), html.Strong(f"{row['mean_e2e']:.2%}")], className="overview-drawer__metric"),
            html.Div([html.Span("P10 E2E"), html.Strong(f"{row['p10_e2e']:.2%}")], className="overview-drawer__metric"),
            html.Div([html.Span("Bootstrap 95% CI"), html.Strong(f"[{row['bootstrap_ci_lower']:.2%}, {row['bootstrap_ci_upper']:.2%}]")], className="overview-drawer__metric"),
            html.P(f"Provenance: {row['mean_e2e_report_number_id']}", className="overview-drawer__note"),
            html.Div([dcc.Link("Mở Mechanisms", href=f"/mechanisms?tab=quality&{query}", className="analysis-link-button analysis-link-button--filled"), dcc.Link("Mở Case Explorer", href=f"/cases?{query}", className="analysis-link-button analysis-link-button--light")], className="overview-drawer__actions"),
        ],
        className="overview-drawer",
    )
    return title, body


def contrast_drawer(click_data: dict | None):
    if not click_data or not click_data.get("points"):
        return None
    point = click_data["points"][0]
    custom = list(point.get("customdata") or [])
    if len(custom) < 6:
        return None
    title = str(point.get("y") or "Planned contrast")
    body = html.Div(
        [
            html.Div([html.Span("Mean Δ"), html.Strong(f"{float(point.get('x', 0)):.4f}")], className="overview-drawer__metric"),
            html.Div([html.Span("Holm-adjusted p"), html.Strong(str(custom[0]))], className="overview-drawer__metric"),
            html.Div([html.Span("Rank-biserial"), html.Strong(f"{float(custom[1]):.3f}")], className="overview-drawer__metric"),
            html.P(f"Observed pairs {int(custom[3])}/{int(custom[2])}; excluded {int(custom[4])}. Adjusted significant: {bool(custom[5])}.", className="overview-drawer__note"),
            html.P("Exact values đến trực tiếp từ planned_contrasts; không có statistical recomputation trong dashboard.", className="overview-drawer__note"),
        ],
        className="overview-drawer",
    )
    return title, body


def layout(**_):
    return html.Div(id=CONTENT_ID)
