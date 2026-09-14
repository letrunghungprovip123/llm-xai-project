"""Figure contract tests for Page 7."""

from __future__ import annotations

from pathlib import Path
import sys
import types

import pandas as pd


# The methods figure imports dashboard settings, whose project-path helper is
# available in the full repository. This test focuses on figure semantics.
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.python.dashboard.figures.methods import build_metric_visibility_profile


def test_metric_visibility_profile_has_four_governance_bars() -> None:
    data = pd.read_csv(
        ROOT / "data/reports/llm_validation/validation_v1/analysis/visualization_v2/metric_visibility_registry.csv"
    )
    figure = build_metric_visibility_profile(data, locale="en")
    assert len(figure.data) == 1
    assert len(figure.data[0].x) == 4
    assert set(figure.data[0].y) == {
        "Headline",
        "Explanatory",
        "Internal validation",
        "Disabled pending better data",
    }
    assert sum(int(value) for value in figure.data[0].x) == len(data)
    assert figure.layout.showlegend is False
    assert figure.layout.meta["interpretation"] == "governance_categories_not_quality_scores"
