"""Callbacks and pure update helpers for Page 4 — Decision Studio."""

from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from dash import ALL, Input, Output, State, ctx, dcc, no_update
import pandas as pd

from ..components.decision import (
    certified_custom_recommendation_panel,
    contribution_summary,
    rank_change_summary,
    recommendation_panel,
)
from ..data.repository import get_dashboard_repository
from ..export.localization import export_readme
from ..i18n import (
    DEFAULT_LOCALE,
    localize_component_tree,
    localize_plotly_figure,
    localize_records,
    localize_text,
    normalize_locale,
)
from ..figures.decision import (
    build_certified_custom_contribution_comparison,
    build_criterion_contribution_profile,
    build_tradeoff_map,
)
from ..ids import (
    APP_LOCALE_STORE_ID,
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
    DECISION_TABS_ID,
    DECISION_RECOMMENDATION_ID,
    DECISION_RESET_WEIGHTS_ID,
    DECISION_SCENARIO_DESCRIPTION_ID,
    DECISION_SCENARIO_ID,
    DECISION_TOP_RANKING_ID,
    DECISION_TRADEOFF_ID,
    DECISION_WHAT_IF_COMPARISON_ID,
    DECISION_WHAT_IF_GRID_ID,
    DECISION_WHAT_IF_PANEL_ID,
    DECISION_WHAT_IF_RANK_SUMMARY_ID,
    DECISION_X_AXIS_ID,
)
from ..pages.decision import _top_ranking_table, comparison_table, layout as decision_layout
from ..settings import (
    DECISION_SCENARIO_IDS,
    DECISION_X_AXIS_LABELS,
    DEFAULT_DECISION_SCENARIO,
    DEFAULT_DECISION_X_AXIS,
)


def _ranking_rows(frame: pd.DataFrame, *, custom: bool = False, locale: object = DEFAULT_LOCALE) -> list[dict]:
    display = frame.copy()
    display["configuration"] = display["model_label"] + " · " + display["evidence_level"]
    display["pareto_status"] = display["is_pareto_optimal"].map({True: "Efficient", False: "Dominated"})
    if custom:
        display["rank"] = display["custom_rank"]
        display["utility"] = display["custom_utility"]
        display["status"] = display["eligible"].map({True: "Eligible", False: "Ineligible"})
    else:
        display["rank"] = display["scenario_rank"]
        display["utility"] = display["utility_score"]
        display["status"] = display["recommendation_role"].fillna("").replace({"PRIMARY": "Recommended", "ALTERNATIVE": "Alternative"})
    columns = [
        "rank", "configuration", "utility", "mean_end_to_end_yield",
        "p10_end_to_end_yield", "usability_rate",
        "mean_latency_seconds_planned", "mean_total_token_count_planned",
        "mean_supported_claims_per_1000_tokens", "pareto_status", "status",
    ]
    records = display[columns].astype(object).where(pd.notna(display[columns]), None).to_dict("records")
    return localize_records(records, locale, prefixes=("decision.",))


def certified_updates(scenario_id: str, x_metric: str, locale: object = DEFAULT_LOCALE):
    repository = get_dashboard_repository()
    resolved_scenario = scenario_id if scenario_id in DECISION_SCENARIO_IDS else DEFAULT_DECISION_SCENARIO
    resolved_x = x_metric if x_metric in DECISION_X_AXIS_LABELS else DEFAULT_DECISION_X_AXIS
    scenario = next(item for item in repository.decision_scenarios() if item.scenario_id == resolved_scenario)
    ranking = repository.scenario_ranking(resolved_scenario)
    recommendations = repository.scenario_recommendations(resolved_scenario)
    primary = recommendations.loc[recommendations["recommendation_role"] == "PRIMARY"].iloc[0]
    alternatives = recommendations.loc[recommendations["recommendation_role"] == "ALTERNATIVE"]
    alternative_id = str(alternatives.iloc[0]["option_id"]) if not alternatives.empty else None
    profile = repository.scenario_contribution_profile(resolved_scenario, str(primary["option_id"]))
    return (
        localize_text(scenario.description, locale, prefixes=("decision.",)),
        localize_plotly_figure(build_tradeoff_map(ranking, x_metric=resolved_x, recommended_option_id=str(primary["option_id"]), alternative_option_id=alternative_id), locale, prefixes=("decision.",)),
        recommendation_panel(recommendations, scenario_label=scenario.label, locale=locale),
        localize_plotly_figure(build_criterion_contribution_profile(profile), locale, prefixes=("decision.",)),
        contribution_summary(profile, locale),
        _top_ranking_table(ranking, locale),
        _ranking_rows(ranking, locale=locale),
        [{"label": f"{row.model_label} · {row.evidence_level}", "value": row.option_id} for row in ranking.itertuples()],
        recommendations["option_id"].head(2).tolist(),
    )


def custom_updates(raw_weights: dict[str, float], locale: object = DEFAULT_LOCALE):
    repository = get_dashboard_repository()
    result = repository.custom_what_if(raw_weights)
    balanced = repository.scenario_ranking(DEFAULT_DECISION_SCENARIO)
    certified = balanced.loc[balanced["is_primary_recommendation"]].iloc[0]
    custom = None
    if result.recommended_option_id:
        custom = result.ranking.loc[result.ranking["option_id"] == result.recommended_option_id].iloc[0]
    option_id = result.recommended_option_id or str(certified["option_id"])
    certified_profile = repository.scenario_contribution_profile(DEFAULT_DECISION_SCENARIO, option_id)
    custom_profile = result.contributions.loc[result.contributions["option_id"] == option_id] if not result.contributions.empty else certified_profile.assign(custom_weight=0.0, custom_contribution=0.0)
    query = "&".join(f"w_{key}={value:g}" for key, value in raw_weights.items())
    return (
        certified_custom_recommendation_panel(certified, custom, certified_label="Balanced", locale=locale),
        localize_plotly_figure(build_certified_custom_contribution_comparison(certified_profile, custom_profile), locale, prefixes=("decision.",)),
        rank_change_summary(balanced, result.ranking, locale),
        _ranking_rows(result.ranking, custom=True, locale=locale),
        f"/decision?tab=what-if&{query}",
    )


def decision_figures(scenario_id: str = DEFAULT_DECISION_SCENARIO, raw_weights: dict[str, float] | None = None, locale: object = DEFAULT_LOCALE):
    repository = get_dashboard_repository()
    ranking = repository.scenario_ranking(scenario_id)
    recommendations = repository.scenario_recommendations(scenario_id)
    primary = recommendations.loc[recommendations["recommendation_role"] == "PRIMARY"].iloc[0]
    alternatives = recommendations.loc[recommendations["recommendation_role"] == "ALTERNATIVE"]
    alternative_id = str(alternatives.iloc[0]["option_id"]) if not alternatives.empty else None
    profile = repository.scenario_contribution_profile(scenario_id, str(primary["option_id"]))
    defaults = raw_weights or {item.criterion_id: item.default_weight * 100 for item in repository.decision_criteria()}
    result = repository.custom_what_if(defaults)
    custom_option = result.recommended_option_id or str(primary["option_id"])
    certified_custom = repository.scenario_contribution_profile(DEFAULT_DECISION_SCENARIO, custom_option)
    custom_profile = result.contributions.loc[result.contributions["option_id"] == custom_option] if not result.contributions.empty else certified_custom.assign(custom_weight=0.0, custom_contribution=0.0)
    figures = {
        "FIG_DECISION_TRADEOFF_MAP": build_tradeoff_map(ranking, x_metric=DEFAULT_DECISION_X_AXIS, recommended_option_id=str(primary["option_id"]), alternative_option_id=alternative_id),
        "FIG_DECISION_CRITERION_CONTRIBUTIONS": build_criterion_contribution_profile(profile),
        "FIG_DECISION_WHAT_IF_CONTRIBUTION_COMPARISON": build_certified_custom_contribution_comparison(certified_custom, custom_profile),
    }
    return {
        figure_id: localize_plotly_figure(figure, locale, prefixes=("decision.",))
        for figure_id, figure in figures.items()
    }


def build_decision_archive(scenario_id: str, raw_weights: dict[str, float], locale: object = DEFAULT_LOCALE) -> bytes:
    repository = get_dashboard_repository()
    resolved_locale = normalize_locale(locale)
    figures = decision_figures(scenario_id, raw_weights, resolved_locale)
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        manifest = []
        for figure_id, figure in figures.items():
            path = f"figures/json/{figure_id}.json"
            archive.writestr(path, figure.to_json(pretty=True))
            manifest.append({"figure_id": figure_id, "path": path, "metadata": dict(figure.layout.meta)})
        archive.writestr(
            "README.txt",
            export_readme(
                resolved_locale,
                "decision",
                analytical_release=repository.release.analytical_release_id,
                visualization_release=repository.release.visualization_release_id,
            ),
        )
        archive.writestr(
            "manifest.json",
            json.dumps({
                "schema_version": "decision_export_manifest_v1",
                "analytical_release": repository.release.analytical_release_id,
                "visualization_release": repository.release.visualization_release_id,
                "scenario_id": scenario_id,
                "what_if_raw_weights": raw_weights,
                "display_locale": resolved_locale,
                "figures": manifest,
            }, indent=2),
        )
    return buffer.getvalue()


def register_decision_callbacks(app) -> None:
    @app.callback(
        Output(DECISION_PAGE_ID, "children"),
        Input(APP_LOCALE_STORE_ID, "data"),
        State(DECISION_TABS_ID, "value", allow_optional=True),
        State(DECISION_SCENARIO_ID, "value", allow_optional=True),
        State(DECISION_X_AXIS_ID, "value", allow_optional=True),
        State({"type": "decision-weight-slider", "criterion": ALL}, "value"),
        State({"type": "decision-weight-slider", "criterion": ALL}, "id"),
        State(DECISION_COMPARISON_DRAWER_ID, "opened", allow_optional=True),
        State(DECISION_COMPARISON_OPTIONS_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def relocalize_decision_page(
        locale, tab, scenario_id, x_metric, values, slider_ids, comparison_open, comparison_options
    ):
        weights = {
            item["criterion"]: float(value or 0)
            for item, value in zip(slider_ids or [], values or [], strict=False)
        }
        page = decision_layout(
            tab=tab,
            scenario=scenario_id,
            x=x_metric,
            locale=locale,
            comparison_open=bool(comparison_open),
            comparison_options=comparison_options or [],
            **{f"w_{key}": value for key, value in weights.items()},
        )
        return page.children
    @app.callback(
        Output(DECISION_SCENARIO_DESCRIPTION_ID, "children"),
        Output(DECISION_TRADEOFF_ID, "figure"),
        Output(DECISION_RECOMMENDATION_ID, "children"),
        Output(DECISION_CONTRIBUTION_ID, "figure"),
        Output(DECISION_CONTRIBUTION_SUMMARY_ID, "children"),
        Output(DECISION_TOP_RANKING_ID, "children"),
        Output(DECISION_FULL_RANKING_GRID_ID, "rowData"),
        Output(DECISION_COMPARISON_OPTIONS_ID, "options"),
        Output(DECISION_COMPARISON_OPTIONS_ID, "value"),
        Input(DECISION_SCENARIO_ID, "value"),
        Input(DECISION_X_AXIS_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_certified_scenario(scenario_id, x_metric, locale):
        return certified_updates(scenario_id, x_metric, locale)

    @app.callback(
        Output({"type": "decision-weight-value", "criterion": ALL}, "children"),
        Input({"type": "decision-weight-slider", "criterion": ALL}, "value"),
    )
    def update_weight_labels(values):
        return [f"{float(value or 0):.0f}" for value in values]

    @app.callback(
        Output({"type": "decision-weight-slider", "criterion": ALL}, "value"),
        Input(DECISION_RESET_WEIGHTS_ID, "n_clicks"),
        Input(DECISION_EQUAL_WEIGHTS_ID, "n_clicks"),
        State({"type": "decision-weight-slider", "criterion": ALL}, "id"),
        prevent_initial_call=True,
    )
    def set_weight_vector(reset_clicks, equal_clicks, slider_ids):
        repository = get_dashboard_repository()
        defaults = {item.criterion_id: item.default_weight * 100 for item in repository.decision_criteria()}
        if ctx.triggered_id == DECISION_EQUAL_WEIGHTS_ID:
            return [1.0 for _ in slider_ids]
        if ctx.triggered_id == DECISION_RESET_WEIGHTS_ID:
            return [defaults[item["criterion"]] for item in slider_ids]
        return no_update

    @app.callback(
        Output(DECISION_WHAT_IF_PANEL_ID, "children"),
        Output(DECISION_WHAT_IF_COMPARISON_ID, "figure"),
        Output(DECISION_WHAT_IF_RANK_SUMMARY_ID, "children"),
        Output(DECISION_WHAT_IF_GRID_ID, "rowData"),
        Output(DECISION_CLIPBOARD_ID, "content"),
        Input({"type": "decision-weight-slider", "criterion": ALL}, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
        State({"type": "decision-weight-slider", "criterion": ALL}, "id"),
    )
    def update_what_if(values, locale, slider_ids):
        raw = {item["criterion"]: float(value or 0) for item, value in zip(slider_ids, values, strict=False)}
        return custom_updates(raw, locale)

    @app.callback(
        Output(DECISION_COMPARISON_DRAWER_ID, "opened"),
        Input(DECISION_COMPARISON_OPEN_ID, "n_clicks"),
        Input(DECISION_COMPARISON_CLOSE_ID, "n_clicks"),
        State(DECISION_COMPARISON_DRAWER_ID, "opened"),
        prevent_initial_call=True,
    )
    def toggle_comparison(open_clicks, close_clicks, opened):
        if ctx.triggered_id == DECISION_COMPARISON_OPEN_ID:
            return True
        if ctx.triggered_id == DECISION_COMPARISON_CLOSE_ID:
            return False
        return opened

    @app.callback(
        Output(DECISION_COMPARISON_TABLE_ID, "children"),
        Input(DECISION_COMPARISON_OPTIONS_ID, "value"),
        Input(DECISION_SCENARIO_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_comparison(option_ids, scenario_id, locale):
        return comparison_table(get_dashboard_repository().scenario_ranking(scenario_id or DEFAULT_DECISION_SCENARIO), (option_ids or [])[:3], locale)

    @app.callback(
        Output(DECISION_DOWNLOAD_ID, "data"),
        Input(DECISION_EXPORT_ID, "n_clicks"),
        State(DECISION_SCENARIO_ID, "value"),
        State({"type": "decision-weight-slider", "criterion": ALL}, "value"),
        State({"type": "decision-weight-slider", "criterion": ALL}, "id"),
        State(APP_LOCALE_STORE_ID, "data"),
        prevent_initial_call=True,
    )
    def export_decision(n_clicks, scenario_id, values, slider_ids, locale):
        if not n_clicks:
            return no_update
        raw = {item["criterion"]: float(value or 0) for item, value in zip(slider_ids, values, strict=False)}
        payload = build_decision_archive(scenario_id or DEFAULT_DECISION_SCENARIO, raw, locale)
        return dcc.send_bytes(lambda target: target.write(payload), "LLM_XAI_Decision_Studio_view.zip")
