from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from research.python.dashboard.theme import DMC_THEME

from .contracts import VisualizationReleaseV3
from .i18n import vt
from .settings import DATASET_SCOPES, DEFAULT_DATASET_SCOPE, PAGE_ORDER, PAGE_PATHS


SCOPE_STORE = "v3-dataset-scope-store"
LOCALE_STORE = "v3-locale-store"
SCOPE_SELECT = "v3-dataset-scope-select"
# Retained as an internal compatibility identifier only; there is no locale UI.
LOCALE_SELECT = "v3-locale-select"
LOCATION = "v3-location"
PAGE_CONTAINER = "v3-page-container"
EXPORT_BUTTON = "v3-export-current"
EXPORT_DOWNLOAD = "v3-export-download"
NAV_CONTAINER = "v3-nav-container"
APP_TITLE_TEXT = "v3-app-title-text"
RELEASE_TEXT = "v3-release-text"

_PAGE_ICONS = {
    "overview": "solar:widget-5-linear",
    "effectiveness": "solar:chart-2-linear",
    "mechanisms": "solar:layers-minimalistic-linear",
    "decision": "solar:scale-linear",
    "robustness": "solar:shield-check-linear",
    "cases": "solar:case-round-linear",
    "methods": "solar:notebook-bookmark-linear",
}


def navigation_v3(locale: object = "vi"):
    return [
        dmc.NavLink(
            label=vt("vi", key),
            href=PAGE_PATHS[key],
            active="exact",
            leftSection=DashIconify(icon=_PAGE_ICONS[key], width=18),
            className="dashboard-nav-link",
        )
        for key in PAGE_ORDER
    ]


def build_v3_shell(release: VisualizationReleaseV3):
    del release  # Certified identity stays internal; product UI intentionally has no version label.
    scope_data = [
        {"value": "HOME_CREDIT", "label": "Home Credit"},
        {"value": "FREDDIE", "label": "Freddie Mac"},
        {"value": "CROSS_DATASET", "label": "Cross-dataset"},
    ]
    assert tuple(item["value"] for item in scope_data) == DATASET_SCOPES

    return dmc.MantineProvider(
        [
            dcc.Location(id=LOCATION, refresh="callback-nav"),
            dcc.Download(id=EXPORT_DOWNLOAD),
            dcc.Store(id=SCOPE_STORE, data=DEFAULT_DATASET_SCOPE, storage_type="memory"),
            # Fixed Vietnamese product locale. Memory storage prevents an old EN localStorage value
            # from reviving bilingual behavior after the redesign.
            dcc.Store(id=LOCALE_STORE, data="vi", storage_type="memory"),
            dmc.AppShell(
                [
                    dmc.AppShellHeader(
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div("LLM–XAI Research Dashboard", id=APP_TITLE_TEXT, className="research-shell__brand"),
                                        html.Div("Phân tích nghiên cứu multi-dataset", id=RELEASE_TEXT, className="research-shell__subtitle"),
                                    ],
                                    className="research-shell__identity",
                                ),
                                html.Div(
                                    [
                                        dmc.SegmentedControl(
                                            id=SCOPE_SELECT,
                                            value=DEFAULT_DATASET_SCOPE,
                                            data=scope_data,
                                            radius="xl",
                                            size="sm",
                                            className="research-shell__scope",
                                            **{"aria-label": "Phạm vi dataset"},
                                        ),
                                        dmc.Button(
                                            [DashIconify(icon="solar:download-minimalistic-linear", width=17), "Xuất"],
                                            id=EXPORT_BUTTON,
                                            variant="light",
                                            size="sm",
                                            radius="xl",
                                            className="research-shell__export",
                                        ),
                                    ],
                                    className="research-shell__actions",
                                ),
                            ],
                            className="research-shell__header",
                        ),
                        className="app-header research-shell-header",
                    ),
                    dmc.AppShellNavbar(
                        html.Nav(
                            [
                                html.Div("Phân tích", className="research-shell__nav-label"),
                                html.Div(navigation_v3("vi"), id=NAV_CONTAINER),
                                html.Div(
                                    [
                                        html.Span(className="research-shell__cert-dot"),
                                        html.Div(
                                            [
                                                html.Strong("Dữ liệu đã chứng nhận"),
                                                html.Span("Truy xuất từ certified analytical release"),
                                            ]
                                        ),
                                    ],
                                    className="research-shell__cert",
                                ),
                            ],
                            className="research-shell__nav",
                        ),
                        p="md",
                        className="app-navbar",
                    ),
                    dmc.AppShellMain(
                        html.Div(id=PAGE_CONTAINER, children=dash.page_container),
                        className="app-main",
                    ),
                ],
                header={"height": 72},
                navbar={"width": 216, "breakpoint": "md"},
                padding=0,
            ),
        ],
        defaultColorScheme="light",
        theme=DMC_THEME,
    )
