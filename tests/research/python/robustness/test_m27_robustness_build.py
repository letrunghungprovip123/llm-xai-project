import pandas as pd

from research.python.robustness.build import canonical_contrast_id, margin_sensitivity, recompute_claim_exclusion_metrics


def test_margin_sensitivity_preserves_primary_margin_semantics_and_exact_sets() -> None:
    ni=pd.DataFrame([
        {"dataset_id":"home_credit_default_risk","candidate_option_id":"m::S1","upper_one_sided_bound_95":0.025},
        {"dataset_id":"freddie_sflld_2024","candidate_option_id":"m::S1","upper_one_sided_bound_95":0.028},
        {"dataset_id":"home_credit_default_risk","candidate_option_id":"m::S2","upper_one_sided_bound_95":0.040},
        {"dataset_id":"freddie_sflld_2024","candidate_option_id":"m::S2","upper_one_sided_bound_95":0.045},
    ])
    assessment=pd.DataFrame([
        {"option_id":"m::S1","option_role":"PRIMARY_CANDIDATE","both_datasets_hard_gate_pass":True,"robust_eligible":True},
        {"option_id":"m::S2","option_role":"PRIMARY_CANDIDATE","both_datasets_hard_gate_pass":True,"robust_eligible":False},
    ])
    rows,summary=margin_sensitivity(ni,assessment,[
        {"margin":0.02,"lane_id":"STRICT","analysis_status":"SENSITIVITY_ONLY"},
        {"margin":0.03,"lane_id":"PRIMARY_003","analysis_status":"PRIMARY_CERTIFIED"},
        {"margin":0.05,"lane_id":"RELAXED","analysis_status":"SENSITIVITY_ONLY"},
    ])
    assert not bool(rows.loc[(rows["margin_lane_id"]=="STRICT")&(rows["option_id"]=="m::S1"),"robust_eligible_at_margin"].iloc[0])
    assert bool(rows.loc[(rows["margin_lane_id"]=="PRIMARY_003")&(rows["option_id"]=="m::S1"),"robust_eligible_at_margin"].iloc[0])
    primary=summary.loc[summary["margin_lane_id"].eq("PRIMARY_003")].iloc[0]
    relaxed=summary.loc[summary["margin_lane_id"].eq("RELAXED")].iloc[0]
    assert primary["active_pool_mode"] == "PRIMARY"
    assert primary["robust_eligible_option_ids"] == "m::S1"
    assert relaxed["robust_eligible_option_ids"] == "m::S1|m::S2"


def test_claim_exclusion_reuses_quality_metric_semantics() -> None:
    metrics=pd.DataFrame([{"generation_id":"g1","usable":True,"supported_count":2,"unsupported_count":0,"contradicted_count":0,"not_verifiable_count":0,"not_applicable_count":0,"applicable_count":2,"resolved_count":2,"total_claims":2,"claim_count":2}])
    claims=pd.DataFrame([{"generation_id":"g1","claim_type":"numeric","validation_status":"SUPPORTED"},{"generation_id":"g1","claim_type":"feature_presence","validation_status":"SUPPORTED"}])
    output=recompute_claim_exclusion_metrics(metrics,claims,{"numeric"})
    assert output.loc[0,"end_to_end_faithfulness_yield"] == 1.0
    assert output.loc[0,"applicable_count"] == 1


def test_canonical_contrast_id_normalizes_m25_evidence_vs_s0_shape() -> None:
    assert canonical_contrast_id("evidence_vs_s0", "m", "S2", "m", "S0") == "evidence_vs_s0::m::S2"
    assert canonical_contrast_id("model_within_evidence", "a", "S3", "b", "S3") == "model_within_evidence::S3::a::b"
