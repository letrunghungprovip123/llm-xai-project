"""Official LLM–XAI research dashboard entrypoint.

The internal module name is retained for compatibility with the certified
multi-dataset data boundary; product UI intentionally exposes no version label.
"""
from __future__ import annotations

import os

import dash_mantine_components as dmc
from dash import Dash

from .components.empty_state import blocking_release_state
from .v3.callbacks import (
    register_cases_callbacks,
    register_decision_callbacks,
    register_effectiveness_callbacks,
    register_export_callbacks,
    register_foundation_callbacks,
    register_mechanisms_callbacks,
    register_methods_callbacks,
    register_overview_callbacks,
    register_robustness_callbacks,
)
from .v3.pages import register_pages_v3
from .v3.release_guard import get_v3_release_guard
from .v3.settings import DASHBOARD_ASSETS_DIR, DEFAULT_HOST, DEFAULT_PORT
from .v3.shell import build_v3_shell


def create_app_v3() -> Dash:
    app = Dash(
        __name__,
        title="LLM–XAI Research Dashboard",
        use_pages=True,
        pages_folder="",
        suppress_callback_exceptions=True,
        assets_folder=str(DASHBOARD_ASSETS_DIR),
        update_title="Đang tải…",
    )
    guard = get_v3_release_guard()
    if not guard.ready or guard.release is None:
        app.layout = dmc.MantineProvider(
            blocking_release_state(guard.errors, locale="vi"),
            defaultColorScheme="light",
        )
        return app

    register_pages_v3()
    app.layout = build_v3_shell(guard.release)
    register_foundation_callbacks(app)
    register_overview_callbacks(app)
    register_effectiveness_callbacks(app)
    register_mechanisms_callbacks(app)
    register_decision_callbacks(app)
    register_robustness_callbacks(app)
    register_cases_callbacks(app)
    register_methods_callbacks(app)
    register_export_callbacks(app)
    return app


app = create_app_v3()
server = app.server

if __name__ == "__main__":
    app.run(
        host=os.getenv("DASH_HOST", DEFAULT_HOST),
        port=int(os.getenv("DASH_PORT", str(DEFAULT_PORT))),
        debug=os.getenv("DASH_DEBUG", "0") == "1",
    )
