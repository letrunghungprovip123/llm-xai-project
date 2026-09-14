"""Minimal seven-page sidebar navigation."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from ..i18n import DEFAULT_LOCALE, normalize_locale, t
from ..navigation import NAVIGATION_ITEMS


def dashboard_navigation(locale: object = DEFAULT_LOCALE):
    """Render navigation from stable page IDs and locale catalog keys."""

    resolved_locale = normalize_locale(locale)
    links = [
        dmc.NavLink(
            label=t(resolved_locale, item.label_key),
            href=item.path,
            active="exact",
            leftSection=DashIconify(icon=item.icon, width=19),
            className="dashboard-nav-link",
            variant="light",
            **{"aria-label": t(resolved_locale, item.description_key)},
        )
        for item in NAVIGATION_ITEMS
    ]
    return html.Nav(
        links,
        className="dashboard-navigation",
        **{"aria-label": t(resolved_locale, "app.navigation_aria")},
    )
