"""Pure navigation logic tests for Executive Overview callbacks."""

from __future__ import annotations

from research.python.dashboard.callbacks.overview import navigation_target_from_click
from research.python.dashboard.ids import OVERVIEW_HEATMAP_ID, OVERVIEW_PROFILE_ID


def test_heatmap_click_builds_effectiveness_deep_link() -> None:
    target = navigation_target_from_click(
        triggered_id=OVERVIEW_HEATMAP_ID,
        heatmap_click={"points": [{"customdata": ["qwen3_8b", "Qwen", "S1"]}]},
        profile_click=None,
    )
    assert target == "/effectiveness?model=qwen3_8b&evidence=S1"


def test_profile_click_builds_effectiveness_deep_link() -> None:
    target = navigation_target_from_click(
        triggered_id=OVERVIEW_PROFILE_ID,
        heatmap_click=None,
        profile_click={"points": [{"customdata": ["phi4_mini_instruct", "S4"]}]},
    )
    assert target == "/effectiveness?model=phi4_mini_instruct&evidence=S4"


def test_invalid_click_returns_none() -> None:
    assert navigation_target_from_click(
        triggered_id=OVERVIEW_HEATMAP_ID,
        heatmap_click=None,
        profile_click=None,
    ) is None
