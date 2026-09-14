#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, tempfile
from pathlib import Path

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def count_jsonl(p:Path): return sum(1 for x in p.read_text(encoding="utf-8").splitlines() if x.strip())
def load_jsonl(p:Path): return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def rel(root,p):
    try:return str(p.resolve().relative_to(root.resolve()))
    except ValueError:return str(p.resolve())
def desc(root,p,records=None):
    d={"path":rel(root,p),"sha256":sha(p),"byte_count":p.stat().st_size}
    if records is not None:d["record_count"]=records
    return d

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--repo-root",required=True); ap.add_argument("--claims",required=True); ap.add_argument("--generation-index",required=True); ap.add_argument("--evidence-packages",required=True); ap.add_argument("--replay-manifest",required=True); ap.add_argument("--semantic-manifest",required=True); ap.add_argument("--output",required=True); a=ap.parse_args()
    root=Path(a.repo_root); claims=Path(a.claims); generation=Path(a.generation_index); evidence=Path(a.evidence_packages)
    required={
      "claims_final":claims,"generation_index":generation,"evidence_packages":evidence,"replay_finalization_manifest":Path(a.replay_manifest),"semantic_finalization_manifest":Path(a.semantic_manifest),
      "claim_validation_policy":root/"config/research/ts-validation/claim_validation_policy_v1.json",
      "numeric_tolerance_policy":root/"config/research/ts-validation/numeric_tolerance_policy_v1.json",
      "claim_validation_reason_codes":root/"config/research/ts-validation/claim_validation_reason_codes_v1.json",
      "claim_type_compatibility":root/"config/research/ts-validation/claim_type_compatibility.json",
      "claim_validation_schema":root/"contracts/llm-validation/claim_validation_v4.schema.json",
      "claims_schema":root/"contracts/llm-validation/claims.schema.json",
      "feature_policy":root/"config/research/datasets/freddie_sflld_2024_feature_policy_v1.json",
      "concept_registry":root/"config/research/datasets/freddie_sflld_2024_concept_registry_v1.yaml",
    }
    missing=[f"{k}:{p}" for k,p in required.items() if not p.is_file()]
    if missing: raise SystemExit("M20A fail-closed: missing required validation input/config:\n"+"\n".join(missing))
    c=load_jsonl(claims); g=load_jsonl(generation); e=load_jsonl(evidence)
    if len(g)!=648 or sum(bool(x["usable"]) for x in g)!=645: raise SystemExit("M20A cohort mismatch; expected 648/645/3")
    if len(e)!=216: raise SystemExit(f"M20A expected 216 evidence packages, found {len(e)}")
    if not c or any(x.get("claim_schema_version")!="claims_v3" for x in c): raise SystemExit("M20A requires finalized claims_v3 input")
    usable={x["generation_id"] for x in g if x["usable"]}; if_claims={x["generation_id"] for x in c}
    if if_claims!=usable: raise SystemExit(f"M20A final claim generation coverage mismatch: {len(if_claims)}/645")
    commit=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    lock={"schema_version":"freddie_validation_input_lock_v1","dataset_id":"freddie_sflld_2024","experiment_id":"freddie_sflld_2024_replication_v1","deterministic":True,"provider_calls_made":0,"source_commit":commit,"cohort":{"canonical_generations":648,"usable_generations":645,"unusable_generations":3,"evidence_packages":216,"final_claims":len(c)},"artifacts":{}}
    for k,p in required.items(): lock["artifacts"][k]=desc(root,p,count_jsonl(p) if p.suffix==".jsonl" else None)
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); data=json.dumps(lock,ensure_ascii=False,indent=2)+"\n"; tmp=out.with_suffix(out.suffix+".tmp"); tmp.write_text(data,encoding="utf-8"); tmp.replace(out)
    print(f"FREDDIE_M20A_INPUT_LOCK=PASS final_claims={len(c)} lock_sha256={sha(out)}")
if __name__=="__main__": main()
