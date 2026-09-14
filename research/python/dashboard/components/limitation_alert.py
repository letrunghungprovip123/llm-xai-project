"""Calm limitation note used throughout the research dashboard."""

from __future__ import annotations

from dash import html


def limitation_alert(text: str, *, tone: str = "information"):
    return html.Aside(
        text,
        className=f"limitation-alert limitation-alert--{tone}",
        role="note",
    )
