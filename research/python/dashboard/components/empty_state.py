"""Fail-closed and no-data presentation states."""

from __future__ import annotations

from collections.abc import Iterable

from dash import html

from ..i18n import DEFAULT_LOCALE, normalize_locale, t


def blocking_release_state(
    errors: Iterable[str],
    *,
    locale: object = DEFAULT_LOCALE,
):
    resolved_locale = normalize_locale(locale)
    items = tuple(str(item) for item in errors)
    return html.Main(
        [
            html.Div("!", className="blocking-state__icon", **{"aria-hidden": "true"}),
            html.H1(t(resolved_locale, "app.blocked_title")),
            html.P(t(resolved_locale, "app.blocked_detail")),
            html.Ul([html.Li(item) for item in items]),
        ],
        className="blocking-state",
        role="alert",
    )


def empty_state(title: str, detail: str):
    return html.Div(
        [html.H2(title), html.P(detail)],
        className="empty-state",
    )
