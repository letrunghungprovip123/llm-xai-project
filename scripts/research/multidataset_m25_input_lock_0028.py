#!/usr/bin/env python3
"""Certify Home Credit/Freddie composition compatibility before M25 execution."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError(path)
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows=[]
    with path.open("r",encoding="utf-8") as h:
        for line_no,line in enumerate(h,1):
            if not line.strip(): continue
            value=json.loads(line)
            if not isinstance(value,dict): raise ValueError(f"{path}:{line_no}")
            rows.append(value)
    if not rows: raise ValueError(f"Empty JSONL: {path}")
    return rows


def record(root: Path, path: Path, rows: int | None=None) -> dict[str,Any]:
    path=path.resolve()
    if not path.is_file(): raise FileNotFoundError(path)
    try: display=str(path.relative_to(root.resolve()))
    except ValueError: display=str(path)
    out={"path":display,"sha256":sha(path),"byte_count":path.stat().st_size}
    if rows is not None: out["row_count"]=int(rows)
    return out


def gate(report: dict[str,Any], expected: str) -> bool:
    return report.get("passed") is True and report.get("failed_check_count")==0 and report.get("exit_gate")==expected


def contrast_id(row: pd.Series) -> str:
    family=str(row["contrast_family"])
    if family=="model_within_evidence":
        return f"model_within_evidence::{row['context_evidence_level']}::{row['condition_a_model_id']}::{row['condition_b_model_id']}"
    if family=="evidence_vs_s0":
        return f"evidence_vs_s0::{row['context_model_id']}::{row['condition_a_evidence_level']}::S0"
    raise ValueError(f"Unknown contrast family: {family}")


def model_revisions(rows: list[dict[str,Any]]) -> dict[str,list[str]]:
    values: dict[str,set[str]]={}
    for row in rows:
        model=str(row.get("model_id"))
        rec=row.get("generation_record") if isinstance(row.get("generation_record"),dict) else row
        raw=rec.get("model_revision")
        if raw is None or str(raw).strip()=="": continue
        values.setdefault(model,set()).add(str(raw))
    return {k:sorted(v) for k,v in sorted(values.items())}


def revision_scope(models: list[str], hc: dict[str,list[str]], fm: dict[str,list[str]]) -> tuple[str,dict[str,Any]]:
    details={}
    has_unknown=False; mismatch=False
    for model in models:
        a=hc.get(model,[]); b=fm.get(model,[])
        if len(a)!=1 or len(b)!=1:
            state="UNKNOWN"; has_unknown=True
        elif a[0]==b[0]: state="MATCH"
        else: state="MISMATCH"; mismatch=True
        details[model]={"home_credit_revisions":a,"freddie_revisions":b,"status":state}
    if has_unknown: scope="MODEL_REVISION_UNKNOWN"
    elif mismatch: scope="MODEL_FAMILY_PROTOCOL_REPLICATION"
    else: scope="EXACT_MODEL_REVISION_REPLICATION"
    return scope,details


def option_set(metrics: pd.DataFrame) -> set[str]:
    return set((metrics["model_id"].astype(str)+"::"+metrics["evidence_level"].astype(str)).unique())


EVIDENCE_SIGNATURE_FIELDS = (
    "semantic_guidance_level",
    "structural_guidance_level",
    "safe_phrase_available",
    "adaptive_selection",
    "concept_evidence_available",
    "backend_skeleton_available",
)


def _normalize_bool(value: Any, *, field: str, level: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    text=str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise ValueError(f"Invalid boolean for {level}.{field}: {value!r}")


def _signature_value(value: Any, *, field: str, level: str) -> Any:
    if field in {
        "safe_phrase_available",
        "adaptive_selection",
        "concept_evidence_available",
        "backend_skeleton_available",
    }:
        return _normalize_bool(value, field=field, level=level)
    return str(value).strip()


def validate_evidence_mapping(frame: pd.DataFrame, mapping: list[dict[str,Any]], label: str) -> dict[str,Any]:
    required={"evidence_level","intended_role",*EVIDENCE_SIGNATURE_FIELDS}
    missing_columns=sorted(required-set(frame.columns))
    if missing_columns:
        return {
            "dataset":label,
            "levels":{},
            "incompatible_levels":[],
            "extra_levels":[],
            "duplicate_levels":[],
            "missing_columns":missing_columns,
            "passed":False,
        }

    levels=frame["evidence_level"].astype(str)
    duplicate_levels=sorted(levels[levels.duplicated(keep=False)].unique().tolist())
    by_level={str(row["evidence_level"]):row for _,row in frame.iterrows()}
    result={}; failures=[]
    expected_levels={str(x["evidence_level"]) for x in mapping}
    for entry in mapping:
        level=str(entry["evidence_level"]); row=by_level.get(level)
        accepted_roles={str(x) for x in entry["accepted_roles"]}
        expected_signature=entry.get("expected_signature")
        if not isinstance(expected_signature,dict) or set(expected_signature)!=set(EVIDENCE_SIGNATURE_FIELDS):
            raise ValueError(f"Protocol evidence mapping for {level} does not define the exact structural signature.")
        if row is None:
            result[level]={
                "observed_role":None,
                "canonical_role":entry["canonical_role"],
                "role_compatible":False,
                "signature_compatible":False,
                "signature_mismatches":["missing_evidence_level"],
                "compatible":False,
            }
            failures.append(level); continue

        role=str(row["intended_role"]); role_ok=role in accepted_roles
        observed_signature={
            field:_signature_value(row[field],field=field,level=level)
            for field in EVIDENCE_SIGNATURE_FIELDS
        }
        normalized_expected={
            field:_signature_value(expected_signature[field],field=field,level=level)
            for field in EVIDENCE_SIGNATURE_FIELDS
        }
        mismatches=[field for field in EVIDENCE_SIGNATURE_FIELDS if observed_signature[field]!=normalized_expected[field]]
        signature_ok=not mismatches
        ok=role_ok and signature_ok
        result[level]={
            "observed_role":role,
            "accepted_roles":sorted(accepted_roles),
            "canonical_role":entry["canonical_role"],
            "role_compatible":role_ok,
            "observed_signature":observed_signature,
            "expected_signature":normalized_expected,
            "signature_compatible":signature_ok,
            "signature_mismatches":mismatches,
            "compatible":ok,
        }
        if not ok: failures.append(level)
    extras=sorted(set(by_level)-expected_levels)
    return {
        "dataset":label,
        "levels":result,
        "incompatible_levels":failures,
        "extra_levels":extras,
        "duplicate_levels":duplicate_levels,
        "missing_columns":missing_columns,
        "passed":not failures and not extras and not duplicate_levels and not missing_columns,
    }


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",required=True); ap.add_argument("--protocol",required=True)
    ap.add_argument("--freddie-analysis-lock",required=True); ap.add_argument("--freddie-metric-dir",required=True); ap.add_argument("--freddie-stat-dir",required=True); ap.add_argument("--freddie-diagnostics-dir",required=True)
    ap.add_argument("--home-validation-root",required=True); ap.add_argument("--output",required=True)
    a=ap.parse_args()
    root=Path(a.repo_root).resolve(); protocol_path=Path(a.protocol).resolve(); protocol=read_json(protocol_path)
    fm_analysis_lock=Path(a.freddie_analysis_lock).resolve(); fm_metric=Path(a.freddie_metric_dir).resolve(); fm_stat=Path(a.freddie_stat_dir).resolve(); fm_diag=Path(a.freddie_diagnostics_dir).resolve(); hc_root=Path(a.home_validation_root).resolve(); output=Path(a.output).resolve()

    # Freddie certification.
    fm_metric_manifest=read_json(fm_metric/"metric_manifest.json"); fm_stat_manifest=read_json(fm_stat/"statistical_manifest.json"); fm_diag_manifest=read_json(fm_diag/"diagnostics_manifest.json")
    fm_metric_validation=read_json(fm_metric/"metric_validation.json"); fm_stat_validation=read_json(fm_stat/"statistical_validation.json"); fm_diag_validation=read_json(fm_diag/"diagnostics_validation.json")
    if fm_metric_manifest.get("gate")!="ANALYTICAL_MART_READY" or fm_stat_manifest.get("gate")!="STATISTICAL_CORE_READY" or fm_diag_manifest.get("gate")!="DIAGNOSTICS_READY": raise SystemExit("Freddie M22-M24 parents are not certified.")
    if not gate(fm_metric_validation,"ANALYTICAL_MART_READY") or not gate(fm_stat_validation,"STATISTICAL_CORE_READY") or not gate(fm_diag_validation,"DIAGNOSTICS_READY"): raise SystemExit("Freddie validation gates are not certified.")

    # Home Credit certified historical analytical release.
    hc_mart=hc_root/"analysis/data_mart"; hc_stat=hc_root/"analysis/statistical_analysis"; hc_diag=hc_root/"analysis/diagnostics"
    hc_dm_validation=read_json(hc_mart/"data_mart_validation.json"); hc_metric_validation=read_json(hc_mart/"metric_validation.json"); hc_stat_validation=read_json(hc_stat/"statistical_validation.json"); hc_diag_validation=read_json(hc_diag/"diagnostic_validation.json")
    if not gate(hc_dm_validation,"DATA_MART_READY") or not gate(hc_metric_validation,"ANALYTICAL_MART_READY") or not gate(hc_stat_validation,"STATISTICAL_CORE_READY") or not gate(hc_diag_validation,"DIAGNOSTICS_READY"):
        raise SystemExit("Home Credit analytical parents are not certified.")

    hc_metrics=pd.read_csv(hc_mart/"generation_metrics.csv",low_memory=False); fm_metrics=pd.read_csv(fm_metric/"generation_metrics.csv",low_memory=False)
    hc_models=pd.read_csv(hc_mart/"models.csv",low_memory=False); fm_models=pd.read_csv((Path(read_json(fm_analysis_lock)["artifacts"]["generation_index"]["path"]).parent if False else fm_metric/"../data_mart_v1/models.csv").resolve(),low_memory=False)
    # Freddie evidence/model dimension tables are in the sibling certified data mart.
    fm_mart=fm_metric.parent/"data_mart_v1"
    fm_models=pd.read_csv(fm_mart/"models.csv",low_memory=False); fm_levels=pd.read_csv(fm_mart/"evidence_levels.csv",low_memory=False)
    hc_levels=pd.read_csv(hc_mart/"evidence_levels.csv",low_memory=False)
    hc_pairs=pd.read_csv(hc_stat/"paired_tests.csv",low_memory=False); fm_pairs=pd.read_csv(fm_stat/"paired_tests.csv",low_memory=False)

    expected_models=set(str(x) for x in protocol["models"]); expected_levels=set(str(x["evidence_level"]) for x in protocol["evidence_mapping"]); expected_options={f"{m}::{s}" for m in expected_models for s in expected_levels}
    for label,metrics,models,levels in [("home_credit",hc_metrics,hc_models,hc_levels),("freddie",fm_metrics,fm_models,fm_levels)]:
        if len(metrics)!=648 or metrics["case_id"].astype(str).nunique()!=36: raise SystemExit(f"{label} generation matrix is not 648 rows / 36 cases.")
        if set(models["model_id"].astype(str))!=expected_models: raise SystemExit(f"{label} model IDs do not match protocol.")
        if set(levels["evidence_level"].astype(str))!=expected_levels: raise SystemExit(f"{label} evidence IDs do not match protocol.")
        if option_set(metrics)!=expected_options: raise SystemExit(f"{label} option set does not contain exact 18 protocol options.")
        counts=metrics.groupby(["model_id","evidence_level"]).size()
        if not counts.eq(36).all(): raise SystemExit(f"{label} does not preserve 36 planned generations per option.")

    hc_ev=validate_evidence_mapping(hc_levels,protocol["evidence_mapping"],"home_credit"); fm_ev=validate_evidence_mapping(fm_levels,protocol["evidence_mapping"],"freddie")
    if not hc_ev["passed"] or not fm_ev["passed"]: raise SystemExit("Evidence semantic composition mapping failed.")

    hc_pairs=hc_pairs.copy(); fm_pairs=fm_pairs.copy(); hc_pairs["derived_contrast_id"]=hc_pairs.apply(contrast_id,axis=1); fm_pairs["derived_contrast_id"]=fm_pairs.apply(contrast_id,axis=1)
    hc_contrasts=set(hc_pairs["derived_contrast_id"]); fm_contrasts=set(fm_pairs["derived_contrast_id"])
    if len(hc_pairs)!=33 or len(fm_pairs)!=33 or len(hc_contrasts)!=33 or hc_contrasts!=fm_contrasts: raise SystemExit("The two studies do not expose the same 33 primary contrasts.")

    hc_index=read_jsonl(hc_root/"canonicalization/generation_index.jsonl"); fm_index_path=Path(read_json(fm_analysis_lock)["artifacts"]["generation_index"]["path"]); fm_index_path=fm_index_path if fm_index_path.is_absolute() else root/fm_index_path; fm_index=read_jsonl(fm_index_path)
    hc_revisions=model_revisions(hc_index); fm_revisions=model_revisions(fm_index); revision_status, revision_details=revision_scope(list(protocol["models"]),hc_revisions,fm_revisions)

    inputs={
      "home_credit_generation_index":record(root,hc_root/"canonicalization/generation_index.jsonl",len(hc_index)),
      "home_credit_generation_metrics":record(root,hc_mart/"generation_metrics.csv",len(hc_metrics)),
      "home_credit_models":record(root,hc_mart/"models.csv",len(hc_models)),
      "home_credit_evidence_levels":record(root,hc_mart/"evidence_levels.csv",len(hc_levels)),
      "home_credit_paired_tests":record(root,hc_stat/"paired_tests.csv",len(hc_pairs)),
      "home_credit_omnibus_tests":record(root,hc_stat/"omnibus_tests.csv"),
      "home_credit_generation_diagnostics":record(root,hc_diag/"generation_diagnostics.csv"),
      "home_credit_data_mart_validation":record(root,hc_mart/"data_mart_validation.json"),
      "home_credit_metric_validation":record(root,hc_mart/"metric_validation.json"),
      "home_credit_statistical_validation":record(root,hc_stat/"statistical_validation.json"),
      "home_credit_diagnostic_validation":record(root,hc_diag/"diagnostic_validation.json"),
      "freddie_generation_metrics":record(root,fm_metric/"generation_metrics.csv",len(fm_metrics)),
      "freddie_option_performance":record(root,fm_metric/"option_performance.csv"),
      "freddie_paired_tests":record(root,fm_stat/"paired_tests.csv",len(fm_pairs)),
      "freddie_omnibus_tests":record(root,fm_stat/"omnibus_tests.csv"),
      "freddie_generation_diagnostics":record(root,fm_diag/"generation_diagnostics.csv"),
      "freddie_metric_manifest":record(root,fm_metric/"metric_manifest.json"),
      "freddie_statistical_manifest":record(root,fm_stat/"statistical_manifest.json"),
      "freddie_diagnostics_manifest":record(root,fm_diag/"diagnostics_manifest.json"),
    }
    lock={
      "schema_version":"multidataset_replication_input_lock_v1","protocol_id":protocol["protocol_id"],"producer":"M25A_0028",
      "protocol":record(root,protocol_path),"freddie_analysis_input_lock":record(root,fm_analysis_lock),"inputs":inputs,
      "compatibility":{
        "datasets":["home_credit_default_risk","freddie_sflld_2024"],"cases_per_study":36,"models":sorted(expected_models),"evidence_levels":sorted(expected_levels),"options":18,"primary_contrasts":33,
        "evidence_mapping":{"home_credit":hc_ev,"freddie":fm_ev},"model_revision_scope":revision_status,"model_revision_details":revision_details,
        "cross_dataset_case_pairing_allowed":False
      },
      "contrast_ids":sorted(hc_contrasts),"bootstrap":protocol["bootstrap"],"primary_metric":protocol["primary_metric"],"provider_execution_allowed":False,"gate":"MULTIDATASET_REPLICATION_INPUT_LOCK_READY"
    }
    encoded=json.dumps(lock,ensure_ascii=False,indent=2,sort_keys=True)+"\n"; output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        if output.read_text(encoding="utf-8")==encoded:
            print(f"MULTIDATASET_M25A_REPLICATION_INPUT_LOCK=ALREADY_CERTIFIED scope={revision_status}"); return 0
        raise SystemExit(f"Refusing to overwrite different M25 input lock: {output}")
    output.write_text(encoded,encoding="utf-8")
    print(f"MULTIDATASET_M25A_REPLICATION_INPUT_LOCK=PASS options=18 contrasts=33 scope={revision_status}")
    return 0

if __name__=="__main__": raise SystemExit(main())
