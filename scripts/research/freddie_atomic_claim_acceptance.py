#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path

def read_jsonl(p): return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser()
    for x in ("generation-index","claims-final","changes","manifest","output"): ap.add_argument("--"+x,required=True)
    a=ap.parse_args(); g=read_jsonl(a.generation_index); c=read_jsonl(a.claims_final); changes=read_jsonl(a.changes); manifest=json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    if len(g)!=648: raise SystemExit(f"canonical expected 648, got {len(g)}")
    usable={str(r["generation_id"]) for r in g if r.get("usable") is True}; unusable={str(r["generation_id"]) for r in g if r.get("usable") is not True}
    if (len(usable),len(unusable))!=(645,3): raise SystemExit(f"usable/unusable expected 645/3, got {len(usable)}/{len(unusable)}")
    ids=[str(r.get("claim_id")) for r in c]
    if len(ids)!=len(set(ids)): raise SystemExit("duplicate final claim_id")
    claim_gids={str(r.get("generation_id")) for r in c}
    if claim_gids-usable: raise SystemExit("final claims reference non-usable/unknown generation")
    missing=usable-claim_gids
    if missing: raise SystemExit(f"usable generations missing finalized claims: {len(missing)}")
    result={"schema_version":"freddie_atomic_claim_release_acceptance_v1","status":"PASS","canonical_generations":648,"usable_generations":645,"unusable_generations":3,"final_claims":len(c),"claim_generations":len(claim_gids),"duplicate_claim_ids":0,"usable_generations_without_claims":0,"claims_on_unusable_generations":0,"model_claim_counts":dict(Counter(str(r.get("model_id")) for r in c)),"evidence_level_claim_counts":dict(Counter(str(r.get("evidence_level")) for r in c)),"claim_type_counts":dict(Counter(str(r.get("claim_type")) for r in c)),"change_records":len(changes),"claims_final_sha256":sha(a.claims_final),"changes_sha256":sha(a.changes),"manifest_sha256":sha(a.manifest),"finalizer_manifest_schema_version":manifest.get("schema_version")}
    p=Path(a.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2)); print("FREDDIE_ATOMIC_CLAIM_RELEASE=PASS")
if __name__=="__main__": main()
