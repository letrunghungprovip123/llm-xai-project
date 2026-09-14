from __future__ import annotations

import pandas as pd

from scripts.research.freddie_m24_diagnostics_0027 import dynamic_claim_type_columns
from scripts.research.freddie_m24_diagnostics_input_lock_0026 import safe_phrase_readiness


def test_dynamic_claim_type_columns_adds_causal_without_removing_legacy_types() -> None:
    mapping = dynamic_claim_type_columns(["prediction", "causal"])
    assert mapping["prediction"] == "prediction_claim_count"
    assert mapping["causal"] == "causal_claim_count"


def test_safe_phrase_readiness_disables_on_package_count_mismatch() -> None:
    levels = pd.DataFrame([
        {"evidence_level":"S0","safe_phrase_available":False},
        {"evidence_level":"S2","safe_phrase_available":True},
    ])
    packages = pd.DataFrame([
        {"package_id":"p0","evidence_level":"S0","safe_phrase_count":0},
        {"package_id":"p2","evidence_level":"S2","safe_phrase_count":2},
    ])
    items = pd.DataFrame([
        {"package_id":"p2","safe_phrase":"one phrase"},
    ])
    result = safe_phrase_readiness(levels, packages, items, True)
    assert result["enabled"] is False
    assert result["mismatched_package_count"] == 1
