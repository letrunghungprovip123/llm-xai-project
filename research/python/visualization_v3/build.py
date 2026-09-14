from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.python.robustness.common import read_json, resolve_record, sha256_file
from .common import m28_dir, read_authorized_csv

SCOPE_META={
 "HOME_CREDIT":("home_credit_default_risk","home_credit_generation_metrics","home_credit_claim_diagnostics","m25::home_credit_omnibus_tests","m25::home_credit_paired_tests"),
 "FREDDIE":("freddie_sflld_2024","freddie_generation_metrics","freddie_claim_diagnostics","m25::freddie_omnibus_tests","m25::freddie_paired_tests"),
}


def _records(root:Path)->list[dict[str,Any]]: return read_json(m28_dir(root)/"report_numbers.json")["records"]
def _record_map(root:Path)->dict[str,dict[str,Any]]: return {r["report_number_id"]:r for r in _records(root)}
def _write(frame:pd.DataFrame,path:Path)->None: frame.to_csv(path,index=False,lineterminator="\n")

def study_summary(root:Path)->pd.DataFrame:
 m=_record_map(root); rows=[]
 for scope,(dataset_id,*_) in SCOPE_META.items():
  def rec(suffix): return m[f"dataset::{scope}::{suffix}"]
  row={"dataset_scope":scope,"dataset_id":dataset_id}
  for col,suffix in [("planned_generations","planned_generations"),("usable_generations","usable_generations"),("unusable_generations","unusable_generations"),("final_claims","final_claims"),("primary_e2e","mean_e2e")]:
   r=rec(suffix); row[col]=r["value"]; row[f"{col}_report_number_id"]=r["report_number_id"]
  for status in ["SUPPORTED","NOT_VERIFIABLE","UNSUPPORTED","CONTRADICTED","NOT_APPLICABLE"]:
   r=m[f"dataset::{scope}::status::{status}"]; row[f"{status.lower()}_claims"]=r["value"]; row[f"{status.lower()}_report_number_id"]=r["report_number_id"]
  row["analysis_lane"]="PRIMARY"; rows.append(row)
 return pd.DataFrame(rows)

def option_performance(root:Path,sources)->pd.DataFrame:
 assessment=read_authorized_csv(root,sources,"m26_dataset_option_assessment"); report=_record_map(root); rows=[]
 for r in assessment.to_dict(orient="records"):
  for scope,prefix in [("HOME_CREDIT","home_credit"),("FREDDIE","freddie")]:
   model=str(r[f"{prefix}_model_id"]); evidence=str(r[f"{prefix}_evidence_level"]); rid=f"option::{scope}::{model}::{evidence}::mean_e2e"; certified=report[rid]
   value=float(r[f"{prefix}_mean_end_to_end_faithfulness_yield"])
   if not np.isclose(value,float(certified["value"]),rtol=0,atol=1e-12): raise ValueError(f"M26/M28 option value drift: {rid}")
   rows.append({"dataset_scope":scope,"dataset_id":r[f"{prefix}_dataset_id"],"option_id":r["option_id"],"model_id":model,"evidence_level":evidence,"evidence_order":r["evidence_order"],"planned_generation_count":r[f"{prefix}_planned_generation_count"],"usable_generation_count":r[f"{prefix}_usable_generation_count"],"usability_rate":r[f"{prefix}_usability_rate"],"mean_e2e":value,"median_e2e":r[f"{prefix}_median_end_to_end_faithfulness_yield"],"p10_e2e":r[f"{prefix}_p10_end_to_end_faithfulness_yield"],"bootstrap_ci_lower":r[f"{prefix}_bootstrap_ci_lower"],"bootstrap_ci_upper":r[f"{prefix}_bootstrap_ci_upper"],"quality_rank":r[f"{prefix}_quality_rank"],"option_role":r["option_role"],"hard_gate_pass":r[f"{prefix}_hard_gate_pass"],"non_inferior":r[f"{prefix}_non_inferior"],"mean_e2e_report_number_id":rid,"analysis_lane":"PRIMARY"})
 return pd.DataFrame(rows).sort_values(["dataset_scope","evidence_order","model_id"],kind="stable").reset_index(drop=True)

def omnibus(root:Path,sources)->pd.DataFrame:
 frames=[]
 for scope,(_,_,_,aid,_) in SCOPE_META.items():
  x=read_authorized_csv(root,sources,aid).copy(); x.insert(0,"dataset_scope",scope); frames.append(x)
 return pd.concat(frames,ignore_index=True)

def contrasts(root:Path,sources)->pd.DataFrame:
 frames=[]
 for scope,(_,_,_,_,aid) in SCOPE_META.items():
  x=read_authorized_csv(root,sources,aid).copy(); x.insert(0,"dataset_scope",scope); frames.append(x)
 return pd.concat(frames,ignore_index=True)

def failure_decomposition(root:Path)->pd.DataFrame:
 r=_record_map(root); rows=[]
 for scope in SCOPE_META:
  row={"dataset_scope":scope,"analysis_lane":"DIAGNOSTIC"}
  for metric in ["pipeline_loss","not_verifiable_loss","unsupported_loss","contradiction_loss","safe_phrase_matched_claim_rate"]:
   rid=f"diagnostic::{scope}::{metric}::mean"
   if rid in r: row[metric]=r[rid]["value"]; row[f"{metric}_report_number_id"]=rid
  rows.append(row)
 return pd.DataFrame(rows)

def claim_profile(root:Path,sources)->pd.DataFrame:
 frames=[]
 for scope,(_,_,claim_aid,_,_) in SCOPE_META.items():
  x=read_authorized_csv(root,sources,claim_aid); keys=["claim_type","validation_status"]; g=x.groupby(keys,dropna=False,sort=True).size().rename("claim_count").reset_index(); g.insert(0,"dataset_scope",scope); frames.append(g)
 return pd.concat(frames,ignore_index=True)

def cross_option(root:Path,sources)->pd.DataFrame: return read_authorized_csv(root,sources,"m26_dataset_option_assessment")
def cross_effects(root:Path,sources)->pd.DataFrame:
 h=read_authorized_csv(root,sources,"m25::home_credit_omnibus_tests").set_index("effect"); f=read_authorized_csv(root,sources,"m25::freddie_omnibus_tests").set_index("effect"); rows=[]
 for effect in sorted(set(h.index)&set(f.index)):
  rows.append({"effect":effect,"home_credit_f_statistic":h.loc[effect,"f_statistic"],"home_credit_p_value":h.loc[effect,"p_value_used"],"home_credit_partial_eta_squared":h.loc[effect,"partial_eta_squared"],"home_credit_significant":h.loc[effect,"significant"],"freddie_f_statistic":f.loc[effect,"f_statistic"],"freddie_p_value":f.loc[effect,"p_value_used"],"freddie_partial_eta_squared":f.loc[effect,"partial_eta_squared"],"freddie_significant":f.loc[effect,"significant"],"both_significant":bool(h.loc[effect,"significant"] and f.loc[effect,"significant"]),"analysis_lane":"REPLICATION"})
 return pd.DataFrame(rows)

def case_tables(root:Path,sources)->tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame,pd.DataFrame]:
 gen=[]; claims=[]; index=[]; caps=[]
 for scope,(dataset_id,gen_aid,claim_aid,_,_) in SCOPE_META.items():
  g=read_authorized_csv(root,sources,gen_aid).copy(); g.insert(0,"dataset_scope",scope); g.insert(1,"dataset_id",dataset_id); gen.append(g)
  c=read_authorized_csv(root,sources,claim_aid).copy(); c.insert(0,"dataset_scope",scope); c.insert(1,"dataset_id",dataset_id); claims.append(c)
  z=g.assign(case_id=g["case_id"].astype(str)).groupby("case_id",sort=True).agg(generation_count=("generation_id","size"),usable_generation_count=("usable","sum"),claim_count=("claim_count","sum")).reset_index(); z.insert(0,"dataset_scope",scope); z.insert(1,"dataset_id",dataset_id); z["complete_case"]=z["usable_generation_count"].eq(z["generation_count"]); index.append(z)
  caps.append({"dataset_scope":scope,"dataset_id":dataset_id,"generation_metrics":"AVAILABLE","claim_validation_diagnostics":"AVAILABLE","raw_generation_text":"NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE","raw_claim_text":"NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE","evidence_source_text":"NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE"})
 return pd.concat(index,ignore_index=True),pd.concat(gen,ignore_index=True),pd.concat(claims,ignore_index=True),pd.DataFrame(caps)

def dictionary(tables:dict[str,pd.DataFrame])->pd.DataFrame:
 rows=[]
 for name,df in sorted(tables.items()):
  for col in df.columns: rows.append({"table_name":name,"column_name":col,"dtype":str(df[col].dtype),"presentation_only":True})
 return pd.DataFrame(rows)

def build_tables(root:Path,lock:dict[str,Any])->dict[str,pd.DataFrame]:
 sources=lock["authorized_sources"]; d=m28_dir(root); case_idx,case_gen,case_claims,caps=case_tables(root,sources)
 tables={
  "study_summary":study_summary(root),"option_performance":option_performance(root,sources),"omnibus_effects":omnibus(root,sources),"planned_contrasts":contrasts(root,sources),"failure_decomposition":failure_decomposition(root),"claim_type_profile":claim_profile(root,sources),
  "cross_dataset_option_performance":cross_option(root,sources),"cross_dataset_effects":cross_effects(root,sources),"contrast_concordance":read_authorized_csv(root,sources,"m25_contrast_concordance"),"rank_stability":read_authorized_csv(root,sources,"m25_rank_stability"),
  "decision_option_assessment":read_authorized_csv(root,sources,"m26_dataset_option_assessment"),"noninferiority_results":read_authorized_csv(root,sources,"m26_noninferiority_results"),"cross_dataset_eligibility":read_authorized_csv(root,sources,"m26_dataset_option_assessment")[["option_id","model_id","evidence_level","option_role","home_credit_hard_gate_pass","freddie_hard_gate_pass","home_credit_non_inferior","freddie_non_inferior","robust_noninferior","robust_eligible","is_pareto_optimal"]].copy(),"pareto_frontier":read_authorized_csv(root,sources,"m26_dataset_option_assessment")[["option_id","model_id","evidence_level","option_role","robust_eligible","worst_dataset_mean_e2e","worst_dataset_p10_e2e","minimum_dataset_usability","maximum_dataset_mean_total_tokens","is_pareto_optimal"]].copy(),"scenario_options":read_authorized_csv(root,sources,"m26_scenario_options"),"recommendations":read_authorized_csv(root,sources,"m26_recommendations"),
  "robustness_summary":read_authorized_csv(root,sources,"m27::robustness_summary.csv"),"population_effect_sensitivity":read_authorized_csv(root,sources,"m27::population_effect_sensitivity.csv"),"population_contrast_sensitivity":read_authorized_csv(root,sources,"m27::population_contrast_sensitivity.csv"),"metric_sensitivity":read_authorized_csv(root,sources,"m27::metric_sensitivity.csv"),"margin_sensitivity_summary":read_authorized_csv(root,sources,"m27::margin_sensitivity_summary.csv"),"recommendation_sensitivity":read_authorized_csv(root,sources,"m27::recommendation_sensitivity.csv"),
  "case_index":case_idx,"case_generation_metrics":case_gen,"case_claim_diagnostics":case_claims,"case_detail_capabilities":caps,
  "metric_dictionary":pd.read_csv(d/"release_metric_dictionary.csv"),"limitations":pd.read_csv(d/"limitations_registry.csv"),"findings":pd.read_csv(d/"findings_registry.csv"),"research_questions":pd.read_csv(d/"research_question_registry.csv"),"report_source_index":pd.read_csv(d/"report_source_index.csv")
 }
 tables["visualization_dictionary"]=dictionary(tables)
 return tables
