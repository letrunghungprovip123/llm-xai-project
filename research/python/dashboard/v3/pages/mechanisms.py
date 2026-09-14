from __future__ import annotations

from urllib.parse import urlencode

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from research.python.dashboard.theme import PLOTLY_CONFIG

from ..effectiveness_model import MODEL_LABELS
from ..figures import (
    mechanism_claim_matrix,
    mechanism_faithfulness_accounting,
    mechanism_lexical_signal,
    mechanism_quality_map,
)
from ..mechanisms_model import MechanismsModelV3

CONTENT_ID = "v3-mechanisms-content"
TABS_ID = "mechanisms-tabs"
LOSS_PANEL_ID = "mechanisms-tab-loss-panel"
CLAIMS_PANEL_ID = "mechanisms-tab-claims-panel"
QUALITY_PANEL_TAB_ID = "mechanisms-tab-quality-panel"
ACCOUNTING_ID = "mechanisms-faithfulness-accounting"
LEXICAL_ID = "mechanisms-lexical-overlap-signal"
CLAIM_MATRIX_ID = "mechanisms-claim-validation-matrix"
CLAIM_TYPE_FILTER_ID = "mechanisms-claim-type-filter"
VALIDATION_FILTER_ID = "mechanisms-validation-status-filter"
CLAIM_MEASURE_ID = "mechanisms-claim-measure"
CLAIM_GRID_ID = "mechanisms-claim-grid"
QUALITY_MAP_ID = "mechanisms-quality-map"
QUALITY_MODEL_FILTER_ID = "mechanisms-quality-model-filter"
QUALITY_EVIDENCE_FILTER_ID = "mechanisms-quality-evidence-filter"
QUALITY_PANEL_ID = "mechanisms-selected-option"
DETAIL_DRAWER_ID = "mechanisms-detail-drawer"
DETAIL_DRAWER_TITLE_ID = "mechanisms-detail-drawer-title-content"
DETAIL_DRAWER_BODY_ID = "mechanisms-detail-drawer-body-content"


def register_page() -> None:
    dash.register_page(
        "llm_xai_dashboard_v3.mechanisms",
        path="/mechanisms",
        name="Mechanisms",
        title="Mechanisms · LLM–XAI Research Dashboard",
        order=2,
        layout=layout,
    )


def _provenance(label: str):
    return dmc.Tooltip(
        dmc.ActionIcon(DashIconify(icon="solar:info-circle-linear", width=17), variant="subtle", color="gray", size="sm", radius="xl", **{"aria-label": "Xem provenance"}),
        label=label, multiline=True, w=340, position="left", withArrow=True,
    )


def _chart_panel(*, graph_id: str, title: str, subtitle: str, source: str, figure, class_name: str = ""):
    classes = "mechanisms-chart"
    if class_name:
        classes += f" {class_name}"
    height = int(figure.layout.height or 360)
    return html.Section(
        [
            html.Div([html.Div([html.H2(title, className="analysis-chart__title"), html.P(subtitle, className="analysis-chart__subtitle")]), _provenance(source)], className="analysis-chart__header"),
            dcc.Graph(id=graph_id, figure=figure, config=PLOTLY_CONFIG, responsive=True, clear_on_unhover=False, className="analysis-chart__graph", style={"height": f"{height}px", "minHeight": f"{height}px"}),
        ],
        className=classes,
    )


def _page_header(model: MechanismsModelV3):
    scope_label = "Cross-dataset" if model.scope == "CROSS_DATASET" else ("Home Credit" if model.scope == "HOME_CREDIT" else "Freddie Mac")
    return html.Header(
        [
            html.Div(
                [
                    html.Div([html.Span("RQ · Mechanisms", className="analysis-eyebrow"), html.Span("DIAGNOSTIC · không causal attribution", className="analysis-lane-badge analysis-lane-badge--diagnostic")], className="analysis-page-header__eyebrow"),
                    html.H1("Mechanisms", className="analysis-page-header__title"),
                    html.P("Diagnostic decomposition of explanation quality: faithfulness loss nằm ở đâu, claim types có validation profile thế nào, và Verifiability liên hệ ra sao với Resolved Faithfulness. Các association này không được diễn giải như causal mechanism.", className="analysis-page-header__subtitle"),
                ]
            ),
            html.Div(
                [
                    html.Div([html.Span("Phạm vi"), html.Strong(scope_label)], className="analysis-context-pill"),
                    html.Div([html.Span("Loss identity"), html.Strong("E2E + losses = 100%")], className="analysis-context-pill"),
                    html.Div([html.Span("Claim outcomes"), html.Strong("5 validation statuses")], className="analysis-context-pill"),
                ],
                className="analysis-page-header__context",
            ),
        ],
        className="analysis-page-header",
    )


def _claim_controls(model: MechanismsModelV3):
    claim_types = sorted({str(row["claim_type"]) for row in model.claim_rows})
    type_data = [{"value": "ALL", "label": "Tất cả claim type"}] + [{"value": value, "label": value} for value in claim_types]
    status_data = [{"value": "ALL", "label": "Tất cả status"}] + [{"value": value, "label": value} for value in ("SUPPORTED", "NOT_VERIFIABLE", "UNSUPPORTED", "CONTRADICTED", "NOT_APPLICABLE")]
    return html.Div(
        [
            html.Div(
                [
                    dmc.Select(id=CLAIM_TYPE_FILTER_ID, data=type_data, value="ALL", allowDeselect=False, w=220, size="sm"),
                    dmc.Select(id=VALIDATION_FILTER_ID, data=status_data, value=model.focus_validation_status or "ALL", allowDeselect=False, w=220, size="sm"),
                    dmc.SegmentedControl(id=CLAIM_MEASURE_ID, value="share", data=[{"value": "share", "label": "Share"}, {"value": "count", "label": "Count"}], size="xs", radius="xl"),
                ],
                className="analysis-filter-bar__controls",
            ),
            html.Div([DashIconify(icon="solar:info-circle-linear", width=15), html.Span("Share = presentation normalization within claim type; raw certified counts luôn giữ trong tooltip/DataGrid.")], className="analysis-filter-bar__note"),
        ],
        className="analysis-filter-bar analysis-filter-bar--embedded",
    )


def _quality_controls(model: MechanismsModelV3):
    model_data = [{"value": "ALL", "label": "Tất cả model"}] + [{"value": model_id, "label": label} for model_id, label in MODEL_LABELS.items()]
    evidence_data = [{"value": "ALL", "label": "Tất cả Evidence"}] + [{"value": f"S{i}", "label": f"S{i}"} for i in range(6)]
    return html.Div(
        [
            html.Div([dmc.Select(id=QUALITY_MODEL_FILTER_ID, data=model_data, value=model.focus_model or "ALL", allowDeselect=False, w=210, size="sm"), dmc.Select(id=QUALITY_EVIDENCE_FILTER_ID, data=evidence_data, value=model.focus_evidence or "ALL", allowDeselect=False, w=185, size="sm")], className="analysis-filter-bar__controls"),
            html.Div([DashIconify(icon="solar:info-circle-linear", width=15), html.Span("Các điểm là certified option-level means; dashboard chỉ select/filter, không tính metric mới.")], className="analysis-filter-bar__note"),
        ],
        className="analysis-filter-bar analysis-filter-bar--embedded",
    )


def _claim_grid(model: MechanismsModelV3):
    rows = []
    for row in model.claim_rows:
        rows.append({"dataset": "Home Credit" if row["dataset_scope"] == "HOME_CREDIT" else "Freddie Mac", "claim_type": row["claim_type"], "validation_status": row["validation_status"], "claim_count": int(row["claim_count"])})
    return dag.AgGrid(
        id=CLAIM_GRID_ID,
        rowData=rows,
        columnDefs=[
            {"field": "dataset", "headerName": "Dataset", "minWidth": 120},
            {"field": "claim_type", "headerName": "Claim type", "minWidth": 190, "flex": 1},
            {"field": "validation_status", "headerName": "Validation status", "minWidth": 180},
            {"field": "claim_count", "headerName": "Certified claim count"},
        ],
        defaultColDef={"sortable": True, "filter": True, "resizable": True, "minWidth": 100},
        dashGridOptions={"pagination": True, "paginationPageSize": 12, "paginationPageSizeSelector": False, "animateRows": False, "suppressCellFocus": True},
        className="ag-theme-quartz research-data-grid",
        style={"height": "390px", "width": "100%"},
    )


def quality_panel(row: dict | None):
    if not row:
        return html.Div([html.Span("Selected option", className="analysis-eyebrow"), html.H3("Chọn một điểm trên Quality Map", className="analysis-side-panel__title"), html.P("Click để xem 4 quality dimensions và drill-through sang Effectiveness/Case Explorer.", className="analysis-side-panel__text")], className="analysis-side-panel__empty")
    query = urlencode({"dataset": row["dataset_scope"], "model": row["model_id"], "evidence": row["evidence_level"]})
    metrics = [
        ("End-to-End Faithfulness", row["end_to_end_faithfulness_yield"]),
        ("Resolved Faithfulness", row["resolved_faithfulness"]),
        ("Verifiability", row["verifiability"]),
        ("Conservative Faithfulness", row["conservative_faithfulness"]),
    ]
    return html.Div(
        [
            html.Span("Selected option", className="analysis-eyebrow"),
            html.H3(f"{row['model_label']} × {row['evidence_level']}", className="analysis-side-panel__title"),
            html.Div(row["dataset_label"], className="analysis-side-panel__dataset"),
            html.Div([html.Div([html.Span(label), html.Strong(f"{float(value):.2%}")], className="analysis-side-panel__metric") for label, value in metrics], className="analysis-side-panel__metrics"),
            html.P("Secondary analytical lens; không đặt quadrant GOOD/BAD vì protocol không định nghĩa threshold.", className="analysis-side-panel__text"),
            html.Div([dcc.Link("Mở Effectiveness", href=f"/effectiveness?tab=primary&{query}", className="analysis-link-button analysis-link-button--filled"), dcc.Link("Mở Case Explorer", href=f"/cases?{query}", className="analysis-link-button analysis-link-button--light")], className="analysis-side-panel__actions"),
        ],
        className="analysis-side-panel__body",
    )


def filter_quality_rows(rows, model_id: str | None = None, evidence: str | None = None) -> list[dict]:
    selected = [dict(row) for row in rows]
    if model_id and model_id != "ALL":
        selected = [row for row in selected if str(row.get("model_id")) == str(model_id)]
    if evidence and evidence != "ALL":
        selected = [row for row in selected if str(row.get("evidence_level")) == str(evidence)]
    return selected


def best_quality_row(rows, dataset_scope: str | None = None) -> dict | None:
    selected = [dict(row) for row in rows]
    if dataset_scope in {"HOME_CREDIT", "FREDDIE"}:
        focused = [row for row in selected if str(row.get("dataset_scope")) == dataset_scope]
        if focused:
            selected = focused
    if not selected:
        return None
    return max(
        selected,
        key=lambda row: (
            float(row.get("verifiability", 0)) + float(row.get("resolved_faithfulness", 0)),
            float(row.get("end_to_end_faithfulness_yield", 0)),
        ),
    )


def _find_initial_quality(model: MechanismsModelV3):
    rows = filter_quality_rows(model.quality_rows, model.focus_model, model.focus_evidence)
    return best_quality_row(rows, model.focus_dataset)


def tab_panel_style(active_tab: str | None, panel: str) -> dict[str, str]:
    active = active_tab if active_tab in {"loss", "claims", "quality"} else "loss"
    return {"display": "block" if active == panel else "none", "width": "100%"}


def render(model: MechanismsModelV3):
    cross = model.scope == "CROSS_DATASET"
    accounting = mechanism_faithfulness_accounting(model.loss_rows)
    lexical = mechanism_lexical_signal(model.loss_rows)
    claims = mechanism_claim_matrix(model.claim_rows, cross_dataset=cross, measure="share", validation_status=model.focus_validation_status)
    visible_quality = filter_quality_rows(model.quality_rows, model.focus_model, model.focus_evidence)
    quality = mechanism_quality_map(visible_quality, cross_dataset=cross)
    initial_quality = best_quality_row(visible_quality, model.focus_dataset)

    return html.Main(
        [
            _page_header(model),
            html.Div(
                [
                    dmc.SegmentedControl(
                        id=TABS_ID,
                        value=model.initial_tab,
                        data=[
                            {"value": "loss", "label": "Loss decomposition"},
                            {"value": "claims", "label": "Claim diagnostics"},
                            {"value": "quality", "label": "Quality mechanisms"},
                        ],
                        radius="xl",
                        size="sm",
                        className="analysis-tab-switcher__control",
                        **{"aria-label": "Mechanisms analytical section"},
                    )
                ],
                className="analysis-tab-switcher",
            ),
            html.Div(
                [
                    _chart_panel(graph_id=ACCOUNTING_ID, title="100% Faithfulness Accounting", subtitle="Supported yield (End-to-End Faithfulness) và bốn certified loss components reconcile về 100% planned output mass.", source="Certified tables: study_summary + failure_decomposition", figure=accounting, class_name="mechanisms-chart--accounting"),
                    html.Div(
                        [
                            _chart_panel(graph_id=LEXICAL_ID, title="Lexical-overlap signal", subtitle="Diagnostic signal độc lập với loss identity; không stack vào 100% accounting.", source="Certified table: failure_decomposition.safe_phrase_matched_claim_rate", figure=lexical, class_name="mechanisms-chart--lexical"),
                            html.Section(
                                [
                                    html.Span("Diagnostic safeguard", className="analysis-eyebrow"),
                                    html.H3("Không diễn giải lexical overlap như copying", className="analysis-side-panel__title"),
                                    html.P("Lexical overlap không phải bằng chứng về copying, memorization, causal dependency hoặc model non-independence.", className="analysis-side-panel__text"),
                                    html.Div([html.Span("Reason profile"), html.Strong("Không có trong certified lineage hiện tại")], className="analysis-capability-note"),
                                    html.Code(model.reason_profile_status, className="analysis-capability-code"),
                                ],
                                className="analysis-side-panel mechanisms-diagnostic-note",
                            ),
                        ],
                        className="mechanisms-loss-secondary-grid",
                    ),
                ],
                id=LOSS_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "loss"),
            ),
            html.Div(
                [
                    _claim_controls(model),
                    _chart_panel(graph_id=CLAIM_MATRIX_ID, title="Claim type × Validation status", subtitle="Share mode chuẩn hóa trong từng claim type để so profile; Count mode hiển thị raw certified volume. N/A khác 0.", source="Certified table: claim_type_profile", figure=claims, class_name="mechanisms-chart--claims"),
                    html.Details([html.Summary("Xem exact certified claim counts"), html.Div(_claim_grid(model), className="analysis-grid-wrap")], className="analysis-details"),
                ],
                id=CLAIMS_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "claims"),
            ),
            html.Div(
                [
                    _quality_controls(model),
                    html.Div(
                        [
                            _chart_panel(graph_id=QUALITY_MAP_ID, title="Verifiability × Resolved Faithfulness Map", subtitle="Descriptive option-level association; shared 0–100% axes, không đặt threshold GOOD/BAD tùy ý.", source="Certified table: metric_sensitivity", figure=quality, class_name="mechanisms-chart--quality"),
                            html.Aside(quality_panel(initial_quality), id=QUALITY_PANEL_ID, className="analysis-side-panel"),
                        ],
                        className="mechanisms-quality-grid",
                    ),
                ],
                id=QUALITY_PANEL_TAB_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "quality"),
            ),
            html.Div([DashIconify(icon="solar:shield-check-linear", width=16), html.Span("Certified diagnostic presentation · Association không được diễn giải như causal attribution")], className="analysis-certified-footer"),
            dmc.Drawer(html.Div(id=DETAIL_DRAWER_BODY_ID), id=DETAIL_DRAWER_ID, title=html.Div(id=DETAIL_DRAWER_TITLE_ID), opened=False, position="right", size="md", padding="xl", overlayProps={"backgroundOpacity": 0.25, "blur": 2}),
        ],
        className=f"research-page analysis-page mechanisms-page--redesign analysis-page--{'cross' if cross else 'study'}",
    )


def quality_from_click(click_data: dict | None) -> dict | None:
    if not click_data or not click_data.get("points"):
        return None
    point = click_data["points"][0]
    custom = list(point.get("customdata") or [])
    if len(custom) < 6:
        return None
    return {
        "dataset_scope": str(custom[0]),
        "dataset_label": "Home Credit" if str(custom[0]) == "HOME_CREDIT" else "Freddie Mac",
        "model_id": str(custom[1]),
        "model_label": str(custom[2]),
        "evidence_level": str(custom[3]),
        "conservative_faithfulness": float(custom[4]),
        "end_to_end_faithfulness_yield": float(custom[5]),
        "verifiability": float(point.get("x", 0)),
        "resolved_faithfulness": float(point.get("y", 0)),
    }


def quality_drawer(row: dict):
    query = urlencode({"dataset": row["dataset_scope"], "model": row["model_id"], "evidence": row["evidence_level"]})
    title = f"{row['model_label']} × {row['evidence_level']}"
    body = html.Div(
        [
            html.Div(row["dataset_label"], className="overview-drawer__dataset"),
            html.Div([html.Span("Verifiability"), html.Strong(f"{row['verifiability']:.2%}")], className="overview-drawer__metric"),
            html.Div([html.Span("Resolved Faithfulness"), html.Strong(f"{row['resolved_faithfulness']:.2%}")], className="overview-drawer__metric"),
            html.Div([html.Span("Conservative Faithfulness"), html.Strong(f"{row['conservative_faithfulness']:.2%}")], className="overview-drawer__metric"),
            html.P("Các metric này đã được M29 materialize; dashboard chỉ present/join theo option identity.", className="overview-drawer__note"),
            html.Div(
                [
                    dcc.Link("Mở Effectiveness", href=f"/effectiveness?tab=primary&{query}", className="analysis-link-button analysis-link-button--filled"),
                    dcc.Link("Mở Case Explorer", href=f"/cases?{query}", className="analysis-link-button analysis-link-button--light"),
                ],
                className="overview-drawer__actions",
            ),
        ],
        className="overview-drawer",
    )
    return title, body


def claim_drawer(click_data: dict | None):
    if not click_data or not click_data.get("points"):
        return None
    custom = list(click_data["points"][0].get("customdata") or [])
    if len(custom) < 6:
        return None
    scope, claim_type, status, count, total, share = custom[:6]
    dataset = "Home Credit" if str(scope) == "HOME_CREDIT" else "Freddie Mac"
    title = f"{claim_type} × {status}"
    count_text = "N/A" if count is None else f"{int(count):,}"
    share_text = "N/A" if share is None else f"{float(share):.2%}"
    body = html.Div(
        [
            html.Div(dataset, className="overview-drawer__dataset"),
            html.Div([html.Span("Certified claims"), html.Strong(count_text)], className="overview-drawer__metric"),
            html.Div([html.Span("Share within claim type"), html.Strong(share_text)], className="overview-drawer__metric"),
            html.P(f"Total claims of this type: {int(total):,}" if total is not None else "Total claims of this type: N/A", className="overview-drawer__note"),
            html.P("Share là presentation-only normalization; raw claim_count là certified source value.", className="overview-drawer__note"),
        ],
        className="overview-drawer",
    )
    return title, body


def layout(**_):
    return html.Div(id=CONTENT_ID)
