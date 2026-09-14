#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from collections import defaultdict
from pathlib import Path

def load(p): return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]
def file_sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    q=argparse.ArgumentParser();
    for k in ["generation-index","effective-extraction","replay-dir","semantic-dir"]: q.add_argument("--"+k,required=True)
    a=q.parse_args(); gen=load(a.generation_index); replay=Path(a.replay_dir); sem=Path(a.semantic_dir)
    v2=load(replay/"claims_final_v2.jsonl"); v3=load(sem/"claims_final.jsonl"); replay_manifest=json.loads((replay/"claim_finalization_manifest_v2.json").read_text()); sem_manifest=json.loads((sem/"semantic_migration_manifest.json").read_text())
    usable={r["generation_id"] for r in gen if r["usable"]}; unusable={r["generation_id"] for r in gen if not r["usable"]}; assert (len(gen),len(usable),len(unusable))==(648,645,3)
    assert len(v2)>0 and len(v3)>0; assert len(v2)==len(v3), "semantic migration must preserve count under Freddie policy v1"
    assert {c["generation_id"] for c in v2}==usable and {c["generation_id"] for c in v3}==usable
    assert all(c["claim_schema_version"]=="claims_v2" for c in v2); assert all(c["claim_schema_version"]=="claims_v3" for c in v3)
    ids=[c["claim_id"] for c in v3]; assert len(ids)==len(set(ids))
    by=defaultdict(set)
    for c in v3:
        assert c["parent_claim_id"]
        assert c["source_start"]==c["source_span_start"] and c["source_end"]==c["source_span_end"]
        assert c["semantic_signature"] not in by[c["generation_id"]]; by[c["generation_id"]].add(c["semantic_signature"])
    assert replay_manifest["cohort"]["canonical_generations"]==648 and replay_manifest["cohort"]["successful_generations"]==645 and replay_manifest["cohort"]["unusable_generations"]==3
    assert replay_manifest["reproducibility"]["provider_calls_made"]==0
    assert sem_manifest["provider_calls_made"]==0 and sem_manifest["lineage"]["output_claim_schema_version"]=="claims_v3"
    print(f"FREDDIE_M19_FINALIZATION=PASS final_claims={len(v3)} claim_generations=645 replay_sha256={file_sha(replay/'claims_final_v2.jsonl')} semantic_sha256={file_sha(sem/'claims_final.jsonl')}")
if __name__=="__main__": main()
