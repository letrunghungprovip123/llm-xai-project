"""Locale-aware presentation components used by Page 2."""

from __future__ import annotations

from dash import html
import pandas as pd

from ..data.contracts import FocusedOption
from ..i18n import (
    DEFAULT_LOCALE,
    evidence_label,
    format_integer,
    format_number,
    format_p_value,
    format_percent,
    normalize_locale,
    t,
)


def _rate(locale: object, value: float) -> str:
    return format_percent(locale, value, decimals=1)


def _number(locale: object, value: float | None, *, digits: int = 1) -> str:
    if value is None:
        return t(normalize_locale(locale), "effectiveness.panel.not_available")
    return format_number(locale, value, decimals=digits)


def operational_interpretation_panel(
    options: pd.DataFrame,
    focused: FocusedOption | None,
    *,
    locale: object = DEFAULT_LOCALE,
):
    """Render either the focused option or a concise localized reading guide."""

    resolved = normalize_locale(locale)
    if focused is None:
        return html.Aside(
            [
                html.H2(
                    t(resolved, "effectiveness.panel.read_title"),
                    className="analysis-panel__title",
                ),
                html.P(
                    t(resolved, "effectiveness.panel.read_upper"),
                    className="analysis-panel__text",
                ),
                html.P(
                    t(resolved, "effectiveness.panel.read_triangle"),
                    className="analysis-panel__text",
                ),
                html.P(
                    t(resolved, "effectiveness.panel.read_robustness"),
                    className="analysis-panel__text analysis-panel__text--emphasis",
                ),
            ],
            className="analysis-panel",
        )

    mean_rank = int(
        options["mean_end_to_end_yield"].rank(method="min", ascending=False).loc[
            options["option_id"] == focused.option_id
        ].iloc[0]
    )
    p10_rank = int(
        options["p10_end_to_end_yield"].rank(method="min", ascending=False).loc[
            options["option_id"] == focused.option_id
        ].iloc[0]
    )
    rows = (
        (t(resolved, "effectiveness.panel.mean_e2e"), _rate(resolved, focused.mean_e2e)),
        (t(resolved, "effectiveness.panel.p10_e2e"), _rate(resolved, focused.p10_e2e)),
        (t(resolved, "effectiveness.panel.median_e2e"), _rate(resolved, focused.median_e2e)),
        (t(resolved, "effectiveness.panel.usability"), _rate(resolved, focused.usability_rate)),
        (
            t(resolved, "effectiveness.panel.planned_usable"),
            f"{format_integer(resolved, focused.planned_count)} / "
            f"{format_integer(resolved, focused.usable_count)}",
        ),
        (
            t(resolved, "effectiveness.panel.unusable"),
            format_integer(resolved, focused.unusable_count),
        ),
        (
            t(resolved, "effectiveness.panel.mean_rank"),
            t(resolved, "effectiveness.panel.rank_of", rank=format_integer(resolved, mean_rank)),
        ),
        (
            t(resolved, "effectiveness.panel.p10_rank"),
            t(resolved, "effectiveness.panel.rank_of", rank=format_integer(resolved, p10_rank)),
        ),
        (
            t(resolved, "effectiveness.panel.mean_latency"),
            t(
                resolved,
                "effectiveness.panel.seconds",
                value=_number(resolved, focused.mean_latency_seconds, digits=1),
            ),
        ),
        (
            t(resolved, "effectiveness.panel.mean_tokens"),
            _number(resolved, focused.mean_total_tokens, digits=0),
        ),
    )
    return html.Aside(
        [
            html.Div(
                t(resolved, "effectiveness.panel.focused"),
                className="analysis-panel__eyebrow",
            ),
            html.H2(
                f"{focused.model_label} · {focused.evidence_level}",
                className="analysis-panel__title",
            ),
            html.P(
                evidence_label(resolved, focused.evidence_level),
                className="analysis-panel__text",
            ),
            html.Dl(
                [
                    html.Div(
                        [html.Dt(label), html.Dd(value)],
                        className="analysis-panel__metric-row",
                    )
                    for label, value in rows
                ],
                className="analysis-panel__metrics",
            ),
        ],
        className="analysis-panel analysis-panel--focused",
    )


def conditional_context_panel(
    summary: pd.DataFrame,
    *,
    metric_label: str,
    locale: object = DEFAULT_LOCALE,
):
    """Explain conditional semantics and the largest operational gap."""

    resolved = normalize_locale(locale)
    largest = summary.sort_values("operational_gap", ascending=False).iloc[0]
    return html.Aside(
        [
            html.H2(
                t(resolved, "effectiveness.panel.conditional_title"),
                className="analysis-panel__title",
            ),
            html.P(
                t(resolved, "effectiveness.panel.conditional_detail"),
                className="analysis-panel__text",
            ),
            html.Div(
                [
                    html.Span(
                        t(resolved, "effectiveness.panel.largest_gap"),
                        className="analysis-panel__eyebrow",
                    ),
                    html.Strong(
                        f"{largest['model_label']} · {largest['evidence_level']}",
                        className="analysis-panel__callout",
                    ),
                    html.Span(
                        t(
                            resolved,
                            "effectiveness.panel.gap_statement",
                            metric=metric_label,
                            gap=format_percent(
                                resolved,
                                float(largest["operational_gap"]),
                                decimals=1,
                            ),
                        ),
                        className="analysis-panel__text",
                    ),
                ],
                className="analysis-panel__callout-block",
            ),
        ],
        className="analysis-panel",
    )


def sensitivity_summary_panel(
    frame: pd.DataFrame,
    *,
    locale: object = DEFAULT_LOCALE,
):
    """Compare primary 36-case and complete-case 27-case conclusions."""

    resolved = normalize_locale(locale)
    labels = {
        "model": t(resolved, "effectiveness.panel.effect_model"),
        "evidence": t(resolved, "effectiveness.panel.effect_evidence"),
        "model:evidence": t(resolved, "effectiveness.panel.effect_interaction"),
    }
    return html.Section(
        [
            html.H2(
                t(resolved, "effectiveness.panel.sensitivity_title"),
                className="analysis-panel__title",
            ),
            html.P(
                t(resolved, "effectiveness.panel.sensitivity_detail"),
                className="analysis-panel__text",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong(labels[str(row.effect)]),
                            html.Span(
                                t(
                                    resolved,
                                    "effectiveness.panel.cases_primary",
                                    p=format_p_value(
                                        resolved,
                                        float(row.primary_p_value),
                                        decimals=3,
                                    ),
                                    eta=format_number(
                                        resolved,
                                        float(row.primary_partial_eta_squared),
                                        decimals=3,
                                        trim_trailing_zeros=False,
                                    ),
                                )
                            ),
                            html.Span(
                                t(
                                    resolved,
                                    "effectiveness.panel.cases_sensitivity",
                                    p=format_p_value(
                                        resolved,
                                        float(row.sensitivity_p_value),
                                        decimals=3,
                                    ),
                                    eta=format_number(
                                        resolved,
                                        float(row.sensitivity_partial_eta_squared),
                                        decimals=3,
                                        trim_trailing_zeros=False,
                                    ),
                                )
                            ),
                            html.Span(
                                t(
                                    resolved,
                                    "effectiveness.panel.stable"
                                    if bool(row.significance_conclusion_stable)
                                    else "effectiveness.panel.changed",
                                ),
                                className=(
                                    "stability-state stability-state--stable"
                                    if bool(row.significance_conclusion_stable)
                                    else "stability-state stability-state--changed"
                                ),
                            ),
                        ],
                        className="sensitivity-row",
                    )
                    for row in frame.itertuples(index=False)
                ],
                className="sensitivity-list",
            ),
        ],
        className="analysis-panel sensitivity-panel",
    )
