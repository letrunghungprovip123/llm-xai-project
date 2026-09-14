"""Pure Plotly figure factories for Page 7."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from ..i18n import DEFAULT_LOCALE, normalize_locale, t
from ..settings import (
    METHODS_VISIBILITY_TIER_DESCRIPTIONS,
    METHODS_VISIBILITY_TIER_LABELS,
    METHODS_VISIBILITY_TIER_ORDER,
    VISUALIZATION_RELEASE_ID,
)
from .common import apply_research_layout, figure_metadata


FIG_METHODS_VISIBILITY_PROFILE = "FIG-METHODS-01"

_TIER_COLORS = {
    "A_HEADLINE": "#0F766E",
    "B_EXPLANATORY": "#2563EB",
    "C_INTERNAL_VALIDATION": "#667085",
    "D_DISABLED_UNTIL_BETTER_DATA": "#B54708",
}


def build_metric_visibility_profile(frame: pd.DataFrame, locale: object = DEFAULT_LOCALE) -> go.Figure:
    """Show frozen metric-governance tiers without implying a quality score."""

    resolved_locale = normalize_locale(locale)
    data = frame.copy()
    counts = data["visibility_tier"].astype(str).value_counts()
    rows = []
    for order, tier in enumerate(METHODS_VISIBILITY_TIER_ORDER):
        rows.append(
            {
                "tier": tier,
                "label": t(resolved_locale, f"methods.visibility.{tier}.label"),
                "description": t(resolved_locale, f"methods.visibility.{tier}.description"),
                "count": int(counts.get(tier, 0)),
                "order": order,
            }
        )
    plot = pd.DataFrame(rows).sort_values("order", ascending=False)
    figure = go.Figure(
        go.Bar(
            x=plot["count"],
            y=plot["label"],
            orientation="h",
            marker_color=[_TIER_COLORS[item] for item in plot["tier"]],
            text=plot["count"].map(lambda value: t(resolved_locale, "methods.figure.metric_count", count=int(value))),
            textposition="outside",
            cliponaxis=False,
            customdata=plot[["tier", "description"]].to_numpy(),
            hovertemplate=(
                "<b>%{y}</b><br>"
                + t(resolved_locale, "methods.figure.metrics_hover") + ": %{x}<br>"
                "%{customdata[1]}"
                "<extra></extra>"
            ),
        )
    )
    figure.update_xaxes(
        title=t(resolved_locale, "methods.figure.registered_metrics"),
        rangemode="tozero",
        gridcolor="rgba(102,112,133,0.16)",
        fixedrange=True,
        automargin=True,
    )
    figure.update_yaxes(fixedrange=True, automargin=True)
    figure.update_layout(bargap=0.38)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_METHODS_VISIBILITY_PROFILE,
            source="metric_visibility_registry.csv",
            metric="registered_metrics_by_visibility_tier",
            denominator="registered_dashboard_metrics",
            release=VISUALIZATION_RELEASE_ID,
            grain="metric_registry_entry",
            extra={"interpretation": "governance_categories_not_quality_scores"},
        ),
        height=310,
        margin={"l": 170, "r": 90, "t": 20, "b": 54},
        show_legend=False,
    )
