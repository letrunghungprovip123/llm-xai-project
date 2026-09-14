"""Reactive callback regression tests for Page 5."""

from __future__ import annotations

from research.python.dashboard.callbacks.robustness import measurement_updates
from research.python.dashboard.settings import (
    DEFAULT_ROBUSTNESS_METRIC,
    EXPECTED_MODEL_ORDER,
)


def test_measurement_model_scope_does_not_freeze_metric_updates() -> None:
    model_id = EXPECTED_MODEL_ORDER[0]
    first = measurement_updates(
        DEFAULT_ROBUSTNESS_METRIC,
        model_id,
        None,
        None,
        accept_click=False,
    )

    assert len(first) == 5
    assert len(first[0].data) == 3
    assert first[2]["model_id"] == model_id
    assert first[0].layout.meta["metric"] == DEFAULT_ROBUSTNESS_METRIC

    second = measurement_updates(
        "verifiability",
        model_id,
        None,
        first[2],
        accept_click=False,
    )

    assert len(second[0].data) == 3
    assert second[0].layout.meta["metric"] == "verifiability"
    assert second[2]["model_id"] == model_id
