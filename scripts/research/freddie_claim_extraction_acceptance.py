#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path

def read_jsonl(p:Path):
    if not p.exists(): return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def gid(r): return str(r["generation_id"]) if r.get("generation_id") is not None else None
def main():
    ap=argparse.ArgumentParser()
    for x in ("generation-index","claims","failures","attempts"): ap.add_argument("--"+x,required=True)
    ap.add_argument("--expected-canonical",type=int,required=True); ap.add_argument("--expected-usable",type=int,required=True); ap.add_argument("--expected-unusable",type=int,required=True); ap.add_argument("--require-complete",action="store_true"); ap.add_argument("--output")
    a=ap.parse_args(); g=read_jsonl(Path(a.generation_index)); c=read_jsonl(Path(a.claims)); f=read_jsonl(Path(a.failures)); at=read_jsonl(Path(a.attempts))
    if len(g)!=a.expected_canonical: raise SystemExit(f"canonical expected {a.expected_canonical}, got {len(g)}")
    usable={str(r["generation_id"]) for r in g if r.get("usable") is True}; unusable={str(r["generation_id"]) for r in g if r.get("usable") is not True}
    if len(usable)!=a.expected_usable or len(unusable)!=a.expected_unusable: raise SystemExit(f"usable/unusable mismatch {len(usable)}/{len(unusable)}")
    claim_ids=[str(r.get("claim_id")) for r in c]
    if len(claim_ids)!=len(set(claim_ids)): raise SystemExit("duplicate claim_id")
    claim_gids={x for r in c if (x:=gid(r))}; outside=claim_gids-usable
    if outside: raise SystemExit(f"claims on non-usable/unknown generations: {sorted(outside)[:5]}")
    unresolved=usable-claim_gids
    if unusable & claim_gids: raise SystemExit("unusable generations received claims")
    result={"schema_version":"freddie_claim_extraction_acceptance_v1","canonical_generations":len(g),"usable_generations":len(usable),"unusable_generations":len(unusable),"claim_count":len(c),"claim_generations":len(claim_gids),"unresolved_usable_generations":len(unresolved),"failure_records":len(f),"failure_generation_ids":len({x for r in f if (x:=gid(r))}),"attempt_records":len(at),"attempt_status_counts":dict(Counter(str(r.get("status") or r.get("attempt_status") or "UNKNOWN") for r in at)),"failure_code_counts":dict(Counter(str(r.get("failure_code") or r.get("error_type") or r.get("reason_code") or "UNKNOWN") for r in f)),"claims_sha256":sha(Path(a.claims)),"attempts_sha256":sha(Path(a.attempts)),"failures_sha256":sha(Path(a.failures)),"complete_usable_coverage":len(unresolved)==0,"status":"PASS" if not unresolved else "INCOMPLETE"}
    if a.output:
        p=Path(a.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if a.require_complete and unresolved: print("CLAIM_EXTRACTION_COMPLETE=NO"); raise SystemExit(2)
    if not unresolved: print("CLAIM_EXTRACTION_COMPLETE=PASS")
if __name__=="__main__": main()
