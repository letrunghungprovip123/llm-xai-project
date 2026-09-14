"""Pure update helpers for Page 2 callbacks."""

from __future__ import annotations

from research.python.dashboard.callbacks.effectiveness import (
    conditional_updates,
    parse_focus,
    primary_contrast_rows,
)


def test_focus_query_parser() -> None:
    assert parse_focus("?model=phi4_mini_instruct&evidence=S4") == (
        "phi4_mini_instruct",
        "S4",
    )
    assert parse_focus("") == (None, None)


def test_conditional_update_changes_metric_without_recomputing_tests() -> None:
    heatmap, gap, _panel, rows = conditional_updates("verifiability")
    assert heatmap.layout.meta["metric"] == "verifiability"
    assert "verifiability" in gap.layout.meta["metric"]
    assert len(rows) == 33


def test_primary_contrast_family_filter() -> None:
    assert len(primary_contrast_rows("all")) == 33
    assert len(primary_contrast_rows("model_within_evidence")) == 18
    assert len(primary_contrast_rows("evidence_vs_s0")) == 15
