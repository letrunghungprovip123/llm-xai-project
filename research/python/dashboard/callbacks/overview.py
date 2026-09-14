"""Page-1 localization, drill-through and certified export callbacks."""

from __future__ import annotations

from urllib.parse import urlencode

from dash import Input, Output, State, ctx, dcc, no_update

from ..export.static_figures import build_overview_export_archive
from ..ids import (
    APP_LOCATION_ID,
    APP_LOCALE_STORE_ID,
    OVERVIEW_CONTENT_ID,
    OVERVIEW_DOWNLOAD_ID,
    OVERVIEW_EXPORT_ID,
    OVERVIEW_HEATMAP_ID,
    OVERVIEW_PROFILE_ID,
)
from ..pages.overview import build_overview_children


def navigation_target_from_click(
    *,
    triggered_id: str | None,
    heatmap_click: dict | None,
    profile_click: dict | None,
) -> str | None:
    """Convert Plotly customdata into an Effectiveness deep link."""

    click = heatmap_click if triggered_id == OVERVIEW_HEATMAP_ID else profile_click
    if not click:
        return None
    points = click.get("points")
    if not isinstance(points, list) or not points:
        return None
    customdata = points[0].get("customdata")
    if not isinstance(customdata, (list, tuple)):
        return None

    if triggered_id == OVERVIEW_HEATMAP_ID:
        if len(customdata) < 3:
            return None
        model_id = str(customdata[0])
        evidence_level = str(customdata[2])
    elif triggered_id == OVERVIEW_PROFILE_ID:
        if len(customdata) < 2:
            return None
        model_id = str(customdata[0])
        evidence_level = str(customdata[1])
    else:
        return None

    return "/effectiveness?" + urlencode(
        {"model": model_id, "evidence": evidence_level}
    )


def register_overview_callbacks(app) -> None:
    @app.callback(
        Output(OVERVIEW_CONTENT_ID, "children"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def render_overview_locale(locale):
        return build_overview_children(locale)

    @app.callback(
        Output(APP_LOCATION_ID, "href"),
        Input(OVERVIEW_HEATMAP_ID, "clickData"),
        Input(OVERVIEW_PROFILE_ID, "clickData"),
        prevent_initial_call=True,
    )
    def navigate_to_effectiveness(heatmap_click, profile_click):
        target = navigation_target_from_click(
            triggered_id=ctx.triggered_id,
            heatmap_click=heatmap_click,
            profile_click=profile_click,
        )
        return target if target is not None else no_update

    @app.callback(
        Output(OVERVIEW_DOWNLOAD_ID, "data"),
        Input(OVERVIEW_EXPORT_ID, "n_clicks"),
        State(APP_LOCALE_STORE_ID, "data"),
        prevent_initial_call=True,
    )
    def download_overview_bundle(n_clicks, locale):
        # Header is rebuilt when locale changes. Only a real user click may
        # initiate a browser download.
        if type(n_clicks) is not int or n_clicks <= 0:
            return no_update

        payload = build_overview_export_archive(locale=locale)
        return dcc.send_bytes(
            lambda buffer: buffer.write(payload),
            "LLM_XAI_Executive_Overview_certified_figures.zip",
        )
