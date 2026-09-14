from __future__ import annotations

from scripts.research.multidataset_m26_decision_0031 import no_robust_recommendation_row, normalized


def test_no_robust_recommendation_is_first_class_outcome() -> None:
    row=no_robust_recommendation_row("BALANCED")
    assert row["status"]=="NO_ROBUST_RECOMMENDATION"
    assert row["option_id"] is None


def test_normalization_directions() -> None:
    assert normalized(10,0,10,"MAX")==1.0
    assert normalized(0,0,10,"MIN")==1.0
    assert normalized(5,5,5,"MAX")==1.0
