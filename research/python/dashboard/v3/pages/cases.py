from __future__ import annotations

from urllib.parse import urlencode
import math

import dash
import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from research.python.dashboard.theme import PLOTLY_CONFIG

from ..cases_model import CasesModelV3, STRATUM_LABELS, canonical_cases_state, case_option_records, stratum_options
from ..effectiveness_model import MODEL_LABELS
from ..figures import (
    cases_claim_type_status_matrix,
    cases_performance_landscape,
    cases_section_profile,
    cases_validation_composition,
)

CONTENT_ID = "v3-cases-content"
DATASET_ID = "v3-cases-dataset"
STRATUM_ID = "v3-cases-stratum"
CASE_ID = "v3-cases-case"
MODEL_ID = "v3-cases-model"
EVIDENCE_ID = "v3-cases-evidence"
TABS_ID = "cases-tabs"
LANDSCAPE_PANEL_ID = "cases-tab-landscape-panel"
DIAGNOSTICS_PANEL_ID = "cases-tab-diagnostics-panel"
CLAIMS_PANEL_ID = "cases-tab-claims-panel"
LANDSCAPE_ID = "cases-performance-landscape"
VALIDATION_ID = "cases-validation-composition"
CLAIM_TYPE_ID = "cases-claim-type-status"
SECTION_ID = "cases-section-profile"
CONTEXT_ID = "cases-context-strip"
CONTEXT_HOST_ID = "cases-context-host"
GENERATION_SUMMARY_ID = "cases-selected-generation-summary"
GENERATION_SUMMARY_HOST_ID = "cases-selected-generation-host"
CLAIM_GRID_ID = "cases-claim-grid"
CAPABILITY_ID = "cases-capability-boundary"
SELECTED_GENERATION_STORE_ID = "cases-selected-generation-store"
LANDSCAPE_SELECTION_STORE_ID = "cases-landscape-selection-store"
HYDRATED_STORE_ID = "cases-state-hydrated-store"
HEADER_DATASET_VALUE_ID = "cases-header-dataset-value"
DETAIL_DRAWER_ID = "cases-claim-detail-drawer"
DETAIL_DRAWER_TITLE_ID = "cases-claim-detail-title-content"
DETAIL_DRAWER_BODY_ID = "cases-claim-detail-body-content"


def register_page() -> None:
    dash.register_page(
        "llm_xai_dashboard_v3.cases",
        path="/cases",
        name="Cases",
        title="Case Explorer · LLM–XAI Research Dashboard",
        order=5,
        layout=layout,
    )


def tab_panel_style(active_tab: str | None, panel: str) -> dict[str, str]:
    active = active_tab if active_tab in {"landscape", "diagnostics", "claims"} else "landscape"
    return {"display": "block" if active == panel else "none", "width": "100%"}


def _scope_label(scope: str) -> str:
    return "Home Credit" if scope == "HOME_CREDIT" else "Freddie Mac"


def _chart_panel(*, graph_id: str, title: str, subtitle: str, source: str, figure, class_name: str = ""):
    height = int(figure.layout.height or 360)
    classes = "cases-chart"
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
                        w=360,
                        position="left",
                        withArrow=True,
                    ),
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


def _page_header(model: CasesModelV3):
    return html.Header(
        [
            html.Div(
                [
                    html.Div([html.Span("CASE-LEVEL EVIDENCE", className="analysis-eyebrow"), html.Span("CERTIFIED DIAGNOSTICS", className="analysis-lane-badge")], className="analysis-page-header__eyebrow"),
                    html.H1("Case Explorer", className="analysis-page-header__title"),
                    html.P("Đi từ aggregate finding xuống một canonical case, một model × evidence generation và cuối cùng là từng certified claim diagnostic — không dựng lại raw provider text.", className="analysis-page-header__subtitle"),
                ]
            ),
            html.Div(
                [
                    html.Div([html.Span("Dataset"), html.Strong(_scope_label(model.scope), id=HEADER_DATASET_VALUE_ID)], className="analysis-context-pill"),
                    html.Div([html.Span("Case universe"), html.Strong("36 / study")], className="analysis-context-pill"),
                    html.Div([html.Span("Per case"), html.Strong("3 models × S0–S5")], className="analysis-context-pill"),
                ],
                className="analysis-page-header__context",
            ),
        ],
        className="analysis-page-header cases-page__header",
    )


def _controls(model: CasesModelV3):
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Điều hướng case", className="analysis-filter-bar__label"),
                    dmc.Select(
                        id=DATASET_ID,
                        label="Dataset",
                        value=model.scope,
                        data=[{"value": "HOME_CREDIT", "label": "Home Credit"}, {"value": "FREDDIE", "label": "Freddie Mac"}],
                        allowDeselect=False,
                        w=185,
                        size="sm",
                    ),
                    dmc.Select(id=STRATUM_ID, label="Stratum", value=model.selected_stratum, data=stratum_options(model), allowDeselect=False, w=205, size="sm"),
                    dmc.Select(id=CASE_ID, label="Case", value=model.selected_case_id, data=case_option_records(model), allowDeselect=False, searchable=True, w=220, size="sm"),
                    dmc.Select(
                        id=MODEL_ID,
                        label="Model",
                        value=model.selected_model_id,
                        data=[{"value": value, "label": MODEL_LABELS.get(value, value)} for value in model.model_ids],
                        allowDeselect=False,
                        w=210,
                        size="sm",
                    ),
                    dmc.Select(
                        id=EVIDENCE_ID,
                        label="Evidence",
                        value=model.selected_evidence_level,
                        data=[{"value": value, "label": value} for value in model.evidence_levels],
                        allowDeselect=False,
                        w=135,
                        size="sm",
                    ),
                ],
                className="cases-control-bar__controls",
            ),
            html.Div(
                [DashIconify(icon="solar:shield-check-linear", width=16), html.Span("Controls chỉ resolve identity trong certified M29; không tái chạy generation, validator hay metric engine.")],
                className="analysis-filter-bar__note",
            ),
        ],
        className="analysis-filter-bar cases-control-bar",
    )


def case_context(model: CasesModelV3):
    row = model.case_summary
    complete = bool(row.get("complete_case"))
    usable = int(row.get("usable_generation_count", 0))
    claims = int(row.get("claim_count", 0))
    return html.Div(
        [
            html.Div([html.Span("Case"), html.Strong(model.selected_case_id)], className="cases-context-item"),
            html.Div([html.Span("Selection stratum"), html.Strong(STRATUM_LABELS.get(model.selected_stratum, model.selected_stratum))], className="cases-context-item"),
            html.Div([html.Span("Complete case"), html.Strong("YES" if complete else "NO")], className=f"cases-context-item {'cases-context-item--warn' if not complete else ''}"),
            html.Div([html.Span("Usable generations"), html.Strong(f"{usable} / 18")], className="cases-context-item"),
            html.Div([html.Span("Claims across case"), html.Strong(f"{claims:,}")], className="cases-context-item"),
        ],
        id=CONTEXT_ID,
        className="cases-context-strip",
        **{"data-testid": "cases-context-strip", "data-case-id": model.selected_case_id, "data-dataset-id": model.scope},
    )


def _metric_card(label: str, value: str, *, primary: bool = False):
    return html.Div([html.Span(label, className="cases-metric-card__label"), html.Strong(value, className="cases-metric-card__value")], className=f"cases-metric-card {'cases-metric-card--primary' if primary else ''}")


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(math.isnan(value))
    except (TypeError, ValueError):
        return str(value).strip().lower() in {"", "nan", "none", "null"}


def _display_int(value: object) -> str:
    if _is_missing(value):
        return "—"
    return f"{int(float(value)):,}"


def _display_float(value: object, *, suffix: str = "") -> str:
    if _is_missing(value):
        return "—"
    return f"{float(value):.2f}{suffix}"


def generation_summary(model: CasesModelV3):
    g = model.generation
    unusable = bool(g.get("is_unusable"))
    query = urlencode({"dataset": model.scope, "model": model.selected_model_id, "evidence": model.selected_evidence_level})
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("SELECTED GENERATION", className="analysis-eyebrow"),
                            html.H2(f"{g['model_label']} × {model.selected_evidence_level}", className="cases-generation-summary__title"),
                            html.P(f"generation_id · {g['generation_id']}", className="cases-generation-summary__id"),
                        ]
                    ),
                    html.Span("UNUSABLE" if unusable else "USABLE", className=f"cases-generation-state {'cases-generation-state--bad' if unusable else 'cases-generation-state--good'}"),
                ],
                className="cases-generation-summary__header",
            ),
            html.Div(
                [
                    _metric_card("End-to-End Faithfulness", g["end_to_end_faithfulness_yield_display"], primary=True),
                    _metric_card("Resolved Faithfulness", g["resolved_faithfulness_display"]),
                    _metric_card("Verifiability", g["verifiability_display"]),
                    _metric_card("Conservative Faithfulness", g["conservative_faithfulness_display"]),
                ],
                className="cases-metric-grid",
            ),
            html.Div(
                [
                    html.Div([html.Span("Runtime"), html.Strong(str(g.get("runtime_status", "—")))], className="cases-generation-meta__item"),
                    html.Div([html.Span("Claims"), html.Strong(_display_int(g.get("claim_count")))], className="cases-generation-meta__item"),
                    html.Div([html.Span("Total tokens"), html.Strong(_display_int(g.get("total_token_count")))], className="cases-generation-meta__item"),
                    html.Div([html.Span("Latency"), html.Strong(_display_float(g.get("latency_seconds"), suffix="s"))], className="cases-generation-meta__item"),
                    html.Div([html.Span("Retry"), html.Strong(_display_int(g.get("retry_count")))], className="cases-generation-meta__item"),
                ],
                className="cases-generation-meta",
            ),
            html.Div(
                [
                    dcc.Link("Mở Effectiveness", href=f"/effectiveness?tab=primary&{query}", className="analysis-link-button analysis-link-button--light"),
                    dcc.Link("Mở Mechanisms", href=f"/mechanisms?tab=quality&{query}", className="analysis-link-button analysis-link-button--light"),
                ],
                className="cases-generation-summary__actions",
            ),
        ],
        id=GENERATION_SUMMARY_ID,
        className="cases-generation-summary",
        **{
            "data-testid": "cases-selected-generation",
            "data-dataset-id": model.scope,
            "data-case-id": model.selected_case_id,
            "data-generation-id": model.selected_generation_id,
            "data-model-id": model.selected_model_id,
            "data-evidence-level": model.selected_evidence_level,
        },
    )


def claim_grid_records(model: CasesModelV3) -> list[dict]:
    rows = []
    for row in model.claims:
        span = str(row.get("source_text") or "")
        preview = span if len(span) <= 140 else span[:137] + "…"
        rows.append(
            {
                "claim_id": str(row.get("claim_id")),
                "validation_status": str(row.get("validation_status")),
                "claim_type": str(row.get("claim_type")),
                "claim_subtype": "—" if row.get("claim_subtype") is None else str(row.get("claim_subtype")),
                "source_section": "—" if row.get("source_section") is None else str(row.get("source_section")),
                "source_preview": preview,
                "feature_id": "—" if row.get("feature_id") is None or str(row.get("feature_id")) == "nan" else str(row.get("feature_id")),
                "concept_id": "—" if row.get("concept_id") is None or str(row.get("concept_id")) == "nan" else str(row.get("concept_id")),
                "has_source_anchor": bool(row.get("has_source_anchor")),
                "has_numeric_value": bool(row.get("has_numeric_value")),
            }
        )
    return rows


def claim_grid(model: CasesModelV3):
    return dag.AgGrid(
        id=CLAIM_GRID_ID,
        rowData=claim_grid_records(model),
        columnDefs=[
            {"field": "validation_status", "headerName": "Validation", "minWidth": 160},
            {"field": "claim_type", "headerName": "Claim type", "minWidth": 155},
            {"field": "claim_subtype", "headerName": "Subtype", "minWidth": 150},
            {"field": "source_section", "headerName": "Source section", "minWidth": 170},
            {"field": "source_preview", "headerName": "Certified diagnostic source span", "minWidth": 360, "flex": 2, "tooltipField": "source_preview"},
            {"field": "feature_id", "headerName": "Feature", "minWidth": 160},
            {"field": "concept_id", "headerName": "Concept", "minWidth": 150},
            {"field": "has_source_anchor", "headerName": "Source anchor", "minWidth": 125},
            {"field": "has_numeric_value", "headerName": "Numeric", "minWidth": 105},
        ],
        defaultColDef={"sortable": True, "filter": True, "resizable": True, "minWidth": 95},
        dashGridOptions={"pagination": True, "paginationPageSize": 15, "paginationPageSizeSelector": False, "animateRows": False, "tooltipShowDelay": 250},
        getRowId="params.data.claim_id",
        className="ag-theme-quartz research-data-grid cases-claim-grid",
        style={"height": "520px", "width": "100%"},
    )


def _kv(label: str, value: object):
    text = "—" if value is None or str(value) == "nan" else str(value)
    return html.Div([html.Span(label), html.Strong(text)], className="cases-claim-detail__kv")


def claim_drawer(row: dict | None):
    if not row:
        return "Claim trace", html.Div("Không tìm thấy certified claim row.")
    source_text = str(row.get("source_text") or "—")
    coverage = row.get("best_safe_phrase_token_coverage")
    coverage_text = "—" if coverage is None or str(coverage) == "nan" else f"{float(coverage):.1%}"
    body = html.Div(
        [
            html.Div(
                [
                    _kv("claim_id", row.get("claim_id")),
                    _kv("generation_id", row.get("generation_id")),
                    _kv("Validation", row.get("validation_status")),
                    _kv("Claim type", row.get("claim_type")),
                    _kv("Subtype", row.get("claim_subtype")),
                    _kv("Subject", row.get("subject_type")),
                    _kv("Source section", row.get("source_section")),
                    _kv("Feature ID", row.get("feature_id")),
                    _kv("Concept ID", row.get("concept_id")),
                ],
                className="cases-claim-detail__grid",
            ),
            html.Div([html.Span("Certified diagnostic source span", className="analysis-eyebrow"), html.Blockquote(source_text, className="cases-certified-span")], className="cases-certified-span-wrap"),
            html.Div(
                [
                    _kv("Has source anchor", bool(row.get("has_source_anchor"))),
                    _kv("Has numeric value", bool(row.get("has_numeric_value"))),
                    _kv("Feature reference", bool(row.get("has_feature_reference"))),
                    _kv("Concept reference", bool(row.get("has_concept_reference"))),
                ],
                className="cases-claim-detail__grid",
            ),
            html.Div(
                [
                    html.H4("Lexical-overlap diagnostic", className="cases-claim-detail__section-title"),
                    html.P("Tín hiệu lexical chỉ là diagnostic safeguard; không phải bằng chứng nhân quả của copying.", className="cases-claim-detail__note"),
                    _kv("Match eligible", bool(row.get("safe_phrase_match_eligible"))),
                    _kv("Best match type", row.get("best_safe_phrase_match_type")),
                    _kv("Token coverage", coverage_text),
                    _kv("Any match", bool(row.get("safe_phrase_any_match"))),
                ],
                className="cases-claim-detail__section",
            ),
            html.Div(
                [
                    html.H4("Certified capability boundary", className="cases-claim-detail__section-title"),
                    html.P("Raw generation text · NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE"),
                    html.P("Raw claim text · NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE"),
                    html.P("Evidence source text · NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE"),
                ],
                className="cases-capability-inline",
            ),
        ],
        className="cases-claim-detail",
        **{"data-testid": "cases-claim-drawer-content", "data-claim-id": str(row.get("claim_id")), "data-generation-id": str(row.get("generation_id"))},
    )
    return f"Claim · {row.get('claim_id')}", body


def capability_boundary(model: CasesModelV3):
    items = [
        ("Generation metrics", model.capabilities.get("generation_metrics")),
        ("Claim validation diagnostics", model.capabilities.get("claim_validation_diagnostics")),
        ("Raw generation text", model.capabilities.get("raw_generation_text")),
        ("Raw claim text", model.capabilities.get("raw_claim_text")),
        ("Evidence source text", model.capabilities.get("evidence_source_text")),
    ]
    return html.Section(
        [
            html.Div([html.Span("CERTIFIED CAPABILITY BOUNDARY", className="analysis-eyebrow"), html.H2("Case-level evidence availability", className="cases-capability__title"), html.P("Trang chỉ hiển thị artifacts nằm trong authorized M28→M29 lineage; capability không có được ghi rõ thay vì fallback sang raw/legacy data.", className="cases-capability__subtitle")]),
            html.Div([html.Div([html.Span(label), html.Strong(str(value))], className=f"cases-capability__item {'cases-capability__item--available' if value == 'AVAILABLE' else ''}") for label, value in items], className="cases-capability__grid"),
        ],
        id=CAPABILITY_ID,
        className="cases-capability",
        **{"data-testid": "cases-capability-boundary"},
    )


def render(model: CasesModelV3):
    landscape = cases_performance_landscape(model.generation_rows, selected_generation_id=model.selected_generation_id)
    validation = cases_validation_composition(model.status_counts)
    claim_matrix = cases_claim_type_status_matrix(model.claim_type_status)
    sections = cases_section_profile(model.section_profile)

    landscape_panel = html.Div(
        [
            html.Div(
                [
                    _chart_panel(
                        graph_id=LANDSCAPE_ID,
                        title="Case Performance Landscape",
                        subtitle="Cùng một canonical case qua 3 models × S0–S5. Unusable generation được giữ N/A, không mã hóa như E2E=0.",
                        source="case_generation_metrics · certified generation-level End-to-End Faithfulness",
                        figure=landscape,
                    ),
                    html.Div(generation_summary(model), id=GENERATION_SUMMARY_HOST_ID),
                ],
                className="cases-landscape-grid",
            )
        ],
        id=LANDSCAPE_PANEL_ID,
        style=tab_panel_style(model.initial_tab, "landscape"),
    )

    diagnostics_panel = html.Div(
        [
            html.Div(
                [
                    _chart_panel(
                        graph_id=VALIDATION_ID,
                        title="Claim Validation Composition",
                        subtitle="100% composition của claims trong selected generation; tooltip luôn giữ exact numerator / denominator.",
                        source="case_generation_metrics · certified validation-status counts",
                        figure=validation,
                    ),
                    _chart_panel(
                        graph_id=SECTION_ID,
                        title="Narrative Section Profile",
                        subtitle="Certified claim count theo source_section của selected generation.",
                        source="case_claim_diagnostics · descriptive grouping only",
                        figure=sections,
                    ),
                ],
                className="cases-diagnostics-top-grid",
            ),
            _chart_panel(
                graph_id=CLAIM_TYPE_ID,
                title="Claim Type × Validation Status",
                subtitle="Local diagnostic matrix cho selected generation; đây là descriptive count, không phải inferential effect.",
                source="case_claim_diagnostics · certified claim_type × validation_status rows",
                figure=claim_matrix,
            ),
        ],
        id=DIAGNOSTICS_PANEL_ID,
        style=tab_panel_style(model.initial_tab, "diagnostics"),
    )

    claims_panel = html.Div(
        [
            html.Section(
                [
                    html.Div([html.H2("Claim Trace", className="analysis-chart__title"), html.P("Filter/search trực tiếp trong grid; click bất kỳ cell nào để mở exact certified claim trace.", className="analysis-chart__subtitle")], className="analysis-chart__header"),
                    claim_grid(model),
                ],
                className="cases-claim-trace",
            )
        ],
        id=CLAIMS_PANEL_ID,
        style=tab_panel_style(model.initial_tab, "claims"),
    )

    return html.Main(
        [
            _page_header(model),
            _controls(model),
            html.Div(case_context(model), id=CONTEXT_HOST_ID),
            dmc.SegmentedControl(
                id=TABS_ID,
                value=model.initial_tab,
                data=[
                    {"value": "landscape", "label": "Case landscape"},
                    {"value": "diagnostics", "label": "Generation diagnostics"},
                    {"value": "claims", "label": "Claim trace"},
                ],
                w="100%",
                radius="md",
                size="sm",
                className="analysis-tabs-control cases-tabs-control",
            ),
            dcc.Store(id=SELECTED_GENERATION_STORE_ID, data=canonical_cases_state(model), storage_type="memory"),
            dcc.Store(id=LANDSCAPE_SELECTION_STORE_ID, data=None, storage_type="memory"),
            dcc.Store(id=HYDRATED_STORE_ID, data=False, storage_type="memory"),
            landscape_panel,
            diagnostics_panel,
            claims_panel,
            capability_boundary(model),
            dmc.Drawer(
                html.Div(id=DETAIL_DRAWER_BODY_ID),
                id=DETAIL_DRAWER_ID,
                title=html.Div(id=DETAIL_DRAWER_TITLE_ID),
                opened=False,
                position="right",
                size="lg",
                padding="xl",
                overlayProps={"backgroundOpacity": 0.25, "blur": 2},
            ),
            html.P("Certified presentation source · M29 visualization-data-v3 · Không recompute science trong UI", className="analysis-source-footer"),
        ],
        className="research-page cases-page cases-page--golden",
        **{"data-testid": "cases-page"},
    )


def layout(**_):
    from ..cases_model import build_cases_model
    from ..repository import get_v3_repository

    return html.Div(render(build_cases_model(get_v3_repository(), "HOME_CREDIT", "vi")), id=CONTENT_ID)
