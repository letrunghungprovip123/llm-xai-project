"""AppShell state, persisted locale and methodology drawer callbacks."""

from __future__ import annotations

from dash import Input, Output, State, ctx, no_update

from ..components.app_shell import header_content, methods_drawer_content
from ..components.navigation import dashboard_navigation
from ..components.release_badge import release_strip
from ..data.contracts import ReleaseMetadata
from ..i18n import document_metadata, locale_from_trigger, normalize_locale, t
from ..ids import (
    APP_DOCUMENT_METADATA_ID,
    APP_DOCUMENT_STATUS_ID,
    APP_HEADER_CONTENT_ID,
    APP_LOCALE_EN_ID,
    APP_LOCALE_STATUS_ID,
    APP_LOCALE_STORE_ID,
    APP_LOCALE_VI_ID,
    APP_LOCATION_ID,
    APP_METHODS_DRAWER_CLOSE_ID,
    APP_METHODS_DRAWER_CONTENT_ID,
    APP_METHODS_DRAWER_ID,
    APP_METHODS_DRAWER_OPEN_ID,
    APP_NAVBAR_BURGER_ID,
    APP_NAVIGATION_CONTENT_ID,
    APP_RELEASE_STRIP_ID,
    APP_SHELL_ID,
)


def _has_user_click(triggered_id: object, control_id: str, n_clicks: object) -> bool:
    """Return true only for an actual Dash click, never component insertion."""

    return triggered_id == control_id and type(n_clicks) is int and n_clicks > 0


def _methods_drawer_state(
    triggered_id: object,
    open_clicks: object,
    close_clicks: object,
    opened: object,
) -> bool:
    """Resolve drawer state without treating localized subtree rebuilds as clicks."""

    if _has_user_click(triggered_id, APP_METHODS_DRAWER_OPEN_ID, open_clicks):
        return True
    if _has_user_click(triggered_id, APP_METHODS_DRAWER_CLOSE_ID, close_clicks):
        return False
    return bool(opened)


def register_global_callbacks(app, release: ReleaseMetadata) -> None:
    @app.callback(
        Output(APP_LOCALE_STORE_ID, "data"),
        Input(APP_LOCALE_VI_ID, "n_clicks"),
        Input(APP_LOCALE_EN_ID, "n_clicks"),
        State(APP_LOCALE_STORE_ID, "data"),
        prevent_initial_call=True,
    )
    def update_locale(vi_clicks, en_clicks, current):
        triggered_id = ctx.triggered_id
        # The localized header is rebuilt whenever the locale store changes. Dash can
        # report a newly inserted button as the trigger with ``n_clicks=None``.
        # Accept only a real click so rendering cannot bounce the persisted locale.
        if not (
            _has_user_click(triggered_id, APP_LOCALE_VI_ID, vi_clicks)
            or _has_user_click(triggered_id, APP_LOCALE_EN_ID, en_clicks)
        ):
            return no_update

        resolved = locale_from_trigger(
            triggered_id,
            current,
            vietnamese_control_id=APP_LOCALE_VI_ID,
            english_control_id=APP_LOCALE_EN_ID,
        )
        return resolved if resolved != normalize_locale(current) else no_update

    app.clientside_callback(
        """
        function(locale) {
            if (!window.dash_clientside || !window.dash_clientside.llm_xai) {
                return "locale-client-missing";
            }
            return window.dash_clientside.llm_xai.applyLocaleState(locale);
        }
        """,
        Output(APP_LOCALE_STATUS_ID, "children"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )

    @app.callback(
        Output(APP_HEADER_CONTENT_ID, "children"),
        Output(APP_NAVIGATION_CONTENT_ID, "children"),
        Output(APP_RELEASE_STRIP_ID, "children"),
        Output(APP_METHODS_DRAWER_CONTENT_ID, "children"),
        Output(APP_METHODS_DRAWER_ID, "title"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def render_localized_shell(locale):
        resolved = normalize_locale(locale)
        return (
            header_content(release, resolved),
            dashboard_navigation(resolved),
            release_strip(release, resolved),
            methods_drawer_content(release, resolved),
            t(resolved, "app.methodology_title"),
        )

    @app.callback(
        Output(APP_DOCUMENT_METADATA_ID, "data"),
        Input(APP_LOCALE_STORE_ID, "data"),
        Input(APP_LOCATION_ID, "pathname"),
    )
    def update_document_metadata(locale, pathname):
        return document_metadata(locale, pathname).to_dict()

    app.clientside_callback(
        """
        function(metadata) {
            if (!window.dash_clientside || !window.dash_clientside.llm_xai) {
                return "metadata-client-missing";
            }
            return window.dash_clientside.llm_xai.applyDocumentMetadata(metadata);
        }
        """,
        Output(APP_DOCUMENT_STATUS_ID, "children"),
        Input(APP_DOCUMENT_METADATA_ID, "data"),
    )

    @app.callback(
        Output(APP_SHELL_ID, "navbar"),
        Input(APP_NAVBAR_BURGER_ID, "opened"),
        State(APP_SHELL_ID, "navbar"),
    )
    def navbar_is_open(opened, navbar):
        updated = dict(navbar or {})
        updated["collapsed"] = {"mobile": not bool(opened)}
        return updated

    @app.callback(
        Output(APP_METHODS_DRAWER_ID, "opened"),
        Input(APP_METHODS_DRAWER_OPEN_ID, "n_clicks"),
        Input(APP_METHODS_DRAWER_CLOSE_ID, "n_clicks"),
        State(APP_METHODS_DRAWER_ID, "opened"),
        prevent_initial_call=True,
    )
    def toggle_methods_drawer(open_clicks, close_clicks, opened):
        return _methods_drawer_state(
            ctx.triggered_id,
            open_clicks,
            close_clicks,
            opened,
        )
