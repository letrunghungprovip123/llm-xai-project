"""Canonical JSON export for Page 2."""

from __future__ import annotations

from research.python.dashboard.export.effectiveness_figures import (
    effectiveness_figures,
)


def test_effectiveness_export_registry_has_five_figures() -> None:
    figures = effectiveness_figures()
    assert len(figures) == 5
    assert all(figure.layout.meta["figure_id"] == figure_id for figure_id, figure in figures.items())
