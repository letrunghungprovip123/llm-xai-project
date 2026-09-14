"""Page 2 — localized Effectiveness & Reliability for RQ1 and RQ2."""

from __future__ import annotations

import dash
from dash import dcc, html
import pandas as pd

from ..components.chart_card import chart_card
from ..components.data_grid import data_grid
from ..components.effectiveness import (
    conditional_context_panel,
    operational_interpretation_panel,
    sensitivity_summary_panel,
)
from ..components.page_header import page_header
from ..data.repository import DashboardRepository, get_dashboard_repository
from ..figures.effectiveness import (
    FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP,
    FIG_EFFECTIVENESS_LOSS_DECOMPOSITION,
    FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP,
    FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES,
    FIG_EFFECTIVENESS_RELIABILITY_MAP,
    build_conditional_quality_heatmap,
    build_effect_size_chart,
    build_operational_conditional_gap,
    build_operational_loss_decomposition,
    build_reliability_map,
)
from ..i18n import (
    DEFAULT_LOCALE,
    evidence_label,
    format_integer,
    format_number,
    format_p_value,
    localize_plotly_figure,
    metric_label,
    normalize_locale,
    t,
)
from ..ids import (
    EFFECTIVENESS_CLEAR_FOCUS_ID,
    EFFECTIVENESS_CONDITIONAL_CONTRAST_GRID_ID,
    EFFECTIVENESS_CONDITIONAL_HEATMAP_ID,
    EFFECTIVENESS_CONDITIONAL_METRIC_ID,
    EFFECTIVENESS_CONDITIONAL_PANEL_ID,
    EFFECTIVENESS_CONTENT_ID,
    EFFECTIVENESS_CONTRAST_FAMILY_ID,
    EFFECTIVENESS_CONTRAST_GRID_ID,
    EFFECTIVENESS_DOWNLOAD_ID,
    EFFECTIVENESS_EFFECT_SIZE_ID,
    EFFECTIVENESS_EXPORT_ID,
    EFFECTIVENESS_FAILURE_GRID_ID,
    EFFECTIVENESS_FOCUS_CHIP_ID,
    EFFECTIVENESS_FOCUS_PANEL_ID,
    EFFECTIVENESS_GAP_ID,
    EFFECTIVENESS_LOSS_ID,
    EFFECTIVENESS_OPTION_GRID_ID,
    EFFECTIVENESS_PAGE_ID,
    EFFECTIVENESS_RELIABILITY_MAP_ID,
    EFFECTIVENESS_SENSITIVITY_ID,
    EFFECTIVENESS_TABS_ID,
    EFFECTIVENESS_UI_STATE_ID,
)
from ..settings import DEFAULT_CONDITIONAL_METRIC, VISUALIZATION_RELEASE_ID


PAGE_MODULE = "llm_xai_dashboard.effectiveness"
_FIGURE_PREFIXES = ("effectiveness.figure.",)
_VALID_TABS = frozenset({"operational", "conditional", "statistics"})
_VALID_CONTRAST_FAMILIES = frozenset(
    {"all", "model_within_evidence", "evidence_vs_s0"}
)
_VALID_CONDITIONAL_METRICS = frozenset(
    {"conservative_faithfulness", "verifiability", "resolved_faithfulness"}
)
MODEL_LABELS = {
    "qwen3_8b": "Qwen3 8B",
    "deepseek_v4_flash": "DeepSeek V4 Flash",
    "phi4_mini_instruct": "Phi-4 Mini Instruct",
}


def register_page() -> None:
    if PAGE_MODULE not in dash.page_registry:
        dash.register_page(
            PAGE_MODULE,
            path="/effectiveness",
            name="Effectiveness",
            title="Effectiveness & Reliability · LLM-XAI",
            description=(
                "Average quality, lower-tail reliability, conditional quality "
                "and certified statistical evidence."
            ),
            order=1,
            layout=layout,
        )


def normalize_effectiveness_state(value: object | None) -> dict[str, str]:
    """Normalize persisted presentation state without touching analytical IDs."""

    raw = value if isinstance(value, dict) else {}
    tab = str(raw.get("tab", "operational"))
    metric = str(raw.get("conditional_metric", DEFAULT_CONDITIONAL_METRIC))
    family = str(raw.get("contrast_family", "all"))
    return {
        "tab": tab if tab in _VALID_TABS else "operational",
        "conditional_metric": (
            metric if metric in _VALID_CONDITIONAL_METRICS else DEFAULT_CONDITIONAL_METRIC
        ),
        "contrast_family": family if family in _VALID_CONTRAST_FAMILIES else "all",
    }


def _number_formatter(locale: object, digits: int = 1) -> dict[str, str]:
    locale_tag = "vi-VN" if normalize_locale(locale) == "vi" else "en-US"
    return {
        "function": (
            "params.value == null ? '' : "
            f"new Intl.NumberFormat('{locale_tag}', "
            f"{{minimumFractionDigits:{digits},maximumFractionDigits:{digits}}})"
            ".format(Number(params.value))"
        )
    }


def _percent_formatter(locale: object, digits: int = 1) -> dict[str, str]:
    locale_tag = "vi-VN" if normalize_locale(locale) == "vi" else "en-US"
    return {
        "function": (
            "params.value == null ? '' : "
            f"new Intl.NumberFormat('{locale_tag}', "
            "{style:'percent',minimumFractionDigits:"
            f"{digits},maximumFractionDigits:{digits}}})"
            ".format(Number(params.value))"
        )
    }


def _p_formatter(locale: object) -> dict[str, str]:
    decimal = "," if normalize_locale(locale) == "vi" else "."
    return {
        "function": (
            "params.value == null ? '' : "
            f"(Number(params.value) < 0.0001 ? '<0{decimal}0001' : "
            f"Number(params.value).toFixed(4).replace('.', '{decimal}'))"
        )
    }


def _localized_option_frame(frame: pd.DataFrame, locale: object) -> pd.DataFrame:
    localized = frame.copy(deep=True)
    localized["evidence_display"] = localized["evidence_level"].map(
        lambda value: evidence_label(locale, value)
    )
    return localized


def _option_grid(frame: pd.DataFrame, locale: object):
    resolved = normalize_locale(locale)
    columns = [
        {"field": "model_label", "headerName": t(resolved, "effectiveness.grid.model"), "minWidth": 150},
        {"field": "evidence_display", "headerName": t(resolved, "effectiveness.grid.evidence"), "minWidth": 170},
        {"field": "mean_end_to_end_yield", "headerName": t(resolved, "effectiveness.grid.mean_e2e"), "valueFormatter": _percent_formatter(resolved)},
        {"field": "p10_end_to_end_yield", "headerName": t(resolved, "effectiveness.grid.p10_e2e"), "valueFormatter": _percent_formatter(resolved)},
        {"field": "median_end_to_end_yield", "headerName": t(resolved, "effectiveness.grid.median_e2e"), "valueFormatter": _percent_formatter(resolved)},
        {"field": "usability_rate", "headerName": t(resolved, "effectiveness.grid.usability"), "valueFormatter": _percent_formatter(resolved)},
        {"field": "unusable_generation_count", "headerName": t(resolved, "effectiveness.grid.unusable")},
        {"field": "mean_latency_seconds_planned", "headerName": t(resolved, "effectiveness.grid.latency"), "valueFormatter": _number_formatter(resolved, 1)},
        {"field": "mean_total_token_count_planned", "headerName": t(resolved, "effectiveness.grid.tokens"), "valueFormatter": _number_formatter(resolved, 0)},
        {"field": "mean_supported_claims_per_1000_tokens", "headerName": t(resolved, "effectiveness.grid.supported_per_1k"), "valueFormatter": _number_formatter(resolved, 2), "minWidth": 175},
    ]
    selected = frame[[item["field"] for item in columns]].copy()
    return data_grid(
        grid_id=EFFECTIVENESS_OPTION_GRID_ID,
        frame=selected,
        column_defs=columns,
        height=400,
        page_size=18,
        locale=resolved,
    )


def localized_failure_frame(frame: pd.DataFrame, locale: object) -> pd.DataFrame:
    """Return display-only labels while preserving the certified source frame."""

    resolved = normalize_locale(locale)
    localized = frame.copy(deep=True)
    localized["evidence_display"] = localized["evidence_level"].map(
        lambda value: evidence_label(resolved, value)
    )
    localized["missingness_display"] = localized["missingness_class"].map(
        lambda value: t(
            resolved,
            "effectiveness.grid.structured_pipeline_failure"
            if str(value) == "STRUCTURED_PIPELINE_FAILURE"
            else "effectiveness.grid.missing_not_imputed",
        )
    )
    yes = t(resolved, "effectiveness.grid.yes")
    no = t(resolved, "effectiveness.grid.no")
    for source, target in (
        ("is_truncated", "truncated_display"),
        ("is_parse_success", "parsed_display"),
        ("is_schema_valid", "schema_display"),
    ):
        localized[target] = localized[source].map(lambda value: yes if bool(value) else no)
    localized["conditional_display"] = localized["conditional_endpoint_handling"].map(
        lambda value: (
            t(resolved, "effectiveness.grid.missing_not_imputed")
            if str(value).upper() == "MISSING_NOT_IMPUTED"
            else str(value).replace("_", " ").strip()
        )
    )
    return localized


def _failure_grid(frame: pd.DataFrame, locale: object):
    resolved = normalize_locale(locale)
    localized = localized_failure_frame(frame, resolved)
    columns = [
        {"field": "case_id", "headerName": t(resolved, "effectiveness.grid.case")},
        {"field": "model_label", "headerName": t(resolved, "effectiveness.grid.model"), "minWidth": 150},
        {"field": "evidence_display", "headerName": t(resolved, "effectiveness.grid.evidence"), "minWidth": 170},
        {"field": "missingness_display", "headerName": t(resolved, "effectiveness.grid.failure_class"), "minWidth": 190},
        {"field": "truncated_display", "headerName": t(resolved, "effectiveness.grid.truncated")},
        {"field": "parsed_display", "headerName": t(resolved, "effectiveness.grid.parsed")},
        {"field": "schema_display", "headerName": t(resolved, "effectiveness.grid.schema_valid")},
        {"field": "latency_seconds", "headerName": t(resolved, "effectiveness.grid.latency"), "valueFormatter": _number_formatter(resolved, 2)},
        {"field": "total_token_count", "headerName": t(resolved, "effectiveness.grid.tokens")},
        {"field": "conditional_display", "headerName": t(resolved, "effectiveness.grid.conditional_handling"), "minWidth": 200},
    ]
    return data_grid(
        grid_id=EFFECTIVENESS_FAILURE_GRID_ID,
        frame=localized[[item["field"] for item in columns]].copy(),
        column_defs=columns,
        height=360,
        page_size=10,
        locale=resolved,
    )


def _contrast_label(row: pd.Series, locale: object) -> str:
    a_model = MODEL_LABELS.get(str(row["condition_a_model_id"]), str(row["condition_a_model_id"]))
    b_model = MODEL_LABELS.get(str(row["condition_b_model_id"]), str(row["condition_b_model_id"]))
    a = f"{a_model} · {row['condition_a_evidence_level']}"
    b = f"{b_model} · {row['condition_b_evidence_level']}"
    return t(normalize_locale(locale), "effectiveness.grid.versus", a=a, b=b)


def contrast_display_frame(
    frame: pd.DataFrame,
    locale: object = DEFAULT_LOCALE,
) -> pd.DataFrame:
    """Create a localized display view without changing certified test results."""

    resolved = normalize_locale(locale)
    result = frame.copy(deep=True)
    result["contrast"] = result.apply(lambda row: _contrast_label(row, resolved), axis=1)
    result["result_state"] = result["significant_adjusted"].map(
        {
            True: t(resolved, "effectiveness.grid.significant"),
            False: t(resolved, "effectiveness.grid.not_significant"),
        }
    )
    result.loc[result["adjusted_p_value"].isna(), "result_state"] = t(
        resolved, "effectiveness.grid.not_tested"
    )
    return result[
        [
            "contrast_family",
            "contrast",
            "planned_pair_count",
            "observed_pair_count",
            "excluded_pair_count",
            "mean_difference",
            "adjusted_p_value",
            "rank_biserial_correlation",
            "result_state",
        ]
    ]


def _contrast_grid(frame: pd.DataFrame, *, grid_id: str, locale: object, page_size: int = 12):
    resolved = normalize_locale(locale)
    display = contrast_display_frame(frame, resolved)
    columns = [
        {"field": "contrast", "headerName": t(resolved, "effectiveness.grid.contrast"), "minWidth": 280},
        {"field": "planned_pair_count", "headerName": t(resolved, "effectiveness.grid.planned_pairs")},
        {"field": "observed_pair_count", "headerName": t(resolved, "effectiveness.grid.observed_pairs")},
        {"field": "excluded_pair_count", "headerName": t(resolved, "effectiveness.grid.excluded")},
        {"field": "mean_difference", "headerName": t(resolved, "effectiveness.grid.mean_difference"), "valueFormatter": _percent_formatter(resolved)},
        {"field": "adjusted_p_value", "headerName": t(resolved, "effectiveness.grid.holm_p"), "valueFormatter": _p_formatter(resolved)},
        {"field": "rank_biserial_correlation", "headerName": t(resolved, "effectiveness.grid.rank_biserial"), "valueFormatter": _number_formatter(resolved, 3)},
        {"field": "result_state", "headerName": t(resolved, "effectiveness.grid.result"), "minWidth": 145},
    ]
    return data_grid(
        grid_id=grid_id,
        frame=display,
        column_defs=columns,
        height=420,
        page_size=page_size,
        locale=resolved,
    )


def _omnibus_strip(frame: pd.DataFrame, locale: object):
    resolved = normalize_locale(locale)
    labels = {
        "model": t(resolved, "effectiveness.panel.effect_model"),
        "evidence": t(resolved, "effectiveness.panel.effect_evidence"),
        "model:evidence": t(resolved, "effectiveness.panel.effect_interaction"),
    }
    ordered = frame.set_index("effect").loc[["model", "evidence", "model:evidence"]]
    return html.Section(
        [
            html.Div(
                [
                    html.Span(labels[str(effect)], className="omnibus-item__label"),
                    html.Span(t(resolved, "effectiveness.omnibus.f_stat", value=format_number(resolved, float(row.f_statistic), decimals=2, trim_trailing_zeros=False)), className="omnibus-item__stat"),
                    html.Span(
                        t(resolved, "effectiveness.omnibus.p_less")
                        if float(row.p_value_used) < 0.0001
                        else t(resolved, "effectiveness.omnibus.p_equal", value=format_number(resolved, float(row.p_value_used), decimals=4, trim_trailing_zeros=False)),
                        className="omnibus-item__stat",
                    ),
                    html.Span(t(resolved, "effectiveness.omnibus.eta", value=format_number(resolved, float(row.partial_eta_squared), decimals=3, trim_trailing_zeros=False)), className="omnibus-item__stat"),
                ],
                className="omnibus-item",
            )
            for effect, row in ordered.iterrows()
        ],
        className="omnibus-strip",
        **{"aria-label": t(resolved, "effectiveness.omnibus.aria")},
    )


def _figure(figure, locale: object):
    return localize_plotly_figure(figure, locale, prefixes=_FIGURE_PREFIXES)


def _operational_tab(data, focused, locale: object):
    resolved = normalize_locale(locale)
    options = _localized_option_frame(data.option_performance, resolved)
    reliability = _figure(
        build_reliability_map(options, focused_option_id=focused.option_id if focused else None),
        resolved,
    )
    loss = _figure(build_operational_loss_decomposition(options), resolved)
    return html.Div(
        [
            html.Section(
                [
                    chart_card(
                        graph_id=EFFECTIVENESS_RELIABILITY_MAP_ID,
                        title=t(resolved, "effectiveness.operational.reliability_title"),
                        subtitle=t(resolved, "effectiveness.operational.reliability_subtitle"),
                        figure=reliability,
                        figure_id=FIG_EFFECTIVENESS_RELIABILITY_MAP,
                        source=t(resolved, "shared.option_performance"),
                        metric=t(resolved, "effectiveness.operational.reliability_metric"),
                        denominator=t(resolved, "effectiveness.operational.denominator_option"),
                        release=VISUALIZATION_RELEASE_ID,
                        locale=resolved,
                    ),
                    html.Div(
                        operational_interpretation_panel(data.option_performance, focused, locale=resolved),
                        id=EFFECTIVENESS_FOCUS_PANEL_ID,
                    ),
                ],
                className="effectiveness-hero-grid",
            ),
            chart_card(
                graph_id=EFFECTIVENESS_LOSS_ID,
                title=t(resolved, "effectiveness.operational.loss_title"),
                subtitle=t(resolved, "effectiveness.operational.loss_subtitle"),
                figure=loss,
                figure_id=FIG_EFFECTIVENESS_LOSS_DECOMPOSITION,
                source=t(resolved, "shared.option_performance"),
                metric=t(resolved, "effectiveness.operational.loss_metric"),
                denominator=t(resolved, "effectiveness.operational.loss_denominator"),
                release=VISUALIZATION_RELEASE_ID,
                locale=resolved,
            ),
            html.Details(
                [html.Summary(t(resolved, "effectiveness.operational.view_all")), html.Div(_option_grid(options, resolved), className="effectiveness-details__body")],
                className="effectiveness-details",
            ),
        ],
        className="tab-content",
    )


def _conditional_tab(data, summary: pd.DataFrame, selected_metric: str, locale: object):
    resolved = normalize_locale(locale)
    selected_label = metric_label(resolved, selected_metric)
    heatmap = _figure(build_conditional_quality_heatmap(summary, metric_id=selected_metric, metric_label=selected_label), resolved)
    gap = _figure(build_operational_conditional_gap(summary, metric_id=selected_metric, metric_label=selected_label), resolved)
    tests = data.conditional_paired_tests.loc[data.conditional_paired_tests["metric_id"] == selected_metric]
    model_counts = data.unusable_generations["model_label"].value_counts()
    failure_text = [
        html.Strong(t(resolved, "effectiveness.conditional.unusable_count", count=format_integer(resolved, len(data.unusable_generations)))),
        html.Span(t(resolved, "effectiveness.conditional.all_s4")),
    ]
    for model in ("Qwen3 8B", "DeepSeek V4 Flash", "Phi-4 Mini Instruct"):
        failure_text.append(html.Span(t(resolved, "effectiveness.conditional.model_failure_count", model=model, count=format_integer(resolved, int(model_counts.get(model, 0))))))

    return html.Div(
        [
            html.Div(
                [
                    dcc.RadioItems(
                        id=EFFECTIVENESS_CONDITIONAL_METRIC_ID,
                        options=[{"label": metric_label(resolved, item), "value": item} for item in sorted(_VALID_CONDITIONAL_METRICS)],
                        value=selected_metric,
                        inline=True,
                        className="segmented-control",
                        inputClassName="segmented-control__input",
                        labelClassName="segmented-control__label",
                    ),
                    html.P(t(resolved, "effectiveness.conditional.note"), className="conditional-note"),
                ],
                className="conditional-control-row",
            ),
            html.Section(
                [
                    chart_card(
                        graph_id=EFFECTIVENESS_CONDITIONAL_HEATMAP_ID,
                        title=t(resolved, "effectiveness.conditional.title"),
                        subtitle=t(resolved, "effectiveness.conditional.subtitle"),
                        figure=heatmap,
                        figure_id=FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP,
                        source=t(resolved, "effectiveness.conditional.source"),
                        metric=selected_label,
                        denominator=t(resolved, "effectiveness.conditional.denominator"),
                        release=VISUALIZATION_RELEASE_ID,
                        locale=resolved,
                    ),
                    html.Div(conditional_context_panel(summary, metric_label=selected_label, locale=resolved), id=EFFECTIVENESS_CONDITIONAL_PANEL_ID),
                ],
                className="conditional-hero-grid",
            ),
            chart_card(
                graph_id=EFFECTIVENESS_GAP_ID,
                title=t(resolved, "effectiveness.conditional.gap_title"),
                subtitle=t(resolved, "effectiveness.conditional.gap_subtitle"),
                figure=gap,
                figure_id=FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP,
                source=t(resolved, "effectiveness.conditional.gap_source"),
                metric=t(resolved, "effectiveness.conditional.gap_metric", metric=selected_label),
                denominator=t(resolved, "effectiveness.conditional.gap_denominator"),
                release=VISUALIZATION_RELEASE_ID,
                locale=resolved,
            ),
            html.Div(failure_text, className="failure-strip"),
            html.Details([html.Summary(t(resolved, "effectiveness.conditional.view_failures")), html.Div(_failure_grid(data.unusable_generations, resolved), className="effectiveness-details__body")], className="effectiveness-details"),
            html.Details([html.Summary(t(resolved, "effectiveness.conditional.view_comparisons")), html.Div(_contrast_grid(tests, grid_id=EFFECTIVENESS_CONDITIONAL_CONTRAST_GRID_ID, locale=resolved), className="effectiveness-details__body")], className="effectiveness-details"),
        ],
        className="tab-content",
    )


def _statistics_tab(data, family: str, locale: object):
    resolved = normalize_locale(locale)
    effects = _figure(build_effect_size_chart(data.omnibus_tests), resolved)
    primary = data.paired_tests.copy()
    filtered = primary if family == "all" else primary.loc[primary["contrast_family"] == family]
    significant_count = int(primary["significant_adjusted"].astype(bool).sum())
    not_tested_count = int(primary["adjusted_p_value"].isna().sum())
    summary = t(resolved, "effectiveness.statistics.comparisons_summary", significant=format_integer(resolved, significant_count), not_tested=format_integer(resolved, not_tested_count))
    return html.Div(
        [
            _omnibus_strip(data.omnibus_tests, resolved),
            html.Section(
                [
                    chart_card(
                        graph_id=EFFECTIVENESS_EFFECT_SIZE_ID,
                        title=t(resolved, "effectiveness.statistics.effect_title"),
                        subtitle=t(resolved, "effectiveness.statistics.effect_subtitle"),
                        figure=effects,
                        figure_id=FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES,
                        source=t(resolved, "effectiveness.statistics.effect_source"),
                        metric=t(resolved, "effectiveness.statistics.effect_metric"),
                        denominator=t(resolved, "effectiveness.statistics.effect_denominator"),
                        release=VISUALIZATION_RELEASE_ID,
                        locale=resolved,
                    ),
                    html.Div(sensitivity_summary_panel(data.sensitivity_summary, locale=resolved), id=EFFECTIVENESS_SENSITIVITY_ID),
                ],
                className="statistics-hero-grid",
            ),
            html.Section(
                [
                    html.Div([html.H2(t(resolved, "effectiveness.statistics.comparisons_title"), className="effectiveness-section__title"), html.P(summary, className="effectiveness-section__subtitle")]),
                    dcc.RadioItems(
                        id=EFFECTIVENESS_CONTRAST_FAMILY_ID,
                        options=[
                            {"label": t(resolved, "effectiveness.statistics.family_all"), "value": "all"},
                            {"label": t(resolved, "effectiveness.statistics.family_model"), "value": "model_within_evidence"},
                            {"label": t(resolved, "effectiveness.statistics.family_evidence"), "value": "evidence_vs_s0"},
                        ],
                        value=family,
                        inline=True,
                        className="segmented-control segmented-control--compact",
                        inputClassName="segmented-control__input",
                        labelClassName="segmented-control__label",
                    ),
                ],
                className="contrast-control-row",
            ),
            _contrast_grid(filtered, grid_id=EFFECTIVENESS_CONTRAST_GRID_ID, locale=resolved, page_size=12),
            html.P(t(resolved, "effectiveness.statistics.disclaimer"), className="research-disclaimer"),
        ],
        className="tab-content",
    )


def build_effectiveness_children(
    locale: object = DEFAULT_LOCALE,
    *,
    model: str | None = None,
    evidence: str | None = None,
    ui_state: object | None = None,
    repository: DashboardRepository | None = None,
):
    """Build every user-facing Page-2 element for one explicit locale."""

    resolved = normalize_locale(locale)
    state = normalize_effectiveness_state(ui_state)
    repo = repository or get_dashboard_repository()
    data = repo.effectiveness_data()
    focused = repo.focused_option(model, evidence)
    selected_metric = state["conditional_metric"]
    summary = repo.conditional_option_summary(selected_metric)
    focus_children = (
        [
            html.Span(t(resolved, "effectiveness.focused_configuration", model=focused.model_label, evidence=focused.evidence_level), className="focus-chip"),
            html.Button(t(resolved, "effectiveness.clear_focus"), id=EFFECTIVENESS_CLEAR_FOCUS_ID, className="focus-clear", type="button"),
        ]
        if focused
        else []
    )
    return [
        page_header(
            title=t(resolved, "effectiveness.title"),
            subtitle=t(resolved, "effectiveness.subtitle"),
            endpoint=t(resolved, "effectiveness.endpoint"),
            inference_unit=t(resolved, "effectiveness.inference_unit"),
            locale=resolved,
        ),
        html.Div(
            [
                html.Span(t(resolved, "effectiveness.context")),
                html.Div(focus_children, id=EFFECTIVENESS_FOCUS_CHIP_ID, className="effectiveness-context__focus"),
                html.Button(t(resolved, "effectiveness.export"), id=EFFECTIVENESS_EXPORT_ID, className="focus-clear", type="button"),
            ],
            className="effectiveness-context",
        ),
        dcc.Tabs(
            id=EFFECTIVENESS_TABS_ID,
            value=state["tab"],
            className="effectiveness-tabs",
            parent_className="effectiveness-tabs-parent",
            children=[
                dcc.Tab(label=t(resolved, "effectiveness.tab_operational"), value="operational", className="tab", selected_className="tab tab--selected", children=_operational_tab(data, focused, resolved)),
                dcc.Tab(label=t(resolved, "effectiveness.tab_conditional"), value="conditional", className="tab", selected_className="tab tab--selected", children=_conditional_tab(data, summary, selected_metric, resolved)),
                dcc.Tab(label=t(resolved, "effectiveness.tab_statistics"), value="statistics", className="tab", selected_className="tab tab--selected", children=_statistics_tab(data, state["contrast_family"], resolved)),
            ],
        ),
    ]


def layout(
    model: str | None = None,
    evidence: str | None = None,
    tab: str | None = None,
    metric: str | None = None,
    **_: object,
):
    """Return a Vietnamese-first page with persistent locale-neutral UI state."""

    state = normalize_effectiveness_state(
        {"tab": tab, "conditional_metric": metric, "contrast_family": "all"}
    )
    repository = get_dashboard_repository()
    data = repository.effectiveness_data()
    return html.Main(
        [
            dcc.Store(id=EFFECTIVENESS_UI_STATE_ID, data=state, storage_type="memory"),
            dcc.Download(id=EFFECTIVENESS_DOWNLOAD_ID),
            html.Div(
                build_effectiveness_children(DEFAULT_LOCALE, model=model, evidence=evidence, ui_state=state, repository=repository),
                id=EFFECTIVENESS_CONTENT_ID,
            ),
        ],
        id=EFFECTIVENESS_PAGE_ID,
        className="dashboard-page effectiveness-page",
        **{
            "data-analytical-release": data.release.analytical_release_id,
            "data-visualization-release": data.release.visualization_release_id,
        },
    )
