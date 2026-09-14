#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path

def load(p): return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--lock",required=True); ap.add_argument("--repo-root",required=True); ap.add_argument("--output-dir",required=True); a=ap.parse_args(); root=Path(a.repo_root); lock=json.loads(Path(a.lock).read_text()); out=Path(a.output_dir)
    # Reverify every locked file immediately after validation.
    for name,d in lock["artifacts"].items():
        p=Path(d["path"]); p=p if p.is_absolute() else root/p
        assert p.is_file(), f"locked artifact missing after validation: {name}:{p}"
        assert sha(p)==d["sha256"], f"locked artifact drift after validation: {name}"
    claims_path=Path(lock["artifacts"]["claims_final"]["path"]); claims_path=claims_path if claims_path.is_absolute() else root/claims_path
    claims=load(claims_path); results=load(out/"claim_validation_results.jsonl"); generations=load(out/"generation_validation_summary.jsonl"); errors=load(out/"validation_execution_errors.jsonl")
    input_ids=[x["claim_id"] for x in claims]; result_ids=[x["claim_id"] for x in results]
    assert len(input_ids)==len(set(input_ids)); assert len(result_ids)==len(set(result_ids)); assert set(input_ids)==set(result_ids); assert len(results)==len(claims)
    assert not errors, f"deterministic validation execution errors: {len(errors)}"
    assert len(generations)==648 and len({x["generation_id"] for x in generations})==648
    allowed={"SUPPORTED","UNSUPPORTED","CONTRADICTED","NOT_VERIFIABLE","NOT_APPLICABLE"}; status=Counter()
    for r in results:
        assert r["execution_status"]=="SUCCESS", f"execution error result: {r['claim_id']}"
        assert r["validation_status"] in allowed; status[r["validation_status"]]+=1
        assert r["claim_schema_version"]=="claims_v3"
    manifest=json.loads((out/"claim_validation_manifest.json").read_text()); assert manifest
    print("FREDDIE_M20_CLAIM_VALIDATION=PASS " + f"claims={len(claims)} results={len(results)} generations=648 execution_errors=0 statuses=" + json.dumps(dict(status),sort_keys=True,separators=(",",":")))
if __name__=="__main__": main()
