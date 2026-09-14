from __future__ import annotations

from urllib.parse import urlencode

import dash
import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from research.python.dashboard.theme import PLOTLY_CONFIG

from ..effectiveness_model import MODEL_LABELS
from ..figures import (
    robustness_contrast_stability_map,
    robustness_effect_dumbbell,
    robustness_margin_sensitivity_plot,
    robustness_rank_shift_heatmap,
)
from ..robustness_model import RobustnessModelV3


CONTENT_ID = "v3-robustness-content"
TABS_ID = "robustness-tabs"
POPULATION_PANEL_ID = "robustness-tab-population-panel"
METRIC_PANEL_ID = "robustness-tab-metric-panel"
DECISION_PANEL_ID = "robustness-tab-decision-panel"
CONTRAST_FAMILY_ID = "robustness-contrast-family"
EFFECT_DUMBBELL_ID = "robustness-effect-dumbbell"
CONTRAST_MAP_ID = "robustness-contrast-stability-map"
METRIC_MODEL_FILTER_ID = "robustness-metric-model-filter"
METRIC_EVIDENCE_FILTER_ID = "robustness-metric-evidence-filter"
METRIC_SELECT_ID = "robustness-metric-select"
RANK_SHIFT_ID = "robustness-rank-shift-heatmap"
MARGIN_SELECT_ID = "robustness-margin-select"
MARGIN_PLOT_ID = "robustness-margin-sensitivity"
MARGIN_DETAIL_ID = "robustness-margin-detail"
DETAIL_DRAWER_ID = "robustness-detail-drawer"
DETAIL_DRAWER_TITLE_ID = "robustness-detail-drawer-title-content"
DETAIL_DRAWER_BODY_ID = "robustness-detail-drawer-body-content"

METRIC_LABELS = {
    "ALL": "All secondary metrics",
    "resolved_faithfulness": "Resolved Faithfulness",
    "verifiability": "Verifiability",
    "conservative_faithfulness": "Conservative Faithfulness",
}


def register_page() -> None:
    dash.register_page(
        "llm_xai_dashboard_v3.robustness",
        path="/robustness",
        name="Robustness",
        title="Robustness · LLM–XAI Research Dashboard",
        order=4,
        layout=layout,
    )


def tab_panel_style(active_tab: str | None, panel: str) -> dict[str, str]:
    active = active_tab if active_tab in {"population", "metric", "decision"} else "population"
    return {"display": "block" if active == panel else "none", "width": "100%"}


def _scope_label(scope: str) -> str:
    return {"HOME_CREDIT": "Home Credit", "FREDDIE": "Freddie Mac", "CROSS_DATASET": "Cross-dataset"}.get(scope, scope)


def _chart_panel(*, graph_id: str, title: str, subtitle: str, source: str, figure, class_name: str = ""):
    height = int(figure.layout.height or 380)
    classes = "robustness-chart"
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


def _page_header(model: RobustnessModelV3):
    return html.Header(
        [
            html.Div(
                [
                    html.Div([html.Span("ROBUSTNESS", className="analysis-eyebrow"), html.Span("PRIMARY ≠ SENSITIVITY", className="analysis-lane-badge")], className="analysis-page-header__eyebrow"),
                    html.H1("Robustness", className="analysis-page-header__title"),
                    html.P("Kết luận nào giữ ổn định khi thay population, metric hoặc NI margin; kết luận nào phụ thuộc vào analytical choice đã freeze?", className="analysis-page-header__subtitle"),
                ]
            ),
            html.Div(
                [
                    html.Div([html.Span("Phạm vi"), html.Strong(_scope_label(model.scope))], className="analysis-context-pill"),
                    html.Div([html.Span("Primary lane"), html.Strong("PRIMARY_CERTIFIED")], className="analysis-context-pill"),
                    html.Div([html.Span("Sensitivity lanes"), html.Strong("Population · Metric · Margin")], className="analysis-context-pill"),
                ],
                className="analysis-page-header__context",
            ),
        ],
        className="analysis-page-header",
    )


def _status_strip(model: RobustnessModelV3):
    labels = {
        "population": "Population",
        "metric": "Metric",
        "margin": "Margin",
        "bootstrap": "Bootstrap",
        "claim_type": "Claim type",
        "decision": "Decision",
    }
    return html.Div(
        [
            html.Div(
                [
                    html.Span(labels.get(str(row["dimension"]), str(row["dimension"])), className="robustness-status-card__label"),
                    html.Strong(str(row["status"]), className="robustness-status-card__status"),
                    dmc.Tooltip(DashIconify(icon="solar:info-circle-linear", width=15), label=str(row["note"]), multiline=True, w=360, withArrow=True),
                ],
                className=f"robustness-status-card robustness-status-card--{'stable' if 'STABLE' in str(row['status']) else 'sensitive'}",
            )
            for row in model.summary
        ],
        className="robustness-status-strip",
    )


def filter_population_contrasts(rows, family: str = "evidence_vs_s0") -> list[dict]:
    selected = [dict(row) for row in rows]
    if family and family != "all":
        selected = [row for row in selected if str(row.get("contrast_family")) == str(family)]
    return selected


def filter_metric_rows(rows, model_id: str | None = None, evidence: str | None = None, metric: str | None = None) -> list[dict]:
    selected = [dict(row) for row in rows]
    if model_id and model_id != "ALL":
        selected = [row for row in selected if str(row.get("model_id")) == str(model_id)]
    if evidence and evidence != "ALL":
        selected = [row for row in selected if str(row.get("evidence_level")) == str(evidence)]
    if metric and metric != "ALL":
        selected = [row for row in selected if str(row.get("metric_id")) == str(metric)]
    return selected


def _population_controls(model: RobustnessModelV3):
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Contrast family", className="analysis-filter-bar__label"),
                    dmc.SegmentedControl(
                        id=CONTRAST_FAMILY_ID,
                        value=model.focus_family,
                        data=[
                            {"value": "evidence_vs_s0", "label": "Evidence vs S0"},
                            {"value": "model_within_evidence", "label": "Model within Evidence"},
                            {"value": "all", "label": "All"},
                        ],
                        radius="xl",
                        size="xs",
                    ),
                ],
                className="analysis-filter-bar__controls",
            ),
            html.Div([DashIconify(icon="solar:info-circle-linear", width=15), html.Span("Primary and complete-case statistics are read from certified sensitivity rows; no tests are rerun.")], className="analysis-filter-bar__note"),
        ],
        className="analysis-filter-bar",
    )


def _metric_controls(model: RobustnessModelV3):
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Certified rank focus", className="analysis-filter-bar__label"),
                    dmc.Select(id=METRIC_MODEL_FILTER_ID, data=[{"value": "ALL", "label": "Tất cả model"}] + [{"value": m, "label": label} for m, label in MODEL_LABELS.items()], value=model.focus_model or "ALL", allowDeselect=False, w=200, size="sm"),
                    dmc.Select(id=METRIC_EVIDENCE_FILTER_ID, data=[{"value": "ALL", "label": "Tất cả Evidence"}] + [{"value": f"S{i}", "label": f"S{i}"} for i in range(6)], value=model.focus_evidence or "ALL", allowDeselect=False, w=175, size="sm"),
                    dmc.Select(id=METRIC_SELECT_ID, data=[{"value": key, "label": label} for key, label in METRIC_LABELS.items()], value=model.focus_metric, allowDeselect=False, w=220, size="sm"),
                ],
                className="analysis-filter-bar__controls",
            ),
            html.Div([DashIconify(icon="solar:shield-check-linear", width=15), html.Span("Ranks remain the certified 18-option ranks even after visual filtering; dashboard never reranks the filtered subset.")], className="analysis-filter-bar__note"),
        ],
        className="analysis-filter-bar",
    )


def _margin_controls(model: RobustnessModelV3):
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Certified margin lane", className="analysis-filter-bar__label"),
                    dmc.SegmentedControl(id=MARGIN_SELECT_ID, value=f"{model.focus_margin:.2f}", data=[{"value": "0.02", "label": "δ 0.02"}, {"value": "0.03", "label": "δ 0.03 · PRIMARY"}, {"value": "0.05", "label": "δ 0.05"}], radius="xl", size="sm"),
                ],
                className="analysis-filter-bar__controls",
            ),
            html.Div([DashIconify(icon="solar:lock-keyhole-minimalistic-linear", width=15), html.Span("Only the three frozen lanes can be selected. δ=0.03 remains PRIMARY_CERTIFIED and is never replaced by sensitivity-only lanes.")], className="analysis-filter-bar__note"),
        ],
        className="analysis-filter-bar",
    )


def _population_summary(model: RobustnessModelV3):
    effects = list(model.population_effects)
    contrasts = list(model.population_contrasts)
    sig_effect_stable = sum(bool(r["significance_conclusion_stable"]) for r in effects)
    direction_stable = sum(bool(r["direction_stable"]) for r in contrasts)
    sig_stable = sum(bool(r["significance_conclusion_stable"]) for r in contrasts)
    return html.Div(
        [
            html.Div([html.Strong(f"{sig_effect_stable}/{len(effects)}"), html.Span("Omnibus significance stable")], className="robustness-kpi"),
            html.Div([html.Strong(f"{direction_stable}/{len(contrasts)}"), html.Span("Contrast direction stable")], className="robustness-kpi"),
            html.Div([html.Strong(f"{sig_stable}/{len(contrasts)}"), html.Span("Contrast significance stable")], className="robustness-kpi"),
        ],
        className="robustness-kpi-row",
    )


def margin_detail(row: dict | None):
    if not row:
        return html.Div("Margin lane unavailable", className="analysis-side-panel__text")
    ids = row.get("robust_eligible_option_ids")
    eligible = "—" if ids is None or str(ids) == "nan" else str(ids).replace("|", " · ")
    is_primary = str(row.get("analysis_status")) == "PRIMARY_CERTIFIED"
    return html.Div(
        [
            html.Span("Selected margin lane", className="analysis-eyebrow"),
            html.H3(f"δ={float(row['margin']):.2f}", className="analysis-side-panel__title"),
            html.Div("Primary policy" if is_primary else "Sensitivity-only", className="analysis-side-panel__dataset"),
            html.Div(
                [
                    html.Div([html.Span("Analysis role"), html.Strong(str(row["analysis_status"]))], className="analysis-side-panel__metric"),
                    html.Div([html.Span("Robust primary candidates"), html.Strong(str(int(row["robust_primary_candidate_count"])))], className="analysis-side-panel__metric"),
                    html.Div([html.Span("Active pool"), html.Strong(str(row["active_pool_mode"]))], className="analysis-side-panel__metric"),
                    html.Div([html.Span("Eligible IDs"), html.Strong(eligible)], className="analysis-side-panel__metric"),
                ],
                className="analysis-side-panel__metrics",
            ),
            html.P("Sensitivity-only candidate emergence does not replace the certified δ=0.03 decision.", className="analysis-side-panel__text"),
            dcc.Link("Mở Decision Studio", href="/decision?tab=certified", className="analysis-link-button analysis-link-button--filled"),
        ],
        className="analysis-side-panel__body",
        **{"data-testid": "robustness-margin-detail"},
    )


def contrast_from_click(click_data: dict | None) -> dict | None:
    if not click_data or not click_data.get("points"):
        return None
    custom = list(click_data["points"][0].get("customdata") or [])
    if len(custom) < 9:
        return None
    return {
        "dataset_scope": str(custom[0]),
        "contrast_id": str(custom[1]),
        "contrast_family": str(custom[2]),
        "primary_p": float(custom[3]),
        "complete_p": float(custom[4]),
        "direction_stable": bool(custom[5]),
        "significance_stable": bool(custom[6]),
        "significant_primary": bool(custom[7]),
        "significant_complete": bool(custom[8]),
        "primary_delta": float(click_data["points"][0].get("x", 0)),
        "complete_delta": float(click_data["points"][0].get("y", 0)),
    }


def metric_from_click(click_data: dict | None) -> dict | None:
    if not click_data or not click_data.get("points"):
        return None
    custom = list(click_data["points"][0].get("customdata") or [])
    if len(custom) < 9:
        return None
    return {
        "dataset_scope": str(custom[0]),
        "option_id": str(custom[1]),
        "model_id": str(custom[2]),
        "evidence_level": str(custom[3]),
        "metric_id": str(custom[4]),
        "primary_rank": int(custom[5]),
        "quality_rank": int(custom[6]),
        "rank_shift": int(custom[7]),
        "metric_mean": float(custom[8]),
    }


def margin_from_click(click_data: dict | None) -> float | None:
    if not click_data or not click_data.get("points"):
        return None
    try:
        value = float(click_data["points"][0].get("x"))
    except (TypeError, ValueError):
        return None
    return value if value in {0.02, 0.03, 0.05} else None


def contrast_drawer(detail: dict):
    title = f"Contrast sensitivity · {detail['contrast_id']}"
    body = html.Div(
        [
            html.Div(_scope_label(detail["dataset_scope"]), className="overview-drawer__dataset"),
            html.Div([html.Span("Primary mean Δ"), html.Strong(f"{detail['primary_delta']:+.4f}")], className="overview-drawer__metric"),
            html.Div([html.Span("Complete-case mean Δ"), html.Strong(f"{detail['complete_delta']:+.4f}")], className="overview-drawer__metric"),
            html.Div([html.Span("Primary Holm p"), html.Strong(f"{detail['primary_p']:.4g}")], className="overview-drawer__metric"),
            html.Div([html.Span("Complete-case Holm p"), html.Strong(f"{detail['complete_p']:.4g}")], className="overview-drawer__metric"),
            html.Div([html.Span("Direction stable"), html.Strong("YES" if detail["direction_stable"] else "NO")], className="overview-drawer__metric"),
            html.Div([html.Span("Significance stable"), html.Strong("YES" if detail["significance_stable"] else "NO")], className="overview-drawer__metric"),
            html.P("Both primary and complete-case values are certified population sensitivity outputs; the dashboard runs no statistical test.", className="overview-drawer__note"),
        ],
        className="overview-drawer",
        **{"data-testid": "robustness-drawer-content"},
    )
    return title, body


def metric_drawer(detail: dict):
    query = urlencode({"dataset": detail["dataset_scope"], "model": detail["model_id"], "evidence": detail["evidence_level"]})
    title = f"Rank sensitivity · {MODEL_LABELS.get(detail['model_id'], detail['model_id'])} × {detail['evidence_level']}"
    body = html.Div(
        [
            html.Div(_scope_label(detail["dataset_scope"]), className="overview-drawer__dataset"),
            html.Div([html.Span("Metric"), html.Strong(METRIC_LABELS.get(detail["metric_id"], detail["metric_id"]))], className="overview-drawer__metric"),
            html.Div([html.Span("Primary rank"), html.Strong(f"#{detail['primary_rank']}")], className="overview-drawer__metric"),
            html.Div([html.Span("Sensitivity rank"), html.Strong(f"#{detail['quality_rank']}")], className="overview-drawer__metric"),
            html.Div([html.Span("Rank shift"), html.Strong(f"{detail['rank_shift']:+d}")], className="overview-drawer__metric"),
            html.Div([html.Span("Metric mean"), html.Strong(f"{detail['metric_mean']:.2%}")], className="overview-drawer__metric"),
            html.P("Ranks are the certified 18-option ranks. Visual filtering never reranks the subset.", className="overview-drawer__note"),
            html.Div([dcc.Link("Effectiveness", href=f"/effectiveness?tab=secondary&{query}", className="analysis-link-button analysis-link-button--filled"), dcc.Link("Case Explorer", href=f"/cases?{query}", className="analysis-link-button analysis-link-button--light")], className="overview-drawer__actions"),
        ],
        className="overview-drawer",
        **{"data-testid": "robustness-drawer-content"},
    )
    return title, body


def margin_drawer(row: dict):
    title = f"NI margin sensitivity · δ={float(row['margin']):.2f}"
    body = html.Div(
        [
            html.Div(str(row["analysis_status"]), className="overview-drawer__dataset"),
            html.Div([html.Span("Primary candidates"), html.Strong(str(int(row["robust_primary_candidate_count"])))], className="overview-drawer__metric"),
            html.Div([html.Span("Fallback candidates"), html.Strong(str(int(row["robust_fallback_candidate_count"])))], className="overview-drawer__metric"),
            html.Div([html.Span("Active pool"), html.Strong(str(row["active_pool_mode"]))], className="overview-drawer__metric"),
            html.P("Only the three pre-certified margin lanes are displayed. PRIMARY_CERTIFIED δ=0.03 remains the decision policy.", className="overview-drawer__note"),
        ],
        className="overview-drawer",
        **{"data-testid": "robustness-drawer-content"},
    )
    return title, body


def _capability_state(model: RobustnessModelV3):
    return html.Section(
        [
            html.Div([html.Span("CERTIFIED CAPABILITY STATE", className="analysis-eyebrow"), html.H2("Measurement extensions not materialized in M29", className="decision-section-title"), html.P("Không lấy dữ liệu legacy hoặc tái dựng validator/template analysis trong presentation layer.", className="analysis-chart__subtitle")], className="decision-section-heading"),
            html.Div(
                [
                    html.Div([html.Strong("Alternative validator sensitivity"), html.Code(model.validator_status), html.P("Không có validator sensitivity tables trong visualization_data_v3 hiện tại.")], className="robustness-capability-card"),
                    html.Div([html.Strong("Deterministic Template baseline"), html.Code(model.template_status), html.P("Không có template baseline tables trong visualization_data_v3 hiện tại.")], className="robustness-capability-card"),
                ],
                className="robustness-capability-grid",
            ),
        ],
        className="robustness-capability-state",
    )


def render(model: RobustnessModelV3):
    cross = model.scope == "CROSS_DATASET"
    population_contrasts = filter_population_contrasts(model.population_contrasts, model.focus_family)
    metric_rows = filter_metric_rows(model.metric_rows, model.focus_model, model.focus_evidence, model.focus_metric)
    effects = robustness_effect_dumbbell(model.population_effects, cross_dataset=cross)
    contrast_map = robustness_contrast_stability_map(population_contrasts, cross_dataset=cross)
    rank_heatmap = robustness_rank_shift_heatmap(metric_rows, cross_dataset=cross)
    margin_plot = robustness_margin_sensitivity_plot(model.margin_rows, selected_margin=model.focus_margin)
    selected_margin = next((dict(r) for r in model.margin_rows if abs(float(r["margin"]) - model.focus_margin) < 1e-9), dict(model.margin_rows[1]))

    return html.Main(
        [
            _page_header(model),
            _status_strip(model),
            html.Div([DashIconify(icon="solar:info-circle-linear", width=16), html.Span("δ=0.03 / PRIMARY_CERTIFIED remains the primary policy. δ=0.02 and δ=0.05 are SENSITIVITY_ONLY lanes; they describe dependence on analytical choices and never overwrite the primary conclusion.")], className="robustness-primary-warning"),
            html.Div(
                [
                    dmc.SegmentedControl(
                        id=TABS_ID,
                        value=model.initial_tab,
                        data=[
                            {"value": "population", "label": "Population sensitivity"},
                            {"value": "metric", "label": "Metric sensitivity"},
                            {"value": "decision", "label": "Decision sensitivity"},
                        ],
                        radius="xl",
                        size="sm",
                        className="analysis-tab-switcher__control",
                        **{"aria-label": "Robustness analytical section"},
                    )
                ],
                className="analysis-tab-switcher",
            ),
            html.Div(
                [
                    _population_summary(model),
                    _population_controls(model),
                    _chart_panel(graph_id=EFFECT_DUMBBELL_ID, title="Effect-size stability", subtitle="Primary vs complete-case Partial η². Statistical significance can remain stable while estimated magnitude shifts.", source="Certified table: population_effect_sensitivity", figure=effects, class_name="robustness-chart--effects"),
                    _chart_panel(graph_id=CONTRAST_MAP_ID, title="Contrast Stability Map", subtitle="Primary mean Δ vs complete-case mean Δ. The dashed diagonal represents exact numerical agreement; marker shape distinguishes certified conclusion changes.", source="Certified table: population_contrast_sensitivity", figure=contrast_map, class_name="robustness-chart--contrasts"),
                ],
                id=POPULATION_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "population"),
            ),
            html.Div(
                [
                    _metric_controls(model),
                    _chart_panel(graph_id=RANK_SHIFT_ID, title="Certified Rank Shift Heatmap", subtitle="Cell = sensitivity rank − primary rank. Negative values moved upward; positive values moved downward. Ranks remain the frozen 18-option ranks.", source="Certified table: metric_sensitivity", figure=rank_heatmap, class_name="robustness-chart--rank"),
                    html.Div([DashIconify(icon="solar:shield-check-linear", width=16), html.Span("End-to-End Faithfulness itself is the primary lane and therefore has rank shift 0; the heatmap intentionally focuses on the three frozen secondary metrics.")], className="robustness-metric-note"),
                ],
                id=METRIC_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "metric"),
            ),
            html.Div(
                [
                    _margin_controls(model),
                    html.Div(
                        [
                            _chart_panel(graph_id=MARGIN_PLOT_ID, title="NI Margin Sensitivity", subtitle="Candidate-pool availability across the three frozen margins. δ=0.05 creates candidates only in a SENSITIVITY_ONLY lane.", source="Certified tables: margin_sensitivity_summary + recommendation_sensitivity", figure=margin_plot, class_name="robustness-chart--margin"),
                            html.Aside(margin_detail(selected_margin), id=MARGIN_DETAIL_ID, className="analysis-side-panel"),
                        ],
                        className="robustness-margin-grid",
                    ),
                    html.Section([html.H2("Certified decision implication", className="decision-section-title"), html.P("At δ=0.02 and δ=0.03 the robust pool remains empty. At δ=0.05 two robust primary candidates emerge (Qwen3 8B × S1 and Qwen3 8B × S4), but this sensitivity result does not replace the certified primary recommendation state.", className="analysis-chart__subtitle"), html.Code("MARGIN_SENSITIVE · PRIMARY remains NO_ROBUST_RECOMMENDATION", className="robustness-decision-code")], className="robustness-decision-note"),
                ],
                id=DECISION_PANEL_ID,
                className="analysis-tab-panel",
                style=tab_panel_style(model.initial_tab, "decision"),
            ),
            _capability_state(model),
            html.Div([DashIconify(icon="solar:shield-check-linear", width=16), html.Span("Certified sensitivity presentation · No statistical rerun, reranking or NI recomputation in UI")], className="analysis-certified-footer"),
            dmc.Drawer(html.Div(id=DETAIL_DRAWER_BODY_ID), id=DETAIL_DRAWER_ID, title=html.Div(id=DETAIL_DRAWER_TITLE_ID), opened=False, position="right", size="md", padding="xl", overlayProps={"backgroundOpacity": 0.25, "blur": 2}),
        ],
        className=f"research-page analysis-page robustness-page--golden analysis-page--{'cross' if cross else 'study'}",
    )


def layout(**_):
    return html.Div(id=CONTENT_ID)
