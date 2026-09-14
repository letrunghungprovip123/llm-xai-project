"""Reusable analytical chart container."""

from __future__ import annotations

from dash import dcc, html
import plotly.graph_objects as go

from ..i18n import DEFAULT_LOCALE, normalize_locale, t
from ..theme import PLOTLY_CONFIG
from .source_footer import source_footer


def chart_card(
    *,
    graph_id: str,
    title: str,
    subtitle: str,
    figure: go.Figure,
    figure_id: str,
    source: str,
    metric: str,
    denominator: str,
    release: str,
    class_name: str = "",
    locale: object = DEFAULT_LOCALE,
):
    """Render a chart with title, traceability and export metadata."""

    resolved_locale = normalize_locale(locale)
    resolved_class = "chart-card"
    if class_name:
        resolved_class += f" {class_name}"

    return html.Section(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.H2(title, className="chart-card__title"),
                            html.P(subtitle, className="chart-card__subtitle"),
                        ]
                    ),
                    html.Span(
                        figure_id,
                        className="chart-card__figure-id",
                        title=t(
                            resolved_locale, "shared.stable_export_identifier"
                        ),
                    ),
                ],
                className="chart-card__header",
            ),
            dcc.Graph(
                id=graph_id,
                figure=figure,
                config=PLOTLY_CONFIG,
                responsive=True,
                className="chart-card__graph",
                clear_on_unhover=False,
            ),
            source_footer(
                source=source,
                metric=metric,
                denominator=denominator,
                release=release,
                locale=resolved_locale,
            ),
        ],
        className=resolved_class,
        **{"data-figure-id": figure_id},
    )
