"""Compact report-facing KPI card."""

from __future__ import annotations

from dash import html

from ..data.contracts import OverviewKpi
from ..i18n import DEFAULT_LOCALE, normalize_locale, t
from ..ids import kpi_info_id


def metric_card(
    kpi: OverviewKpi,
    *,
    locale: object = DEFAULT_LOCALE,
):
    """Render one certified KPI without recomputing its value."""

    resolved_locale = normalize_locale(locale)
    class_name = "metric-card"
    if kpi.variant != "default":
        class_name += f" metric-card--{kpi.variant}"

    return html.Article(
        [
            html.Div(
                [
                    html.Span(kpi.label, className="metric-card__label"),
                    html.Button(
                        "i",
                        id=kpi_info_id(kpi.metric_id),
                        className="metric-card__info",
                        title=(
                            f"{kpi.tooltip}\n"
                            f'{t(resolved_locale, "shared.denominator")}: '
                            f"{kpi.denominator}\n"
                            f'{t(resolved_locale, "shared.source")}: {kpi.source}'
                        ),
                        type="button",
                        **{
                            "aria-label": t(
                                resolved_locale,
                                "shared.method_note_for",
                                label=kpi.label,
                            )
                        },
                    ),
                ],
                className="metric-card__topline",
            ),
            html.Div(kpi.display_value, className="metric-card__value"),
            html.Div(kpi.subtext or "", className="metric-card__subtext"),
        ],
        className=class_name,
        **{
            "data-metric-id": kpi.metric_id,
            "data-denominator": kpi.denominator,
            "data-source": kpi.source,
        },
    )
