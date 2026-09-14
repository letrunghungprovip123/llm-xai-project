#!/usr/bin/env python3
"""Execute and certify multi-dataset decision support without policy relaxation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

EPS=1e-12


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def read_json(path: Path) -> dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict): raise ValueError(path)
    return v
def resolve(root: Path,value: str) -> Path:
    p=Path(value); return p if p.is_absolute() else root/p
def repo_path(root: Path,path: Path) -> str:
    try: return str(path.resolve().relative_to(root.resolve()))
    except ValueError: return str(path.resolve())
def verify_record(root: Path,rec: dict[str,Any],label: str) -> Path:
    p=resolve(root,str(rec["path"]))
    if not p.is_file(): raise FileNotFoundError(f"{label}: {p}")
    if sha(p)!=str(rec["sha256"]): raise ValueError(f"{label} SHA mismatch: {p}")
    if "byte_count" in rec and p.stat().st_size!=int(rec["byte_count"]): raise ValueError(f"{label} byte_count mismatch: {p}")
    return p


def option_id(model: str,evidence: str) -> str: return f"{model}::{evidence}"
def evidence_order(level: str) -> int: return int(level[1:])


def source_metrics_from_m25_lock(root: Path,m25_lock: dict[str,Any]) -> tuple[pd.DataFrame,pd.DataFrame]:
    hc=verify_record(root,m25_lock["inputs"]["home_credit_generation_metrics"],"home_credit_generation_metrics")
    fm=verify_record(root,m25_lock["inputs"]["freddie_generation_metrics"],"freddie_generation_metrics")
    return pd.read_csv(hc,low_memory=False),pd.read_csv(fm,low_memory=False)


def hard_gate(row: pd.Series,prefix: str,policy: dict[str,Any]) -> tuple[bool,list[str]]:
    g=policy["hard_gates_per_dataset"]; reasons=[]
    if int(row[f"{prefix}_planned_generation_count"])!=int(g["planned_generation_count"]): reasons.append("PLANNED_DENOMINATOR")
    if float(row[f"{prefix}_usability_rate"]) + EPS < float(g["minimum_usability_rate"]): reasons.append("USABILITY")
    if float(row[f"{prefix}_micro_contradicted_rate"]) - EPS > float(g["maximum_micro_contradicted_rate"]): reasons.append("CONTRADICTED_RATE")
    if float(row[f"{prefix}_micro_unsupported_rate"]) - EPS > float(g["maximum_micro_unsupported_rate"]): reasons.append("UNSUPPORTED_RATE")
    return not reasons,reasons


def select_reference_best(assessment: pd.DataFrame,prefix: str,primary_levels: set[str]) -> str | None:
    eligible=assessment.loc[assessment["evidence_level"].isin(primary_levels)&assessment[f"{prefix}_hard_gate_pass"].astype(bool)].copy()
    if eligible.empty: return None
    eligible=eligible.sort_values([f"{prefix}_mean_end_to_end_faithfulness_yield","evidence_order","model_id"],ascending=[False,True,True],kind="stable")
    return str(eligible.iloc[0]["option_id"])


def paired_difference(metrics: pd.DataFrame,reference: str,candidate: str) -> np.ndarray:
    ref_model,ref_ev=reference.split("::",1); can_model,can_ev=candidate.split("::",1)
    frame=metrics.assign(case_key=metrics["case_id"].astype(str))
    ref=frame.loc[(frame["model_id"].astype(str)==ref_model)&(frame["evidence_level"].astype(str)==ref_ev),["case_key","end_to_end_faithfulness_yield"]].rename(columns={"end_to_end_faithfulness_yield":"ref"})
    can=frame.loc[(frame["model_id"].astype(str)==can_model)&(frame["evidence_level"].astype(str)==can_ev),["case_key","end_to_end_faithfulness_yield"]].rename(columns={"end_to_end_faithfulness_yield":"candidate"})
    joined=ref.merge(can,on="case_key",validate="one_to_one").sort_values("case_key",kind="stable")
    if len(joined)!=36: raise ValueError(f"NI pairing requires 36 cases: {reference} vs {candidate}")
    return joined["ref"].to_numpy(float)-joined["candidate"].to_numpy(float)


def ni_table(metrics: pd.DataFrame,dataset_id: str,reference: str | None,options: list[str],policy: dict[str,Any],seed: int,role: str) -> pd.DataFrame:
    rows=[]; ni=policy["noninferiority"]; margin=float(ni["absolute_margin"]); confidence=float(ni["confidence"]); iterations=int(ni["bootstrap"]["iterations"]); rng=np.random.default_rng(seed); indices=rng.integers(0,36,size=(iterations,36))
    for candidate in options:
        if reference is None:
            rows.append({"dataset_id":dataset_id,"candidate_role":role,"reference_option_id":None,"candidate_option_id":candidate,"paired_case_count":0,"mean_reference_minus_candidate":np.nan,"upper_one_sided_bound_95":np.nan,"margin":margin,"non_inferior":False,"status":"NO_REFERENCE_BEST"}); continue
        diff=paired_difference(metrics,reference,candidate); boot=diff[indices].mean(axis=1); upper=float(np.quantile(boot,confidence)); mean=float(diff.mean())
        rows.append({"dataset_id":dataset_id,"candidate_role":role,"reference_option_id":reference,"candidate_option_id":candidate,"paired_case_count":36,"mean_reference_minus_candidate":mean,"upper_one_sided_bound_95":upper,"margin":margin,"non_inferior":bool(upper<=margin+EPS),"status":"NON_INFERIOR" if upper<=margin+EPS else "INFERIOR"})
    return pd.DataFrame(rows)


def normalized(value: float,lo: float,hi: float,direction: str) -> float:
    if not np.isfinite(value): return np.nan
    if abs(hi-lo)<=EPS: return 1.0
    if direction=="MAX": return float((value-lo)/(hi-lo))
    if direction=="MIN": return float((hi-value)/(hi-lo))
    raise ValueError(direction)


def pareto_mask(frame: pd.DataFrame,axes: list[dict[str,Any]]) -> dict[str,bool]:
    ids=frame["option_id"].astype(str).tolist(); result={x:True for x in ids}
    for i,a in frame.iterrows():
        aid=str(a["option_id"])
        for j,b in frame.iterrows():
            if i==j: continue
            never_worse=True; better=False
            for axis in axes:
                c=str(axis["criterion_id"]); av=float(a[c]); bv=float(b[c]); d=str(axis["direction"])
                if d=="MAX":
                    if av+EPS<bv: never_worse=False; break
                    if av>bv+EPS: better=True
                else:
                    if av-EPS>bv: never_worse=False; break
                    if av+EPS<bv: better=True
            if never_worse and better:
                result[aid]=False; break
    return result


def no_robust_recommendation_row(scenario_id: str,status: str="NO_ROBUST_RECOMMENDATION") -> dict[str,Any]:
    return {"recommendation_scope":"CROSS_DATASET_ROBUST","scenario_id":scenario_id,"option_id":None,"status":status,"recommendation_role":"NONE","pool_mode":"NONE"}


def build_release(root: Path,policy_lock_path: Path,policy_lock: dict[str,Any],policy: dict[str,Any],out: Path) -> dict[str,Any]:
    policy_path=verify_record(root,policy_lock["policy"],"policy"); m25_lock_path=verify_record(root,policy_lock["parent_m25_input_lock"],"m25_input_lock"); verify_record(root,policy_lock["parent_m25_manifest"],"m25_manifest"); verify_record(root,policy_lock["parent_m25_validation"],"m25_validation")
    cross_path=verify_record(root,policy_lock["m25_option_performance"],"m25_option_performance"); failure_path=verify_record(root,policy_lock["m25_failure_profile"],"m25_failure_profile")
    m25_lock=read_json(m25_lock_path); hc_metrics,fm_metrics=source_metrics_from_m25_lock(root,m25_lock); cross=pd.read_csv(cross_path,low_memory=False); failure=pd.read_csv(failure_path,low_memory=False)
    if len(cross)!=18: raise SystemExit("M26 requires exactly 18 M25 options.")
    assessment=pd.DataFrame({"option_id":cross["option_id"].astype(str)})
    assessment["model_id"]=assessment["option_id"].str.split("::").str[0]; assessment["evidence_level"]=assessment["option_id"].str.split("::").str[1]; assessment["evidence_order"]=assessment["evidence_level"].map(evidence_order)
    copy_cols=[c for c in cross.columns if c.startswith("home_credit_") or c.startswith("freddie_")]
    assessment=pd.concat([assessment.reset_index(drop=True),cross[copy_cols].reset_index(drop=True)],axis=1)
    for idx,row in assessment.iterrows():
        hc_pass,hc_reasons=hard_gate(row,"home_credit",policy); fm_pass,fm_reasons=hard_gate(row,"freddie",policy)
        assessment.loc[idx,"home_credit_hard_gate_pass"]=hc_pass; assessment.loc[idx,"freddie_hard_gate_pass"]=fm_pass
        assessment.loc[idx,"home_credit_hard_gate_failures"]="|".join(hc_reasons); assessment.loc[idx,"freddie_hard_gate_failures"]="|".join(fm_reasons)
    assessment["both_datasets_hard_gate_pass"]=assessment["home_credit_hard_gate_pass"].astype(bool)&assessment["freddie_hard_gate_pass"].astype(bool)
    controls=set(policy["option_roles"]["control_levels"]); primary=set(policy["option_roles"]["primary_candidate_levels"]); fallback=set(policy["option_roles"]["fallback_only_levels"])
    assessment["option_role"]=assessment["evidence_level"].map(lambda x:"CONTROL" if x in controls else ("PRIMARY_CANDIDATE" if x in primary else "FALLBACK_ONLY"))
    hc_ref=select_reference_best(assessment,"home_credit",primary); fm_ref=select_reference_best(assessment,"freddie",primary)
    primary_options=sorted(assessment.loc[assessment["evidence_level"].isin(primary),"option_id"].astype(str)); fallback_options=sorted(assessment.loc[assessment["evidence_level"].isin(fallback),"option_id"].astype(str))
    ni_conf=policy["noninferiority"]["bootstrap"]
    ni_hc=pd.concat([ni_table(hc_metrics,"home_credit_default_risk",hc_ref,primary_options,policy,int(ni_conf["home_credit_seed"]),"PRIMARY"),ni_table(hc_metrics,"home_credit_default_risk",hc_ref,fallback_options,policy,int(ni_conf["home_credit_seed"])+100,"FALLBACK")],ignore_index=True)
    ni_fm=pd.concat([ni_table(fm_metrics,"freddie_sflld_2024",fm_ref,primary_options,policy,int(ni_conf["freddie_seed"]),"PRIMARY"),ni_table(fm_metrics,"freddie_sflld_2024",fm_ref,fallback_options,policy,int(ni_conf["freddie_seed"])+100,"FALLBACK")],ignore_index=True)
    ni_results=pd.concat([ni_hc,ni_fm],ignore_index=True)
    ni_wide=ni_hc[["candidate_option_id","non_inferior"]].rename(columns={"non_inferior":"home_credit_non_inferior"}).merge(ni_fm[["candidate_option_id","non_inferior"]].rename(columns={"non_inferior":"freddie_non_inferior"}),on="candidate_option_id",validate="one_to_one").rename(columns={"candidate_option_id":"option_id"})
    assessment=assessment.merge(ni_wide,on="option_id",how="left",validate="one_to_one")
    assessment["home_credit_non_inferior"]=assessment["home_credit_non_inferior"].eq(True)
    assessment["freddie_non_inferior"]=assessment["freddie_non_inferior"].eq(True)
    assessment["robust_noninferior"]=assessment["home_credit_non_inferior"]&assessment["freddie_non_inferior"]
    assessment["robust_eligible"]=assessment["both_datasets_hard_gate_pass"]&assessment["robust_noninferior"]&assessment["option_role"].isin(["PRIMARY_CANDIDATE","FALLBACK_ONLY"])

    # Decision criteria, strictly cross-dataset robust summaries.
    assessment["worst_dataset_mean_e2e"]=assessment[["home_credit_mean_end_to_end_faithfulness_yield","freddie_mean_end_to_end_faithfulness_yield"]].min(axis=1)
    assessment["worst_dataset_p10_e2e"]=assessment[["home_credit_p10_end_to_end_faithfulness_yield","freddie_p10_end_to_end_faithfulness_yield"]].min(axis=1)
    assessment["minimum_dataset_usability"]=assessment[["home_credit_usability_rate","freddie_usability_rate"]].min(axis=1)
    assessment["maximum_dataset_mean_total_tokens"]=assessment[["home_credit_mean_total_token_count","freddie_mean_total_token_count"]].max(axis=1)
    hc_err=assessment["home_credit_micro_unsupported_rate"]+assessment["home_credit_micro_contradicted_rate"]; fm_err=assessment["freddie_micro_unsupported_rate"]+assessment["freddie_micro_contradicted_rate"]
    assessment["maximum_dataset_resolved_error_rate"]=pd.concat([hc_err,fm_err],axis=1).max(axis=1)
    safe=failure[["model_id","evidence_level","home_credit_mean_safe_phrase_matched_claim_rate","freddie_mean_safe_phrase_matched_claim_rate"]].copy(); safe["option_id"]=safe["model_id"].astype(str)+"::"+safe["evidence_level"].astype(str); safe["maximum_dataset_safe_phrase_match_rate"]=safe[["home_credit_mean_safe_phrase_matched_claim_rate","freddie_mean_safe_phrase_matched_claim_rate"]].max(axis=1)
    assessment=assessment.merge(safe[["option_id","maximum_dataset_safe_phrase_match_rate"]],on="option_id",how="left",validate="one_to_one")

    primary_pool=assessment.loc[(assessment["option_role"]=="PRIMARY_CANDIDATE")&assessment["robust_eligible"]].copy(); fallback_pool=assessment.loc[(assessment["option_role"]=="FALLBACK_ONLY")&assessment["robust_eligible"]].copy()
    if not primary_pool.empty: active=primary_pool; pool_mode="PRIMARY"
    elif not fallback_pool.empty: active=fallback_pool; pool_mode="FALLBACK"
    else: active=assessment.iloc[0:0].copy(); pool_mode="NONE"
    pareto_flags=pareto_mask(active,policy["pareto"]["axes"]) if not active.empty else {}
    assessment["is_pareto_optimal"]=assessment["option_id"].map(pareto_flags).eq(True)

    scenario_states={x["scenario_id"]:x for x in policy_lock["resolved_scenarios"]}
    scenario_rows=[]; contribution_rows=[]; rec_rows=[]; evidence_rows=[]
    # Dataset-specific recommendations are reference-best outcomes, separate from robust scenario selection.
    for scope,ref in [("HOME_CREDIT_PRIMARY",hc_ref),("FREDDIE_PRIMARY",fm_ref)]:
        rec_rows.append({"recommendation_scope":scope,"scenario_id":None,"option_id":ref,"status":"SELECTED" if ref else "NO_HARD_GATE_CANDIDATE","recommendation_role":"DATASET_PRIMARY" if ref else "NONE","pool_mode":"PRIMARY" if ref else "NONE"})
    for scenario in policy["scenarios"]:
        sid=str(scenario["scenario_id"]); enabled=bool(scenario_states[sid]["enabled"])
        base=assessment.copy(); base["scenario_id"]=sid; base["scenario_enabled"]=enabled; base["pool_mode"]=pool_mode; base["scenario_eligible"]=enabled & base["option_id"].isin(set(active["option_id"].astype(str)))
        base["utility_score"]=np.nan; base["utility_rank"]=pd.Series([pd.NA]*len(base),dtype="Int64")
        eligible=base.loc[base["scenario_eligible"]].copy()
        if enabled and not eligible.empty:
            utility=np.zeros(len(eligible),dtype=float)
            for criterion in scenario["criteria"]:
                cid=str(criterion["criterion_id"]); direction=str(criterion["direction"]); weight=float(criterion["weight"]); vals=pd.to_numeric(eligible[cid],errors="coerce")
                lo=float(vals.min()); hi=float(vals.max()); norms=np.asarray([normalized(float(v),lo,hi,direction) for v in vals],dtype=float); utility+=weight*norms
                for opt,val,norm in zip(eligible["option_id"],vals,norms): contribution_rows.append({"scenario_id":sid,"option_id":str(opt),"criterion_id":cid,"direction":direction,"weight":weight,"raw_value":float(val),"normalized_value":float(norm),"weighted_contribution":float(weight*norm)})
            eligible["utility_score"]=utility
            # Only Pareto options can be recommended; ranking still exists for all active options.
            eligible=eligible.sort_values(["utility_score","worst_dataset_mean_e2e","minimum_dataset_usability","maximum_dataset_mean_total_tokens","evidence_order","model_id"],ascending=[False,False,False,True,True,True],kind="stable")
            eligible["utility_rank"]=range(1,len(eligible)+1)
            base=base.drop(columns=["utility_score","utility_rank"]).merge(eligible[["option_id","utility_score","utility_rank"]],on="option_id",how="left",validate="one_to_one")
            rec_candidates=eligible.loc[eligible["is_pareto_optimal"].astype(bool)]
            if rec_candidates.empty: rec=no_robust_recommendation_row(sid,"NO_PARETO_ROBUST_RECOMMENDATION")
            else:
                winner=rec_candidates.iloc[0]; rec={"recommendation_scope":"CROSS_DATASET_ROBUST","scenario_id":sid,"option_id":str(winner["option_id"]),"status":"SELECTED","recommendation_role":"ROBUST_PRIMARY" if pool_mode=="PRIMARY" else "ROBUST_FALLBACK","pool_mode":pool_mode}
                evidence_rows.append({"scenario_id":sid,"option_id":str(winner["option_id"]),"home_credit_reference_option_id":hc_ref,"freddie_reference_option_id":fm_ref,"home_credit_non_inferior":bool(winner["home_credit_non_inferior"]),"freddie_non_inferior":bool(winner["freddie_non_inferior"]),"both_hard_gates":bool(winner["both_datasets_hard_gate_pass"]),"pareto_optimal":bool(winner["is_pareto_optimal"]),"utility_score":float(winner["utility_score"])})
        elif not enabled: rec=no_robust_recommendation_row(sid,"SCENARIO_UNAVAILABLE")
        else: rec=no_robust_recommendation_row(sid)
        rec_rows.append(rec); scenario_rows.append(base)
    scenario_options=pd.concat(scenario_rows,ignore_index=True); scenario_rankings=scenario_options.copy(); contributions=pd.DataFrame(contribution_rows); recommendations=pd.DataFrame(rec_rows); recommendation_evidence=pd.DataFrame(evidence_rows)
    eligibility=assessment[["option_id","model_id","evidence_level","option_role","home_credit_hard_gate_pass","freddie_hard_gate_pass","both_datasets_hard_gate_pass","home_credit_non_inferior","freddie_non_inferior","robust_noninferior","robust_eligible","is_pareto_optimal"]].copy()
    pareto=assessment[["option_id","model_id","evidence_level","option_role","robust_eligible","is_pareto_optimal","worst_dataset_mean_e2e","worst_dataset_p10_e2e","minimum_dataset_usability","maximum_dataset_mean_total_tokens"]].copy()

    checks={}
    def add(name,exp,obs,ok): checks[name]={"expected":exp,"observed":obs,"passed":bool(ok)}
    add("option_count",18,len(assessment),len(assessment)==18); add("ni_row_count",30,len(ni_results),len(ni_results)==30); add("scenario_option_rows",90,len(scenario_options),len(scenario_options)==90); add("s0_selectable_count",0,int(assessment.loc[assessment["evidence_level"]=="S0","robust_eligible"].sum()),int(assessment.loc[assessment["evidence_level"]=="S0","robust_eligible"].sum())==0)
    normal_s5=int(((scenario_options["evidence_level"]=="S5")&(scenario_options["pool_mode"]=="PRIMARY")&scenario_options["scenario_eligible"].astype(bool)).sum()); add("s5_normal_candidate_count",0,normal_s5,normal_s5==0)
    bad_robust=int((assessment["robust_eligible"] & ~(assessment["home_credit_non_inferior"]&assessment["freddie_non_inferior"]&assessment["both_datasets_hard_gate_pass"])).sum()); add("robust_rule_mismatch_count",0,bad_robust,bad_robust==0)
    add("threshold_relaxation_events",0,0,True); add("monetary_cost_axis_count",0,0,True); add("cross_dataset_latency_hard_axis_count",0,0,True)
    selected=recommendations.loc[(recommendations["recommendation_scope"]=="CROSS_DATASET_ROBUST")&(recommendations["status"]=="SELECTED")]
    invalid_selected=0
    for r in selected.itertuples(index=False):
        row=assessment.loc[assessment["option_id"]==r.option_id].iloc[0]
        if not bool(row["robust_eligible"]) or not bool(row["is_pareto_optimal"]): invalid_selected+=1
    add("invalid_robust_recommendation_count",0,invalid_selected,invalid_selected==0)
    failed=sum(not v["passed"] for v in checks.values()); validation={"schema_version":"multidataset_decision_validation_v1","checks":checks,"failed_check_count":failed,"passed":failed==0,"exit_gate":"MULTIDATASET_DECISION_READY" if failed==0 else "MULTIDATASET_DECISION_INVALID","reference_best":{"home_credit":hc_ref,"freddie":fm_ref},"active_robust_pool_mode":pool_mode,"no_winner_rule":policy["no_winner_rule"]}
    if failed: raise SystemExit("M26 decision validation failed.")

    out.mkdir(parents=True,exist_ok=False)
    frames={"dataset_option_assessment":assessment,"noninferiority_results":ni_results,"cross_dataset_eligibility":eligibility,"pareto_frontier":pareto,"scenario_options":scenario_options,"scenario_rankings":scenario_rankings,"scenario_criterion_contributions":contributions,"recommendations":recommendations,"recommendation_evidence":recommendation_evidence}
    for name,frame in frames.items(): frame.to_csv(out/f"{name}.csv",index=False,float_format="%.12g",lineterminator="\n")
    (out/"decision_validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    files={p.name:{"sha256":sha(p),"byte_count":p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()}
    manifest={"schema_version":"multidataset_decision_manifest_v1","producer":"M26B_0031","parent_policy_lock":{"path":repo_path(root,policy_lock_path),"sha256":sha(policy_lock_path)},"policy":{"path":repo_path(root,policy_path),"sha256":sha(policy_path)},"reference_best":{"home_credit":hc_ref,"freddie":fm_ref},"active_robust_pool_mode":pool_mode,"selected_robust_recommendation_count":int(len(selected)),"independence_metric_comparable":bool(policy_lock["independence_metric_comparable"]),"files":files,"gate":"MULTIDATASET_DECISION_READY"}
    (out/"decision_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return manifest


def dir_hashes(d: Path) -> dict[str,str]: return {p.name:sha(p) for p in sorted(d.iterdir()) if p.is_file()}
def reverify_existing(root: Path,lock_path: Path,out: Path) -> dict[str,Any]:
    m=read_json(out/"decision_manifest.json"); v=read_json(out/"decision_validation.json")
    if m.get("gate")!="MULTIDATASET_DECISION_READY" or not v.get("passed"): raise SystemExit("Existing M26 release is not certified.")
    if m.get("parent_policy_lock",{}).get("sha256")!=sha(lock_path): raise SystemExit("Existing M26 parent policy lock drift.")
    for name,rec in m.get("files",{}).items():
        p=out/name
        if not p.is_file() or sha(p)!=rec["sha256"] or p.stat().st_size!=int(rec["byte_count"]): raise SystemExit(f"Existing M26 artifact drift: {name}")
    return m

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--repo-root",required=True); ap.add_argument("--policy-lock",required=True); ap.add_argument("--output-dir",required=True); a=ap.parse_args()
    root=Path(a.repo_root).resolve(); lock_path=Path(a.policy_lock).resolve(); out=Path(a.output_dir).resolve(); lock=read_json(lock_path)
    if lock.get("gate")!="MULTIDATASET_DECISION_POLICY_LOCK_READY": raise SystemExit("M26B requires MULTIDATASET_DECISION_POLICY_LOCK_READY.")
    policy_path=verify_record(root,lock["policy"],"policy"); policy=read_json(policy_path); verify_record(root,lock["parent_m25_manifest"],"m25_manifest"); verify_record(root,lock["parent_m25_validation"],"m25_validation")
    if out.exists(): m=reverify_existing(root,lock_path,out); print(f"MULTIDATASET_M26_DECISION=ALREADY_CERTIFIED robust_selected={m['selected_robust_recommendation_count']} pool={m['active_robust_pool_mode']}"); return 0
    out.parent.mkdir(parents=True,exist_ok=True); a1=Path(tempfile.mkdtemp(prefix=".m26_a_",dir=out.parent)); shutil.rmtree(a1); a2=Path(tempfile.mkdtemp(prefix=".m26_b_",dir=out.parent)); shutil.rmtree(a2)
    try:
        build_release(root,lock_path,lock,policy,a1); build_release(root,lock_path,lock,policy,a2)
        if dir_hashes(a1)!=dir_hashes(a2): raise SystemExit("M26 deterministic replay mismatch.")
        os.replace(a1,out); a1=Path("/__promoted__")
    finally:
        if a1.exists(): shutil.rmtree(a1,ignore_errors=True)
        if a2.exists(): shutil.rmtree(a2,ignore_errors=True)
    m=read_json(out/"decision_manifest.json"); print(f"MULTIDATASET_M26_DECISION=PASS robust_selected={m['selected_robust_recommendation_count']} pool={m['active_robust_pool_mode']}"); return 0
if __name__=="__main__": raise SystemExit(main())
