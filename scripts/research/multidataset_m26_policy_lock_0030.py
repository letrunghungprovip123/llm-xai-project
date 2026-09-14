#!/usr/bin/env python3
"""Freeze M26 decision policy against the certified M25 release without ranking options."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def read_json(path: Path) -> dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict): raise ValueError(path)
    return v

def repo_path(root: Path,path: Path) -> str:
    try: return str(path.resolve().relative_to(root.resolve()))
    except ValueError: return str(path.resolve())

def record(root: Path,path: Path) -> dict[str,Any]:
    path=path.resolve()
    if not path.is_file(): raise FileNotFoundError(path)
    return {"path":repo_path(root,path),"sha256":sha(path),"byte_count":path.stat().st_size}

def validate_policy(policy: dict[str,Any], independence_comparable: bool) -> dict[str,Any]:
    checks={}
    def add(name,exp,obs,ok): checks[name]={"expected":exp,"observed":obs,"passed":bool(ok)}
    roles=policy["option_roles"]
    add("control_levels",["S0"],roles["control_levels"],roles["control_levels"]==["S0"])
    add("primary_candidate_levels",["S1","S2","S3","S4"],roles["primary_candidate_levels"],roles["primary_candidate_levels"]==["S1","S2","S3","S4"])
    add("fallback_only_levels",["S5"],roles["fallback_only_levels"],roles["fallback_only_levels"]==["S5"])
    ni=policy["noninferiority"]; add("ni_endpoint","end_to_end_faithfulness_yield",ni["endpoint"],ni["endpoint"]=="end_to_end_faithfulness_yield"); add("ni_margin",0.03,float(ni["absolute_margin"]),abs(float(ni["absolute_margin"])-0.03)<=1e-12)
    add("threshold_relaxation_allowed",False,policy["threshold_relaxation_allowed"],policy["threshold_relaxation_allowed"] is False)
    add("monetary_cost_allowed",False,policy["pareto"]["monetary_cost_allowed"],policy["pareto"]["monetary_cost_allowed"] is False)
    add("latency_hard_axis_allowed",False,policy["pareto"]["cross_dataset_latency_hard_axis_allowed"],policy["pareto"]["cross_dataset_latency_hard_axis_allowed"] is False)
    scenario_ids=[str(s["scenario_id"]) for s in policy["scenarios"]]; expected=["QUALITY_FIRST","RELIABILITY_FIRST","BALANCED","EFFICIENCY_AWARE","INDEPENDENCE_SENSITIVE"]
    add("scenario_ids",expected,scenario_ids,scenario_ids==expected)
    bad_weights=[]; forbidden=[]
    for scenario in policy["scenarios"]:
        total=sum(float(c["weight"]) for c in scenario["criteria"])
        if abs(total-1.0)>1e-12: bad_weights.append(scenario["scenario_id"])
        for criterion in scenario["criteria"]:
            cid=str(criterion["criterion_id"]).lower()
            if "cost" in cid or "latency" in cid: forbidden.append(f"{scenario['scenario_id']}::{criterion['criterion_id']}")
    add("scenario_weight_mismatches",[],bad_weights,not bad_weights); add("forbidden_scenario_criteria",[],forbidden,not forbidden)
    resolved=[{"scenario_id":s["scenario_id"],"enabled":not bool(s.get("requires_independence_metric")) or independence_comparable,"disabled_reason":None if (not bool(s.get("requires_independence_metric")) or independence_comparable) else "independence_metric_not_comparable"} for s in policy["scenarios"]]
    failed=sum(not x["passed"] for x in checks.values())
    return {"checks":checks,"failed_check_count":failed,"passed":failed==0,"resolved_scenarios":resolved}

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--repo-root",required=True); ap.add_argument("--policy",required=True); ap.add_argument("--m25-lock",required=True); ap.add_argument("--m25-dir",required=True); ap.add_argument("--output",required=True); a=ap.parse_args()
    root=Path(a.repo_root).resolve(); policy_path=Path(a.policy).resolve(); m25_lock_path=Path(a.m25_lock).resolve(); m25_dir=Path(a.m25_dir).resolve(); output=Path(a.output).resolve()
    policy=read_json(policy_path); m25_lock=read_json(m25_lock_path); m25_manifest=read_json(m25_dir/"replication_manifest.json"); m25_validation=read_json(m25_dir/"replication_validation.json")
    if m25_lock.get("gate")!="MULTIDATASET_REPLICATION_INPUT_LOCK_READY" or m25_manifest.get("gate")!="MULTIDATASET_REPLICATION_READY" or not m25_validation.get("passed"): raise SystemExit("M26 requires certified M25 inputs/release.")
    independence=bool(m25_manifest.get("independence_metric_comparable")); pv=validate_policy(policy,independence)
    if not pv["passed"]:
        failed=[k for k,v in pv["checks"].items() if not v["passed"]]; raise SystemExit("M26 policy validation failed: "+", ".join(failed))
    lock={"schema_version":"multidataset_decision_policy_lock_v1","producer":"M26A_0030","policy":record(root,policy_path),"parent_m25_input_lock":record(root,m25_lock_path),"parent_m25_manifest":record(root,m25_dir/"replication_manifest.json"),"parent_m25_validation":record(root,m25_dir/"replication_validation.json"),"m25_option_performance":record(root,m25_dir/"cross_dataset_option_performance.csv"),"m25_failure_profile":record(root,m25_dir/"failure_profile_comparison.csv"),"policy_validation":pv,"resolved_scenarios":pv["resolved_scenarios"],"independence_metric_comparable":independence,"provider_execution_allowed":False,"gate":"MULTIDATASET_DECISION_POLICY_LOCK_READY"}
    encoded=json.dumps(lock,ensure_ascii=False,indent=2,sort_keys=True)+"\n"; output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        if output.read_text(encoding="utf-8")==encoded: print(f"MULTIDATASET_M26A_DECISION_POLICY=ALREADY_CERTIFIED independence_comparable={str(independence).lower()}"); return 0
        raise SystemExit(f"Refusing to overwrite different M26 policy lock: {output}")
    output.write_text(encoded,encoding="utf-8"); print(f"MULTIDATASET_M26A_DECISION_POLICY=PASS scenarios=5 margin=0.03 independence_comparable={str(independence).lower()}"); return 0
if __name__=="__main__": raise SystemExit(main())
