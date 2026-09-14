#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter, defaultdict
from pathlib import Path

def load(path): return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
def sha(s): return hashlib.sha256(s.encode()).hexdigest()

def main():
    p=argparse.ArgumentParser();
    for k in ["generation-index","claims","attempts","failures","output"]: p.add_argument("--"+k, required=True)
    a=p.parse_args(); gen=load(a.generation_index); claims=load(a.claims); attempts=load(a.attempts); failures=load(a.failures)
    assert len(gen)==648
    usable={r["generation_id"] for r in gen if r["usable"]}; unusable={r["generation_id"] for r in gen if not r["usable"]}; assert (len(usable),len(unusable))==(645,3)
    claim_ids={c["generation_id"] for c in claims}; assert claim_ids==usable
    assert len(failures)==3 and {f["generation_id"] for f in failures}==unusable
    candidates=defaultdict(list)
    for at in attempts:
        raw=at.get("raw_response_text"); raw_hash=at.get("raw_response_sha256")
        if not raw: continue
        if sha(raw)!=raw_hash: raise AssertionError(f"raw response hash mismatch: {at.get('attempt_id')}")
        if at.get("extractor_provider")=="deepseek" and at.get("extractor_model_id")=="deepseek-v4-flash": candidates[at["generation_id"]].append(at)
    missing=[gid for gid in usable if not candidates[gid]]; assert not missing, f"missing reproducible raw response candidates: {len(missing)}"
    offline={gid for gid,ats in candidates.items() if any(str(x.get("attempt_id","")).startswith("offline_replay_attempt_") for x in ats)}
    historical=usable-offline
    assert len(offline)==447, len(offline); assert len(historical)==198, len(historical)
    for gid in offline:
        synth=[x for x in candidates[gid] if str(x.get("attempt_id","")).startswith("offline_replay_attempt_")]
        assert len(synth)==1, f"ambiguous synthetic replay candidate for {gid}"
    report={"schema_version":"freddie_m19a_replay_preflight_v1","passed":True,"provider_calls_made":0,"canonical_generations":648,"usable_generations":645,"unusable_generations":3,"reproducible_generations":645,"historical_stored_response_generations":198,"offline_frozen_response_generations":447,"missing_replay_source_count":0,"ambiguous_offline_source_count":0}
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); tmp=out.with_suffix(out.suffix+".tmp"); tmp.write_text(json.dumps(report,indent=2)+"\n"); tmp.replace(out)
    print("FREDDIE_M19A_REPLAY_PREFLIGHT=PASS stored=198 offline=447 reproducible=645")
if __name__=="__main__": main()
