from __future__ import annotations

import pandas as pd

from research.python.diagnostics.claim_diagnostics import build_claim_base_frame
from research.python.diagnostics.generation_diagnostics import aggregate_claim_diagnostics


def test_claim_base_accepts_opt_in_diagnostic_version() -> None:
    claims = pd.DataFrame([{
        "claim_id":"c1","generation_id":"g1","case_id":"case1","model_id":"m1","evidence_level":"S0",
        "source_section":"prediction_summary","source_text":"x","claim_type":"causal","claim_subtype":"causal",
        "subject_type":"prediction","feature_id":None,"concept_id":None,"claim_origin":"llm","validation_status":"SUPPORTED",
        "source_start":0,"source_end":1,"numeric_value":None,"local_claim_index":0,
    }])
    generations = pd.DataFrame([{"generation_id":"g1","case_id":"case1","model_id":"m1","evidence_level":"S0","package_id":"p1","selection_stratum":"low_risk"}])
    packages = pd.DataFrame([{"package_id":"p1","safe_phrase_count":0}])
    frame = build_claim_base_frame({"claims":claims,"generations":generations,"evidence_packages":packages}, diagnostic_version="freddie_diagnostics_v1")
    assert frame["diagnostic_version"].tolist() == ["freddie_diagnostics_v1"]


def test_claim_aggregation_supports_dataset_opt_in_causal_type() -> None:
    frame = pd.DataFrame([{
        "generation_id":"g1","claim_id":"c1","is_supported":True,"is_unsupported":False,
        "is_contradicted":False,"is_not_verifiable":False,"is_not_applicable":False,
        "is_resolved":True,"is_applicable":True,"is_resolved_error":False,
        "safe_phrase_exposed":False,"safe_phrase_match_eligible":False,"safe_phrase_any_match":False,
        "safe_phrase_exact_match":False,"safe_phrase_contained_match":False,"safe_phrase_high_overlap":False,
        "claim_type":"causal",
    }])
    out = aggregate_claim_diagnostics(frame, claim_type_count_columns={"causal":"causal_claim_count"})
    assert out.loc[0, "causal_claim_count"] == 1
