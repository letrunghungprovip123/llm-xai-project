"""Global AppShell shared by all seven official dashboard pages."""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from ..data.contracts import ReleaseMetadata
from ..i18n import (
    DEFAULT_LOCALE,
    locale_control_state,
    normalize_locale,
    t,
)
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
    APP_NAVBAR_ID,
    APP_NAVIGATION_CONTENT_ID,
    APP_RELEASE_STRIP_ID,
    APP_SHELL_ID,
    MANTINE_PROVIDER_ID,
    OVERVIEW_DOWNLOAD_ID,
    OVERVIEW_EXPORT_ID,
)
from ..theme import DMC_THEME
from .navigation import dashboard_navigation
from .release_badge import release_badge, release_strip


def _locale_switch(locale: object):
    resolved_locale = normalize_locale(locale)
    vi_state = locale_control_state(resolved_locale, "vi")
    en_state = locale_control_state(resolved_locale, "en")
    return html.Div(
        [
            html.Button(
                "VI",
                id=APP_LOCALE_VI_ID,
                type="button",
                className=vi_state.class_name,
                **{
                    "aria-label": t(resolved_locale, "navigation.switch_to_vietnamese"),
                    "aria-pressed": vi_state.aria_pressed,
                    "data-locale-target": "vi",
                },
            ),
            html.Button(
                "EN",
                id=APP_LOCALE_EN_ID,
                type="button",
                className=en_state.class_name,
                **{
                    "aria-label": t(resolved_locale, "navigation.switch_to_english"),
                    "aria-pressed": en_state.aria_pressed,
                    "data-locale-target": "en",
                },
            ),
        ],
        className="locale-switch",
        role="group",
        **{"aria-label": t(resolved_locale, "navigation.language")},
    )


def header_content(release: ReleaseMetadata, locale: object = DEFAULT_LOCALE):
    resolved_locale = normalize_locale(locale)
    return dmc.Group(
        [
            dmc.Group(
                [
                    dmc.Burger(
                        id=APP_NAVBAR_BURGER_ID,
                        opened=False,
                        size="sm",
                        hiddenFrom="md",
                        **{"aria-label": t(resolved_locale, "app.navigation_toggle")},
                    ),
                    html.Div(
                        [
                            html.Div(
                                t(resolved_locale, "app.title"),
                                className="app-brand__title",
                            ),
                            html.Div(
                                t(resolved_locale, "app.subtitle"),
                                className="app-brand__subtitle",
                            ),
                        ],
                        className="app-brand",
                    ),
                ],
                gap="sm",
                wrap="nowrap",
            ),
            dmc.Group(
                [
                    release_badge(release, resolved_locale),
                    _locale_switch(resolved_locale),
                    dmc.Tooltip(
                        dmc.ActionIcon(
                            DashIconify(
                                icon="solar:download-minimalistic-linear", width=19
                            ),
                            id=OVERVIEW_EXPORT_ID,
                            variant="subtle",
                            color="gray",
                            size="lg",
                            **{
                                "aria-label": t(
                                    resolved_locale, "app.export_overview_aria"
                                )
                            },
                        ),
                        label=t(resolved_locale, "app.export_overview"),
                        position="bottom",
                    ),
                    dmc.Tooltip(
                        dmc.ActionIcon(
                            DashIconify(icon="solar:info-circle-linear", width=19),
                            id=APP_METHODS_DRAWER_OPEN_ID,
                            variant="subtle",
                            color="gray",
                            size="lg",
                            **{
                                "aria-label": t(
                                    resolved_locale, "app.methodology_open_aria"
                                )
                            },
                        ),
                        label=t(resolved_locale, "app.methodology_open"),
                        position="bottom",
                    ),
                    dmc.Tooltip(
                        dmc.ColorSchemeToggle(
                            lightIcon=DashIconify(icon="radix-icons:sun", width=18),
                            darkIcon=DashIconify(icon="radix-icons:moon", width=18),
                            color="yellow",
                            variant="subtle",
                            size="lg",
                            **{"aria-label": t(resolved_locale, "app.color_scheme")},
                        ),
                        label=t(resolved_locale, "app.color_scheme"),
                        position="bottom",
                    ),
                ],
                gap=4,
                wrap="nowrap",
                className="app-header__actions",
            ),
        ],
        justify="space-between",
        h="100%",
        px="md",
        wrap="nowrap",
    )


def _header(release: ReleaseMetadata, locale: object = DEFAULT_LOCALE):
    return dmc.AppShellHeader(
        html.Div(
            header_content(release, locale),
            id=APP_HEADER_CONTENT_ID,
            className="app-header__content",
        ),
        className="app-header",
    )


def methods_drawer_content(
    release: ReleaseMetadata,
    locale: object = DEFAULT_LOCALE,
):
    resolved_locale = normalize_locale(locale)
    return dmc.Stack(
        [
            dmc.Text(
                t(resolved_locale, "app.methodology_primary_contract"),
                fw=700,
                size="sm",
            ),
            dmc.Text(
                t(resolved_locale, "app.methodology_primary_detail"),
                size="sm",
                c="dimmed",
            ),
            dmc.Divider(),
            dmc.Text(
                t(resolved_locale, "app.methodology_inference_unit"),
                fw=700,
                size="sm",
            ),
            dmc.Text(
                t(resolved_locale, "app.methodology_inference_detail"),
                size="sm",
                c="dimmed",
            ),
            dmc.Divider(),
            dmc.Text(
                t(resolved_locale, "app.methodology_template_reference"),
                fw=700,
                size="sm",
            ),
            dmc.Text(
                t(resolved_locale, "app.methodology_template_detail"),
                size="sm",
                c="dimmed",
            ),
            dmc.Divider(),
            dmc.Text(
                t(resolved_locale, "app.methodology_boundary"),
                fw=700,
                size="sm",
            ),
            dmc.Text(
                t(resolved_locale, "app.methodology_boundary_detail"),
                size="sm",
                c="dimmed",
            ),
            dmc.Anchor(
                t(resolved_locale, "app.methodology_open_full"),
                href="/methods",
                size="sm",
            ),
            dmc.Code(
                f"{release.analytical_release_id} · "
                f"{release.visualization_release_id} · "
                f"{release.short_commit}",
                block=True,
            ),
            dmc.Button(
                t(resolved_locale, "app.methodology_close"),
                id=APP_METHODS_DRAWER_CLOSE_ID,
                variant="light",
                fullWidth=True,
            ),
        ],
        gap="sm",
    )


def _methods_drawer(release: ReleaseMetadata, locale: object = DEFAULT_LOCALE):
    resolved_locale = normalize_locale(locale)
    return dmc.Drawer(
        html.Div(
            methods_drawer_content(release, resolved_locale),
            id=APP_METHODS_DRAWER_CONTENT_ID,
        ),
        id=APP_METHODS_DRAWER_ID,
        title=t(resolved_locale, "app.methodology_title"),
        opened=False,
        position="right",
        size="md",
        overlayProps={"backgroundOpacity": 0.35, "blur": 2},
    )


def build_app_shell(release: ReleaseMetadata):
    """Build the global shell without loading or recalculating page data."""

    locale = DEFAULT_LOCALE
    shell = dmc.AppShell(
        [
            _header(release, locale),
            dmc.AppShellNavbar(
                html.Div(
                    dashboard_navigation(locale),
                    id=APP_NAVIGATION_CONTENT_ID,
                ),
                id=APP_NAVBAR_ID,
                p="sm",
                className="app-navbar",
            ),
            dmc.AppShellMain(
                [
                    html.Div(
                        release_strip(release, locale),
                        id=APP_RELEASE_STRIP_ID,
                    ),
                    dash.page_container,
                ],
                className="app-main",
            ),
        ],
        id=APP_SHELL_ID,
        header={"height": 56},
        navbar={
            "width": 184,
            "breakpoint": "md",
            "collapsed": {"mobile": True},
        },
        padding=0,
    )

    return dmc.MantineProvider(
        [
            dcc.Location(id=APP_LOCATION_ID, refresh="callback-nav"),
            dcc.Store(
                id=APP_LOCALE_STORE_ID,
                storage_type="local",
                data=DEFAULT_LOCALE,
            ),
            dcc.Store(id=APP_DOCUMENT_METADATA_ID, storage_type="memory"),
            html.Div(id=APP_LOCALE_STATUS_ID, hidden=True),
            html.Div(id=APP_DOCUMENT_STATUS_ID, hidden=True),
            dcc.Download(id=OVERVIEW_DOWNLOAD_ID),
            shell,
            _methods_drawer(release, locale),
        ],
        id=MANTINE_PROVIDER_ID,
        theme=DMC_THEME,
        defaultColorScheme="light",
    )


__all__ = [
    "build_app_shell",
    "header_content",
    "methods_drawer_content",
]
