from __future__ import annotations

from urllib.parse import urlencode

import dash
import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from research.python.dashboard.theme import PLOTLY_CONFIG

from ..decision_model import DecisionModelV3, SCENARIO_ORDER
from ..effectiveness_model import MODEL_LABELS
from ..figures import (
    decision_noninferiority_plot,
    decision_quality_efficiency_plot,
    decision_quality_reliability_plot,
)


CONTENT_ID = "v3-decision-content"
TABS_ID = "decision-tabs"
CERTIFIED_PANEL_ID = "decision-tab-certified-panel"
TRADEOFF_PANEL_ID = "decision-tab-tradeoffs-panel"
SCENARIO_PANEL_ID = "decision-tab-scenarios-panel"
MODEL_FILTER_ID = "decision-model-filter"
EVIDENCE_FILTER_ID = "decision-evidence-filter"
NI_PLOT_ID = "decision-ni-evidence"
QUALITY_RELIABILITY_ID = "decision-quality-reliability"
QUALITY_EFFICIENCY_ID = "decision-quality-efficiency"
OPTION_PANEL_ID = "decision-selected-option"
TRADEOFF_OPTION_PANEL_ID = "decision-tradeoff-selected-option"
SELECTED_OPTION_STORE_ID = "decision-selected-option-store"
SCENARIO_ID = "decision-scenario-select"
SCENARIO_DETAIL_ID = "decision-scenario-detail"
DETAIL_DRAWER_ID = "decision-detail-drawer"
DETAIL_DRAWER_TITLE_ID = "decision-detail-drawer-title-content"
DETAIL_DRAWER_BODY_ID = "decision-detail-drawer-body-content"

SCENARIO_LABELS = {
    "QUALITY_FIRST": "Quality first",
    "RELIABILITY_FIRST": "Reliability first",
    "BALANCED": "Balanced",
    "EFFICIENCY_AWARE": "Efficiency aware",
    "INDEPENDENCE_SENSITIVE": "Independence sensitive",
}


def register_page() -> None:
    dash.register_page(
        "llm_xai_dashboard_v3.decision",
        path="/decision",
        name="Decision",
        title="Decision Studio · LLM–XAI Research Dashboard",
        order=3,
        layout=layout,
    )


def _chart_panel(*, graph_id: str, title: str, subtitle: str, source: str, figure, class_name: str = ""):
    height = int(figure.layout.height or 380)
    classes = "decision-chart"
    if class_name:
        classes += f" {class_name}"
    return html.Section(
        [
            html.Div(
                [
                    html.Div([html.H2(title, className="analysis-chart__title"), html.P(subtitle, className="analysis-chart__subtitle")]),
                    dmc.Tooltip(
                        dmc.ActionIcon(DashIconify(icon="solar:info-circle-linear", width=17), variant="subtle", color="gray", size="sm", radius="xl", **{"aria-label": "Xem provenance"}),
                        label=source,
                        multiline=True,
                        w=340,
                        position="left",
                        withArrow=True,
                    ),
                ],
                className="analysis-chart__header",
            ),
            dcc.Graph(id=graph_id, figure=figure, config=PLOTLY_CONFIG, responsive=True, clear_on_unhover=False, className="analysis-chart__graph", style={"height": f"{height}px", "minHeight": f"{height}px"}),
        ],
        className=classes,
    )


def tab_panel_style(active_tab: str | None, panel: str) -> dict[str, str]:
    active = active_tab if active_tab in {"certified", "tradeoffs", "scenarios"} else "certified"
    return {"display": "block" if active == panel else "none", "width": "100%"}


def filter_option_rows(rows, model_id: str | None = None, evidence: str | None = None) -> list[dict]:
    selected = [dict(row) for row in rows]
    if model_id and model_id != "ALL":
        selected = [row for row in selected if str(row.get("model_id")) == str(model_id)]
    if evidence and evidence != "ALL":
        selected = [row for row in selected if str(row.get("evidence_level")) == str(evidence)]
    return selected


def _find_option(rows, option_id: str | None) -> dict | None:
    if not option_id:
        return None
    return next((dict(row) for row in rows if str(row.get("option_id")) == str(option_id)), None)


def _initial_option(model: DecisionModelV3, visible_rows: list[dict]) -> dict | None:
    if not visible_rows:
        return None
    focused = _find_option(visible_rows, model.focus_option)
    if focused:
        return focused
    if model.scope != "CROSS_DATASET" and model.recommendations:
        selected = _find_option(visible_rows, str(model.recommendations[0].get("option_id")))
        if selected:
            return selected
    if model.scope == "CROSS_DATASET":
        hc = next((r for r in model.dataset_recommendations if str(r.get("recommendation_scope")) == "HOME_CREDIT_PRIMARY"), None)
        if hc:
            selected = _find_option(visible_rows, str(hc.get("option_id")))
            if selected:
                return selected
    return dict(visible_rows[0])


def with_drill_dataset(row: dict | None, focus_dataset: str | None) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    if focus_dataset in {"HOME_CREDIT", "FREDDIE"}:
        item["drill_dataset_scope"] = focus_dataset
    return item


def _scope_label(scope: str) -> str:
    return {"HOME_CREDIT": "Home Credit", "FREDDIE": "Freddie Mac", "CROSS_DATASET": "Cross-dataset"}.get(scope, scope)


def _option_label(option_id: object) -> str:
    if not option_id or str(option_id) == "nan":
        return "—"
    model_id, evidence = str(option_id).split("::", 1)
    return f"{MODEL_LABELS.get(model_id, model_id)} × {evidence}"


def _page_header(model: DecisionModelV3):
    return html.Header(
        [
            html.Div(
                [
                    html.Div([html.Span("DECISION SUPPORT", className="analysis-eyebrow"), html.Span("PRIMARY POLICY · δ=0.03", className="analysis-lane-badge")], className="analysis-page-header__eyebrow"),
                    html.H1("Decision Studio", className="analysis-page-header__title"),
                    html.P("Certified evidence dẫn tới lựa chọn nào, option bị loại ở bước nào, và vì sao dataset-specific winners không tạo thành một robust cross-dataset winner?", className="analysis-page-header__subtitle"),
                ]
            ),
            html.Div(
                [
                    html.Div([html.Span("Phạm vi"), html.Strong(_scope_label(model.scope))], className="analysis-context-pill"),
                    html.Div([html.Span("Primary endpoint"), html.Strong("End-to-End Faithfulness")], className="analysis-context-pill"),
                    html.Div([html.Span("Selection policy"), html.Strong("Hard gate → NI → robust pool")], className="analysis-context-pill"),
                ],
                className="analysis-page-header__context",
            ),
        ],
        className="analysis-page-header",
    )


def _recommendation_card(label: str, recommendation: dict | None, *, status: str | None = None, emphasis: str = ""):
    option = _option_label(recommendation.get("option_id") if recommendation else None)
    code = status or (str(recommendation.get("status")) if recommendation else "—")
    classes = "decision-recommendation-card"
    if emphasis:
        classes += f" decision-recommendation-card--{emphasis}"
    return html.Div(
        [
            html.Span(label, className="decision-recommendation-card__label"),
            html.Strong(option if option != "—" else ("No robust winner" if code == "NO_ROBUST_RECOMMENDATION" else "—"), className="decision-recommendation-card__value"),
            html.Code(code, className="decision-recommendation-card__status"),
        ],
        className=classes,
    )


def _recommendation_strip(model: DecisionModelV3):
    by_scope = {str(row.get("recommendation_scope")): dict(row) for row in model.dataset_recommendations}
    if model.scope == "HOME_CREDIT":
        return html.Div([_recommendation_card("Home Credit", by_scope.get("HOME_CREDIT_PRIMARY"), emphasis="selected"), _recommendation_card("Policy", None, status=f"PRIMARY_CERTIFIED · δ={model.primary_margin:.2f}")], className="decision-recommendation-strip decision-recommendation-strip--study")
    if model.scope == "FREDDIE":
        return html.Div([_recommendation_card("Freddie Mac", by_scope.get("FREDDIE_PRIMARY"), emphasis="selected"), _recommendation_card("Policy", None, status=f"PRIMARY_CERTIFIED · δ={model.primary_margin:.2f}")], className="decision-recommendation-strip decision-recommendation-strip--study")
    return html.Div(
        [
            _recommendation_card("Home Credit", by_scope.get("HOME_CREDIT_PRIMARY"), emphasis="selected"),
            _recommendation_card("Freddie Mac", by_scope.get("FREDDIE_PRIMARY"), emphasis="selected"),
            _recommendation_card("Cross-dataset", None, status=model.robust_status or "—", emphasis="warning"),
        ],
        className="decision-recommendation-strip",
    )


def _decision_path(model: DecisionModelV3):
    c = model.decision_counts
    if model.scope != "CROSS_DATASET":
        scope = model.scope
        gate = c["home_credit_hard_gate"] if scope == "HOME_CREDIT" else c["freddie_hard_gate"]
        ni = c["home_credit_ni"] if scope == "HOME_CREDIT" else c["freddie_ni"]
        return html.Section(
            [
                html.Div([html.Span("CERTIFIED DECISION PATH", className="analysis-eyebrow"), html.H2("Dataset-specific eligibility", className="decision-section-title")], className="decision-section-heading"),
                html.Div(
                    [
                        html.Div([html.Strong(str(c["total"])), html.Span("Options")], className="decision-path-node"),
                        html.Div("→", className="decision-path-arrow"),
                        html.Div([html.Strong(str(gate)), html.Span("Hard-gate pass")], className="decision-path-node"),
                        html.Div("→", className="decision-path-arrow"),
                        html.Div([html.Strong(str(ni)), html.Span("Non-inferior")], className="decision-path-node decision-path-node--selected"),
                        html.Div("→", className="decision-path-arrow"),
                        html.Div([html.Strong("1"), html.Span("Certified selection")], className="decision-path-node decision-path-node--selected"),
                    ],
                    className="decision-path decision-path--study",
                ),
                html.P("Counts are presentation tallies of certified gate/NI flags; the dashboard does not rerun policy logic.", className="decision-path-note"),
            ],
            className="decision-path-card",
        )
    return html.Section(
        [
            html.Div([html.Span("CERTIFIED DECISION PATH", className="analysis-eyebrow"), html.H2("Why there is no robust winner", className="decision-section-title")], className="decision-section-heading"),
            html.Div(
                [
                    html.Div([html.Strong(str(c["total"])), html.Span("All options")], className="decision-path-node"),
                    html.Div("→", className="decision-path-arrow"),
                    html.Div([html.Strong(str(c["both_hard_gate"])), html.Span("Both hard gates")], className="decision-path-node"),
                    html.Div("→", className="decision-path-arrow"),
                    html.Div(
                        [
                            html.Div([html.Strong(str(c["home_credit_ni"])), html.Span("HC non-inferior")], className="decision-path-branch__node"),
                            html.Div([html.Strong(str(c["freddie_ni"])), html.Span("Freddie non-inferior")], className="decision-path-branch__node"),
                        ],
                        className="decision-path-branch",
                    ),
                    html.Div("→", className="decision-path-arrow"),
                    html.Div([html.Strong(str(c["robust_ni"])), html.Span("Cross NI overlap")], className="decision-path-node decision-path-node--warning"),
                    html.Div("→", className="decision-path-arrow"),
                    html.Div([html.Strong(str(c["robust_eligible"])), html.Span("Robust eligible")], className="decision-path-node decision-path-node--warning"),
                ],
                className="decision-path",
            ),
            html.Div([DashIconify(icon="solar:shield-warning-linear", width=17), html.Span("NO_ROBUST_RECOMMENDATION is preserved exactly because the certified robust candidate intersection is empty at δ=0.03.")], className="decision-path-note decision-path-note--warning"),
        ],
        className="decision-path-card",
    )


def _status_cell(label: str, value: bool | None, *, muted: bool = False):
    if value is None:
        return html.Span("—", className="decision-matrix-status decision-matrix-status--na")
    cls = "decision-matrix-status--yes" if bool(value) else "decision-matrix-status--no"
    if muted:
        cls = "decision-matrix-status--muted"
    return html.Span(("✓ " if bool(value) else "— ") + label, className=f"decision-matrix-status {cls}")


def _eligibility_matrix(model: DecisionModelV3):
    headers = ["Option", "Role"]
    if model.scope == "CROSS_DATASET":
        headers += ["HC gate", "Freddie gate", "HC NI", "Freddie NI", "Robust"]
    else:
        headers += ["Hard gate", "NI", "Rank"]
    rows = []
    for row in model.options:
        cells = [
            html.Div([html.Strong(row["model_label"]), html.Span(row["evidence_level"])], className="decision-matrix-option"),
            html.Span(str(row["option_role"]), className="decision-role-chip"),
        ]
        if model.scope == "CROSS_DATASET":
            cells += [
                _status_cell("PASS", bool(row["home_credit_hard_gate_pass"])),
                _status_cell("PASS", bool(row["freddie_hard_gate_pass"])),
                _status_cell("NI", bool(row["home_credit_non_inferior"])),
                _status_cell("NI", bool(row["freddie_non_inferior"])),
                _status_cell("ELIGIBLE", bool(row["robust_eligible"])),
            ]
        else:
            cells += [
                _status_cell("PASS", bool(row["hard_gate_pass"])),
                _status_cell("NI", bool(row["non_inferior"])),
                html.Span(f"#{int(row['quality_rank'])}", className="decision-rank-cell"),
            ]
        rows.append(html.Div([html.Div(cell, className="decision-eligibility-matrix__cell") for cell in cells], className="decision-eligibility-matrix__row"))
    return html.Section(
        [
            html.Div([html.H2("Eligibility Matrix", className="decision-section-title"), html.P("Matrix reads certified gate and NI states; it does not infer them from displayed metrics.", className="analysis-chart__subtitle")], className="decision-section-heading"),
            html.Div(
                [html.Div([html.Div(h, className="decision-eligibility-matrix__head") for h in headers], className="decision-eligibility-matrix__header"), *rows],
                className=f"decision-eligibility-matrix decision-eligibility-matrix--{'cross' if model.scope == 'CROSS_DATASET' else 'study'}",
            ),
        ],
        className="decision-matrix-card",
    )


def _tradeoff_filters(model: DecisionModelV3):
    model_data = [{"value": "ALL", "label": "Tất cả model"}] + [{"value": mid, "label": label} for mid, label in MODEL_LABELS.items()]
    evidence_data = [{"value": "ALL", "label": "Tất cả Evidence"}] + [{"value": f"S{i}", "label": f"S{i}"} for i in range(6)]
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Option focus", className="analysis-filter-bar__label"),
                    dmc.Select(id=MODEL_FILTER_ID, data=model_data, value=model.focus_model or "ALL", allowDeselect=False, w=210, size="sm"),
                    dmc.Select(id=EVIDENCE_FILTER_ID, data=evidence_data, value=model.focus_evidence or "ALL", allowDeselect=False, w=185, size="sm"),
                ],
                className="analysis-filter-bar__controls",
            ),
            html.Div([DashIconify(icon="solar:info-circle-linear", width=15), html.Span("Filters chỉ focus certified option rows; không rerank, recompute Pareto hoặc thay đổi decision path.")], className="analysis-filter-bar__note"),
        ],
        className="analysis-filter-bar decision-filter-bar",
    )


def option_panel(row: dict | None):
    if not row:
        return html.Div([html.Span("Focused option", className="analysis-eyebrow"), html.H3("Không có option trong filter", className="analysis-side-panel__title"), html.P("Nới filter để xem certified decision evidence.", className="analysis-side-panel__text")], className="analysis-side-panel__empty")
    query = urlencode({"dataset": (row.get("drill_dataset_scope") or row.get("dataset_scope")) if (row.get("drill_dataset_scope") or row.get("dataset_scope")) in {"HOME_CREDIT", "FREDDIE"} else "", "model": row.get("model_id"), "evidence": row.get("evidence_level")})
    metrics = [
        ("Decision quality", row.get("mean_e2e_display", "—")),
        ("P10 reliability", row.get("p10_e2e_display", "—")),
        ("Usability", row.get("usability_rate_display", "—")),
        ("Token burden", row.get("tokens_display", "—")),
    ]
    if row.get("dataset_scope") == "CROSS_DATASET":
        chips = ["Worst-case cross-dataset", str(row.get("option_role")), "ROBUST" if bool(row.get("robust_eligible")) else "NOT ROBUST"]
        dataset_note = "Cross-dataset certified worst-case projection"
    else:
        chips = [str(row.get("option_role")), "GATE PASS" if bool(row.get("hard_gate_pass")) else "GATE FAIL", "NON_INFERIOR" if bool(row.get("non_inferior")) else "INFERIOR"]
        dataset_note = str(row.get("dataset_label"))
    return html.Div(
        [
            html.Span("Focused option", className="analysis-eyebrow"),
            html.H3(f"{row.get('model_label')} × {row.get('evidence_level')}", className="analysis-side-panel__title"),
            html.Div(dataset_note, className="analysis-side-panel__dataset"),
            html.Div([html.Div([html.Span(label), html.Strong(str(value))], className="analysis-side-panel__metric") for label, value in metrics], className="analysis-side-panel__metrics"),
            html.Div([html.Span(chip) for chip in chips], className="analysis-side-panel__chips"),
            html.P("Focused option is a presentation selection only; it is not a new recommendation.", className="analysis-side-panel__text"),
            html.Div(
                [
                    dcc.Link("Mở Effectiveness", href=f"/effectiveness?tab=primary&{query}", className="analysis-link-button analysis-link-button--filled"),
                    dcc.Link("Mở Robustness", href=f"/robustness?tab=metric&{query}", className="analysis-link-button analysis-link-button--light"),
                    dcc.Link("Mở Case Explorer", href=f"/cases?{query}", className="analysis-link-button analysis-link-button--light"),
                ],
                className="analysis-side-panel__actions",
            ),
        ],
        className="analysis-side-panel__body",
    )


def option_from_click(click_data: dict | None) -> str | None:
    if not click_data or not click_data.get("points"):
        return None
    custom = list(click_data["points"][0].get("customdata") or [])
    return str(custom[0]) if custom else None


def ni_from_click(click_data: dict | None) -> dict | None:
    if not click_data or not click_data.get("points"):
        return None
    custom = list(click_data["points"][0].get("customdata") or [])
    if len(custom) < 10:
        return None
    return {
        "dataset_scope": str(custom[0]),
        "candidate_option_id": str(custom[1]),
        "candidate_model_id": str(custom[2]),
        "candidate_evidence_level": str(custom[3]),
        "reference_option_id": str(custom[4]),
        "mean_difference": float(custom[5]),
        "upper_bound": float(custom[6]),
        "margin": float(custom[7]),
        "status": str(custom[8]),
        "paired_case_count": int(custom[9]),
    }


def option_drawer(row: dict):
    query = urlencode({"dataset": (row.get("drill_dataset_scope") or row.get("dataset_scope")) if (row.get("drill_dataset_scope") or row.get("dataset_scope")) in {"HOME_CREDIT", "FREDDIE"} else "", "model": row.get("model_id"), "evidence": row.get("evidence_level")})
    title = f"{row.get('model_label')} × {row.get('evidence_level')}"
    body = html.Div(
        [
            html.Div(str(row.get("dataset_label")), className="overview-drawer__dataset"),
            html.Div([html.Span("Decision quality"), html.Strong(str(row.get("mean_e2e_display")))], className="overview-drawer__metric"),
            html.Div([html.Span("P10 reliability"), html.Strong(str(row.get("p10_e2e_display")))], className="overview-drawer__metric"),
            html.Div([html.Span("Token burden"), html.Strong(str(row.get("tokens_display")))], className="overview-drawer__metric"),
            html.Div([html.Span("Hard gate"), html.Strong("PASS" if bool(row.get("hard_gate_pass")) else "FAIL")], className="overview-drawer__metric"),
            html.Div([html.Span("NI state"), html.Strong("NON_INFERIOR" if bool(row.get("non_inferior")) else "INFERIOR")], className="overview-drawer__metric"),
            html.P("Values are read from decision_option_assessment; no Pareto, NI, rank or utility computation occurs in the dashboard.", className="overview-drawer__note"),
            html.Div([dcc.Link("Effectiveness", href=f"/effectiveness?tab=primary&{query}", className="analysis-link-button analysis-link-button--filled"), dcc.Link("Case Explorer", href=f"/cases?{query}", className="analysis-link-button analysis-link-button--light")], className="overview-drawer__actions"),
        ],
        className="overview-drawer",
        **{"data-testid": "decision-drawer-content"},
    )
    return title, body


def ni_drawer(detail: dict):
    candidate = _option_label(detail["candidate_option_id"])
    reference = _option_label(detail["reference_option_id"])
    title = f"NI evidence · {candidate}"
    body = html.Div(
        [
            html.Div(_scope_label(detail["dataset_scope"]), className="overview-drawer__dataset"),
            html.Div([html.Span("Reference"), html.Strong(reference)], className="overview-drawer__metric"),
            html.Div([html.Span("Mean reference − candidate"), html.Strong(f"{detail['mean_difference']:.4f}")], className="overview-drawer__metric"),
            html.Div([html.Span("Upper one-sided 95% bound"), html.Strong(f"{detail['upper_bound']:.4f}")], className="overview-drawer__metric"),
            html.Div([html.Span("Certified margin"), html.Strong(f"δ={detail['margin']:.2f}")], className="overview-drawer__metric"),
            html.Div([html.Span("Status"), html.Strong(detail["status"])], className="overview-drawer__metric"),
            html.Div([html.Span("Paired cases"), html.Strong(str(detail["paired_case_count"]))], className="overview-drawer__metric"),
            html.P("This panel presents the certified NI row; the dashboard does not calculate the bound or decision.", className="overview-drawer__note"),
        ],
        className="overview-drawer",
        **{"data-testid": "decision-drawer-content"},
    )
    return title, body


def scenario_detail(row: dict | None):
    if not row:
        return html.Div("Scenario state unavailable", className="analysis-side-panel__text")
    utility_state = "N/A — utility stage not entered" if int(row.get("utility_non_null_count", 0)) == 0 else f"{int(row['utility_non_null_count'])} utility rows"
    return html.Div(
        [
            html.Span("Frozen scenario", className="analysis-eyebrow"),
            html.H3(SCENARIO_LABELS.get(str(row["scenario_id"]), str(row["scenario_id"])), className="analysis-side-panel__title"),
            html.Div([html.Div([html.Span("Certified status"), html.Strong(str(row["status"]))], className="analysis-side-panel__metric"), html.Div([html.Span("Pool mode"), html.Strong(str(row["pool_mode"]))], className="analysis-side-panel__metric"), html.Div([html.Span("Eligible options"), html.Strong(str(int(row["scenario_eligible_count"])))], className="analysis-side-panel__metric"), html.Div([html.Span("Utility"), html.Strong(utility_state)], className="analysis-side-panel__metric")], className="analysis-side-panel__metrics"),
            html.P("Scenario selection only switches among five certified frozen scenarios. N/A utility is not zero and no live What-if score is computed.", className="analysis-side-panel__text"),
            html.Code(str(row["status"]), className="analysis-capability-code"),
        ],
        className="analysis-side-panel__body",
        **{"data-testid": "decision-scenario-detail"},
    )


def _scenario_cards(model: DecisionModelV3):
    cards = []
    for row in model.scenarios:
        cards.append(
            html.Div(
                [
                    html.Span(SCENARIO_LABELS.get(str(row["scenario_id"]), str(row["scenario_id"])), className="decision-scenario-card__name"),
                    html.Strong(str(row["status"]), className="decision-scenario-card__status"),
                    html.Div([html.Span(f"Pool: {row['pool_mode']}", className="decision-scenario-card__chip"), html.Span(f"Eligible: {int(row['scenario_eligible_count'])}", className="decision-scenario-card__chip")], className="decision-scenario-card__chips"),
                ],
                className="decision-scenario-card",
            )
        )
    return html.Div(cards, className="decision-scenario-grid")


def render(model: DecisionModelV3):
    cross = model.scope == "CROSS_DATASET"
    visible = filter_option_rows(model.options, model.focus_model, model.focus_evidence)
    initial = with_drill_dataset(_initial_option(model, visible), model.focus_dataset)
    selected_option = str(initial["option_id"]) if initial else None
    ni = decision_noninferiority_plot(model.ni_rows, cross_dataset=cross)
    qrel = decision_quality_reliability_plot(visible, selected_option=selected_option)
    qeff = decision_quality_efficiency_plot(visible, selected_option=selected_option)
    selected_scenario = next((dict(r) for r in model.scenarios if str(r["scenario_id"]) == model.focus_scenario), dict(model.scenarios[0]))

    return html.Main(
        [
            _page_header(model),
            _recommendation_strip(model),
            html.Div(
                [
                    dmc.SegmentedControl(
                        id=TABS_ID,
                        value=model.initial_tab,
                        data=[
                            {"value": "certified", "label": "Certified decision"},
                            {"value": "tradeoffs", "label": "Trade-offs"},
                            {"value": "scenarios", "label": "Certified scenarios"},
                        ],
                        radius="xl",
                        size="sm",
                        className="analysis-tab-switcher__control",
                        **{"aria-label": "Decision Studio analytical section"},
                    )
                ],
                className="analysis-tab-switcher",
            ),
            html.Div(
                [
                    _decision_path(model),
                    _eligibility_matrix(model),
                    html.Div(
                        [
                            _chart_panel(graph_id=NI_PLOT_ID, title="Certified Non-Inferiority evidence", subtitle="Upper one-sided 95% bounds are compared with the certified δ=0.03 reference. Filled markers are certified NON_INFERIOR; hollow markers are INFERIOR.", source="Certified table: noninferiority_results", figure=ni, class_name="decision-chart--ni"),
                            html.Aside(option_panel(initial), id=OPTION_PANEL_ID, className="analysis-side-panel decision-certified-side-panel"),
                        ],
                        className="decision-certified-grid",
                    ),
                ],
                id=CERTIFIED_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "certified"),
            ),
            html.Div(
                [
                    _tradeoff_filters(model),
                    html.Div(
                        [
                            _chart_panel(graph_id=QUALITY_RELIABILITY_ID, title="Quality × Reliability", subtitle="Cross scope uses certified worst-dataset mean E2E and P10 E2E; study scope uses the corresponding certified dataset values.", source="Certified table: decision_option_assessment", figure=qrel, class_name="decision-chart--tradeoff"),
                            html.Aside(option_panel(initial), id=TRADEOFF_OPTION_PANEL_ID, className="analysis-side-panel"),
                        ],
                        className="decision-tradeoff-primary-grid",
                    ),
                    _chart_panel(graph_id=QUALITY_EFFICIENCY_ID, title="Quality × Token burden", subtitle="Higher quality and lower token burden are visually preferable, but the dashboard does not compute a new Pareto frontier or utility score.", source="Certified table: decision_option_assessment", figure=qeff, class_name="decision-chart--tradeoff decision-chart--efficiency"),
                    html.Div([DashIconify(icon="solar:shield-check-linear", width=17), html.Span("Certified Pareto set remains empty because robust_eligible = 0 for all options under the primary policy; no alternative frontier is recomputed in the UI.")], className="decision-pareto-note"),
                ],
                id=TRADEOFF_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "tradeoffs"),
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.Span("Scenario explorer", className="analysis-filter-bar__label"), dmc.Select(id=SCENARIO_ID, data=[{"value": s, "label": SCENARIO_LABELS[s]} for s in SCENARIO_ORDER], value=model.focus_scenario, allowDeselect=False, w=260, size="sm")], className="analysis-filter-bar__controls"),
                            html.Div([DashIconify(icon="solar:lock-keyhole-minimalistic-linear", width=15), html.Span("Five frozen scenarios only · no weight sliders · no live recommendation engine")], className="analysis-filter-bar__note"),
                        ],
                        className="analysis-filter-bar",
                    ),
                    html.Div([html.Div(_scenario_cards(model), className="decision-scenario-list"), html.Aside(scenario_detail(selected_scenario), id=SCENARIO_DETAIL_ID, className="analysis-side-panel")], className="decision-scenario-layout"),
                    html.Section([html.H2("Why utility is N/A", className="decision-section-title"), html.P("At PRIMARY_CERTIFIED δ=0.03 the robust candidate pool is empty. The certified scenario utility stage is therefore not entered. N/A is a structural state, not a score of zero.", className="analysis-chart__subtitle"), html.Code("NO_ROBUST_RECOMMENDATION", className="decision-no-winner-code")], className="decision-no-pool-card"),
                ],
                id=SCENARIO_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "scenarios"),
            ),
            dcc.Store(id=SELECTED_OPTION_STORE_ID, data={"option_id": selected_option} if selected_option else None),
            html.Div([DashIconify(icon="solar:shield-check-linear", width=16), html.Span("Certified decision presentation · No NI, Pareto, ranking or utility recomputation in UI")], className="analysis-certified-footer"),
            dmc.Drawer(html.Div(id=DETAIL_DRAWER_BODY_ID), id=DETAIL_DRAWER_ID, title=html.Div(id=DETAIL_DRAWER_TITLE_ID), opened=False, position="right", size="md", padding="xl", overlayProps={"backgroundOpacity": 0.25, "blur": 2}),
        ],
        className=f"research-page analysis-page decision-page--golden analysis-page--{'cross' if cross else 'study'}",
    )


def layout(**_):
    return html.Div(id=CONTENT_ID)
