#!/usr/bin/env python3
from __future__ import annotations

import argparse,json,os,shutil,tempfile
from pathlib import Path
import pandas as pd
from jsonschema import Draft202012Validator

from research.python.analytical_release.build import artifact_index, build_findings, build_limitations, build_report_numbers, collect_artifacts, environment_lock, final_source_identity, validate_report_numbers
from research.python.robustness.common import read_json, repo_relative, resolve_record, sha256_file


def hashes(path: Path) -> dict[str,str]: return {p.name:sha256_file(p) for p in sorted(path.iterdir()) if p.is_file()}

def build(root: Path,lock_path: Path,lock: dict,protocol: dict,out: Path) -> dict:
    if lock.get("gate")!="MULTIDATASET_ANALYTICAL_RELEASE_INPUT_LOCK_READY": raise ValueError("M28B requires certified M28A input lock.")
    resolve_record(root,lock["protocol"],"protocol")
    for group in ["contracts","parent_artifacts","source_artifacts"]:
        for name,rec in lock[group].items(): resolve_record(root,rec,f"{group}::{name}")
    current_source_identity=final_source_identity(root)
    if current_source_identity != lock.get("source_identity"):
        raise ValueError("M28 artifact-relevant source identity drifted after M28A lock.")
    artifacts=collect_artifacts(root,lock); source_index=artifact_index(root,artifacts); records=build_report_numbers(root,protocol,artifacts); trace=validate_report_numbers(root,records,artifacts)
    if not trace["passed"]: raise ValueError("Report-number source trace validation failed.")
    limitations=build_limitations(root,protocol,artifacts); findings=build_findings(root,records,artifacts,limitations); rq=pd.DataFrame(protocol["research_questions"])

    schemas={name:read_json(resolve_record(root,rec,f"contract::{name}")) for name,rec in lock["contracts"].items()}
    report_validator=Draft202012Validator(schemas["report_number"])
    limitation_validator=Draft202012Validator(schemas["limitation_registry"])
    finding_validator=Draft202012Validator(schemas["finding_registry"])
    source_index_validator=Draft202012Validator(schemas["report_source_index"])
    schema_errors=[]
    for record in records:
        for error in report_validator.iter_errors(record): schema_errors.append(f"report::{record.get('report_number_id')}::{error.message}")
    for row in limitations.to_dict(orient="records"):
        for error in limitation_validator.iter_errors(row): schema_errors.append(f"limitation::{row.get('limitation_id')}::{error.message}")
    for row in findings.to_dict(orient="records"):
        schema_row=dict(row)
        schema_row["supporting_report_numbers"]=[x for x in str(row.get("supporting_report_numbers","")).split("|") if x]
        schema_row["limitation_refs"]=[x for x in str(row.get("limitation_refs","")).split("|") if x]
        for error in finding_validator.iter_errors(schema_row): schema_errors.append(f"finding::{row.get('finding_id')}::{error.message}")
    report_ids={r["report_number_id"] for r in records}; bad_findings=[]
    for row in findings.itertuples(index=False):
        refs=[x for x in str(row.supporting_report_numbers).split("|") if x]
        if not refs or any(x not in report_ids for x in refs): bad_findings.append(row.finding_id)
    required=set(protocol["required_limitations"]); observed=set(limitations["limitation_id"].astype(str)); missing_limitations=sorted(required-observed)
    source_rows=[{**r,"value_json":json.dumps(r["value"],ensure_ascii=False,sort_keys=True),"source_filter_json":json.dumps(r["source_filter"],ensure_ascii=False,sort_keys=True)} for r in records]
    for row in source_rows:
        source_schema_row={k:v for k,v in row.items() if k not in {"value","source_filter"}}
        for error in source_index_validator.iter_errors(source_schema_row): schema_errors.append(f"source_index::{row.get('report_number_id')}::{error.message}")
    checks={
        "report_number_ids_unique":{"passed":len(report_ids)==len(records),"expected":len(records),"observed":len(report_ids)},
        "report_number_trace":{"passed":trace["passed"],"expected":0,"observed":trace["mismatch_count"]},
        "findings_backed_by_report_numbers":{"passed":not bad_findings,"expected":[],"observed":bad_findings},
        "required_limitations_present":{"passed":not missing_limitations,"expected":[],"observed":missing_limitations},
        "provider_execution_allowed":{"passed":protocol["provider_execution_allowed"] is False,"expected":False,"observed":protocol["provider_execution_allowed"]},
        "scientific_recomputation_allowed":{"passed":protocol["scientific_recomputation_allowed"] is False,"expected":False,"observed":protocol["scientific_recomputation_allowed"]},
        "artifact_relevant_source_identity":{"passed":current_source_identity==lock.get("source_identity"),"expected":lock.get("source_identity",{}).get("source_tree_identity_sha256"),"observed":current_source_identity.get("source_tree_identity_sha256")},
        "release_schema_validation":{"passed":not schema_errors,"expected":[],"observed":schema_errors},
    }
    failed=sum(not x["passed"] for x in checks.values()); validation={"schema_version":"certified_multidataset_analytical_release_validation_v1","checks":checks,"failed_check_count":failed,"passed":failed==0,"exit_gate":"CERTIFIED_MULTIDATASET_ANALYTICAL_RELEASE_READY" if failed==0 else "CERTIFIED_MULTIDATASET_ANALYTICAL_RELEASE_INVALID","report_trace_validation":trace}
    if failed: raise ValueError("M28 certified analytical release validation failed.")
    out.mkdir(parents=True,exist_ok=False)
    (out/"report_numbers.json").write_text(json.dumps({"schema_version":"report_numbers_v1","release_id":protocol["release_id"],"records":records},ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    pd.DataFrame(source_rows).drop(columns=["value","source_filter"]).to_csv(out/"report_source_index.csv",index=False,lineterminator="\n")
    limitations.to_csv(out/"limitations_registry.csv",index=False,lineterminator="\n"); findings.to_csv(out/"findings_registry.csv",index=False,lineterminator="\n"); rq.to_csv(out/"research_question_registry.csv",index=False,lineterminator="\n"); source_index.to_csv(out/"source_artifact_index.csv",index=False,lineterminator="\n")
    metric_dict=pd.DataFrame(sorted({(r["metric_id"],r["unit"],r["family"],r["analysis_lane"]) for r in records}),columns=["metric_id","unit","family","analysis_lane"]); metric_dict.to_csv(out/"release_metric_dictionary.csv",index=False,lineterminator="\n")
    (out/"environment_lock.json").write_text(json.dumps(environment_lock(root),ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); (out/"source_tree_identity.json").write_text(json.dumps(lock["source_identity"],ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); (out/"analytical_release_validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    files={p.name:{"sha256":sha256_file(p),"byte_count":p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()}
    m25_manifest=read_json(resolve_record(root,artifacts["m25_manifest"],"m25_manifest")); manifest={"schema_version":"certified_multidataset_analytical_release_manifest_v1","release_id":protocol["release_id"],"producer":"M28B_0035","parent_input_lock":{"path":repo_relative(root,lock_path),"sha256":sha256_file(lock_path)},"replication_scope":m25_manifest.get("model_revision_scope"),"report_number_count":len(records),"finding_count":len(findings),"limitation_count":len(limitations),"scientific_truth_frozen":True,"files":files,"gate":"CERTIFIED_MULTIDATASET_ANALYTICAL_RELEASE_READY"}
    (out/"analytical_release_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); return manifest

def reverify(root: Path,lock_path: Path,out: Path) -> dict:
    m=read_json(out/"analytical_release_manifest.json"); v=read_json(out/"analytical_release_validation.json")
    if m.get("gate")!="CERTIFIED_MULTIDATASET_ANALYTICAL_RELEASE_READY" or v.get("passed") is not True: raise ValueError("Existing M28 release not certified.")
    if m.get("parent_input_lock",{}).get("sha256")!=sha256_file(lock_path): raise ValueError("Existing M28 parent lock drift.")
    for name,rec in m["files"].items():
        p=out/name
        if not p.is_file() or sha256_file(p)!=rec["sha256"] or p.stat().st_size!=int(rec["byte_count"]): raise ValueError(f"Existing M28 artifact drift: {name}")
    return m

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--repo-root",required=True); p.add_argument("--input-lock",required=True); p.add_argument("--output-dir",required=True); a=p.parse_args(); root=Path(a.repo_root).resolve(); lock_path=Path(a.input_lock).resolve(); out=Path(a.output_dir).resolve(); lock=read_json(lock_path); protocol=read_json(resolve_record(root,lock["protocol"],"protocol"))
    if out.exists(): m=reverify(root,lock_path,out); print(f"MULTIDATASET_M28_CERTIFIED_ANALYTICAL_RELEASE=ALREADY_CERTIFIED report_numbers={m['report_number_count']} findings={m['finding_count']} limitations={m['limitation_count']}"); return 0
    out.parent.mkdir(parents=True,exist_ok=True); x=Path(tempfile.mkdtemp(prefix=".m28a_",dir=out.parent)); shutil.rmtree(x); y=Path(tempfile.mkdtemp(prefix=".m28b_",dir=out.parent)); shutil.rmtree(y)
    try:
        build(root,lock_path,lock,protocol,x); build(root,lock_path,lock,protocol,y)
        if hashes(x)!=hashes(y): raise ValueError("M28 deterministic replay mismatch.")
        os.replace(x,out); x=Path("/__promoted__")
    finally:
        if x.exists(): shutil.rmtree(x,ignore_errors=True)
        if y.exists(): shutil.rmtree(y,ignore_errors=True)
    m=read_json(out/"analytical_release_manifest.json"); print(f"MULTIDATASET_M28_CERTIFIED_ANALYTICAL_RELEASE=PASS report_numbers={m['report_number_count']} findings={m['finding_count']} limitations={m['limitation_count']} scope={m['replication_scope']}"); return 0
if __name__=="__main__": raise SystemExit(main())
