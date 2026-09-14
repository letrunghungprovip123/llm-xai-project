from __future__ import annotations

from scripts.research.multidataset_m26_policy_lock_0030 import validate_policy


def policy_fixture() -> dict:
    return {
      "option_roles":{"control_levels":["S0"],"primary_candidate_levels":["S1","S2","S3","S4"],"fallback_only_levels":["S5"]},
      "noninferiority":{"endpoint":"end_to_end_faithfulness_yield","absolute_margin":0.03},
      "threshold_relaxation_allowed":False,
      "pareto":{"monetary_cost_allowed":False,"cross_dataset_latency_hard_axis_allowed":False},
      "scenarios":[
        {"scenario_id":"QUALITY_FIRST","requires_independence_metric":False,"criteria":[{"criterion_id":"q","weight":1.0}]},
        {"scenario_id":"RELIABILITY_FIRST","requires_independence_metric":False,"criteria":[{"criterion_id":"q","weight":1.0}]},
        {"scenario_id":"BALANCED","requires_independence_metric":False,"criteria":[{"criterion_id":"q","weight":1.0}]},
        {"scenario_id":"EFFICIENCY_AWARE","requires_independence_metric":False,"criteria":[{"criterion_id":"q","weight":1.0}]},
        {"scenario_id":"INDEPENDENCE_SENSITIVE","requires_independence_metric":True,"criteria":[{"criterion_id":"q","weight":1.0}]},
      ]
    }


def test_policy_disables_independence_scenario_when_metric_not_comparable() -> None:
    result=validate_policy(policy_fixture(),False)
    assert result["passed"]
    states={x["scenario_id"]:x for x in result["resolved_scenarios"]}
    assert states["INDEPENDENCE_SENSITIVE"]["enabled"] is False


def test_policy_rejects_cost_or_latency_criterion() -> None:
    p=policy_fixture(); p["scenarios"][0]["criteria"]=[{"criterion_id":"monetary_cost","weight":1.0}]
    assert validate_policy(p,True)["passed"] is False
