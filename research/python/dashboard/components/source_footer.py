"""Small source and denominator footer shared by analytical cards."""

from __future__ import annotations

from dash import html

from ..i18n import DEFAULT_LOCALE, normalize_locale, t


def source_footer(
    *,
    source: str,
    metric: str,
    denominator: str,
    release: str,
    locale: object = DEFAULT_LOCALE,
):
    """Render traceability metadata without dominating the visual."""

    resolved_locale = normalize_locale(locale)
    return html.Footer(
        [
            html.Span(f'{t(resolved_locale, "shared.source")}: {source}'),
            html.Span("·", **{"aria-hidden": "true"}),
            html.Span(f'{t(resolved_locale, "shared.metric")}: {metric}'),
            html.Span("·", **{"aria-hidden": "true"}),
            html.Span(
                f'{t(resolved_locale, "shared.denominator")}: {denominator}'
            ),
            html.Span("·", **{"aria-hidden": "true"}),
            html.Span(f'{t(resolved_locale, "shared.release")}: {release}'),
        ],
        className="source-footer",
    )
