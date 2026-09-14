from __future__ import annotations

from urllib.parse import urlencode

import dash
import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from research.python.dashboard.theme import PLOTLY_CONFIG

from ..figures import (
    overview_major_effects,
    overview_option_landscape,
    overview_validation_composition,
)
from ..overview_model import OverviewMetricCard, OverviewModelV3


CONTENT_ID = "v3-overview-content"
LANDSCAPE_ID = "overview-model-evidence-landscape"
EFFECTS_ID = "overview-major-effects"
VALIDATION_ID = "overview-validation-composition"
DETAIL_DRAWER_ID = "overview-detail-drawer"
DETAIL_DRAWER_TITLE_ID = "overview-detail-drawer-title-content"
DETAIL_DRAWER_BODY_ID = "overview-detail-drawer-body-content"

_REPLICATION_LABELS = {
    "REPLICATED": "Replicated",
    "DIRECTIONALLY_REPLICATED": "Directional",
    "DIRECTION_CONFLICT": "Conflict",
    "INCONCLUSIVE": "Inconclusive",
}
_REPLICATION_CLASSES = {
    "REPLICATED": "overview-replication-segment--replicated",
    "DIRECTIONALLY_REPLICATED": "overview-replication-segment--directional",
    "DIRECTION_CONFLICT": "overview-replication-segment--conflict",
    "INCONCLUSIVE": "overview-replication-segment--inconclusive",
}


def register_page() -> None:
    dash.register_page(
        "llm_xai_dashboard_v3.overview",
        path="/",
        name="Tổng quan",
        title="Tổng quan · LLM–XAI Research Dashboard",
        order=0,
        layout=layout,
    )


def _provenance_tooltip(text: str):
    return dmc.Tooltip(
        dmc.ActionIcon(
            DashIconify(icon="solar:info-circle-linear", width=17),
            variant="subtle",
            color="gray",
            size="sm",
            radius="xl",
            **{"aria-label": "Xem provenance"},
        ),
        label=text,
        multiline=True,
        w=320,
        position="left",
        withArrow=True,
    )


def _metric_card(card: OverviewMetricCard):
    values = []
    for value in card.values:
        values.append(
            html.Div(
                [
                    html.Span(value.dataset_label, className="overview-kpi__dataset"),
                    html.Strong(value.display_value, className="overview-kpi__value"),
                ],
                className="overview-kpi__row",
            )
        )
    source_text = " · ".join(value.report_number_id for value in card.values)
    return html.Article(
        [
            html.Div(
                [
                    html.Span(card.label, className="overview-kpi__label"),
                    _provenance_tooltip(f"PRIMARY · {source_text}"),
                ],
                className="overview-kpi__topline",
            ),
            html.Div(values, className="overview-kpi__values"),
        ],
        className="overview-kpi overview-kpi--primary" if card.primary else "overview-kpi",
        **{"data-metric-id": card.key, "data-analysis-lane": card.analysis_lane},
    )


def _chart_header(*, title: str, subtitle: str, source: str):
    return html.Div(
        [
            html.Div(
                [
                    html.H2(title, className="overview-chart__title"),
                    html.P(subtitle, className="overview-chart__subtitle"),
                ]
            ),
            _provenance_tooltip(source),
        ],
        className="overview-chart__header",
    )


def _chart_panel(*, graph_id: str, title: str, subtitle: str, source: str, figure, class_name: str = ""):
    resolved = "overview-chart"
    if class_name:
        resolved += f" {class_name}"
    return html.Section(
        [
            _chart_header(title=title, subtitle=subtitle, source=source),
            dcc.Graph(
                id=graph_id,
                figure=figure,
                config=PLOTLY_CONFIG,
                responsive=True,
                className="overview-chart__graph",
                style={
                    "height": f"{int(figure.layout.height or 320)}px",
                    "minHeight": f"{int(figure.layout.height or 320)}px",
                },
                clear_on_unhover=False,
            ),
        ],
        className=resolved,
    )


def _replication_strip(model: OverviewModelV3):
    counts = list(model.replication_counts)
    total = sum(int(item["count"]) for item in counts) or 1
    segments = []
    legend = []
    for item in counts:
        count = int(item["count"])
        if count <= 0:
            continue
        status = str(item["status"])
        segments.append(
            html.Div(
                title=f"{status}: {count}",
                className=f"overview-replication-segment {_REPLICATION_CLASSES.get(status, '')}",
                style={"width": f"{count / total * 100:.6f}%"},
            )
        )
        legend.append(
            html.Div(
                [
                    html.Span(className=f"overview-replication-dot {_REPLICATION_CLASSES.get(status, '')}"),
                    html.Span(_REPLICATION_LABELS.get(status, status)),
                    html.Strong(str(count)),
                ],
                className="overview-replication-legend__item",
            )
        )
    return html.Div(
        [
            html.Div(segments, className="overview-replication-strip"),
            html.Div(legend, className="overview-replication-legend"),
        ]
    )


def _status_panel(model: OverviewModelV3):
    if model.scope != "CROSS_DATASET":
        return html.Section(
            [
                html.Div(
                    [
                        html.Span("Phạm vi nghiên cứu", className="overview-eyebrow"),
                        html.H2("Phân tích chuyên sâu", className="overview-status__title"),
                        html.P(
                            "18 Model × Evidence options và 3 Major Effects được giữ trong cùng certified study scope. Đi sâu vào từng analytical question mà không thay đổi primary endpoint.",
                            className="overview-status__description",
                        ),
                    ]
                ),
                html.Div(
                    [
                        dmc.Anchor([html.Strong("Effectiveness"), html.Span("Model × Evidence, effects và contrasts"), DashIconify(icon="solar:arrow-right-linear", width=16)], href="/effectiveness", className="overview-study-route"),
                        dmc.Anchor([html.Strong("Mechanisms"), html.Span("Loss và claim validation diagnostics"), DashIconify(icon="solar:arrow-right-linear", width=16)], href="/mechanisms", className="overview-study-route"),
                        dmc.Anchor([html.Strong("Case Explorer"), html.Span("Case-level behavior của 18 options"), DashIconify(icon="solar:arrow-right-linear", width=16)], href="/cases", className="overview-study-route"),
                    ],
                    className="overview-study-routes",
                ),
            ],
            className="overview-status-panel overview-status-panel--study",
        )

    rho = None if not model.rank_stability else model.rank_stability.get("spearman_rho")
    rho_display = "—" if rho is None else f"{float(rho):.3f}"
    limitation = next(
        (item for item in model.limitations if str(item.get("limitation_id")) == "MODEL_REVISION_UNKNOWN"),
        None,
    )
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Cross-dataset Replication", className="overview-eyebrow"),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Span("Rank stability", className="overview-stat__label"),
                                            html.Strong(f"ρ = {rho_display}", className="overview-stat__value"),
                                        ],
                                        className="overview-stat",
                                    ),
                                    dmc.Anchor("Xem replication evidence →", href="/effectiveness", className="overview-inline-link"),
                                ],
                                className="overview-status__headline",
                            ),
                            _replication_strip(model),
                            html.Div(
                                [
                                    html.Span("ⓘ Replication scope", className="overview-scope-note__label"),
                                    html.Code(model.replication_scope or "—", className="overview-scope-note__code"),
                                    html.Span(str(limitation.get("statement")) if limitation else "", className="overview-scope-note__text"),
                                ],
                                className="overview-scope-note",
                            ),
                        ],
                        className="overview-status__section",
                    ),
                    html.Div(
                        [
                            html.Span("Robust Decision", className="overview-eyebrow"),
                            html.Div(
                                model.robust_recommendation_status or "—",
                                className="overview-decision-status",
                            ),
                            html.P(
                                "Không có option nào đáp ứng đồng thời toàn bộ frozen cross-dataset selection requirements."
                                if model.robust_recommendation_status == "NO_ROBUST_RECOMMENDATION"
                                else "Kết quả được đọc trực tiếp từ certified decision release.",
                                className="overview-status__description",
                            ),
                            dmc.Anchor("Mở Decision Studio →", href="/decision", className="overview-inline-link"),
                        ],
                        className="overview-status__section overview-status__section--decision",
                    ),
                ],
                className="overview-status__grid",
            )
        ],
        className="overview-status-panel",
    )


def _explore_deeper():
    items = (
        ("Effectiveness", "Model × Evidence, effect sizes và planned contrasts", "/effectiveness", "solar:chart-2-linear"),
        ("Mechanisms", "Loss decomposition và claim validation diagnostics", "/mechanisms", "solar:layers-minimalistic-linear"),
        ("Decision Studio", "Hard gates, Non-Inferiority và certified scenarios", "/decision", "solar:scale-linear"),
        ("Robustness", "Population, metric và NI-margin sensitivity", "/robustness", "solar:shield-check-linear"),
    )
    return html.Section(
        [
            html.Div(
                [
                    html.Span("Phân tích chuyên sâu", className="overview-eyebrow"),
                    html.H2("Đi sâu vào analytical evidence", className="overview-section-title"),
                ]
            ),
            html.Div(
                [
                    dmc.Anchor(
                        [
                            DashIconify(icon=icon, width=20),
                            html.Div([html.Strong(title), html.Span(description)]),
                            DashIconify(icon="solar:arrow-right-linear", width=18),
                        ],
                        href=href,
                        className="overview-explore-card",
                    )
                    for title, description, href, icon in items
                ],
                className="overview-explore-grid",
            ),
        ],
        className="overview-explore",
    )


def render(model: OverviewModelV3):
    landscape = overview_option_landscape(model.option_rows, cross_dataset=model.scope == "CROSS_DATASET")
    effects = overview_major_effects(model.effects, cross_dataset=model.scope == "CROSS_DATASET")
    validation = overview_validation_composition(model.validation_rows)

    scope_label = {
        "HOME_CREDIT": "Home Credit",
        "FREDDIE": "Freddie Mac",
        "CROSS_DATASET": "Cross-dataset",
    }[model.scope]

    return html.Main(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Tổng quan", className="overview-eyebrow"),
                                    dmc.Badge("Đã chứng nhận", variant="light", color="teal", radius="xl", size="sm"),
                                ],
                                className="overview-page-header__eyebrow-row",
                            ),
                            html.H1(model.title, className="overview-page-header__title"),
                            html.P(model.subtitle, className="overview-page-header__subtitle"),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div([html.Span("Primary endpoint"), html.Strong("End-to-End Faithfulness")], className="overview-context-pill"),
                            html.Div([html.Span("Inference unit"), html.Strong("Canonical case")], className="overview-context-pill"),
                            html.Div([html.Span("Phạm vi"), html.Strong(scope_label)], className="overview-context-pill"),
                        ],
                        className="overview-page-header__context",
                    ),
                ],
                className="overview-page-header",
            ),
            html.Section([_metric_card(card) for card in model.cards], className="overview-kpi-grid"),
            html.Section(
                [
                    _chart_panel(
                        graph_id=LANDSCAPE_ID,
                        title="Model × Evidence Landscape",
                        subtitle="Primary endpoint · 3 models × S0–S5 · color scale cố định 0–100%",
                        source="Certified tables: option_performance / cross_dataset_option_performance",
                        figure=landscape,
                        class_name="overview-chart--landscape",
                    ),
                    _chart_panel(
                        graph_id=EFFECTS_ID,
                        title="Major Effects",
                        subtitle="Partial η² · Model, Evidence và Model × Evidence",
                        source="Certified tables: omnibus_effects / cross_dataset_effects",
                        figure=effects,
                        class_name="overview-chart--effects",
                    ),
                ],
                className="overview-primary-grid",
            ),
            html.Section(
                [
                    _chart_panel(
                        graph_id=VALIDATION_ID,
                        title="Claim Validation Composition",
                        subtitle="Tỷ trọng chuẩn hóa để trình bày; tooltip giữ exact certified claim counts",
                        source="Certified table: study_summary status counts",
                        figure=validation,
                        class_name="overview-chart--validation",
                    ),
                    _status_panel(model),
                ],
                className="overview-secondary-grid",
            ),
            _explore_deeper(),
            dmc.Drawer(
                [
                    html.Div(id=DETAIL_DRAWER_BODY_ID),
                ],
                id=DETAIL_DRAWER_ID,
                title=html.Div(id=DETAIL_DRAWER_TITLE_ID),
                position="right",
                size="md",
                padding="xl",
                opened=False,
                overlayProps={"backgroundOpacity": 0.25, "blur": 2},
            ),
        ],
        className=f"research-page overview-page overview-page--golden overview-page--{'cross' if model.scope == 'CROSS_DATASET' else 'study'}",
    )


def detail_from_click(kind: str, click_data: dict | None, scope: str):
    if not click_data or not click_data.get("points"):
        return None
    point = click_data["points"][0]

    if kind == "landscape":
        custom = list(point.get("customdata") or [])
        if scope == "CROSS_DATASET":
            if len(custom) < 4:
                return None
            dataset_scope, model_id, model_label, evidence = map(str, custom[:4])
        else:
            if len(custom) < 3:
                return None
            dataset_scope, model_id, model_label, evidence = scope, str(custom[0]), str(custom[1]), str(custom[2])
        dataset_label = "Home Credit" if dataset_scope == "HOME_CREDIT" else "Freddie Mac"
        mean_e2e = float(point.get("z"))
        query = urlencode({"dataset": dataset_scope, "model": model_id, "evidence": evidence})
        title = f"{model_label} × {evidence}"
        body = html.Div(
            [
                html.Div(dataset_label, className="overview-drawer__dataset"),
                html.Div(
                    [
                        html.Span("End-to-End Faithfulness"),
                        html.Strong(f"{mean_e2e:.2%}"),
                    ],
                    className="overview-drawer__metric",
                ),
                html.P("Cell này là certified option-level presentation value; dashboard không tính lại metric.", className="overview-drawer__note"),
                html.Div(
                    [
                        dcc.Link("Mở Effectiveness", href=f"/effectiveness?{query}", className="analysis-link-button analysis-link-button--filled"),
                        dcc.Link("Mở Case Explorer", href=f"/cases?{query}", className="analysis-link-button analysis-link-button--light"),
                    ],
                    className="overview-drawer__actions",
                ),
            ],
            className="overview-drawer",
        )
        return title, body

    if kind == "effects":
        effect = str(point.get("y", "Effect"))
        eta = float(point.get("x"))
        title = effect
        body = html.Div(
            [
                html.Div([html.Span("Partial η²"), html.Strong(f"{eta:.3f}")], className="overview-drawer__metric"),
                html.P("Effect magnitude được đọc từ certified omnibus output. Xem Effectiveness để audit F, p và contrasts chi tiết.", className="overview-drawer__note"),
                dcc.Link("Mở Effectiveness", href="/effectiveness", className="analysis-link-button analysis-link-button--filled"),
            ],
            className="overview-drawer",
        )
        return title, body

    if kind == "validation":
        statuses = ("SUPPORTED", "NOT_VERIFIABLE", "UNSUPPORTED", "CONTRADICTED", "NOT_APPLICABLE")
        curve = int(point.get("curveNumber", 0))
        status = statuses[curve] if 0 <= curve < len(statuses) else "Validation status"
        dataset = str(point.get("y", ""))
        count = int((point.get("customdata") or [0])[0])
        title = status
        body = html.Div(
            [
                html.Div(dataset, className="overview-drawer__dataset"),
                html.Div([html.Span("Atomic claims"), html.Strong(f"{count:,}")], className="overview-drawer__metric"),
                html.P("Tỷ lệ trên chart chỉ là presentation normalization; exact claim count phía trên là certified source value.", className="overview-drawer__note"),
                dcc.Link("Mở Mechanisms", href=f"/mechanisms?validation_status={status}", className="analysis-link-button analysis-link-button--filled"),
            ],
            className="overview-drawer",
        )
        return title, body
    return None


def layout(**_):
    return html.Div(id=CONTENT_ID)
