#!/usr/bin/env python3
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

from research.python.robustness.build import (
    PRIMARY_METRIC,
    bootstrap_sensitivity,
    canonical_contrast_id,
    claim_type_sensitivity,
    margin_sensitivity,
    metric_sensitivity,
    population_sensitivity,
    recompute_claim_exclusion_metrics,
)
from research.python.robustness.common import read_json, repo_relative, resolve_record, sha256_file


def file_record(root: Path,path: Path) -> dict[str,Any]:
    return {"path":repo_relative(root,path),"sha256":sha256_file(path),"byte_count":path.stat().st_size}


def verify_lock(root: Path,lock: dict[str,Any]) -> None:
    if lock.get("gate")!="MULTIDATASET_ROBUSTNESS_INPUT_LOCK_READY": raise ValueError("M27B requires certified M27A input lock.")
    for group in ["parents","inputs"]:
        for name,record in lock[group].items(): resolve_record(root,record,name)
    resolve_record(root,lock["protocol"],"protocol")


def directory_hashes(path: Path) -> dict[str,str]: return {p.name:sha256_file(p) for p in sorted(path.iterdir()) if p.is_file()}


def build_release(root: Path,lock_path: Path,lock: dict[str,Any],protocol: dict[str,Any],out: Path) -> dict[str,Any]:
    verify_lock(root,lock)
    hc_metrics=pd.read_csv(resolve_record(root,lock["inputs"]["home_credit_generation_metrics"],"hc_metrics"),low_memory=False)
    fm_metrics=pd.read_csv(resolve_record(root,lock["inputs"]["freddie_generation_metrics"],"fm_metrics"),low_memory=False)
    hc_claims=pd.read_csv(resolve_record(root,lock["inputs"]["home_credit_claim_diagnostics"],"hc_claims"),low_memory=False)
    fm_claims=pd.read_csv(resolve_record(root,lock["inputs"]["freddie_claim_diagnostics"],"fm_claims"),low_memory=False)
    ni=pd.read_csv(resolve_record(root,lock["inputs"]["m26_noninferiority_results"],"m26_ni"),low_memory=False)
    assessment=pd.read_csv(resolve_record(root,lock["inputs"]["m26_dataset_option_assessment"],"m26_assessment"),low_memory=False)
    recommendations=pd.read_csv(resolve_record(root,lock["inputs"]["m26_recommendations"],"m26_recommendations"),low_memory=False)
    certified_concordance=pd.read_csv(resolve_record(root,lock["inputs"]["m25_contrast_concordance"],"m25_contrast_concordance"),low_memory=False)

    pop_frames=[]; effect_frames=[]; contrast_frames=[]
    for metrics,dataset,ids in [(hc_metrics,"home_credit_default_risk",lock["observed"]["home_credit_complete_case_ids"]),(fm_metrics,"freddie_sflld_2024",lock["observed"]["freddie_complete_case_ids"])]:
        a,b,c=population_sensitivity(metrics,[str(x) for x in ids],dataset); pop_frames.append(a); effect_frames.append(b); contrast_frames.append(c)
    population=pd.concat(pop_frames,ignore_index=True); population_effects=pd.concat(effect_frames,ignore_index=True); population_contrasts=pd.concat(contrast_frames,ignore_index=True)

    metrics_out=pd.concat([metric_sensitivity(hc_metrics,"home_credit_default_risk",[x["metric_id"] for x in protocol["metric_lanes"]]),metric_sensitivity(fm_metrics,"freddie_sflld_2024",[x["metric_id"] for x in protocol["metric_lanes"]])],ignore_index=True)

    margin_rows,margin_summary=margin_sensitivity(ni,assessment,protocol["noninferiority_margin_lanes"])
    primary_margin=margin_rows.loc[margin_rows["margin_lane_id"].eq("PRIMARY_003"),["option_id","robust_eligible_at_margin"]].rename(columns={"robust_eligible_at_margin":"recomputed_primary_robust_eligible"})
    primary_check=assessment[["option_id","robust_eligible"]].merge(primary_margin,on="option_id",how="left",validate="one_to_one")
    primary_margin_mismatch=int((primary_check["robust_eligible"].astype(bool)!=primary_check["recomputed_primary_robust_eligible"].fillna(False).astype(bool)).sum())

    claim_options=[]; claim_lanes=[]
    for metrics,claims,dataset in [(hc_metrics,hc_claims,"home_credit_default_risk"),(fm_metrics,fm_claims,"freddie_sflld_2024")]:
        opt,lane=claim_type_sensitivity(metrics,claims,dataset,protocol["claim_type_exclusion_lanes"]); claim_options.append(opt); claim_lanes.append(lane)
    claim_option_out=pd.concat(claim_options,ignore_index=True); claim_lane_out=pd.concat(claim_lanes,ignore_index=True)

    all_applicable_mismatch=0
    for metrics,claims,dataset in [(hc_metrics,hc_claims,"home_credit_default_risk"),(fm_metrics,fm_claims,"freddie_sflld_2024")]:
        recomputed=recompute_claim_exclusion_metrics(metrics,claims,set())
        delta=np.abs(pd.to_numeric(recomputed[PRIMARY_METRIC])-pd.to_numeric(metrics[PRIMARY_METRIC]))
        all_applicable_mismatch += int((delta>1e-12).sum())

    bs=protocol["bootstrap_sensitivity"]; bootstrap_opts=[]; bootstrap_cons=[]; bootstrap_summaries=[]
    for metrics,dataset in [(hc_metrics,"home_credit_default_risk"),(fm_metrics,"freddie_sflld_2024")]:
        a,b,c=bootstrap_sensitivity(metrics,dataset,[int(x) for x in bs["seed_registry"]],int(bs["iterations"]),float(bs["confidence"])); bootstrap_opts.append(a); bootstrap_cons.append(b); bootstrap_summaries.append(c)
    bootstrap_option=pd.concat(bootstrap_opts,ignore_index=True); bootstrap_contrast=pd.concat(bootstrap_cons,ignore_index=True); bootstrap_summary=pd.concat(bootstrap_summaries,ignore_index=True)

    # Compare sensitivity-seed CI boundary states against the already-certified M25 primary CI,
    # not merely against one another. This keeps M25 as the authoritative primary analysis.
    certified_states=[]
    canonical_certified=certified_concordance.copy()
    canonical_certified["contrast_id"]=canonical_certified.apply(
        lambda row: canonical_contrast_id(
            str(row["contrast_family"]),
            str(row["a_model"]),
            str(row["a_evidence"]),
            str(row["b_model"]),
            str(row["b_evidence"]),
        ),
        axis=1,
    )
    if canonical_certified["contrast_id"].duplicated().any() or len(canonical_certified)!=33:
        raise ValueError("Certified M25 contrast registry does not map one-to-one onto the 33 M27 planned contrasts.")
    for dataset_id,prefix in [("home_credit_default_risk","home_credit"),("freddie_sflld_2024","freddie")]:
        part=canonical_certified[["contrast_id",f"{prefix}_ci_lower",f"{prefix}_ci_upper"]].copy()
        part.insert(0,"dataset_id",dataset_id)
        part["certified_primary_ci_excludes_zero"]=(pd.to_numeric(part[f"{prefix}_ci_lower"])>0)|(pd.to_numeric(part[f"{prefix}_ci_upper"])<0)
        certified_states.append(part[["dataset_id","contrast_id","certified_primary_ci_excludes_zero"]])
    certified_states=pd.concat(certified_states,ignore_index=True)
    bootstrap_summary=bootstrap_summary.merge(certified_states,on=["dataset_id","contrast_id"],validate="one_to_one")
    sensitivity_state=(bootstrap_contrast.groupby(["dataset_id","contrast_id"],as_index=False)["ci_excludes_zero"].agg(lambda x: "|".join(sorted({"1" if bool(v) else "0" for v in x}))))
    sensitivity_state=sensitivity_state.rename(columns={"ci_excludes_zero":"sensitivity_zero_exclusion_states"})
    bootstrap_summary=bootstrap_summary.merge(sensitivity_state,on=["dataset_id","contrast_id"],validate="one_to_one")
    bootstrap_summary["bootstrap_boundary_stable_with_primary"]=bootstrap_summary.apply(
        lambda row: row["sensitivity_zero_exclusion_states"] == ("1" if bool(row["certified_primary_ci_excludes_zero"]) else "0"), axis=1
    )

    primary_row=margin_summary.loc[margin_summary["margin_lane_id"].eq("PRIMARY_003")].iloc[0]
    primary_pool=str(primary_row["active_pool_mode"]); primary_eligible=str(primary_row["robust_eligible_option_ids"])
    nonprimary=margin_summary.loc[~margin_summary["margin_lane_id"].eq("PRIMARY_003")].copy()
    margin_stable=bool((nonprimary["robust_eligible_option_ids"].astype(str)==primary_eligible).all())
    population_rank_stable=int(population["rank_shift_complete_minus_primary"].fillna(0).abs().sum())==0
    population_inference_stable=bool(population_effects["significance_conclusion_stable"].all() and population_contrasts["direction_stable"].all())
    metric_rank_stable=int(metrics_out.loc[~metrics_out["metric_id"].eq(PRIMARY_METRIC),"rank_shift_vs_primary"].fillna(0).abs().sum())==0
    claim_rank_stable=claim_option_out.empty or int(claim_option_out.loc[~claim_option_out["lane_id"].eq("ALL_APPLICABLE"),"rank_shift_vs_all_applicable"].fillna(0).abs().sum())==0
    bootstrap_stable=bool(bootstrap_summary["bootstrap_boundary_stable_with_primary"].all())
    sensitivity_has_candidate=bool(nonprimary["active_pool_mode"].astype(str).ne("NONE").any())
    primary_robust_selected=int(((recommendations["recommendation_scope"]=="CROSS_DATASET_ROBUST")&(recommendations["status"]=="SELECTED")).sum())
    decision_stable=(primary_robust_selected>0 and bool(nonprimary["active_pool_mode"].astype(str).ne("NONE").all())) or (primary_robust_selected==0 and not sensitivity_has_candidate)
    summary_rows=[
        {"dimension":"population","status":"PRIMARY_STABLE" if population_inference_stable and population_rank_stable else "POPULATION_SENSITIVE","note":"Sensitive if complete-case analysis changes any omnibus significance conclusion, planned-contrast direction, or 18-option rank."},
        {"dimension":"metric","status":"PRIMARY_STABLE" if metric_rank_stable else "METRIC_SENSITIVE","note":"Sensitive if any frozen non-primary metric changes any 18-option rank."},
        {"dimension":"margin","status":"PRIMARY_STABLE" if margin_stable else "MARGIN_SENSITIVE","note":"Sensitive if the exact robust-eligible option set changes at 0.02 or 0.05; certified primary M26 margin remains 0.03."},
        {"dimension":"bootstrap","status":"PRIMARY_STABLE" if bootstrap_stable else "BOOTSTRAP_BOUNDARY_SENSITIVE","note":"Sensitive if any frozen sensitivity seed changes CI zero-exclusion relative to the certified M25 primary CI state."},
        {"dimension":"claim_type","status":"PRIMARY_STABLE" if claim_rank_stable else "CLAIM_TYPE_SENSITIVE","note":"Only pre-frozen one-type exclusions are evaluated; primary validation labels are never changed."},
        {"dimension":"decision","status":"PRIMARY_STABLE" if decision_stable else "MARGIN_SENSITIVE","note":"Decision availability is sensitive if non-primary margin lanes change whether a robust candidate pool exists relative to the certified M26 recommendation state."},
    ]
    robustness_summary=pd.DataFrame(summary_rows)
    recommendation_sensitivity=margin_summary.copy(); recommendation_sensitivity["certified_primary_robust_selected_count"]=primary_robust_selected; recommendation_sensitivity["is_primary_certified_lane"]=recommendation_sensitivity["analysis_status"].eq("PRIMARY_CERTIFIED")

    validator_status={**lock["readiness"]["validator_sensitivity"],"analysis_role":"SENSITIVITY_ONLY","executed":False}
    template_status={**lock["readiness"]["template_baseline"],"analysis_role":"SENSITIVITY_ONLY","executed":False,"baseline_role":"DETERMINISTIC_BASELINE_NOT_FOURTH_LLM"}
    human_status={**lock["readiness"]["human_calibration"],"automated_validator_is_human_ground_truth":False}

    checks={}
    def add(name,expected,observed,passed): checks[name]={"expected":expected,"observed":observed,"passed":bool(passed)}
    add("dataset_count",2,int(population["dataset_id"].nunique()),population["dataset_id"].nunique()==2)
    add("population_option_rows",36,len(population),len(population)==36)
    add("population_effect_rows",6,len(population_effects),len(population_effects)==6)
    add("population_contrast_rows",66,len(population_contrasts),len(population_contrasts)==66)
    add("metric_sensitivity_rows",144,len(metrics_out),len(metrics_out)==144)
    add("margin_lane_count",3,len(margin_summary),len(margin_summary)==3)
    add("primary_margin_reproduction_mismatch",0,primary_margin_mismatch,primary_margin_mismatch==0)
    add("all_applicable_metric_mismatch",0,all_applicable_mismatch,all_applicable_mismatch==0)
    add("bootstrap_claim_resampling_allowed",False,protocol["bootstrap_sensitivity"]["claim_resampling_allowed"],protocol["bootstrap_sensitivity"]["claim_resampling_allowed"] is False)
    add("bootstrap_contrast_rows",198,len(bootstrap_contrast),len(bootstrap_contrast)==198)
    add("bootstrap_option_rows",108,len(bootstrap_option),len(bootstrap_option)==108)
    add("bootstrap_primary_comparison_rows",66,len(bootstrap_summary),len(bootstrap_summary)==66)
    add("robustness_dimension_count",6,len(robustness_summary),len(robustness_summary)==6)
    add("provider_execution_allowed",False,protocol["provider_execution_allowed"],protocol["provider_execution_allowed"] is False)
    failed=sum(not x["passed"] for x in checks.values())
    validation={"schema_version":"multidataset_robustness_validation_v1","checks":checks,"failed_check_count":failed,"passed":failed==0,"exit_gate":"MULTIDATASET_ROBUSTNESS_READY" if failed==0 else "MULTIDATASET_ROBUSTNESS_INVALID"}
    if failed: raise ValueError("M27 robustness validation failed.")

    out.mkdir(parents=True,exist_ok=False)
    frames={"population_sensitivity":population,"population_effect_sensitivity":population_effects,"population_contrast_sensitivity":population_contrasts,"metric_sensitivity":metrics_out,"margin_sensitivity":margin_rows,"margin_sensitivity_summary":margin_summary,"bootstrap_option_sensitivity":bootstrap_option,"bootstrap_sensitivity":bootstrap_contrast,"bootstrap_sensitivity_summary":bootstrap_summary,"claim_type_sensitivity":claim_option_out,"claim_type_sensitivity_lanes":claim_lane_out,"recommendation_sensitivity":recommendation_sensitivity,"robustness_summary":robustness_summary}
    for name,frame in frames.items(): frame.to_csv(out/f"{name}.csv",index=False,float_format="%.12g",lineterminator="\n")
    for name,value in [("validator_sensitivity_status",validator_status),("template_baseline_status",template_status),("human_calibration_status",human_status),("robustness_validation",validation)]: (out/f"{name}.json").write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    files={p.name:{"sha256":sha256_file(p),"byte_count":p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()}
    manifest={"schema_version":"multidataset_robustness_manifest_v1","producer":"M27B_0033","parent_input_lock":{"path":repo_relative(root,lock_path),"sha256":sha256_file(lock_path)},"protocol":{"path":lock["protocol"]["path"],"sha256":lock["protocol"]["sha256"]},"primary_metric":protocol["primary_metric"],"primary_margin":0.03,"counts":{"datasets":2,"options_per_dataset":18,"primary_contrasts_per_dataset":33,"bootstrap_seeds":len(bs["seed_registry"])},"readiness":lock["readiness"],"files":files,"gate":"MULTIDATASET_ROBUSTNESS_READY"}
    (out/"robustness_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return manifest


def reverify_existing(root: Path,lock_path: Path,out: Path) -> dict[str,Any]:
    manifest=read_json(out/"robustness_manifest.json"); validation=read_json(out/"robustness_validation.json")
    if manifest.get("gate")!="MULTIDATASET_ROBUSTNESS_READY" or validation.get("passed") is not True: raise ValueError("Existing M27 release is not certified.")
    if manifest.get("parent_input_lock",{}).get("sha256")!=sha256_file(lock_path): raise ValueError("Existing M27 parent lock drift.")
    for name,record in manifest["files"].items():
        path=out/name
        if not path.is_file() or sha256_file(path)!=record["sha256"] or path.stat().st_size!=int(record["byte_count"]): raise ValueError(f"Existing M27 artifact drift: {name}")
    return manifest


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--repo-root",required=True); parser.add_argument("--input-lock",required=True); parser.add_argument("--output-dir",required=True); args=parser.parse_args()
    root=Path(args.repo_root).resolve(); lock_path=Path(args.input_lock).resolve(); out=Path(args.output_dir).resolve(); lock=read_json(lock_path); protocol=read_json(resolve_record(root,lock["protocol"],"protocol"))
    if out.exists():
        manifest=reverify_existing(root,lock_path,out); print(f"MULTIDATASET_M27_ROBUSTNESS=ALREADY_CERTIFIED datasets={manifest['counts']['datasets']} bootstrap_seeds={manifest['counts']['bootstrap_seeds']}"); return 0
    out.parent.mkdir(parents=True,exist_ok=True); a=Path(tempfile.mkdtemp(prefix=".m27a_",dir=out.parent)); shutil.rmtree(a); b=Path(tempfile.mkdtemp(prefix=".m27b_",dir=out.parent)); shutil.rmtree(b)
    try:
        build_release(root,lock_path,lock,protocol,a); build_release(root,lock_path,lock,protocol,b)
        if directory_hashes(a)!=directory_hashes(b): raise ValueError("M27 deterministic replay mismatch.")
        os.replace(a,out); a=Path("/__promoted__")
    finally:
        if a.exists(): shutil.rmtree(a,ignore_errors=True)
        if b.exists(): shutil.rmtree(b,ignore_errors=True)
    manifest=read_json(out/"robustness_manifest.json"); print(f"MULTIDATASET_M27_ROBUSTNESS=PASS datasets=2 bootstrap_seeds={manifest['counts']['bootstrap_seeds']} validator={manifest['readiness']['validator_sensitivity']['status']} template={manifest['readiness']['template_baseline']['status']}"); return 0


if __name__=="__main__": raise SystemExit(main())
