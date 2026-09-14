"""Page 4 — certified deployment trade-offs and exploratory What-if."""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import dcc, html
import pandas as pd

from ..components.chart_card import chart_card
from ..components.data_grid import data_grid
from ..components.decision import (
    certified_custom_recommendation_panel,
    contribution_summary,
    decision_boundaries,
    rank_change_summary,
    recommendation_panel,
    scenario_selector,
    weight_editor,
    what_if_warning,
)
from ..components.page_header import page_header
from ..data.repository import get_dashboard_repository
from ..figures.decision import (
    FIG_DECISION_CRITERION_CONTRIBUTIONS,
    FIG_DECISION_TRADEOFF_MAP,
    FIG_DECISION_WHAT_IF_CONTRIBUTION_COMPARISON,
    build_certified_custom_contribution_comparison,
    build_criterion_contribution_profile,
    build_tradeoff_map,
)
from ..i18n import DEFAULT_LOCALE, localize_component_tree, normalize_locale
from ..ids import (
    DECISION_CLIPBOARD_ID,
    DECISION_COMPARISON_CLOSE_ID,
    DECISION_COMPARISON_DRAWER_ID,
    DECISION_COMPARISON_OPEN_ID,
    DECISION_COMPARISON_OPTIONS_ID,
    DECISION_COMPARISON_TABLE_ID,
    DECISION_CONTRIBUTION_ID,
    DECISION_CONTRIBUTION_SUMMARY_ID,
    DECISION_DOWNLOAD_ID,
    DECISION_EQUAL_WEIGHTS_ID,
    DECISION_EXPORT_ID,
    DECISION_FULL_RANKING_GRID_ID,
    DECISION_PAGE_ID,
    DECISION_RECOMMENDATION_ID,
    DECISION_RESET_WEIGHTS_ID,
    DECISION_SCENARIO_DESCRIPTION_ID,
    DECISION_SCENARIO_ID,
    DECISION_TABS_ID,
    DECISION_TOP_RANKING_ID,
    DECISION_TRADEOFF_ID,
    DECISION_WHAT_IF_COMPARISON_ID,
    DECISION_WHAT_IF_GRID_ID,
    DECISION_WHAT_IF_PANEL_ID,
    DECISION_WHAT_IF_RANK_SUMMARY_ID,
    DECISION_X_AXIS_ID,
)
from ..settings import (
    DECISION_SCENARIO_IDS,
    DECISION_X_AXIS_LABELS,
    DEFAULT_DECISION_SCENARIO,
    DEFAULT_DECISION_X_AXIS,
    VISUALIZATION_RELEASE_ID,
)


PAGE_MODULE = "llm_xai_dashboard.decision"
_DECISION_PREFIXES = ("decision.",)


def register_page() -> None:
    if PAGE_MODULE not in dash.page_registry:
        dash.register_page(
            PAGE_MODULE,
            path="/decision",
            name="Decision",
            title="Decision Studio · LLM-XAI",
            description="Certified deployment scenarios and exploratory What-if analysis.",
            order=3,
            layout=layout,
        )


def _locale_tag(locale: object) -> str:
    return "vi-VN" if normalize_locale(locale) == "vi" else "en-US"


def _percent_formatter(locale: object) -> dict[str, str]:
    return {
        "function": (
            "params.value == null ? '' : "
            f"new Intl.NumberFormat('{_locale_tag(locale)}', "
            "{style:'percent',minimumFractionDigits:1,maximumFractionDigits:1})"
            ".format(Number(params.value))"
        )
    }


def _number_formatter(locale: object, digits: int = 3) -> dict[str, str]:
    return {
        "function": (
            "params.value == null ? '' : "
            f"new Intl.NumberFormat('{_locale_tag(locale)}', "
            f"{{minimumFractionDigits:{digits},maximumFractionDigits:{digits}}})"
            ".format(Number(params.value))"
        )
    }


def _ranking_grid(frame: pd.DataFrame, *, grid_id: str, custom: bool = False, locale: object = DEFAULT_LOCALE):
    display = frame.copy()
    display["configuration"] = display["model_label"] + " · " + display["evidence_level"]
    display["pareto_status"] = display["is_pareto_optimal"].map({True: "Efficient", False: "Dominated"})
    if custom:
        display["rank"] = display["custom_rank"]
        display["utility"] = display["custom_utility"]
        display["status"] = display["eligible"].map({True: "Eligible", False: "Ineligible"})
        rank_columns = [
            {"field": "rank", "headerName": "Custom rank", "maxWidth": 105, "filter": False},
        ]
    else:
        display["rank"] = display["scenario_rank"]
        display["utility"] = display["utility_score"]
        display["status"] = display["recommendation_role"].fillna("").replace({"PRIMARY": "Recommended", "ALTERNATIVE": "Alternative"})
        rank_columns = [
            {"field": "rank", "headerName": "Decision rank", "maxWidth": 115, "filter": False},
            {"field": "utility_rank", "headerName": "Utility rank", "maxWidth": 105, "filter": False},
        ]
    columns = [
        *rank_columns,
        {"field": "configuration", "headerName": "Configuration", "minWidth": 190},
        {"field": "utility", "headerName": "Utility", "valueFormatter": _number_formatter(locale, 3), "filter": False},
        {"field": "mean_end_to_end_yield", "headerName": "Mean E2E", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "p10_end_to_end_yield", "headerName": "P10", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "usability_rate", "headerName": "Usability", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "mean_latency_seconds_planned", "headerName": "Latency", "valueFormatter": _number_formatter(locale, 1), "filter": False},
        {"field": "mean_total_token_count_planned", "headerName": "Tokens", "valueFormatter": _number_formatter(locale, 0), "filter": False},
        {"field": "mean_supported_claims_per_1000_tokens", "headerName": "Claims / 1k", "valueFormatter": _number_formatter(locale, 2), "filter": False},
        {"field": "pareto_status", "headerName": "Pareto", "filter": True},
        {"field": "status", "headerName": "Role", "filter": True},
    ]
    return data_grid(
        grid_id=grid_id,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=430,
        page_size=12,
        class_name="decision-data-grid",
        locale=locale,
    )


def _top_ranking_table(frame: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    rows = []
    for row in frame.sort_values("scenario_rank").head(5).itertuples(index=False):
        rows.append(
            html.Tr(
                [
                    html.Td(int(row.scenario_rank)),
                    html.Td(
                        int(row.utility_rank)
                        if pd.notna(row.utility_rank)
                        else "—"
                    ),
                    html.Td(f"{row.model_label} · {row.evidence_level}"),
                    html.Td(f"{row.utility_score:.3f}" if pd.notna(row.utility_score) else "—"),
                    html.Td(f"{row.mean_end_to_end_yield:.1%}"),
                    html.Td(f"{row.p10_end_to_end_yield:.1%}"),
                    html.Td(f"{row.usability_rate:.1%}"),
                    html.Td("Efficient" if row.is_pareto_optimal else "Dominated"),
                ]
            )
        )
    component = html.Div(
        html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Decision rank"),
                            html.Th("Utility rank"),
                            html.Th("Configuration"),
                            html.Th("Utility"),
                            html.Th("Mean E2E"),
                            html.Th("P10"),
                            html.Th("Usability"),
                            html.Th("Pareto"),
                        ]
                    )
                ),
                html.Tbody(rows),
            ]
        ),
        className="decision-top-ranking",
    )
    return localize_component_tree(component, locale, prefixes=_DECISION_PREFIXES)


def comparison_table(frame: pd.DataFrame, option_ids: list[str] | None, locale: object = DEFAULT_LOCALE):
    chosen = list(dict.fromkeys(option_ids or []))[:3]
    selected = frame.loc[frame["option_id"].isin(chosen)].copy()
    if selected.empty:
        return localize_component_tree(html.P("Choose up to three configurations to compare."), locale, prefixes=_DECISION_PREFIXES)
    selected = selected.set_index("option_id").reindex(chosen).dropna(how="all")
    metrics = [
        ("Mean E2E", "mean_end_to_end_yield", ".1%"),
        ("P10 E2E", "p10_end_to_end_yield", ".1%"),
        ("Usability", "usability_rate", ".1%"),
        ("Latency (s)", "mean_latency_seconds_planned", ".1f"),
        ("Total tokens", "mean_total_token_count_planned", ",.0f"),
        ("Supported claims / 1k", "mean_supported_claims_per_1000_tokens", ".2f"),
        ("Decision rank", "scenario_rank", ".0f"),
        ("Utility rank", "utility_rank", ".0f"),
        ("Utility", "utility_score", ".3f"),
    ]
    headers = [html.Th("Metric")]
    for row in selected.itertuples():
        headers.append(html.Th(f"{row.model_label} · {row.evidence_level}"))
    body = []
    for label, field, fmt in metrics:
        cells = [html.Td(label)]
        for _, row in selected.iterrows():
            value = row[field]
            cells.append(html.Td(format(value, fmt) if pd.notna(value) else "—"))
        body.append(html.Tr(cells))
    return localize_component_tree(html.Table([html.Thead(html.Tr(headers)), html.Tbody(body)], className="decision-comparison-table"), locale, prefixes=_DECISION_PREFIXES)


def _certified_tab(repository, data, scenario_id: str, x_metric: str, locale: object = DEFAULT_LOCALE):
    scenario = next(item for item in data.scenarios if item.scenario_id == scenario_id)
    ranking = repository.scenario_ranking(scenario_id)
    recommendations = repository.scenario_recommendations(scenario_id)
    primary = recommendations.loc[recommendations["recommendation_role"] == "PRIMARY"].iloc[0]
    alternatives = recommendations.loc[recommendations["recommendation_role"] == "ALTERNATIVE"]
    alternative_id = str(alternatives.iloc[0]["option_id"]) if not alternatives.empty else None
    profile = repository.scenario_contribution_profile(scenario_id, str(primary["option_id"]))
    figure = build_tradeoff_map(
        ranking,
        x_metric=x_metric,
        recommended_option_id=str(primary["option_id"]),
        alternative_option_id=alternative_id,
    )
    return html.Div(
        [
            html.Section(
                [
                    scenario_selector(data.scenarios, selected=scenario_id, component_id=DECISION_SCENARIO_ID, locale=locale),
                    html.P(scenario.description, id=DECISION_SCENARIO_DESCRIPTION_ID, className="decision-scenario-description"),
                ],
                className="decision-scenario-block",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(),
                                    dmc.SegmentedControl(
                                        id=DECISION_X_AXIS_ID,
                                        value=x_metric,
                                        data=[{"value": key, "label": label} for key, label in DECISION_X_AXIS_LABELS.items()],
                                        className="decision-axis-control",
                                    ),
                                ],
                                className="decision-controls-row",
                            ),
                            chart_card(
                                graph_id=DECISION_TRADEOFF_ID,
                                title="Quality–efficiency trade-offs",
                                subtitle="Observed performance and deployment proxies across 18 configurations",
                                figure=figure,
                                figure_id=FIG_DECISION_TRADEOFF_MAP,
                                source="18 certified configurations",
                                metric="Quality–efficiency comparison",
                                denominator="18 model–evidence options",
                                release=VISUALIZATION_RELEASE_ID,
                                locale=locale,
                            ),
                        ]
                    ),
                    html.Div(recommendation_panel(recommendations, scenario_label=scenario.label, locale=locale), id=DECISION_RECOMMENDATION_ID),
                ],
                className="decision-hero-grid",
            ),
            html.Section(
                [
                    chart_card(
                        graph_id=DECISION_CONTRIBUTION_ID,
                        title="Why this configuration is preferred",
                        subtitle="Normalized criterion values multiplied by certified scenario weights",
                        figure=build_criterion_contribution_profile(profile),
                        figure_id=FIG_DECISION_CRITERION_CONTRIBUTIONS,
                        source="Certified scenario contributions",
                        metric="Weighted criterion contribution",
                        denominator="Primary recommended option",
                        release=VISUALIZATION_RELEASE_ID,
                        locale=locale,
                    ),
                    html.Div(contribution_summary(profile, locale), id=DECISION_CONTRIBUTION_SUMMARY_ID),
                ],
                className="decision-contribution-section",
            ),
            html.Section(
                [
                    html.Div([html.H2("Top certified decision ranks", className="effectiveness-section__title"), html.Button("Compare configurations", id=DECISION_COMPARISON_OPEN_ID, className="page-export-button decision-action-button", type="button")], className="decision-controls-row"),
                    html.P(
                        "Decision rank places eligible, scored Pareto-efficient options first and then orders them by utility. Utility rank shows the direct descending utility order.",
                        className="decision-ranking-rule",
                    ),
                    html.Div(_top_ranking_table(ranking, locale), id=DECISION_TOP_RANKING_ID),
                    html.Details([html.Summary("View all 18 ranked configurations"), html.Div(_ranking_grid(ranking, grid_id=DECISION_FULL_RANKING_GRID_ID, locale=locale), className="decision-details__body")], className="decision-details"),
                ],
                className="decision-ranking-section",
            ),
            decision_boundaries(locale),
        ],
        className="decision-certified-tab",
    )


def _what_if_tab(repository, data, initial_weights: dict[str, float], locale: object = DEFAULT_LOCALE):
    balanced = repository.scenario_ranking(DEFAULT_DECISION_SCENARIO)
    certified = balanced.loc[balanced["is_primary_recommendation"]].iloc[0]
    result = repository.custom_what_if(initial_weights)
    custom = None
    if result.recommended_option_id:
        custom = result.ranking.loc[
            result.ranking["option_id"] == result.recommended_option_id
        ].iloc[0]
    option_id = result.recommended_option_id or str(certified["option_id"])
    certified_profile = repository.scenario_contribution_profile(
        DEFAULT_DECISION_SCENARIO,
        option_id,
    )
    custom_profile = (
        result.contributions.loc[result.contributions["option_id"] == option_id]
        if not result.contributions.empty
        else certified_profile.assign(custom_weight=0.0, custom_contribution=0.0)
    )
    query = "&".join(f"w_{key}={value:g}" for key, value in initial_weights.items())

    return html.Div(
        [
            what_if_warning(locale),
            html.Div(
                [
                    html.Div(
                        certified_custom_recommendation_panel(
                            certified,
                            custom,
                            certified_label="Balanced",
                            locale=locale,
                        ),
                        id=DECISION_WHAT_IF_PANEL_ID,
                        className="decision-what-if-recommendation",
                    ),
                    html.Section(
                        [
                            html.H2(
                                "Largest ranking changes",
                                className="effectiveness-section__title",
                            ),
                            html.Div(
                                rank_change_summary(balanced, result.ranking, locale),
                                id=DECISION_WHAT_IF_RANK_SUMMARY_ID,
                            ),
                        ],
                        className="decision-ranking-section decision-rank-change-section",
                    ),
                ],
                className="decision-what-if-overview-grid",
            ),
            chart_card(
                graph_id=DECISION_WHAT_IF_COMPARISON_ID,
                title="How custom priorities change the utility profile",
                subtitle=(
                    "Certified Balanced contributions versus user-specified "
                    "contributions"
                ),
                figure=build_certified_custom_contribution_comparison(
                    certified_profile,
                    custom_profile,
                ),
                figure_id=FIG_DECISION_WHAT_IF_CONTRIBUTION_COMPARISON,
                source="Balanced normalized criterion values + custom weights",
                metric="Contribution comparison",
                denominator="Custom recommended option",
                release=VISUALIZATION_RELEASE_ID,
                locale=locale,
                class_name="decision-what-if-comparison-card",
            ),
            html.Details(
                [
                    html.Summary("View full custom ranking"),
                    html.Div(
                        _ranking_grid(
                            result.ranking,
                            grid_id=DECISION_WHAT_IF_GRID_ID,
                            custom=True,
                            locale=locale,
                        ),
                        className="decision-details__body",
                    ),
                ],
                className="decision-details decision-custom-ranking-details",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2(
                                "Adjust What-if priorities",
                                className="effectiveness-section__title",
                            ),
                            html.P(
                                "These controls update only the exploratory "
                                "results above. Certified scenarios remain unchanged.",
                                className="decision-weight-editor-intro",
                            ),
                        ],
                        className="decision-weight-editor-heading",
                    ),
                    weight_editor(data.criteria, values=initial_weights, locale=locale),
                    html.Div(
                        [
                            html.Button(
                                "Reset to Balanced",
                                id=DECISION_RESET_WEIGHTS_ID,
                                className="page-export-button decision-action-button",
                                type="button",
                            ),
                            html.Button(
                                "Use equal weights",
                                id=DECISION_EQUAL_WEIGHTS_ID,
                                className="page-export-button decision-action-button",
                                type="button",
                            ),
                            dcc.Clipboard(
                                id=DECISION_CLIPBOARD_ID,
                                content=f"/decision?tab=what-if&{query}",
                                title="Copy What-if link",
                                className=(
                                    "page-export-button decision-action-button "
                                    "decision-copy-button"
                                ),
                            ),
                        ],
                        className="decision-weight-actions",
                    ),
                    html.P(
                        "Unavailable criteria — monetary cost, human trust, "
                        "naturalness and stochastic stability — are excluded "
                        "because the certified study does not support ranking them.",
                        className="decision-boundary-copy",
                    ),
                ],
                className=(
                    "decision-weight-editor-panel "
                    "decision-weight-editor-panel--bottom"
                ),
            ),
        ],
        className="decision-what-if-tab",
    )


def layout(tab: str | None = None, scenario: str | None = None, x: str | None = None, locale: object = DEFAULT_LOCALE, **kwargs: object):
    repository = get_dashboard_repository()
    data = repository.decision_data()
    selected_scenario = scenario if scenario in DECISION_SCENARIO_IDS else DEFAULT_DECISION_SCENARIO
    selected_x = x if x in DECISION_X_AXIS_LABELS else DEFAULT_DECISION_X_AXIS
    selected_tab = tab if tab in {"certified", "what-if"} else "certified"
    initial_weights = {
        item.criterion_id: float(kwargs.get(f"w_{item.criterion_id}", item.default_weight * 100))
        for item in data.criteria
    }
    default_comparison_options = repository.scenario_recommendations(selected_scenario)["option_id"].head(2).tolist()
    requested_comparison = kwargs.get("comparison_options")
    valid_option_ids = set(repository.scenario_ranking(selected_scenario)["option_id"].astype(str))
    comparison_options = (
        [str(value) for value in requested_comparison if str(value) in valid_option_ids][:3]
        if isinstance(requested_comparison, (list, tuple))
        else default_comparison_options
    )
    comparison_open = bool(kwargs.get("comparison_open", False))
    page = html.Main(
        [
            page_header(
                title="Decision Studio",
                subtitle="Compare certified deployment scenarios and explore how priorities change the preferred model–evidence configuration.",
                endpoint="RQ4 deployment trade-offs",
                inference_unit="Certified scenario" if selected_tab == "certified" else "User-specified what-if",
                endpoint_label="Research question",
                inference_label="Decision mode",
                locale=locale,
            ),
            html.Div([html.Span("18 configurations · 5 certified scenarios · quality, reliability and efficiency trade-offs"), html.Button("Export decision view", id=DECISION_EXPORT_ID, className="page-export-button decision-action-button", type="button")], className="effectiveness-context"),
            dcc.Download(id=DECISION_DOWNLOAD_ID),
            dcc.Tabs(
                id=DECISION_TABS_ID,
                value=selected_tab,
                className="effectiveness-tabs dashboard-tabs",
                parent_className="effectiveness-tabs__parent",
                children=[
                    dcc.Tab(label="Certified scenarios", value="certified", className="tab", selected_className="tab--selected", children=_certified_tab(repository, data, selected_scenario, selected_x, locale)),
                    dcc.Tab(label="What-if studio", value="what-if", className="tab", selected_className="tab--selected", children=_what_if_tab(repository, data, initial_weights, locale)),
                ],
            ),
            dmc.Drawer(
                id=DECISION_COMPARISON_DRAWER_ID,
                title="Compare configurations",
                opened=comparison_open,
                position="right",
                size="xl",
                children=[
                    dcc.Dropdown(id=DECISION_COMPARISON_OPTIONS_ID, options=[{"label": f"{row.model_label} · {row.evidence_level}", "value": row.option_id} for row in repository.scenario_ranking(selected_scenario).itertuples()], value=comparison_options, multi=True, clearable=True),
                    html.Div(comparison_table(repository.scenario_ranking(selected_scenario), comparison_options, locale), id=DECISION_COMPARISON_TABLE_ID, className="decision-comparison-table-wrap"),
                    html.Button("Close", id=DECISION_COMPARISON_CLOSE_ID, className="page-export-button decision-action-button", type="button"),
                ],
            ),
        ],
        id=DECISION_PAGE_ID,
        className="research-page decision-page",
        **{"data-rq": "RQ4", "data-decision-mode": selected_tab},
    )
    return localize_component_tree(page, locale, prefixes=_DECISION_PREFIXES)
