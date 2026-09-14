"""Accessible loading placeholder."""

from __future__ import annotations

from dash import html

from ..i18n import DEFAULT_LOCALE, normalize_locale, t


def loading_state(
    label: str | None = None,
    *,
    locale: object = DEFAULT_LOCALE,
):
    resolved_locale = normalize_locale(locale)
    resolved_label = label or t(resolved_locale, "shared.loading_certified_data")
    return html.Div(
        [html.Span(className="loading-state__spinner"), html.Span(resolved_label)],
        className="loading-state",
        role="status",
    )
