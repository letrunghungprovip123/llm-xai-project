"""Page 3 — localized Evidence, Mechanisms & Diagnostics for RQ3."""

from __future__ import annotations

import dash
from dash import dcc, html
import pandas as pd

from ..components.chart_card import chart_card
from ..components.data_grid import data_grid
from ..components.mechanisms import (
    claim_mechanism_findings,
    design_interpretation_panel,
    evidence_condition_blueprint,
    humanize_code,
    lexical_signal_disclosure,
    pipeline_failure_summary,
    utilization_interpretation_panel,
)
from ..components.page_header import page_header
from ..data.repository import DashboardRepository, get_dashboard_repository
from ..figures.mechanisms import (
    FIG_MECHANISMS_CLAIM_DIFFICULTY,
    FIG_MECHANISMS_CLAIM_STATUS,
    FIG_MECHANISMS_COVERAGE_DIVERSITY,
    FIG_MECHANISMS_EVIDENCE_COMPOSITION,
    FIG_MECHANISMS_FAILURE_MATRIX,
    FIG_MECHANISMS_NARRATIVE_STRUCTURE,
    FIG_MECHANISMS_PIPELINE_COMPLETION,
    FIG_MECHANISMS_POLICY_COMPLIANCE,
    FIG_MECHANISMS_UTILIZATION_MATRIX,
    FIG_MECHANISMS_UTILIZATION_PROFILE,
    FIG_MECHANISMS_UTILIZATION_QUALITY,
    build_claim_difficulty_matrix,
    build_claim_status_small_multiples,
    build_coverage_diversity_scatter,
    build_evidence_composition_chart,
    build_failure_matrix,
    build_narrative_structure_chart,
    build_pipeline_completion_chart,
    build_policy_compliance_chart,
    build_utilization_matrix,
    build_utilization_quality_scatter,
    build_utilization_stage_profile,
)
from ..i18n import (
    DEFAULT_LOCALE,
    evidence_label,
    failure_type_label,
    localize_plotly_figure,
    normalize_locale,
    reason_code_label,
    t,
    utilization_metric_label,
)
from ..ids import (
    MECHANISMS_CLAIM_DIFFICULTY_ID,
    MECHANISMS_CLAIM_MEASURE_ID,
    MECHANISMS_CLAIM_STATUS_ID,
    MECHANISMS_CONTENT_ID,
    MECHANISMS_COVERAGE_DIVERSITY_ID,
    MECHANISMS_DOWNLOAD_ID,
    MECHANISMS_EVIDENCE_COMPOSITION_ID,
    MECHANISMS_EVIDENCE_GRID_ID,
    MECHANISMS_EXPORT_ID,
    MECHANISMS_FAILURE_GRID_ID,
    MECHANISMS_FAILURE_MATRIX_ID,
    MECHANISMS_FOCUS_STORE_ID,
    MECHANISMS_NARRATIVE_STRUCTURE_ID,
    MECHANISMS_PAGE_ID,
    MECHANISMS_PIPELINE_COMPLETION_ID,
    MECHANISMS_POLICY_COMPLIANCE_ID,
    MECHANISMS_REASON_GRID_ID,
    MECHANISMS_TABS_ID,
    MECHANISMS_UI_STATE_ID,
    MECHANISMS_UTILIZATION_GRID_ID,
    MECHANISMS_UTILIZATION_MATRIX_ID,
    MECHANISMS_UTILIZATION_METRIC_ID,
    MECHANISMS_UTILIZATION_PANEL_ID,
    MECHANISMS_UTILIZATION_PROFILE_ID,
    MECHANISMS_UTILIZATION_SCATTER_ID,
)
from ..settings import DEFAULT_UTILIZATION_METRIC, VISUALIZATION_RELEASE_ID


PAGE_MODULE = "llm_xai_dashboard.mechanisms"
_VALID_TABS = frozenset({"design", "utilization", "claims", "pipeline"})
_VALID_UTILIZATION_METRICS = frozenset(
    {"feature_use", "concept_use", "supported_claim_yield"}
)
_VALID_CLAIM_MEASURES = frozenset({"rate", "count"})
_FIGURE_PREFIXES = (
    "mechanisms.figure.",
    "domain.claim_type.",
    "domain.pipeline_stage.",
    "domain.claim_status.",
)


def register_page() -> None:
    if PAGE_MODULE not in dash.page_registry:
        dash.register_page(
            PAGE_MODULE,
            path="/mechanisms",
            name="Mechanisms",
            title="Evidence, Mechanisms & Diagnostics · LLM-XAI",
            description=(
                "Evidence design, utilization, claim mechanisms and pipeline failures."
            ),
            order=2,
            layout=layout,
        )


def normalize_mechanisms_state(value: object | None) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    tab = str(raw.get("tab", "design"))
    metric = str(raw.get("utilization_metric", DEFAULT_UTILIZATION_METRIC))
    measure = str(raw.get("claim_measure", "rate"))
    return {
        "tab": tab if tab in _VALID_TABS else "design",
        "utilization_metric": (
            metric if metric in _VALID_UTILIZATION_METRICS else DEFAULT_UTILIZATION_METRIC
        ),
        "claim_measure": measure if measure in _VALID_CLAIM_MEASURES else "rate",
    }


def _number_formatter(locale: object, digits: int = 1) -> dict[str, str]:
    tag = "vi-VN" if normalize_locale(locale) == "vi" else "en-US"
    return {
        "function": (
            "params.value == null ? '' : "
            f"new Intl.NumberFormat('{tag}',"
            f"{{minimumFractionDigits:{digits},maximumFractionDigits:{digits}}})"
            ".format(Number(params.value))"
        )
    }


def _percent_formatter(locale: object, digits: int = 1) -> dict[str, str]:
    tag = "vi-VN" if normalize_locale(locale) == "vi" else "en-US"
    return {
        "function": (
            "params.value == null ? '' : "
            f"new Intl.NumberFormat('{tag}',"
            "{style:'percent',minimumFractionDigits:"
            f"{digits},maximumFractionDigits:{digits}}})"
            ".format(Number(params.value))"
        )
    }


def _localized_evidence_frame(frame: pd.DataFrame, locale: object) -> pd.DataFrame:
    result = frame.copy(deep=True)
    result["evidence_display"] = result["evidence_level"].map(
        lambda value: evidence_label(locale, value)
    )
    if "evidence_label" in result:
        result["evidence_label"] = result["evidence_level"].map(
            lambda value: evidence_label(locale, value)
        )
    return result


def localized_utilization_rows(frame: pd.DataFrame, locale: object) -> pd.DataFrame:
    return _localized_evidence_frame(frame, normalize_locale(locale))


def _evidence_grid(frame: pd.DataFrame, locale: object):
    resolved = normalize_locale(locale)
    display = _localized_evidence_frame(frame, resolved)
    yes = t(resolved, "mechanisms.grid.yes")
    no = t(resolved, "mechanisms.grid.no")
    display["semantic_display"] = display["has_semantic_guidance"].map(
        lambda value: yes if bool(value) else no
    )
    display["skeleton_display"] = display["has_structural_skeleton"].map(
        lambda value: yes if bool(value) else no
    )
    columns = [
        {"field": "case_id", "headerName": t(resolved, "mechanisms.grid.case")},
        {"field": "evidence_display", "headerName": t(resolved, "mechanisms.grid.evidence"), "minWidth": 180},
        {"field": "evidence_item_count", "headerName": t(resolved, "mechanisms.grid.items")},
        {"field": "feature_item_count", "headerName": t(resolved, "mechanisms.grid.features")},
        {"field": "concept_item_count", "headerName": t(resolved, "mechanisms.grid.concepts")},
        {"field": "coverage", "headerName": t(resolved, "mechanisms.grid.coverage"), "valueFormatter": _percent_formatter(resolved)},
        {"field": "normalized_entropy", "headerName": t(resolved, "mechanisms.grid.diversity"), "valueFormatter": _number_formatter(resolved, 3)},
        {"field": "semantic_display", "headerName": t(resolved, "mechanisms.grid.semantic_guidance")},
        {"field": "skeleton_display", "headerName": t(resolved, "mechanisms.grid.skeleton")},
    ]
    return data_grid(
        grid_id=MECHANISMS_EVIDENCE_GRID_ID,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=410,
        page_size=12,
        class_name="mechanisms-data-grid",
        locale=resolved,
    )


def _utilization_grid(frame: pd.DataFrame, locale: object):
    resolved = normalize_locale(locale)
    display = localized_utilization_rows(frame, resolved)
    columns = [
        {"field": "generator_label", "headerName": t(resolved, "mechanisms.grid.model"), "minWidth": 155},
        {"field": "evidence_display", "headerName": t(resolved, "mechanisms.grid.evidence"), "minWidth": 180},
        {"field": "case_id", "headerName": t(resolved, "mechanisms.grid.case")},
        {"field": "selected_evidence_count", "headerName": t(resolved, "mechanisms.grid.selected")},
        {"field": "selected_feature_mention_rate", "headerName": t(resolved, "mechanisms.grid.feature_use"), "valueFormatter": _percent_formatter(resolved)},
        {"field": "concept_mention_rate", "headerName": t(resolved, "mechanisms.grid.concept_use"), "valueFormatter": _percent_formatter(resolved)},
        {"field": "supported_count", "headerName": t(resolved, "mechanisms.grid.supported")},
        {"field": "claim_count", "headerName": t(resolved, "mechanisms.grid.claims")},
        {"field": "end_to_end_faithfulness_yield", "headerName": t(resolved, "mechanisms.grid.e2e"), "valueFormatter": _percent_formatter(resolved)},
    ]
    return data_grid(
        grid_id=MECHANISMS_UTILIZATION_GRID_ID,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=420,
        page_size=12,
        class_name="mechanisms-data-grid",
        locale=resolved,
    )


def localized_reason_frame(frame: pd.DataFrame, locale: object) -> pd.DataFrame:
    resolved = normalize_locale(locale)
    grouped = (
        frame.groupby(
            [
                "generator_label",
                "evidence_level",
                "dominant_primary_reason_code",
                "dominant_error_reason_code",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="generation_count")
    )
    grouped["evidence_display"] = grouped["evidence_level"].map(
        lambda value: evidence_label(resolved, value)
    )
    grouped["primary_reason"] = grouped["dominant_primary_reason_code"].map(
        lambda value: humanize_code(value, resolved, namespace="reason_code")
    )
    grouped["error_reason"] = grouped["dominant_error_reason_code"].map(
        lambda value: humanize_code(value, resolved, namespace="reason_code")
    )
    return grouped


def _reason_grid(frame: pd.DataFrame, locale: object):
    resolved = normalize_locale(locale)
    grouped = localized_reason_frame(frame, resolved)
    columns = [
        {"field": "generator_label", "headerName": t(resolved, "mechanisms.grid.model"), "minWidth": 155},
        {"field": "evidence_display", "headerName": t(resolved, "mechanisms.grid.evidence"), "minWidth": 180},
        {"field": "primary_reason", "headerName": t(resolved, "mechanisms.grid.dominant_reason"), "minWidth": 220},
        {"field": "error_reason", "headerName": t(resolved, "mechanisms.grid.error_reason"), "minWidth": 220},
        {"field": "generation_count", "headerName": t(resolved, "mechanisms.grid.runs")},
    ]
    return data_grid(
        grid_id=MECHANISMS_REASON_GRID_ID,
        frame=grouped[[item["field"] for item in columns]],
        column_defs=columns,
        height=400,
        page_size=12,
        class_name="mechanisms-data-grid",
        locale=resolved,
    )


def localized_failure_frame(frame: pd.DataFrame, locale: object) -> pd.DataFrame:
    resolved = normalize_locale(locale)
    display = frame.copy(deep=True)
    display["evidence_display"] = display["evidence_level"].map(
        lambda value: evidence_label(resolved, value)
    )
    display["failure_type"] = display["failure_category_label"].map(
        lambda value: failure_type_label(resolved, value)
    )
    display["truncated_display"] = display["truncated_response"].map(
        lambda value: t(
            resolved,
            "mechanisms.grid.yes" if bool(value) else "mechanisms.grid.no",
        )
    )
    display["latency_seconds"] = display["latency_ms"] / 1000
    return display


def _failure_grid(frame: pd.DataFrame, locale: object):
    resolved = normalize_locale(locale)
    display = localized_failure_frame(frame, resolved)
    columns = [
        {"field": "case_id", "headerName": t(resolved, "mechanisms.grid.case")},
        {"field": "model_label", "headerName": t(resolved, "mechanisms.grid.model"), "minWidth": 155},
        {"field": "evidence_display", "headerName": t(resolved, "mechanisms.grid.evidence"), "minWidth": 180},
        {"field": "failure_type", "headerName": t(resolved, "mechanisms.grid.failure_type"), "minWidth": 180},
        {"field": "truncated_display", "headerName": t(resolved, "mechanisms.grid.truncated")},
        {"field": "latency_seconds", "headerName": t(resolved, "mechanisms.grid.latency"), "valueFormatter": _number_formatter(resolved, 2)},
        {"field": "total_token_count", "headerName": t(resolved, "mechanisms.grid.tokens")},
    ]
    return data_grid(
        grid_id=MECHANISMS_FAILURE_GRID_ID,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=360,
        page_size=10,
        class_name="mechanisms-data-grid",
        locale=resolved,
    )


def _default_focus(repository: DashboardRepository, metric_id: str) -> tuple[str, str]:
    summary = repository.utilization_option_summary(metric_id).dropna(
        subset=["mean_value"]
    )
    row = summary.sort_values(
        ["mean_value", "generator_order", "evidence_order"],
        ascending=[False, True, True],
    ).iloc[0]
    return str(row["generator_id"]), str(row["evidence_level"])


def normalize_mechanisms_focus(
    repository: DashboardRepository,
    metric_id: str,
    value: object | None,
) -> dict[str, str]:
    summary = repository.utilization_option_summary(metric_id)
    raw = value if isinstance(value, dict) else {}
    model = raw.get("model_id")
    evidence = raw.get("evidence_level")
    valid = (
        (summary["generator_id"] == model)
        & (summary["evidence_level"] == evidence)
    ).any()
    if not valid:
        model, evidence = _default_focus(repository, metric_id)
    return {"model_id": str(model), "evidence_level": str(evidence)}


def _figure(figure, locale: object):
    return localize_plotly_figure(
        figure,
        locale,
        prefixes=_FIGURE_PREFIXES,
    )


def _evidence_design_tab(data, locale: object):
    resolved = normalize_locale(locale)
    evidence_design = _localized_evidence_frame(data.evidence_design, resolved)
    composition = _figure(build_evidence_composition_chart(evidence_design), resolved)
    coverage = _figure(build_coverage_diversity_scatter(evidence_design), resolved)
    return html.Div(
        [
            html.Section(
                [
                    html.H2(t(resolved, "mechanisms.design.construction_title"), className="effectiveness-section__title"),
                    html.P(t(resolved, "mechanisms.design.construction_subtitle"), className="effectiveness-section__subtitle"),
                    evidence_condition_blueprint(data.evidence_profiles, locale=resolved),
                ],
                className="tab-content",
            ),
            html.Section(
                [
                    chart_card(
                        graph_id=MECHANISMS_EVIDENCE_COMPOSITION_ID,
                        title=t(resolved, "mechanisms.design.composition_title"),
                        subtitle=t(resolved, "mechanisms.design.composition_subtitle"),
                        figure=composition,
                        figure_id=FIG_MECHANISMS_EVIDENCE_COMPOSITION,
                        source=t(resolved, "mechanisms.design.composition_source"),
                        metric=t(resolved, "mechanisms.design.composition_metric"),
                        denominator=t(resolved, "mechanisms.design.composition_denominator"),
                        release=VISUALIZATION_RELEASE_ID,
                        locale=resolved,
                    ),
                    design_interpretation_panel(data.evidence_profiles, locale=resolved),
                ],
                className="mechanisms-hero-grid",
            ),
            chart_card(
                graph_id=MECHANISMS_COVERAGE_DIVERSITY_ID,
                title=t(resolved, "mechanisms.design.coverage_title"),
                subtitle=t(resolved, "mechanisms.design.coverage_subtitle"),
                figure=coverage,
                figure_id=FIG_MECHANISMS_COVERAGE_DIVERSITY,
                source=t(resolved, "mechanisms.design.coverage_source"),
                metric=t(resolved, "mechanisms.design.coverage_metric"),
                denominator=t(resolved, "mechanisms.design.coverage_denominator"),
                release=VISUALIZATION_RELEASE_ID,
                locale=resolved,
            ),
            html.Details(
                [
                    html.Summary(t(resolved, "mechanisms.design.view_cases")),
                    html.Div(_evidence_grid(evidence_design, resolved), className="mechanisms-details__body"),
                ],
                className="mechanisms-details",
            ),
        ],
        className="mechanisms-tab-content",
    )


def _utilization_tab(
    repository: DashboardRepository,
    data,
    selected_metric: str,
    focus: dict[str, str],
    locale: object,
):
    resolved = normalize_locale(locale)
    label = utilization_metric_label(resolved, selected_metric)
    summary = repository.utilization_option_summary(selected_metric).copy()
    summary["evidence_label"] = summary["evidence_level"].map(
        lambda value: evidence_label(resolved, value)
    )
    focus = normalize_mechanisms_focus(repository, selected_metric, focus)
    model_id = focus["model_id"]
    evidence_level = focus["evidence_level"]
    selected = summary.loc[
        (summary["generator_id"] == model_id)
        & (summary["evidence_level"] == evidence_level)
    ].iloc[0]
    model_label = str(selected["generator_label"])
    profile = repository.utilization_stage_profile(model_id, evidence_level)
    utilization = _localized_evidence_frame(data.evidence_utilization, resolved)
    return html.Div(
        [
            html.Div(
                [
                    dcc.RadioItems(
                        id=MECHANISMS_UTILIZATION_METRIC_ID,
                        options=[
                            {
                                "label": utilization_metric_label(resolved, key),
                                "value": key,
                            }
                            for key in (
                                "feature_use",
                                "concept_use",
                                "supported_claim_yield",
                            )
                        ],
                        value=selected_metric,
                        inline=True,
                        className="segmented-control mechanisms-segmented",
                        inputClassName="segmented-control__input",
                        labelClassName="segmented-control__label",
                    ),
                    html.P(t(resolved, "mechanisms.utilization.note"), className="conditional-note"),
                ],
                className="conditional-control-row",
            ),
            html.Section(
                [
                    chart_card(
                        graph_id=MECHANISMS_UTILIZATION_MATRIX_ID,
                        title=t(resolved, "mechanisms.utilization.matrix_title"),
                        subtitle=t(resolved, "mechanisms.utilization.matrix_subtitle"),
                        figure=_figure(build_utilization_matrix(summary, metric_label=label, metric_id=selected_metric, focused_model_id=model_id, focused_evidence_level=evidence_level), resolved),
                        figure_id=FIG_MECHANISMS_UTILIZATION_MATRIX,
                        source=t(resolved, "mechanisms.utilization.source_runs"),
                        metric=label,
                        denominator=t(resolved, "mechanisms.utilization.matrix_denominator"),
                        release=VISUALIZATION_RELEASE_ID,
                        locale=resolved,
                    ),
                    html.Div(
                        utilization_interpretation_panel(summary, metric_id=selected_metric, metric_label=label, locale=resolved),
                        id=MECHANISMS_UTILIZATION_PANEL_ID,
                    ),
                ],
                className="mechanisms-hero-grid",
            ),
            html.Section(
                [
                    chart_card(
                        graph_id=MECHANISMS_UTILIZATION_PROFILE_ID,
                        title=t(resolved, "mechanisms.utilization.profile_title", model=model_label, evidence=evidence_level),
                        subtitle=t(resolved, "mechanisms.utilization.profile_subtitle"),
                        figure=_figure(build_utilization_stage_profile(
                            profile,
                            model_id=model_id,
                            model_label=model_label,
                            evidence_level=evidence_level,
                            defined_label=t(resolved, "mechanisms.figure.defined"),
                            not_applicable_label=t(
                                resolved, "mechanisms.figure.not_applicable"
                            ),
                        ), resolved),
                        figure_id=FIG_MECHANISMS_UTILIZATION_PROFILE,
                        source=t(resolved, "mechanisms.utilization.profile_source"),
                        metric=t(resolved, "mechanisms.utilization.profile_metric"),
                        denominator=t(resolved, "mechanisms.utilization.profile_denominator"),
                        release=VISUALIZATION_RELEASE_ID,
                        locale=resolved,
                    ),
                    chart_card(
                        graph_id=MECHANISMS_UTILIZATION_SCATTER_ID,
                        title=t(resolved, "mechanisms.utilization.scatter_title"),
                        subtitle=t(resolved, "mechanisms.utilization.scatter_subtitle"),
                        figure=_figure(build_utilization_quality_scatter(utilization, metric_id=selected_metric, metric_label=label), resolved),
                        figure_id=FIG_MECHANISMS_UTILIZATION_QUALITY,
                        source=t(resolved, "mechanisms.utilization.source_runs"),
                        metric=t(resolved, "mechanisms.utilization.scatter_metric", metric=label),
                        denominator=t(resolved, "mechanisms.utilization.scatter_denominator"),
                        release=VISUALIZATION_RELEASE_ID,
                        locale=resolved,
                    ),
                ],
                className="mechanisms-two-column",
            ),
            html.P(t(resolved, "mechanisms.utilization.disclaimer"), className="research-disclaimer"),
            html.Details(
                [html.Summary(t(resolved, "mechanisms.utilization.view_details")), html.Div(_utilization_grid(utilization, resolved), className="mechanisms-details__body")],
                className="mechanisms-details",
            ),
            html.Details(
                [
                    html.Summary(t(resolved, "mechanisms.utilization.narrative_details")),
                    html.Div(
                        [
                            html.P(t(resolved, "mechanisms.utilization.narrative_note"), className="mechanisms-compact-note"),
                            html.Div(
                                [
                                    chart_card(
                                        graph_id=MECHANISMS_NARRATIVE_STRUCTURE_ID,
                                        title=t(resolved, "mechanisms.utilization.narrative_title"),
                                        subtitle=t(resolved, "mechanisms.utilization.narrative_subtitle"),
                                        figure=_figure(build_narrative_structure_chart(data.narrative_model_summary), resolved),
                                        figure_id=FIG_MECHANISMS_NARRATIVE_STRUCTURE,
                                        source=t(resolved, "mechanisms.utilization.narrative_source"),
                                        metric=t(resolved, "mechanisms.utilization.narrative_metric"),
                                        denominator=t(resolved, "mechanisms.utilization.narrative_denominator"),
                                        release=VISUALIZATION_RELEASE_ID,
                                        locale=resolved,
                                    ),
                                    chart_card(
                                        graph_id=MECHANISMS_POLICY_COMPLIANCE_ID,
                                        title=t(resolved, "mechanisms.utilization.policy_title"),
                                        subtitle=t(resolved, "mechanisms.utilization.policy_subtitle"),
                                        figure=_figure(build_policy_compliance_chart(data.narrative_model_summary), resolved),
                                        figure_id=FIG_MECHANISMS_POLICY_COMPLIANCE,
                                        source=t(resolved, "mechanisms.utilization.narrative_source"),
                                        metric=t(resolved, "mechanisms.utilization.policy_metric"),
                                        denominator=t(resolved, "mechanisms.utilization.policy_denominator"),
                                        release=VISUALIZATION_RELEASE_ID,
                                        locale=resolved,
                                    ),
                                ],
                                className="mechanisms-two-column",
                            ),
                        ],
                        className="mechanisms-details__body",
                    ),
                ],
                className="mechanisms-details",
            ),
        ],
        className="mechanisms-tab-content",
    )


def _claim_tab(data, measure: str, locale: object):
    resolved = normalize_locale(locale)
    metric_key = (
        "mechanisms.claims.difficulty_metric_count"
        if measure == "count"
        else "mechanisms.claims.difficulty_metric_rate"
    )
    return html.Div(
        [
            html.Section(
                [
                    chart_card(
                        graph_id=MECHANISMS_CLAIM_STATUS_ID,
                        title=t(resolved, "mechanisms.claims.status_title"),
                        subtitle=t(resolved, "mechanisms.claims.status_subtitle"),
                        figure=_figure(build_claim_status_small_multiples(data.claim_status_by_option), resolved),
                        figure_id=FIG_MECHANISMS_CLAIM_STATUS,
                        source=t(resolved, "mechanisms.claims.status_source"),
                        metric=t(resolved, "mechanisms.claims.status_metric"),
                        denominator=t(resolved, "mechanisms.claims.status_denominator"),
                        release=VISUALIZATION_RELEASE_ID,
                        locale=resolved,
                    ),
                    claim_mechanism_findings(data.claim_difficulty_by_type, locale=resolved),
                ],
                className="mechanisms-hero-grid",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.H2(t(resolved, "mechanisms.claims.difficulty_heading"), className="effectiveness-section__title"),
                            html.P(t(resolved, "mechanisms.claims.difficulty_subtitle"), className="effectiveness-section__subtitle"),
                        ]
                    ),
                    dcc.RadioItems(
                        id=MECHANISMS_CLAIM_MEASURE_ID,
                        options=[
                            {"label": t(resolved, "mechanisms.claims.measure_rate"), "value": "rate"},
                            {"label": t(resolved, "mechanisms.claims.measure_count"), "value": "count"},
                        ],
                        value=measure,
                        inline=True,
                        className="segmented-control segmented-control--compact mechanisms-segmented",
                        inputClassName="segmented-control__input",
                        labelClassName="segmented-control__label",
                    ),
                ],
                className="contrast-control-row",
            ),
            chart_card(
                graph_id=MECHANISMS_CLAIM_DIFFICULTY_ID,
                title=t(resolved, "mechanisms.claims.difficulty_title"),
                subtitle=t(resolved, "mechanisms.claims.difficulty_subtitle"),
                figure=_figure(build_claim_difficulty_matrix(data.claim_difficulty_by_type, measure=measure), resolved),
                figure_id=FIG_MECHANISMS_CLAIM_DIFFICULTY,
                source=t(resolved, "mechanisms.claims.difficulty_source"),
                metric=t(resolved, metric_key),
                denominator=t(resolved, "mechanisms.claims.difficulty_denominator"),
                release=VISUALIZATION_RELEASE_ID,
                locale=resolved,
            ),
            html.Details(
                [html.Summary(t(resolved, "mechanisms.claims.view_reasons")), html.Div(_reason_grid(data.evidence_utilization, resolved), className="mechanisms-details__body")],
                className="mechanisms-details",
            ),
            html.Details(
                [html.Summary(t(resolved, "mechanisms.claims.lexical_details")), html.Div(lexical_signal_disclosure(data.safe_phrase_summary, locale=resolved), className="mechanisms-details__body")],
                className="mechanisms-details",
            ),
            html.P(t(resolved, "mechanisms.claims.lexical_disclaimer"), className="research-disclaimer"),
        ],
        className="mechanisms-tab-content",
    )


def _pipeline_tab(data, locale: object):
    resolved = normalize_locale(locale)
    return html.Div(
        [
            html.Section(
                [
                    chart_card(
                        graph_id=MECHANISMS_PIPELINE_COMPLETION_ID,
                        title=t(resolved, "mechanisms.pipeline.completion_title"),
                        subtitle=t(resolved, "mechanisms.pipeline.completion_subtitle"),
                        figure=_figure(build_pipeline_completion_chart(data.pipeline_stage_summary), resolved),
                        figure_id=FIG_MECHANISMS_PIPELINE_COMPLETION,
                        source=t(resolved, "mechanisms.pipeline.completion_source"),
                        metric=t(resolved, "mechanisms.pipeline.completion_metric"),
                        denominator=t(resolved, "mechanisms.pipeline.completion_denominator"),
                        release=VISUALIZATION_RELEASE_ID,
                        locale=resolved,
                    ),
                    pipeline_failure_summary(data.pipeline_failures, locale=resolved),
                ],
                className="mechanisms-hero-grid",
            ),
            chart_card(
                graph_id=MECHANISMS_FAILURE_MATRIX_ID,
                title=t(resolved, "mechanisms.pipeline.failure_title"),
                subtitle=t(resolved, "mechanisms.pipeline.failure_subtitle"),
                figure=_figure(build_failure_matrix(data.failure_matrix), resolved),
                figure_id=FIG_MECHANISMS_FAILURE_MATRIX,
                source=t(resolved, "mechanisms.pipeline.failure_source"),
                metric=t(resolved, "mechanisms.pipeline.failure_metric"),
                denominator=t(resolved, "mechanisms.pipeline.failure_denominator"),
                release=VISUALIZATION_RELEASE_ID,
                locale=resolved,
            ),
            html.Details(
                [html.Summary(t(resolved, "mechanisms.pipeline.view_failures")), html.Div(_failure_grid(data.pipeline_failures, resolved), className="mechanisms-details__body")],
                className="mechanisms-details",
            ),
        ],
        className="mechanisms-tab-content",
    )


def build_mechanisms_children(
    locale: object = DEFAULT_LOCALE,
    *,
    ui_state: object | None = None,
    focus: object | None = None,
    repository: DashboardRepository | None = None,
):
    resolved = normalize_locale(locale)
    state = normalize_mechanisms_state(ui_state)
    repo = repository or get_dashboard_repository()
    data = repo.mechanisms_data()
    resolved_focus = normalize_mechanisms_focus(
        repo, state["utilization_metric"], focus
    )
    return [
        page_header(
            title=t(resolved, "mechanisms.title"),
            subtitle=t(resolved, "mechanisms.subtitle"),
            endpoint=t(resolved, "mechanisms.endpoint"),
            inference_unit=t(resolved, "mechanisms.inference_unit"),
            endpoint_label=t(resolved, "mechanisms.endpoint_label"),
            inference_label=t(resolved, "mechanisms.inference_label"),
            locale=resolved,
        ),
        html.Div(
            [
                html.Span(t(resolved, "mechanisms.context")),
                html.Button(t(resolved, "mechanisms.export"), id=MECHANISMS_EXPORT_ID, className="page-export-button", type="button"),
            ],
            className="effectiveness-context",
        ),
        dcc.Tabs(
            id=MECHANISMS_TABS_ID,
            value=state["tab"],
            className="effectiveness-tabs mechanisms-tabs",
            parent_className="effectiveness-tabs__parent",
            children=[
                dcc.Tab(label=t(resolved, "mechanisms.tab_design"), value="design", className="tab", selected_className="tab--selected", children=_evidence_design_tab(data, resolved)),
                dcc.Tab(label=t(resolved, "mechanisms.tab_utilization"), value="utilization", className="tab", selected_className="tab--selected", children=_utilization_tab(repo, data, state["utilization_metric"], resolved_focus, resolved)),
                dcc.Tab(label=t(resolved, "mechanisms.tab_claims"), value="claims", className="tab", selected_className="tab--selected", children=_claim_tab(data, state["claim_measure"], resolved)),
                dcc.Tab(label=t(resolved, "mechanisms.tab_pipeline"), value="pipeline", className="tab", selected_className="tab--selected", children=_pipeline_tab(data, resolved)),
            ],
        ),
    ]


def layout(
    tab: str | None = None,
    metric: str | None = None,
    model: str | None = None,
    evidence: str | None = None,
    **_: object,
):
    repository = get_dashboard_repository()
    state = normalize_mechanisms_state(
        {"tab": tab, "utilization_metric": metric, "claim_measure": "rate"}
    )
    focus = normalize_mechanisms_focus(
        repository,
        state["utilization_metric"],
        {"model_id": model, "evidence_level": evidence},
    )
    return html.Main(
        [
            dcc.Store(id=MECHANISMS_UI_STATE_ID, data=state, storage_type="memory"),
            dcc.Store(id=MECHANISMS_FOCUS_STORE_ID, data=focus, storage_type="memory"),
            dcc.Download(id=MECHANISMS_DOWNLOAD_ID),
            html.Div(
                build_mechanisms_children(DEFAULT_LOCALE, ui_state=state, focus=focus, repository=repository),
                id=MECHANISMS_CONTENT_ID,
            ),
        ],
        id=MECHANISMS_PAGE_ID,
        className="research-page mechanisms-page",
        **{"data-rq": "RQ3", "data-analysis-type": "descriptive-diagnostic"},
    )
