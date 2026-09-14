from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.python.robustness.common import read_json, repo_relative, resolve_record, sha256_file
from .source_identity import analytical_release_source_files, build_source_identity, source_relevant_git_status


def _json_value(value: Any) -> Any:
    if value is None or (isinstance(value,float) and np.isnan(value)): return None
    if isinstance(value,(np.integer,)): return int(value)
    if isinstance(value,(np.floating,)): return float(value)
    if isinstance(value,(np.bool_,)): return bool(value)
    return value


def _git(root: Path,*args: str) -> str:
    result=subprocess.run(["git",*args],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
    return result.stdout.strip()


def collect_artifacts(root: Path,lock: dict[str,Any]) -> dict[str,dict[str,Any]]:
    artifacts={}
    for name,rec in lock["source_artifacts"].items(): artifacts[name]=rec
    for name,rec in lock["parent_artifacts"].items(): artifacts[name]=rec
    m25_lock=read_json(resolve_record(root,lock["parent_artifacts"]["m25_input_lock"],"m25_input_lock"))
    for name,rec in m25_lock["inputs"].items(): artifacts[f"m25::{name}"]=rec
    return artifacts


def artifact_index(root: Path,artifacts: dict[str,dict[str,Any]]) -> pd.DataFrame:
    rows=[]
    for artifact_id,rec in sorted(artifacts.items()):
        path=resolve_record(root,rec,artifact_id)
        rows.append({"source_artifact_id":artifact_id,"source_path":repo_relative(root,path),"source_sha256":sha256_file(path),"byte_count":path.stat().st_size})
    return pd.DataFrame(rows)


def _apply_filter(frame: pd.DataFrame,filters: dict[str,Any]) -> pd.DataFrame:
    output=frame
    for column,value in filters.items():
        if column not in output.columns: raise ValueError(f"Unknown filter column {column}")
        if value is None: output=output.loc[output[column].isna()]
        elif isinstance(value,bool): output=output.loc[output[column].astype(bool).eq(value)]
        else: output=output.loc[output[column].astype(str).eq(str(value))]
    return output


def _read_csv_artifact(root: Path,artifacts: dict[str,dict[str,Any]],artifact_id: str) -> tuple[Path,pd.DataFrame]:
    path=resolve_record(root,artifacts[artifact_id],artifact_id)
    return path,pd.read_csv(path,low_memory=False)


def _record(artifact_id: str,artifact_sha: str,report_id: str,family: str,scope: str,metric_id: str,value: Any,population: str,denominator: Any,unit: str,lane: str,field: str,filters: dict[str,Any],aggregation: str) -> dict[str,Any]:
    return {"report_number_id":report_id,"family":family,"dataset_scope":scope,"metric_id":metric_id,"value":_json_value(value),"population_id":population,"denominator":_json_value(denominator),"unit":unit,"analysis_lane":lane,"source_artifact_id":artifact_id,"source_sha256":artifact_sha,"source_field":field,"source_filter":filters,"aggregation":aggregation}


def _contrast_id(row: pd.Series) -> str:
    if str(row["contrast_family"])=="model_within_evidence": return f"model_within_evidence::{row['context_evidence_level']}::{row['condition_a_model_id']}::{row['condition_b_model_id']}"
    return f"evidence_vs_s0::{row['context_model_id']}::{row['condition_a_evidence_level']}"


def build_report_numbers(root: Path,protocol: dict[str,Any],artifacts: dict[str,dict[str,Any]]) -> list[dict[str,Any]]:
    records=[]
    dataset_specs=[
        ("HOME_CREDIT","home_credit_default_risk","home_credit_generation_metrics","m25::home_credit_generation_diagnostics"),
        ("FREDDIE","freddie_sflld_2024","freddie_generation_metrics","m25::freddie_generation_diagnostics"),
    ]
    for scope,dataset_id,artifact_id,diagnostics_id in dataset_specs:
        path,frame=_read_csv_artifact(root,artifacts,artifact_id); artifact_sha=sha256_file(path)
        planned=len(frame); usable=int(frame["usable"].astype(bool).sum()); final_claims=int(pd.to_numeric(frame["claim_count"]).sum())
        records.extend([
            _record(artifact_id,artifact_sha,f"dataset::{scope}::planned_generations","DATASET_SUMMARY",scope,"planned_generations",planned,"PLANNED_648",planned,"count","PRIMARY","__row_count__",{},"COUNT_ROWS"),
            _record(artifact_id,artifact_sha,f"dataset::{scope}::usable_generations","DATASET_SUMMARY",scope,"usable_generations",usable,"PLANNED_648",planned,"count","PRIMARY","usable",{},"SUM"),
            _record(artifact_id,artifact_sha,f"dataset::{scope}::unusable_generations","DATASET_SUMMARY",scope,"unusable_generations",planned-usable,"PLANNED_648",planned,"count","PRIMARY","__row_count__",{"usable":False},"COUNT_ROWS"),
            _record(artifact_id,artifact_sha,f"dataset::{scope}::final_claims","DATASET_SUMMARY",scope,"final_claims",final_claims,"CLAIM_VALIDATION_RESULT",final_claims,"count","PRIMARY","claim_count",{},"SUM"),
            _record(artifact_id,artifact_sha,f"dataset::{scope}::mean_e2e","DATASET_SUMMARY",scope,"end_to_end_faithfulness_yield",float(pd.to_numeric(frame["end_to_end_faithfulness_yield"]).mean()),"PLANNED_648",planned,"proportion","PRIMARY","end_to_end_faithfulness_yield",{},"MEAN"),
        ])
        for status,column in [("SUPPORTED","supported_count"),("NOT_VERIFIABLE","not_verifiable_count"),("UNSUPPORTED","unsupported_count"),("CONTRADICTED","contradicted_count"),("NOT_APPLICABLE","not_applicable_count")]:
            records.append(_record(artifact_id,artifact_sha,f"dataset::{scope}::status::{status}","DATASET_SUMMARY",scope,f"validation_status_count::{status}",int(pd.to_numeric(frame[column]).sum()),"CLAIM_VALIDATION_RESULT",final_claims,"count","PRIMARY",column,{},"SUM"))
        for metric_id in ["resolved_faithfulness","verifiability","conservative_faithfulness"]:
            non_null=int(pd.to_numeric(frame[metric_id],errors="coerce").notna().sum())
            records.append(_record(artifact_id,artifact_sha,f"dataset::{scope}::{metric_id}::mean","CONDITIONAL_QUALITY",scope,metric_id,float(pd.to_numeric(frame[metric_id],errors="coerce").mean()),"CONDITIONAL_GENERATION",non_null,"proportion","SECONDARY",metric_id,{},"MEAN"))
        for (model,evidence),group in frame.groupby(["model_id","evidence_level"],sort=True):
            filters={"model_id":str(model),"evidence_level":str(evidence)}
            records.append(_record(artifact_id,artifact_sha,f"option::{scope}::{model}::{evidence}::mean_e2e","OPTION_PERFORMANCE",scope,"end_to_end_faithfulness_yield",float(group["end_to_end_faithfulness_yield"].mean()),"OPTION_PLANNED_36",len(group),"proportion","PRIMARY","end_to_end_faithfulness_yield",filters,"MEAN"))

        dpath,diagnostics=_read_csv_artifact(root,artifacts,diagnostics_id); dsha=sha256_file(dpath)
        if len(diagnostics)!=planned:
            raise ValueError(f"{scope} diagnostics must retain every planned generation.")
        for column,metric_id in [
            ("pipeline_loss","pipeline_loss"),
            ("not_verifiable_loss","not_verifiable_loss"),
            ("unsupported_loss","unsupported_loss"),
            ("contradiction_loss","contradiction_loss"),
            ("safe_phrase_matched_claim_rate","safe_phrase_matched_claim_rate"),
        ]:
            if column in diagnostics.columns:
                records.append(_record(diagnostics_id,dsha,f"diagnostic::{scope}::{metric_id}::mean","MECHANISM",scope,metric_id,float(pd.to_numeric(diagnostics[column],errors="coerce").mean()),"PLANNED_648",planned,"proportion","DIAGNOSTIC",column,{},"MEAN"))

    for scope,prefix in [("HOME_CREDIT","home_credit"),("FREDDIE","freddie")]:
        omnibus_id=f"m25::{prefix}_omnibus_tests"; path,omnibus=_read_csv_artifact(root,artifacts,omnibus_id); artifact_sha=sha256_file(path)
        for _,row in omnibus.iterrows():
            filters={"effect":str(row["effect"])}; denom=int(row["subject_count"])
            for field,metric,unit in [("p_value_used","omnibus_p_value","probability"),("partial_eta_squared","partial_eta_squared","effect_size")]:
                records.append(_record(omnibus_id,artifact_sha,f"omnibus::{scope}::{row['effect']}::{field}","OMNIBUS_EFFECT",scope,metric,row[field],"CANONICAL_CASE",denom,unit,"PRIMARY",field,filters,"DIRECT_SINGLE_ROW"))
        pairs_id=f"m25::{prefix}_paired_tests"; ppath,pairs=_read_csv_artifact(root,artifacts,pairs_id); psha=sha256_file(ppath)
        for _,row in pairs.iterrows():
            cid=_contrast_id(row); filters={k:_json_value(row[k]) for k in ["contrast_family","context_model_id","context_evidence_level","condition_a_model_id","condition_a_evidence_level","condition_b_model_id","condition_b_evidence_level"]}
            denom=int(row["observed_pair_count"])
            for field,metric,unit in [("mean_difference","planned_contrast_mean_difference","proportion_difference"),("adjusted_p_value","planned_contrast_adjusted_p_value","probability")]:
                records.append(_record(pairs_id,psha,f"contrast::{scope}::{cid}::{field}","PLANNED_CONTRAST",scope,metric,row[field],"PAIRED_CANONICAL_CASE",denom,unit,"PRIMARY",field,filters,"DIRECT_SINGLE_ROW"))

    cc_id="m25_contrast_concordance"; ccpath,cc=_read_csv_artifact(root,artifacts,cc_id); ccsha=sha256_file(ccpath)
    for _,row in cc.iterrows():
        filters={"contrast_id":str(row["contrast_id"])}
        records.append(_record(cc_id,ccsha,f"replication::{row['contrast_id']}::status","REPLICATION","CROSS_DATASET","replication_status",row["replication_status"],"CROSS_DATASET_STUDY_EFFECT",2,"category","REPLICATION","replication_status",filters,"DIRECT_SINGLE_ROW"))
    for status in ["REPLICATED","DIRECTIONALLY_REPLICATED","DIRECTION_CONFLICT","INCONCLUSIVE"]:
        filters={"replication_status":status}
        records.append(_record(cc_id,ccsha,f"replication::status_count::{status}","REPLICATION","CROSS_DATASET",f"replication_status_count::{status}",len(_apply_filter(cc,filters)),"PLANNED_CONTRAST_SET_33",33,"count","REPLICATION","__row_count__",filters,"COUNT_ROWS"))
    heterogeneity_filters={"material_heterogeneity":True}
    records.append(_record(cc_id,ccsha,"replication::material_heterogeneity_count","REPLICATION","CROSS_DATASET","material_heterogeneity_contrast_count",len(_apply_filter(cc,heterogeneity_filters)),"PLANNED_CONTRAST_SET_33",33,"count","REPLICATION","__row_count__",heterogeneity_filters,"COUNT_ROWS"))
    rank_id="m25_rank_stability"; rpath,rank=_read_csv_artifact(root,artifacts,rank_id); rsha=sha256_file(rpath)
    if len(rank)!=1: raise ValueError("M25 rank stability must contain exactly one certified summary row.")
    rr=rank.iloc[0]
    records.append(_record(rank_id,rsha,"replication::option_rank_spearman","REPLICATION","CROSS_DATASET","spearman_rho",rr["spearman_rho"],"OPTION_SET_18",18,"correlation","REPLICATION","spearman_rho",{},"DIRECT_SINGLE_ROW"))

    rec_id="m26_recommendations"; recpath,recs=_read_csv_artifact(root,artifacts,rec_id); recsha=sha256_file(recpath)
    for scope_id,scope in [("HOME_CREDIT_PRIMARY","HOME_CREDIT"),("FREDDIE_PRIMARY","FREDDIE")]:
        subset=_apply_filter(recs,{"recommendation_scope":scope_id})
        if len(subset)!=1: raise ValueError(f"Expected one {scope_id} recommendation row.")
        records.append(_record(rec_id,recsha,f"decision::{scope_id}::option","DECISION",scope,"primary_option_id",subset.iloc[0]["option_id"],"DECISION_OPTION_SET",18,"option_id","DECISION","option_id",{"recommendation_scope":scope_id},"DIRECT_SINGLE_ROW"))
    robust_filters={"recommendation_scope":"CROSS_DATASET_ROBUST","status":"SELECTED"}; robust_count=len(_apply_filter(recs,robust_filters))
    records.append(_record(rec_id,recsha,"decision::cross_dataset_robust_selected_count","DECISION","CROSS_DATASET","robust_selected_count",robust_count,"ROBUST_RECOMMENDATION_SLOT",1,"count","DECISION","__row_count__",robust_filters,"COUNT_ROWS"))
    for scenario_id in ["QUALITY_FIRST","RELIABILITY_FIRST","BALANCED","EFFICIENCY_AWARE","INDEPENDENCE_SENSITIVE"]:
        filters={"recommendation_scope":"CROSS_DATASET_ROBUST","scenario_id":scenario_id}
        subset=_apply_filter(recs,filters)
        if len(subset)!=1: raise ValueError(f"Expected one robust recommendation row for {scenario_id}.")
        records.append(_record(rec_id,recsha,f"decision::scenario::{scenario_id}::status","DECISION","CROSS_DATASET","scenario_recommendation_status",subset.iloc[0]["status"],"DECISION_SCENARIO",1,"category","DECISION","status",filters,"DIRECT_SINGLE_ROW"))

    robust_id="m27::robustness_summary.csv"; rbpath,rb=_read_csv_artifact(root,artifacts,robust_id); rbsha=sha256_file(rbpath)
    for _,row in rb.iterrows():
        filters={"dimension":str(row["dimension"])}
        records.append(_record(robust_id,rbsha,f"robustness::{row['dimension']}::status","ROBUSTNESS","CROSS_DATASET",f"{row['dimension']}_robustness_status",row["status"],"ROBUSTNESS_REGISTRY",1,"category","SENSITIVITY","status",filters,"DIRECT_SINGLE_ROW"))
    margin_id="m27::margin_sensitivity_summary.csv"; mpath,margin_summary=_read_csv_artifact(root,artifacts,margin_id); msha=sha256_file(mpath)
    for _,row in margin_summary.iterrows():
        filters={"margin_lane_id":str(row["margin_lane_id"])}
        records.append(_record(margin_id,msha,f"robustness::margin::{row['margin_lane_id']}::pool","ROBUSTNESS","CROSS_DATASET","active_pool_mode",row["active_pool_mode"],"MARGIN_SENSITIVITY_LANE",1,"category","SENSITIVITY","active_pool_mode",filters,"DIRECT_SINGLE_ROW"))
        records.append(_record(margin_id,msha,f"robustness::margin::{row['margin_lane_id']}::primary_candidate_count","ROBUSTNESS","CROSS_DATASET","robust_primary_candidate_count",row["robust_primary_candidate_count"],"MARGIN_SENSITIVITY_LANE",1,"count","SENSITIVITY","robust_primary_candidate_count",filters,"DIRECT_SINGLE_ROW"))
    artifact_paths={artifact_id: repo_relative(root, resolve_record(root, rec, artifact_id)) for artifact_id,rec in artifacts.items()}
    for record in records:
        record["source_path"]=artifact_paths[record["source_artifact_id"]]
    ids=[r["report_number_id"] for r in records]
    if len(ids)!=len(set(ids)): raise ValueError("Duplicate report_number_id generated.")
    return records


def trace_value(frame: pd.DataFrame,record: dict[str,Any]) -> Any:
    subset=_apply_filter(frame,record["source_filter"]); operation=record["aggregation"]; field=record["source_field"]
    if operation=="COUNT_ROWS": return int(len(subset))
    if field not in subset.columns: raise ValueError(f"Missing source field {field}")
    if operation=="DIRECT_SINGLE_ROW":
        if len(subset)!=1: raise ValueError(f"DIRECT_SINGLE_ROW expected 1 row for {record['report_number_id']}, got {len(subset)}")
        return _json_value(subset.iloc[0][field])
    if operation=="SUM": return _json_value(pd.to_numeric(subset[field]).sum())
    if operation=="MEAN": return _json_value(pd.to_numeric(subset[field]).mean())
    raise ValueError(operation)


def trace_denominator(frame: pd.DataFrame, record: dict[str,Any]) -> Any:
    population=str(record["population_id"]); subset=_apply_filter(frame,record["source_filter"]); field=record["source_field"]
    if population=="PLANNED_648": return int(len(frame))
    if population=="OPTION_PLANNED_36": return int(len(subset))
    if population=="CLAIM_VALIDATION_RESULT":
        if "claim_count" not in frame.columns: raise ValueError("CLAIM_VALIDATION_RESULT denominator requires claim_count.")
        return int(pd.to_numeric(frame["claim_count"]).sum())
    if population=="CONDITIONAL_GENERATION":
        if field not in frame.columns: raise ValueError(f"Conditional denominator field missing: {field}")
        return int(pd.to_numeric(frame[field],errors="coerce").notna().sum())
    if population=="CANONICAL_CASE":
        if len(subset)!=1 or "subject_count" not in subset.columns: raise ValueError("CANONICAL_CASE denominator requires one row with subject_count.")
        return int(subset.iloc[0]["subject_count"])
    if population=="PAIRED_CANONICAL_CASE":
        if len(subset)!=1 or "observed_pair_count" not in subset.columns: raise ValueError("PAIRED_CANONICAL_CASE denominator requires one row with observed_pair_count.")
        return int(subset.iloc[0]["observed_pair_count"])
    constants={
        "CROSS_DATASET_STUDY_EFFECT":2,
        "OPTION_SET_18":18,
        "PLANNED_CONTRAST_SET_33":33,
        "DECISION_OPTION_SET":18,
        "ROBUST_RECOMMENDATION_SLOT":1,
        "DECISION_SCENARIO":1,
        "ROBUSTNESS_REGISTRY":1,
        "MARGIN_SENSITIVITY_LANE":1,
    }
    if population in constants: return constants[population]
    raise ValueError(f"Unknown population denominator contract: {population}")


def validate_report_numbers(root: Path,records: list[dict[str,Any]],artifacts: dict[str,dict[str,Any]]) -> dict[str,Any]:
    frames={}; mismatches=[]
    for record in records:
        aid=record["source_artifact_id"]; path=resolve_record(root,artifacts[aid],aid)
        if record["source_sha256"]!=sha256_file(path): mismatches.append({"report_number_id":record["report_number_id"],"reason":"SOURCE_SHA"}); continue
        if aid not in frames: frames[aid]=pd.read_csv(path,low_memory=False)
        observed=trace_value(frames[aid],record); expected=record["value"]
        if isinstance(expected,(int,float)) and isinstance(observed,(int,float)) and expected is not None and observed is not None: equal=bool(np.isclose(float(expected),float(observed),rtol=1e-10,atol=1e-12,equal_nan=True))
        else: equal=str(expected)==str(observed)
        if not equal: mismatches.append({"report_number_id":record["report_number_id"],"reason":"VALUE","expected":expected,"observed":observed})
        try:
            observed_denominator=trace_denominator(frames[aid],record)
        except Exception as exc:
            mismatches.append({"report_number_id":record["report_number_id"],"reason":"DENOMINATOR_TRACE_ERROR","error":str(exc)})
            continue
        expected_denominator=record.get("denominator")
        if expected_denominator is None or not bool(np.isclose(float(expected_denominator),float(observed_denominator),rtol=0.0,atol=0.0)):
            mismatches.append({"report_number_id":record["report_number_id"],"reason":"DENOMINATOR","expected":expected_denominator,"observed":observed_denominator})
    return {"checked_report_numbers":len(records),"mismatch_count":len(mismatches),"mismatches":mismatches,"passed":not mismatches}


def build_limitations(root: Path,protocol: dict[str,Any],artifacts: dict[str,dict[str,Any]]) -> pd.DataFrame:
    base={
        "AUTOMATED_VALIDATOR_NOT_HUMAN_GROUND_TRUTH":("MEASUREMENT","GLOBAL","HIGH","Automated deterministic validation is not human ground truth.","All faithfulness claims","Report validator scope and human-calibration status explicitly.","m27::human_calibration_status.json"),
        "TWO_CREDIT_RISK_DATASETS_ONLY":("GENERALIZATION","GLOBAL","HIGH","Replication covers two credit-risk datasets only.","Cross-dataset generalization","Do not claim universal-domain generalization.","m25_manifest"),
        "NO_UNIVERSAL_DOMAIN_GENERALIZATION":("GENERALIZATION","GLOBAL","HIGH","Results do not establish universal-domain generalization.","External validity claims","Restrict conclusions to the evaluated credit-risk settings.","m25_manifest"),
        "MONETARY_COST_NOT_COMPARABLE":("EFFICIENCY","GLOBAL","MEDIUM","Monetary cost is not comparable across provider API and self-hosted infrastructure.","Cost recommendations","Exclude monetary cost from robust decision axes.","m26_manifest"),
        "CROSS_RUNTIME_LATENCY_NOT_FULLY_COMPARABLE":("EFFICIENCY","GLOBAL","MEDIUM","Cross-runtime latency is not a fully comparable hard decision axis.","Latency recommendations","Keep latency descriptive rather than a robust hard axis.","m26_manifest"),
    }
    rows=[]
    for lid in protocol["required_limitations"]:
        category,scope,severity,statement,affected,mitigation,evidence=base[lid]; rows.append({"limitation_id":lid,"category":category,"scope":scope,"severity":severity,"status":"ACTIVE","statement":statement,"affected_claims":affected,"mitigation":mitigation,"source_evidence":evidence})
    m25_manifest=read_json(resolve_record(root,artifacts["m25_manifest"],"m25_manifest")); scope=str(m25_manifest.get("model_revision_scope"))
    if scope=="MODEL_REVISION_UNKNOWN": rows.append({"limitation_id":"MODEL_REVISION_UNKNOWN","category":"REPLICATION","scope":"CROSS_DATASET","severity":"HIGH","status":"ACTIVE","statement":"Exact cross-dataset model-revision equivalence could not be established.","affected_claims":"Exact-model replication wording","mitigation":"Describe results as protocol/model-identity replication with revision uncertainty.","source_evidence":"m25_manifest"})
    elif scope=="MODEL_FAMILY_PROTOCOL_REPLICATION": rows.append({"limitation_id":"MODEL_REVISION_MISMATCH","category":"REPLICATION","scope":"CROSS_DATASET","severity":"HIGH","status":"ACTIVE","statement":"At least one exact model revision differs across datasets.","affected_claims":"Exact-model replication wording","mitigation":"Describe replication at model-family/protocol level.","source_evidence":"m25_manifest"})
    _,rb=_read_csv_artifact(root,artifacts,"m27::robustness_summary.csv")
    for row in rb.itertuples(index=False):
        if str(row.status)!="PRIMARY_STABLE":
            rows.append({"limitation_id":f"M27_{str(row.dimension).upper()}_SENSITIVITY","category":"ROBUSTNESS","scope":"CROSS_DATASET","severity":"MEDIUM","status":"ACTIVE","statement":f"The {row.dimension} robustness lane is classified as {row.status}.","affected_claims":"Robustness of primary analytical conclusions","mitigation":"Report the certified primary result together with this sensitivity result; do not replace the primary result.","source_evidence":"m27::robustness_summary.csv"})
    return pd.DataFrame(rows).sort_values("limitation_id",kind="stable").reset_index(drop=True)


def build_findings(root: Path,records: list[dict[str,Any]],artifacts: dict[str,dict[str,Any]],limitations: pd.DataFrame) -> pd.DataFrame:
    record_ids=set(r["report_number_id"] for r in records); limitation_ids=set(limitations["limitation_id"].astype(str)); rows=[]
    m25_manifest=read_json(resolve_record(root,artifacts["m25_manifest"],"m25_manifest")); scope=str(m25_manifest.get("model_revision_scope"))
    rows.append({"finding_id":"F_REPLICATION_SCOPE","research_question_id":"RQ4","finding_type":"REPLICATION_SCOPE","dataset_scope":"CROSS_DATASET","status":scope,"supporting_report_numbers":"replication::option_rank_spearman","robustness_status":"DESCRIPTIVE","limitation_refs":"MODEL_REVISION_UNKNOWN" if "MODEL_REVISION_UNKNOWN" in limitation_ids else ("MODEL_REVISION_MISMATCH" if "MODEL_REVISION_MISMATCH" in limitation_ids else "")})
    robust_id="decision::cross_dataset_robust_selected_count"; selected=next(r["value"] for r in records if r["report_number_id"]==robust_id)
    rows.append({"finding_id":"F_ROBUST_DECISION","research_question_id":"RQ5","finding_type":"ROBUST_RECOMMENDATION_STATUS","dataset_scope":"CROSS_DATASET","status":"NO_ROBUST_RECOMMENDATION" if int(selected)==0 else "ROBUST_RECOMMENDATION_AVAILABLE","supporting_report_numbers":robust_id,"robustness_status":"PRIMARY_CERTIFIED","limitation_refs":""})
    _,rb=_read_csv_artifact(root,artifacts,"m27::robustness_summary.csv")
    for row in rb.itertuples(index=False):
        rid=f"robustness::{row.dimension}::status"; assert rid in record_ids
        lim=f"M27_{str(row.dimension).upper()}_SENSITIVITY"
        rows.append({"finding_id":f"F_ROBUSTNESS_{str(row.dimension).upper()}","research_question_id":"RQ5","finding_type":"ROBUSTNESS_DIMENSION","dataset_scope":"CROSS_DATASET","status":row.status,"supporting_report_numbers":rid,"robustness_status":row.status,"limitation_refs":lim if lim in limitation_ids else ""})
    return pd.DataFrame(rows)


def final_source_identity(root: Path) -> dict[str,Any]:
    return build_source_identity(root, analytical_release_source_files(root))


def environment_lock(root: Path) -> dict[str,Any]:
    node=shutil.which("node"); node_version=subprocess.run([node,"--version"],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.strip() if node else None
    locks={}
    for name in ["package-lock.json","pyproject.toml","requirements.txt"]:
        path=root/name
        if path.is_file(): locks[name]={"sha256":sha256_file(path),"byte_count":path.stat().st_size}
    return {"python_version":platform.python_version(),"node_version":node_version,"platform":platform.platform(),"git_head":_git(root,"rev-parse","HEAD"),"git_branch":_git(root,"branch","--show-current"),"git_status_porcelain":source_relevant_git_status(root, [root / rec["path"] for rec in final_source_identity(root)["files"]]),"dependency_locks":locks}
