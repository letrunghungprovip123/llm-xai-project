from __future__ import annotations

import json
from urllib.parse import urlencode

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from ..methods_model import (
    CAPABILITY_GAP,
    MethodsModelV3,
    finding_by_id,
    metric_by_key,
    report_by_id,
    schema_for_table,
)

CONTENT_ID = "v3-methods-content"
TABS_ID = "methods-tabs"
STUDY_PANEL_ID = "methods-tab-study-panel"
METRICS_PANEL_ID = "methods-tab-metrics-panel"
TRACE_PANEL_ID = "methods-tab-traceability-panel"
FINDINGS_PANEL_ID = "methods-tab-findings-panel"
METRIC_SELECT_ID = "methods-metric-select"
METRIC_DETAIL_ID = "methods-metric-detail"
METRIC_DETAIL_HOST_ID = "methods-metric-detail-host"
REPORT_SELECT_ID = "methods-report-select"
REPORT_GRID_ID = "methods-provenance-grid"
REPORT_DETAIL_ID = "methods-provenance-detail"
REPORT_DETAIL_HOST_ID = "methods-provenance-detail-host"
TABLE_SELECT_ID = "methods-table-select"
SCHEMA_GRID_ID = "methods-schema-grid"
FINDING_SELECT_ID = "methods-finding-select"
FINDING_DETAIL_ID = "methods-finding-detail"
FINDING_DETAIL_HOST_ID = "methods-finding-detail-host"
LIMITATIONS_GRID_ID = "methods-limitations-grid"


def register_page() -> None:
    dash.register_page(
        "llm_xai_dashboard_v3.methods",
        path="/methods",
        name="Methods",
        title="Methods & Audit · LLM–XAI Research Dashboard",
        order=6,
        layout=layout,
    )


def tab_panel_style(active_tab: str | None, panel: str) -> dict[str, str]:
    active = active_tab if active_tab in {"study", "metrics", "traceability", "findings"} else "study"
    return {"display": "block" if active == panel else "none", "width": "100%"}


def _page_header(model: MethodsModelV3):
    return html.Header(
        [
            html.Div(
                [
                    html.Div([html.Span("RESEARCH PROVENANCE", className="analysis-eyebrow"), html.Span("READ-ONLY AUDIT", className="analysis-lane-badge")], className="analysis-page-header__eyebrow"),
                    html.H1("Methods & Audit", className="analysis-page-header__title"),
                    html.P("Canonical registry cho study design, metric roles, statistical protocol, report-number provenance, findings và limitations. Trang này giải thích nguồn gốc kết quả; không tái dựng hoặc tái tính analytical science.", className="analysis-page-header__subtitle"),
                ]
            ),
            html.Div(
                [
                    html.Div([html.Span("Release"), html.Strong(model.release["release_id"])], className="analysis-context-pill"),
                    html.Div([html.Span("Presentation tables"), html.Strong(str(model.release["table_count"]))], className="analysis-context-pill"),
                    html.Div([html.Span("Recompute"), html.Strong("FORBIDDEN")], className="analysis-context-pill"),
                ],
                className="analysis-page-header__context",
            ),
        ],
        className="analysis-page-header methods-page__header",
    )


def _lineage(model: MethodsModelV3):
    nodes = [
        (model.release["parent_release_id"], "Certified analytical release"),
        (model.release["release_id"], "Certified presentation mart"),
        ("llm-xai-multidataset-dashboard-v3", "Read-only research dashboard"),
    ]
    children = []
    for index, (name, label) in enumerate(nodes):
        children.append(html.Div([html.Span(label), html.Strong(name)], className="methods-lineage__node"))
        if index < len(nodes) - 1:
            children.append(DashIconify(icon="solar:arrow-right-linear", width=24, className="methods-lineage__arrow"))
    return html.Section(
        [
            html.Div([html.Span("CERTIFIED LINEAGE", className="analysis-eyebrow"), html.H2("Release provenance", className="methods-section-title")]),
            html.Div(children, className="methods-lineage"),
            html.Div(
                [
                    html.Div([html.Span("Replication scope"), html.Strong(model.release["replication_scope"])], className="methods-release-fact"),
                    html.Div([html.Span("Robust recommendation"), html.Strong(model.release["robust_recommendation_status"])], className="methods-release-fact"),
                    html.Div([html.Span("Scientific recomputation"), html.Strong("false")], className="methods-release-fact"),
                ],
                className="methods-release-facts",
            ),
        ],
        className="methods-card methods-lineage-card",
        **{"data-testid": "methods-release-lineage"},
    )


def _rq_registry(model: MethodsModelV3):
    cards = []
    for row in model.research_questions:
        cards.append(
            html.Div(
                [html.Span(str(row["rq_id"]), className="methods-rq__id"), html.H3(str(row["title"]), className="methods-rq__title"), html.P(str(row["scope"]), className="methods-rq__scope")],
                className="methods-rq",
            )
        )
    return html.Section(
        [html.Div([html.Span("STUDY DESIGN", className="analysis-eyebrow"), html.H2("Research Question Registry", className="methods-section-title"), html.P("Canonical RQ titles được đọc trực tiếp từ M29 research_questions; không hard-code historical naming.", className="methods-section-subtitle")]), html.Div(cards, className="methods-rq-grid")],
        className="methods-card",
    )


def _study_boundaries(model: MethodsModelV3):
    return html.Section(
        [
            html.Div([html.Span("INTERPRETATION BOUNDARY", className="analysis-eyebrow"), html.H2("Scope & external validity", className="methods-section-title")]),
            html.Div(
                [
                    html.Div([html.Span("Evaluated studies"), html.Strong("Home Credit · Freddie Mac")], className="methods-boundary__item"),
                    html.Div([html.Span("Cross-dataset identity"), html.Strong(model.release["replication_scope"])], className="methods-boundary__item"),
                    html.Div([html.Span("Universal-domain generalization"), html.Strong("NOT ESTABLISHED")], className="methods-boundary__item"),
                    html.Div([html.Span("Decision status"), html.Strong(model.release["robust_recommendation_status"])], className="methods-boundary__item"),
                ],
                className="methods-boundary-grid",
            ),
        ],
        className="methods-card methods-boundary-card",
    )


def metric_options(model: MethodsModelV3) -> list[dict[str, str]]:
    return [
        {
            "value": str(row["metric_key"]),
            "label": f"{row['metric_id']} · {row['family']} · {row['analysis_lane']}",
        }
        for row in model.metric_dictionary
    ]


def metric_detail(model: MethodsModelV3, metric_key: str | None):
    row = metric_by_key(model, metric_key)
    if row is None:
        return html.Div("Không tìm thấy certified metric registry row.", className="methods-empty")
    return html.Div(
        [
            html.Div([html.Span("METRIC REGISTRY", className="analysis-eyebrow"), html.H2(str(row["metric_id"]), className="methods-detail-title")]),
            html.Div(
                [
                    _detail_fact("Canonical metric_id", row["metric_id"]),
                    _detail_fact("Family", row["family"]),
                    _detail_fact("Unit", row["unit"]),
                    _detail_fact("Analysis lane", row["analysis_lane"]),
                    _detail_fact("Formula", CAPABILITY_GAP),
                ],
                className="methods-detail-grid",
            ),
            html.P("Analysis lane là scientific role của metric; filtering trong UI không thay đổi role hoặc tái xếp hạng analytical universe.", className="methods-detail-note"),
        ],
        id=METRIC_DETAIL_ID,
        className="methods-detail-card",
        **{"data-testid": "methods-metric-detail", "data-metric-key": str(row["metric_key"]), "data-metric-id": str(row["metric_id"])},
    )


def _analysis_lanes():
    lanes = [
        ("PRIMARY", "Primary inferential/decision endpoint"),
        ("SECONDARY", "Secondary analytical lens"),
        ("DIAGNOSTIC", "Mechanism/diagnostic evidence"),
        ("REPLICATION", "Cross-dataset replication evidence"),
        ("DECISION", "Certified decision-support artifact"),
        ("SENSITIVITY", "Sensitivity-only; không thay primary conclusion"),
    ]
    return html.Section(
        [html.Div([html.Span("SCIENTIFIC ROLE", className="analysis-eyebrow"), html.H2("Analysis Lane semantics", className="methods-section-title")]), html.Div([html.Div([html.Strong(lane), html.Span(text)], className=f"methods-lane methods-lane--{lane.lower()}") for lane, text in lanes], className="methods-lane-grid")],
        className="methods-card",
    )


def _protocol(model: MethodsModelV3):
    m = model.method_evidence
    cards = [
        ("Omnibus test", " · ".join(m["omnibus_test_methods"])),
        ("Planned contrast adjustment", " · ".join(m["contrast_adjustments"])),
        ("Primary subject count(s)", " · ".join(str(value) for value in m["primary_subject_count"])),
        ("Primary NI margin", f"δ = {float(m['primary_margin']):.2f}" if m["primary_margin"] is not None else "—"),
        ("Scientific recomputation", "DISABLED IN DASHBOARD"),
    ]
    return html.Section(
        [html.Div([html.Span("CERTIFIED PROTOCOL", className="analysis-eyebrow"), html.H2("Statistical protocol", className="methods-section-title")]), html.Div([html.Div([html.Span(label), html.Strong(value)], className="methods-protocol__item") for label, value in cards], className="methods-protocol-grid")],
        className="methods-card",
    )


def _detail_fact(label: str, value: object, *, mono: bool = False):
    text = "—" if value is None or str(value) == "nan" else str(value)
    return html.Div([html.Span(label), html.Strong(text, className="methods-mono" if mono else "")], className="methods-detail-fact")


def _pretty_json(value: object) -> str:
    if value is None or str(value) == "nan":
        return "—"
    text = str(value)
    try:
        parsed = json.loads(text)
    except Exception:
        return text
    return json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True)


def report_options(model: MethodsModelV3) -> list[dict[str, str]]:
    return [{"value": str(row["report_number_id"]), "label": str(row["report_number_id"])} for row in model.report_source_index]


def report_detail(model: MethodsModelV3, report_id: str | None):
    row = report_by_id(model, report_id)
    if row is None:
        return html.Div("Không tìm thấy certified provenance row.", className="methods-empty")
    return html.Div(
        [
            html.Div([html.Span("REPORT NUMBER PROVENANCE", className="analysis-eyebrow"), html.H2(str(row["report_number_id"]), className="methods-detail-title methods-mono")]),
            html.Div(
                [
                    _detail_fact("Family", row.get("family")),
                    _detail_fact("Dataset scope", row.get("dataset_scope")),
                    _detail_fact("Metric ID", row.get("metric_id"), mono=True),
                    _detail_fact("Population", row.get("population_id")),
                    _detail_fact("Denominator", row.get("denominator")),
                    _detail_fact("Unit", row.get("unit")),
                    _detail_fact("Analysis lane", row.get("analysis_lane")),
                    _detail_fact("Source artifact", row.get("source_artifact_id"), mono=True),
                    _detail_fact("Source SHA-256", row.get("source_sha256"), mono=True),
                    _detail_fact("Source field", row.get("source_field"), mono=True),
                    _detail_fact("Aggregation", row.get("aggregation")),
                    _detail_fact("Source path", row.get("source_path"), mono=True),
                ],
                className="methods-detail-grid methods-detail-grid--wide",
            ),
            html.Div([html.Span("value_json", className="methods-code-label"), html.Pre(_pretty_json(row.get("value_json")), className="methods-json")]),
            html.Div([html.Span("source_filter_json", className="methods-code-label"), html.Pre(_pretty_json(row.get("source_filter_json")), className="methods-json")]),
        ],
        id=REPORT_DETAIL_ID,
        className="methods-detail-card methods-provenance-detail",
        **{
            "data-testid": "methods-provenance-detail",
            "data-report-number-id": str(row["report_number_id"]),
            "data-source-artifact-id": str(row.get("source_artifact_id")),
        },
    )


def provenance_grid(model: MethodsModelV3):
    rows = []
    for row in model.report_source_index:
        rows.append({
            "report_number_id": str(row["report_number_id"]),
            "family": str(row["family"]),
            "dataset_scope": str(row["dataset_scope"]),
            "metric_id": str(row["metric_id"]),
            "analysis_lane": str(row["analysis_lane"]),
            "source_artifact_id": str(row["source_artifact_id"]),
            "source_field": str(row["source_field"]),
        })
    return dag.AgGrid(
        id=REPORT_GRID_ID,
        rowData=rows,
        columnDefs=[
            {"field": "report_number_id", "headerName": "Report number", "minWidth": 310, "flex": 2},
            {"field": "family", "headerName": "Family", "minWidth": 150},
            {"field": "dataset_scope", "headerName": "Dataset", "minWidth": 135},
            {"field": "metric_id", "headerName": "Metric", "minWidth": 210, "flex": 1},
            {"field": "analysis_lane", "headerName": "Lane", "minWidth": 120},
            {"field": "source_artifact_id", "headerName": "Source artifact", "minWidth": 230},
            {"field": "source_field", "headerName": "Source field", "minWidth": 200},
        ],
        defaultColDef={"sortable": True, "filter": True, "resizable": True, "minWidth": 100},
        dashGridOptions={"pagination": True, "paginationPageSize": 15, "paginationPageSizeSelector": False, "animateRows": False},
        getRowId="params.data.report_number_id",
        className="ag-theme-quartz research-data-grid methods-provenance-grid",
        style={"height": "500px", "width": "100%"},
    )


def schema_grid(model: MethodsModelV3, table_name: str | None):
    rows = schema_for_table(model, table_name)
    return dag.AgGrid(
        id=SCHEMA_GRID_ID,
        rowData=rows,
        columnDefs=[
            {"field": "column_name", "headerName": "Column", "minWidth": 260, "flex": 1},
            {"field": "dtype", "headerName": "dtype", "minWidth": 125},
            {"field": "presentation_only", "headerName": "Presentation only", "minWidth": 165},
        ],
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 15, "paginationPageSizeSelector": False, "animateRows": False},
        className="ag-theme-quartz research-data-grid methods-schema-grid",
        style={"height": "440px", "width": "100%"},
    )


def _report_links(report_ids: tuple[str, ...]):
    if not report_ids:
        return html.P("No certified supporting report-number reference.", className="methods-detail-note")
    return html.Div([dcc.Link(report_id, href=f"/methods?{urlencode({'tab':'traceability','report':report_id})}", className="methods-evidence-link methods-mono") for report_id in report_ids], className="methods-evidence-links")


def finding_detail(model: MethodsModelV3, finding_id: str | None):
    row = finding_by_id(model, finding_id)
    if row is None:
        return html.Div("Không tìm thấy certified finding.", className="methods-empty")
    limitations = row.get("limitations") or ()
    return html.Div(
        [
            html.Div([html.Span("CERTIFIED FINDING", className="analysis-eyebrow"), html.H2(str(row["finding_id"]), className="methods-detail-title methods-mono"), html.Div(str(row["status"]), className="methods-finding-status")]),
            html.Div(
                [
                    _detail_fact("Research question", row.get("research_question_id")),
                    _detail_fact("Finding type", row.get("finding_type")),
                    _detail_fact("Dataset scope", row.get("dataset_scope")),
                    _detail_fact("Robustness status", row.get("robustness_status")),
                ],
                className="methods-detail-grid",
            ),
            html.Div([html.H3("Supporting report number(s)", className="methods-detail-subtitle"), _report_links(tuple(row.get("supporting_report_refs") or ()))], className="methods-finding-chain"),
            html.Div(
                [
                    html.H3("Certified limitation chain", className="methods-detail-subtitle"),
                    html.Div(
                        [
                            html.Div([html.Strong(str(lim["limitation_id"]), className="methods-mono"), html.P(str(lim["statement"])), html.P([html.B("Mitigation · "), str(lim["mitigation"])], className="methods-detail-note")], className="methods-finding-limitation")
                            for lim in limitations
                        ]
                        or [html.P("No certified limitation reference attached to this finding.", className="methods-detail-note")],
                        className="methods-finding-limitations",
                    ),
                ],
                className="methods-finding-chain",
            ),
        ],
        id=FINDING_DETAIL_ID,
        className="methods-detail-card methods-finding-detail",
        **{"data-testid": "methods-finding-detail", "data-finding-id": str(row["finding_id"])},
    )


def limitations_grid(model: MethodsModelV3):
    rows = [dict(row) for row in model.limitations]
    return dag.AgGrid(
        id=LIMITATIONS_GRID_ID,
        rowData=rows,
        columnDefs=[
            {"field": "limitation_id", "headerName": "Limitation ID", "minWidth": 280, "flex": 1},
            {"field": "category", "headerName": "Category", "minWidth": 145},
            {"field": "scope", "headerName": "Scope", "minWidth": 145},
            {"field": "severity", "headerName": "Severity", "minWidth": 110},
            {"field": "statement", "headerName": "Statement", "minWidth": 360, "flex": 2, "tooltipField": "statement"},
            {"field": "mitigation", "headerName": "Mitigation", "minWidth": 360, "flex": 2, "tooltipField": "mitigation"},
            {"field": "source_evidence", "headerName": "Source evidence", "minWidth": 230},
        ],
        defaultColDef={"sortable": True, "filter": True, "resizable": True, "minWidth": 100},
        dashGridOptions={"pagination": True, "paginationPageSize": 11, "paginationPageSizeSelector": False, "animateRows": False, "tooltipShowDelay": 250},
        getRowId="params.data.limitation_id",
        className="ag-theme-quartz research-data-grid methods-limitations-grid",
        style={"height": "510px", "width": "100%"},
    )


def capability_boundary(model: MethodsModelV3):
    m = model.method_evidence
    items = [
        ("Metric formulas", m["metric_formula_capability"]),
        ("Validator detailed sensitivity", m["validator_readiness_capability"]),
        ("Template baseline detailed analysis", m["template_readiness_capability"]),
    ]
    return html.Section(
        [html.Div([html.Span("CAPABILITY BOUNDARIES", className="analysis-eyebrow"), html.H2("Not materialized in visualization-data-v3", className="methods-section-title"), html.P("Các artifacts này không được reconstruct từ memory, legacy release hoặc upstream engines trong presentation layer.", className="methods-section-subtitle")]), html.Div([html.Div([html.Span(label), html.Strong(value)], className="methods-capability__item") for label, value in items], className="methods-capability-grid")],
        className="methods-card methods-capability-card",
        **{"data-testid": "methods-capability-boundary"},
    )


def render(model: MethodsModelV3):
    study_panel = html.Div([_lineage(model), _rq_registry(model), _study_boundaries(model)], id=STUDY_PANEL_ID, style=tab_panel_style(model.initial_tab, "study"))

    metrics_panel = html.Div(
        [
            html.Section(
                [
                    html.Div([html.Span("METRIC REGISTRY", className="analysis-eyebrow"), html.H2("Metric role & unit", className="methods-section-title"), html.P("41 certified registry rows. Một metric_id có thể xuất hiện ở nhiều family/analysis lanes; selector dùng composite key để không làm mất identity.", className="methods-section-subtitle")]),
                    dmc.Select(id=METRIC_SELECT_ID, value=model.selected_metric_key, data=metric_options(model), searchable=True, allowDeselect=False, label="Metric registry row", size="sm"),
                    html.Div(metric_detail(model, model.selected_metric_key), id=METRIC_DETAIL_HOST_ID),
                ],
                className="methods-card",
            ),
            _analysis_lanes(),
            _protocol(model),
        ],
        id=METRICS_PANEL_ID,
        style=tab_panel_style(model.initial_tab, "metrics"),
    )

    trace_panel = html.Div(
        [
            html.Section(
                [
                    html.Div([html.Span("TRACEABILITY", className="analysis-eyebrow"), html.H2("Report Number / Provenance Explorer", className="methods-section-title"), html.P("275 certified mappings từ report_number_id về artifact, SHA-256, source field, aggregation, path, value và filter.", className="methods-section-subtitle")]),
                    dmc.Select(id=REPORT_SELECT_ID, value=model.selected_report_id, data=report_options(model), searchable=True, allowDeselect=False, label="Report number", size="sm"),
                    html.Div([provenance_grid(model), html.Div(report_detail(model, model.selected_report_id), id=REPORT_DETAIL_HOST_ID)], className="methods-provenance-layout"),
                ],
                className="methods-card methods-provenance-card",
            ),
            html.Section(
                [
                    html.Div([html.Span("PRESENTATION SCHEMA", className="analysis-eyebrow"), html.H2("Visualization Schema Explorer", className="methods-section-title"), html.P("31 presentation tables · 560 column dictionary entries. Đây là schema của M29 mart, không phải upstream raw schema.", className="methods-section-subtitle")]),
                    dmc.Select(id=TABLE_SELECT_ID, value=model.selected_table_name, data=[{"value": name, "label": name} for name in model.table_names], searchable=True, allowDeselect=False, label="Presentation table", size="sm"),
                    schema_grid(model, model.selected_table_name),
                ],
                className="methods-card",
            ),
        ],
        id=TRACE_PANEL_ID,
        style=tab_panel_style(model.initial_tab, "traceability"),
    )

    findings_panel = html.Div(
        [
            html.Section(
                [
                    html.Div([html.Span("FINDINGS & EVIDENCE", className="analysis-eyebrow"), html.H2("Finding Evidence Chain", className="methods-section-title"), html.P("Mỗi finding giữ certified supporting report number và limitation refs; dashboard không tự suy luận quan hệ mới.", className="methods-section-subtitle")]),
                    dmc.Select(id=FINDING_SELECT_ID, value=model.selected_finding_id, data=[{"value": value, "label": value} for value in model.finding_ids], allowDeselect=False, label="Certified finding", size="sm"),
                    html.Div(finding_detail(model, model.selected_finding_id), id=FINDING_DETAIL_HOST_ID),
                ],
                className="methods-card",
            ),
            html.Section([html.Div([html.Span("LIMITATIONS REGISTRY", className="analysis-eyebrow"), html.H2("11 certified limitations", className="methods-section-title"), html.P("Dùng column filters để tìm theo severity/category/scope. Severity giữ nguyên categorical metadata; không chuyển thành arbitrary risk score.", className="methods-section-subtitle")]), limitations_grid(model)], className="methods-card"),
            capability_boundary(model),
        ],
        id=FINDINGS_PANEL_ID,
        style=tab_panel_style(model.initial_tab, "findings"),
    )

    return html.Main(
        [
            _page_header(model),
            dmc.SegmentedControl(
                id=TABS_ID,
                value=model.initial_tab,
                data=[
                    {"value": "study", "label": "Study design"},
                    {"value": "metrics", "label": "Metrics & protocol"},
                    {"value": "traceability", "label": "Traceability"},
                    {"value": "findings", "label": "Findings & limitations"},
                ],
                w="100%",
                radius="md",
                size="sm",
                className="analysis-tabs-control methods-tabs-control",
            ),
            study_panel,
            metrics_panel,
            trace_panel,
            findings_panel,
            html.P("Certified presentation source · M29 visualization-data-v3 · Audit surfaces are read-only", className="analysis-source-footer"),
        ],
        className="research-page methods-page methods-page--golden",
        **{"data-testid": "methods-page"},
    )


def layout(**_):
    from ..methods_model import build_methods_model
    from ..repository import get_v3_repository

    return html.Div(render(build_methods_model(get_v3_repository(), "vi")), id=CONTENT_ID)
