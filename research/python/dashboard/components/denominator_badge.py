"""Reusable denominator label for conditional or exploratory views."""

from __future__ import annotations

from dash import html


def denominator_badge(text: str):
    return html.Span(text, className="denominator-badge")
