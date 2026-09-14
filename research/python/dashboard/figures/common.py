"""Pure Plotly helpers shared by dashboard figure factories."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import plotly.graph_objects as go

from ..theme import PLOTLY_FONT_FAMILY


FIGURE_BACKGROUND = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(102,112,133,0.18)"
TEXT_COLOR = "#344054"
MUTED_TEXT_COLOR = "#667085"


def figure_metadata(
    *,
    figure_id: str,
    source: str,
    metric: str,
    denominator: str,
    release: str,
    grain: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return reproducibility metadata embedded in a Plotly layout."""

    metadata: dict[str, Any] = {
        "figure_id": figure_id,
        "source": source,
        "metric": metric,
        "denominator": denominator,
        "release": release,
        "grain": grain,
    }
    if extra:
        metadata.update(dict(extra))
    return metadata


def apply_research_layout(
    figure: go.Figure,
    *,
    metadata: Mapping[str, Any],
    height: int,
    margin: Mapping[str, int] | None = None,
    show_legend: bool = True,
) -> go.Figure:
    """Apply calm editorial styling without mutating analytical values."""

    resolved_margin = dict(margin or {"l": 56, "r": 24, "t": 18, "b": 48})
    figure.update_layout(
        height=height,
        autosize=True,
        paper_bgcolor=FIGURE_BACKGROUND,
        plot_bgcolor=FIGURE_BACKGROUND,
        font={"family": PLOTLY_FONT_FAMILY, "color": TEXT_COLOR, "size": 12},
        margin=resolved_margin,
        hoverlabel={
            "bgcolor": "#101828",
            "bordercolor": "#344054",
            "font": {"family": PLOTLY_FONT_FAMILY, "color": "#FFFFFF"},
        },
        showlegend=show_legend,
        meta=dict(metadata),
        uirevision=str(metadata.get("release", "certified")),
        transition={"duration": 0},
    )
    return figure


def format_percent(value: float, *, digits: int = 1) -> str:
    """Format a unit fraction for compact chart annotation."""

    return f"{float(value):.{digits}%}"
