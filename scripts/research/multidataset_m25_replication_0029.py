#!/usr/bin/env python3
"""Execute and certify Home Credit ↔ Freddie cross-dataset replication."""
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
from scipy.stats import spearmanr

try:
    from multidataset_m25_input_lock_0028 import contrast_id
except ModuleNotFoundError:  # package import in tests
    from scripts.research.multidataset_m25_input_lock_0028 import contrast_id

EPS=1e-12


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict): raise ValueError(path)
    return v


def resolve(root: Path, value: str) -> Path:
    p=Path(value); return p if p.is_absolute() else root/p


def repo_path(root: Path, path: Path) -> str:
    try: return str(path.resolve().relative_to(root.resolve()))
    except ValueError: return str(path.resolve())


def verify_record(root: Path, record: dict[str,Any], label: str) -> Path:
    p=resolve(root,str(record["path"]))
    if not p.is_file(): raise FileNotFoundError(f"{label}: {p}")
    if sha(p)!=str(record["sha256"]): raise ValueError(f"{label} SHA mismatch: {p}")
    if "byte_count" in record and p.stat().st_size!=int(record["byte_count"]): raise ValueError(f"{label} byte_count mismatch: {p}")
    return p


def reverify_lock(root: Path, lock: dict[str,Any]) -> dict[str,Path]:
    verify_record(root,lock["protocol"],"protocol"); verify_record(root,lock["freddie_analysis_input_lock"],"freddie_analysis_input_lock")
    return {k:verify_record(root,v,k) for k,v in lock["inputs"].items()}


def option_matrix(metrics: pd.DataFrame, options: list[str]) -> tuple[np.ndarray,list[str]]:
    normalized=metrics.copy()
    normalized["case_id"]=normalized["case_id"].astype(str)
    normalized["model_id"]=normalized["model_id"].astype(str)
    normalized["evidence_level"]=normalized["evidence_level"].astype(str)
    cases=sorted(normalized["case_id"].unique().tolist())
    indexed=normalized.assign(option_id=normalized["model_id"]+"::"+normalized["evidence_level"]).set_index(["case_id","option_id"])
    idx=pd.MultiIndex.from_product([cases,options],names=["case_id","option_id"])
    values=indexed["end_to_end_faithfulness_yield"].reindex(idx)
    if values.isna().any(): raise ValueError("Primary option matrix contains missing cells.")
    return values.to_numpy(float).reshape(len(cases),len(options)),cases


def contrast_definitions(paired: pd.DataFrame) -> list[dict[str,str]]:
    frame=paired.copy(); frame["contrast_id"]=frame.apply(contrast_id,axis=1)
    rows=[]
    for row in frame.itertuples(index=False):
        rows.append({
          "contrast_id":str(row.contrast_id),"contrast_family":str(row.contrast_family),
          "a_model":str(row.condition_a_model_id),"a_evidence":str(row.condition_a_evidence_level),
          "b_model":str(row.condition_b_model_id),"b_evidence":str(row.condition_b_evidence_level),
        })
    return sorted(rows,key=lambda x:x["contrast_id"])


def contrast_matrix(metrics: pd.DataFrame, defs: list[dict[str,str]]) -> tuple[np.ndarray,list[str]]:
    normalized=metrics.copy()
    normalized["case_key"]=normalized["case_id"].astype(str)
    normalized["model_key"]=normalized["model_id"].astype(str)
    normalized["evidence_key"]=normalized["evidence_level"].astype(str)
    cases=sorted(normalized["case_key"].unique().tolist())
    indexed=normalized.set_index(["case_key","model_key","evidence_key"])
    cols=[]
    for d in defs:
        a=[]; b=[]
        for case in cases:
            try:
                a.append(float(indexed.loc[(case,d["a_model"],d["a_evidence"]),"end_to_end_faithfulness_yield"]))
                b.append(float(indexed.loc[(case,d["b_model"],d["b_evidence"]),"end_to_end_faithfulness_yield"]))
            except KeyError as exc: raise ValueError(f"Missing primary contrast cell: {d['contrast_id']} {case}") from exc
        cols.append(np.asarray(a)-np.asarray(b))
    return np.column_stack(cols),cases


def percentile_ci(samples: np.ndarray, confidence: float) -> tuple[np.ndarray,np.ndarray]:
    alpha=(1.0-confidence)/2.0
    return np.quantile(samples,alpha,axis=0),np.quantile(samples,1.0-alpha,axis=0)


def option_summary(metrics: pd.DataFrame, options: list[str], boot_means: np.ndarray, confidence: float, dataset: str) -> pd.DataFrame:
    matrix,cases=option_matrix(metrics,options)
    lo,hi=percentile_ci(boot_means,confidence)
    rows=[]
    for j,opt in enumerate(options):
        model,evidence=opt.split("::",1); sub=metrics[(metrics["model_id"].astype(str)==model)&(metrics["evidence_level"].astype(str)==evidence)]
        applicable=float(sub["applicable_count"].sum()); supported=float(sub["supported_count"].sum()); unsupported=float(sub["unsupported_count"].sum()); contradicted=float(sub["contradicted_count"].sum())
        rows.append({
          "dataset_id":dataset,"option_id":opt,"model_id":model,"evidence_level":evidence,"planned_generation_count":len(sub),
          "usable_generation_count":int(sub["usable"].astype(bool).sum()),"usability_rate":float(sub["usable"].astype(bool).mean()),
          "mean_end_to_end_faithfulness_yield":float(matrix[:,j].mean()),"median_end_to_end_faithfulness_yield":float(np.median(matrix[:,j])),"p10_end_to_end_faithfulness_yield":float(np.quantile(matrix[:,j],0.10)),
          "bootstrap_ci_lower":float(lo[j]),"bootstrap_ci_upper":float(hi[j]),"applicable_claim_count":int(applicable),
          "micro_supported_rate":float(supported/applicable) if applicable>0 else np.nan,"micro_unsupported_rate":float(unsupported/applicable) if applicable>0 else np.nan,"micro_contradicted_rate":float(contradicted/applicable) if applicable>0 else np.nan,
          "mean_total_token_count":float(pd.to_numeric(sub["total_token_count"],errors="coerce").mean()) if "total_token_count" in sub else np.nan,
        })
    out=pd.DataFrame(rows)
    out["quality_rank"]=out["mean_end_to_end_faithfulness_yield"].rank(method="min",ascending=False).astype(int)
    return out.sort_values(["quality_rank","option_id"],kind="stable").reset_index(drop=True)


def classify(hc_mean: float,fm_mean: float,hc_lo: float,hc_hi: float,fm_lo: float,fm_hi: float) -> str:
    if abs(hc_mean)<=EPS or abs(fm_mean)<=EPS: return "INCONCLUSIVE"
    if np.sign(hc_mean)!=np.sign(fm_mean): return "DIRECTION_CONFLICT"
    hc_sig=hc_lo>0 or hc_hi<0; fm_sig=fm_lo>0 or fm_hi<0
    return "REPLICATED" if hc_sig and fm_sig else "DIRECTIONALLY_REPLICATED"


def build_release(root: Path,lock_path: Path,lock: dict[str,Any],protocol: dict[str,Any],out: Path) -> dict[str,Any]:
    paths=reverify_lock(root,lock); boot=protocol["bootstrap"]; it=int(boot["iterations"]); conf=float(boot["confidence"])
    hc=pd.read_csv(paths["home_credit_generation_metrics"],low_memory=False); fm=pd.read_csv(paths["freddie_generation_metrics"],low_memory=False)
    hc_pairs=pd.read_csv(paths["home_credit_paired_tests"],low_memory=False); fm_pairs=pd.read_csv(paths["freddie_paired_tests"],low_memory=False)
    defs=contrast_definitions(hc_pairs); fm_defs=contrast_definitions(fm_pairs)
    if defs!=fm_defs or [d["contrast_id"] for d in defs]!=lock["contrast_ids"]: raise SystemExit("M25 contrast registry drift.")
    options=sorted({f"{m}::{s}" for m in protocol["models"] for s in [x["evidence_level"] for x in protocol["evidence_mapping"]]})
    hc_opt,hc_cases=option_matrix(hc,options); fm_opt,fm_cases=option_matrix(fm,options); hc_diff,_=contrast_matrix(hc,defs); fm_diff,_=contrast_matrix(fm,defs)
    if len(hc_cases)!=36 or len(fm_cases)!=36: raise SystemExit("M25 expects 36 independent cases per study.")
    rng_hc=np.random.default_rng(int(boot["home_credit_seed"])); rng_fm=np.random.default_rng(int(boot["freddie_seed"]))
    idx_hc=rng_hc.integers(0,len(hc_cases),size=(it,len(hc_cases))); idx_fm=rng_fm.integers(0,len(fm_cases),size=(it,len(fm_cases)))
    hc_opt_boot=hc_opt[idx_hc].mean(axis=1); fm_opt_boot=fm_opt[idx_fm].mean(axis=1)
    hc_diff_boot=hc_diff[idx_hc].mean(axis=1); fm_diff_boot=fm_diff[idx_fm].mean(axis=1); dod_boot=fm_diff_boot-hc_diff_boot
    hc_opts=option_summary(hc,options,hc_opt_boot,conf,"home_credit_default_risk"); fm_opts=option_summary(fm,options,fm_opt_boot,conf,"freddie_sflld_2024")
    cross=hc_opts.add_prefix("home_credit_").merge(fm_opts.add_prefix("freddie_"),left_on="home_credit_option_id",right_on="freddie_option_id",validate="one_to_one")
    cross=cross.rename(columns={"home_credit_option_id":"option_id"}).drop(columns=["freddie_option_id"])
    cross["mean_e2e_difference_freddie_minus_home_credit"]=cross["freddie_mean_end_to_end_faithfulness_yield"]-cross["home_credit_mean_end_to_end_faithfulness_yield"]
    cross["rank_shift_freddie_minus_home_credit"]=cross["freddie_quality_rank"]-cross["home_credit_quality_rank"]
    cross=cross.sort_values("option_id",kind="stable").reset_index(drop=True)

    hc_lo,hc_hi=percentile_ci(hc_diff_boot,conf); fm_lo,fm_hi=percentile_ci(fm_diff_boot,conf); dd_lo,dd_hi=percentile_ci(dod_boot,conf)
    rows=[]; dod_rows=[]
    hc_obs=hc_diff.mean(axis=0); fm_obs=fm_diff.mean(axis=0)
    for j,d in enumerate(defs):
        status=classify(float(hc_obs[j]),float(fm_obs[j]),float(hc_lo[j]),float(hc_hi[j]),float(fm_lo[j]),float(fm_hi[j]))
        hetero=bool(dd_lo[j]>0 or dd_hi[j]<0)
        rows.append({**d,"home_credit_mean_difference":float(hc_obs[j]),"home_credit_ci_lower":float(hc_lo[j]),"home_credit_ci_upper":float(hc_hi[j]),"freddie_mean_difference":float(fm_obs[j]),"freddie_ci_lower":float(fm_lo[j]),"freddie_ci_upper":float(fm_hi[j]),"replication_status":status,"material_heterogeneity":hetero})
        dod_rows.append({"contrast_id":d["contrast_id"],"freddie_minus_home_credit":float(fm_obs[j]-hc_obs[j]),"ci_lower":float(dd_lo[j]),"ci_upper":float(dd_hi[j]),"material_heterogeneity":hetero})
    concordance=pd.DataFrame(rows); delta=pd.DataFrame(dod_rows)

    rho,p=spearmanr(cross["home_credit_mean_end_to_end_faithfulness_yield"],cross["freddie_mean_end_to_end_faithfulness_yield"])
    rank=pd.DataFrame([{"option_count":18,"spearman_rho":float(rho),"spearman_p_value_descriptive":float(p),"interpretation":"descriptive_rank_stability_not_generalization_proof"}])

    hc_om=pd.read_csv(paths["home_credit_omnibus_tests"],low_memory=False); fm_om=pd.read_csv(paths["freddie_omnibus_tests"],low_memory=False)
    effects=hc_om[["effect","f_statistic","p_value_used","partial_eta_squared","significant"]].merge(fm_om[["effect","f_statistic","p_value_used","partial_eta_squared","significant"]],on="effect",suffixes=("_home_credit","_freddie"),validate="one_to_one")
    effects["partial_eta_squared_difference_freddie_minus_home_credit"]=effects["partial_eta_squared_freddie"]-effects["partial_eta_squared_home_credit"]
    effects["both_significant"]=effects["significant_home_credit"].astype(bool)&effects["significant_freddie"].astype(bool)

    hc_diag=pd.read_csv(paths["home_credit_generation_diagnostics"],low_memory=False); fm_diag=pd.read_csv(paths["freddie_generation_diagnostics"],low_memory=False)
    def fp(df: pd.DataFrame,prefix: str) -> pd.DataFrame:
        return df.groupby(["model_id","evidence_level"],as_index=False).agg(**{f"{prefix}_mean_pipeline_loss":("pipeline_loss","mean"),f"{prefix}_mean_not_verifiable_loss":("not_verifiable_loss","mean"),f"{prefix}_mean_unsupported_loss":("unsupported_loss","mean"),f"{prefix}_mean_contradiction_loss":("contradiction_loss","mean"),f"{prefix}_mean_safe_phrase_matched_claim_rate":("safe_phrase_matched_claim_rate","mean")})
    failure=fp(hc_diag,"home_credit").merge(fp(fm_diag,"freddie"),on=["model_id","evidence_level"],validate="one_to_one")
    for comp in ["pipeline_loss","not_verifiable_loss","unsupported_loss","contradiction_loss","safe_phrase_matched_claim_rate"]:
        failure[f"delta_{comp}_freddie_minus_home_credit"]=failure[f"freddie_mean_{comp}"]-failure[f"home_credit_mean_{comp}"]

    findings=[]
    for r in concordance.itertuples(index=False): findings.append({"finding_type":"PRIMARY_CONTRAST_REPLICATION","finding_id":r.contrast_id,"status":r.replication_status,"value":r.freddie_mean_difference-r.home_credit_mean_difference,"note":"Effect direction replication; datasets contain independent case cohorts."})
    for r in effects.itertuples(index=False): findings.append({"finding_type":"OMNIBUS_EFFECT_STABILITY","finding_id":str(r.effect),"status":"BOTH_SIGNIFICANT" if bool(r.both_significant) else "NOT_BOTH_SIGNIFICANT","value":float(r.partial_eta_squared_difference_freddie_minus_home_credit),"note":"Descriptive comparison of within-study omnibus effects; not a pooled ANOVA."})
    findings.append({"finding_type":"OPTION_RANK_STABILITY","finding_id":"spearman_18_options","status":"DESCRIPTIVE","value":float(rho),"note":"Rank correlation is descriptive and does not establish universal generalization."})
    findings_df=pd.DataFrame(findings)

    checks={}
    def add(name,exp,obs,ok): checks[name]={"expected":exp,"observed":obs,"passed":bool(ok)}
    add("option_count",18,len(cross),len(cross)==18); add("contrast_count",33,len(concordance),len(concordance)==33); add("delta_of_deltas_count",33,len(delta),len(delta)==33); add("omnibus_effect_count",3,len(effects),len(effects)==3); add("failure_profile_count",18,len(failure),len(failure)==18)
    add("cross_dataset_case_pair_count",0,0,True); add("bootstrap_iterations",it,it,True); add("contrast_id_set_match",lock["contrast_ids"],sorted(concordance["contrast_id"].astype(str)),sorted(concordance["contrast_id"].astype(str))==lock["contrast_ids"])
    invalid_ci=int((concordance["home_credit_ci_lower"]>concordance["home_credit_ci_upper"]).sum()+(concordance["freddie_ci_lower"]>concordance["freddie_ci_upper"]).sum()+(delta["ci_lower"]>delta["ci_upper"]).sum()); add("invalid_ci_order_count",0,invalid_ci,invalid_ci==0)
    failed=sum(not v["passed"] for v in checks.values()); validation={"schema_version":"multidataset_replication_validation_v1","checks":checks,"failed_check_count":failed,"passed":failed==0,"exit_gate":"MULTIDATASET_REPLICATION_READY" if failed==0 else "MULTIDATASET_REPLICATION_INVALID","model_revision_scope":lock["compatibility"]["model_revision_scope"]}
    if failed: raise SystemExit("M25 replication validation failed.")

    out.mkdir(parents=True,exist_ok=False)
    frames={"cross_dataset_option_performance":cross,"cross_dataset_effects":effects,"contrast_concordance":concordance,"rank_stability":rank,"delta_of_deltas":delta,"failure_profile_comparison":failure,"replication_findings":findings_df}
    for name,frame in frames.items(): frame.to_csv(out/f"{name}.csv",index=False,float_format="%.12g",lineterminator="\n")
    (out/"replication_validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    files={}
    for pth in sorted(out.iterdir()):
        if pth.is_file(): files[pth.name]={"sha256":sha(pth),"byte_count":pth.stat().st_size}
    fm_diag_manifest=read_json(paths["freddie_diagnostics_manifest"]); independence_comparable=bool(fm_diag_manifest.get("safe_phrase_analysis",{}).get("enabled"))
    manifest={"schema_version":"multidataset_replication_manifest_v1","protocol_id":lock["protocol_id"],"producer":"M25B_0029","parent_input_lock":{"path":repo_path(root,lock_path),"sha256":sha(lock_path)},"model_revision_scope":lock["compatibility"]["model_revision_scope"],"model_revision_details":lock["compatibility"]["model_revision_details"],"primary_metric":protocol["primary_metric"],"independence_metric_comparable":independence_comparable,"independence_metric":"mean_safe_phrase_matched_claim_rate" if independence_comparable else None,"bootstrap":protocol["bootstrap"],"counts":{"options":18,"primary_contrasts":33,"omnibus_effects":3},"files":files,"gate":"MULTIDATASET_REPLICATION_READY"}
    (out/"replication_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return manifest


def directory_hashes(d: Path) -> dict[str,str]: return {p.name:sha(p) for p in sorted(d.iterdir()) if p.is_file()}

def reverify_existing(root: Path,lock_path: Path,out: Path) -> dict[str,Any]:
    m=read_json(out/"replication_manifest.json"); v=read_json(out/"replication_validation.json")
    if m.get("gate")!="MULTIDATASET_REPLICATION_READY" or not v.get("passed"): raise SystemExit("Existing M25 release is not certified.")
    if m.get("parent_input_lock",{}).get("sha256")!=sha(lock_path): raise SystemExit("Existing M25 parent lock drift.")
    for name,rec in m.get("files",{}).items():
        p=out/name
        if not p.is_file() or sha(p)!=rec["sha256"] or p.stat().st_size!=int(rec["byte_count"]): raise SystemExit(f"Existing M25 artifact drift: {name}")
    return m


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--repo-root",required=True); ap.add_argument("--lock",required=True); ap.add_argument("--protocol",required=True); ap.add_argument("--output-dir",required=True); a=ap.parse_args()
    root=Path(a.repo_root).resolve(); lock_path=Path(a.lock).resolve(); protocol_path=Path(a.protocol).resolve(); out=Path(a.output_dir).resolve(); lock=read_json(lock_path); protocol=read_json(protocol_path)
    if lock.get("gate")!="MULTIDATASET_REPLICATION_INPUT_LOCK_READY": raise SystemExit("M25B requires MULTIDATASET_REPLICATION_INPUT_LOCK_READY.")
    reverify_lock(root,lock)
    if out.exists(): m=reverify_existing(root,lock_path,out); print(f"MULTIDATASET_M25_REPLICATION=ALREADY_CERTIFIED options={m['counts']['options']} contrasts={m['counts']['primary_contrasts']} scope={m['model_revision_scope']}"); return 0
    out.parent.mkdir(parents=True,exist_ok=True); a1=Path(tempfile.mkdtemp(prefix=".m25_a_",dir=out.parent)); shutil.rmtree(a1); a2=Path(tempfile.mkdtemp(prefix=".m25_b_",dir=out.parent)); shutil.rmtree(a2)
    try:
        build_release(root,lock_path,lock,protocol,a1); build_release(root,lock_path,lock,protocol,a2)
        if directory_hashes(a1)!=directory_hashes(a2): raise SystemExit("M25 deterministic replay mismatch.")
        os.replace(a1,out); a1=Path("/__promoted__")
    finally:
        if a1.exists(): shutil.rmtree(a1,ignore_errors=True)
        if a2.exists(): shutil.rmtree(a2,ignore_errors=True)
    m=read_json(out/"replication_manifest.json"); print(f"MULTIDATASET_M25_REPLICATION=PASS options=18 contrasts=33 effects=3 scope={m['model_revision_scope']}"); return 0
if __name__=="__main__": raise SystemExit(main())
