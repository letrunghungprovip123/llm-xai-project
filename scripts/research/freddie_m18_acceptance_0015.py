#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path

EXPECTED = dict(canonical=648, usable=645, unusable=3, historical=198, offline=447)

def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def main():
    p=argparse.ArgumentParser(); p.add_argument("--generation-index", required=True); p.add_argument("--historical-claims", required=True); p.add_argument("--effective-dir", required=True); a=p.parse_args()
    gen=rows(Path(a.generation_index)); old=rows(Path(a.historical_claims)); d=Path(a.effective_dir)
    claims=rows(d/"claims.jsonl"); attempts=rows(d/"claim_extraction_attempts.jsonl"); failures=rows(d/"claim_extraction_failures.jsonl"); events=rows(d/"offline_replay_events.jsonl")
    assert len(gen)==EXPECTED["canonical"]
    usable={r["generation_id"] for r in gen if r["usable"]}; unusable={r["generation_id"] for r in gen if not r["usable"]}; assert len(usable)==645 and len(unusable)==3
    by_gen=defaultdict(list)
    ids=set()
    signatures=defaultdict(set)
    for c in claims:
        cid=c["claim_id"]; assert cid not in ids; ids.add(cid); by_gen[c["generation_id"]].append(c)
        sig=c["semantic_signature"]; assert sig not in signatures[c["generation_id"]]; signatures[c["generation_id"]].add(sig)
    assert set(by_gen)==usable
    assert not (set(by_gen)&unusable)
    for gid, cs in by_gen.items(): assert [c["local_claim_index"] for c in sorted(cs,key=lambda x:x["local_claim_index"])]==list(range(1,len(cs)+1))
    assert len(failures)==3 and {f["generation_id"] for f in failures}==unusable and all(f["attempted"] is False and f["failure_code"]=="GENERATION_UNUSABLE" for f in failures)
    assert len(events)==447 and len({e["generation_id"] for e in events})==447
    synthetic=[x for x in attempts if str(x.get("attempt_id","")).startswith("offline_replay_attempt_")]
    assert len(synthetic)==447 and all(x["status"]=="SUCCESS" and x["raw_response_text"] and x["raw_response_sha256"] for x in synthetic)
    old_lines={json.dumps(x,ensure_ascii=False,separators=(",",":")) for x in old}
    new_lines={json.dumps(x,ensure_ascii=False,separators=(",",":")) for x in claims}
    missing=old_lines-new_lines; assert not missing, f"historical claim rows changed/missing: {len(missing)}"
    print(f"FREDDIE_M18_EXTRACTION_CLOSURE=PASS canonical=648 usable=645 unusable=3 claim_generations={len(by_gen)} claims={len(claims)} offline_events={len(events)}")
if __name__=="__main__": main()
