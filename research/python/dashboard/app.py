"""Certified seven-page LLM-XAI research dashboard entry point."""

from __future__ import annotations

import os

import dash_mantine_components as dmc
from dash import Dash

from .callbacks import register_callbacks
from .components.app_shell import build_app_shell
from .components.empty_state import blocking_release_state
from .i18n import DEFAULT_LOCALE, t
from .data.release_guard import get_visualization_release_guard
from .pages import register_pages
from .settings import (
    DASHBOARD_ASSETS_DIR,
    DEFAULT_HOST,
    DEFAULT_PORT,
)


dmc.pre_render_color_scheme()


def create_app() -> Dash:
    """Create the app only after the certified release guard has run."""

    app = Dash(
        __name__,
        title=t(DEFAULT_LOCALE, "app.title"),
        use_pages=True,
        pages_folder="",
        suppress_callback_exceptions=True,
        assets_folder=str(DASHBOARD_ASSETS_DIR),
        update_title="…",
    )

    guard = get_visualization_release_guard()
    if not guard.ready or guard.release is None:
        app.layout = dmc.MantineProvider(
            blocking_release_state(guard.errors, locale=DEFAULT_LOCALE),
            defaultColorScheme="light",
        )
        return app

    register_pages()
    app.layout = build_app_shell(guard.release)
    register_callbacks(app, guard.release)
    return app


app = create_app()
server = app.server


if __name__ == "__main__":
    app.run(
        host=os.getenv("DASH_HOST", DEFAULT_HOST),
        port=int(os.getenv("DASH_PORT", str(DEFAULT_PORT))),
        debug=os.getenv("DASH_DEBUG", "0") == "1",
    )
