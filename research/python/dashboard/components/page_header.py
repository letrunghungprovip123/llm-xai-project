"""Research-question-oriented page header."""

from __future__ import annotations

from dash import html

from ..i18n import DEFAULT_LOCALE, normalize_locale, t


def page_header(
    *,
    title: str,
    subtitle: str,
    endpoint: str,
    inference_unit: str,
    endpoint_label: str | None = None,
    inference_label: str | None = None,
    locale: object = DEFAULT_LOCALE,
):
    """Render a concise title and two methodological context badges."""

    resolved_locale = normalize_locale(locale)
    resolved_endpoint_label = endpoint_label or t(
        resolved_locale, "shared.primary_endpoint"
    )
    resolved_inference_label = inference_label or t(
        resolved_locale, "shared.inference_unit"
    )
    return html.Header(
        [
            html.Div(
                [
                    html.H1(title, className="page-header__title"),
                    html.P(subtitle, className="page-header__subtitle"),
                ]
            ),
            html.Div(
                [
                    html.Span(
                        f"{resolved_endpoint_label}: {endpoint}",
                        className="context-badge",
                    ),
                    html.Span(
                        f"{resolved_inference_label}: {inference_unit}",
                        className="context-badge context-badge--neutral",
                    ),
                ],
                className="page-header__badges",
            ),
        ],
        className="page-header",
    )
