#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path
MODELS=("qwen3_8b","deepseek_v4_flash","phi4_mini_instruct")
LEVELS=("S0","S1","S2","S3","S4","S5")
def read_jsonl(p:Path): return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--generation-index",required=True); ap.add_argument("--output",required=True); a=ap.parse_args()
    rows=read_jsonl(Path(a.generation_index)); groups=defaultdict(list)
    for r in rows: groups[str(r["source_ir_id"])].append(r)
    expected={(m,l) for m in MODELS for l in LEVELS}; chosen=None
    for sid in sorted(groups):
        cohort=groups[sid]; keys={(str(r["model_id"]),str(r["evidence_level"])) for r in cohort if r.get("usable") is True}
        if len(cohort)==18 and keys==expected: chosen=sid; break
    if chosen is None: raise SystemExit("No fully usable 3-model x 6-level source_ir_id available for smoke")
    order={(m,l):i for i,(m,l) in enumerate((m,l) for m in MODELS for l in LEVELS)}
    selected=sorted(groups[chosen],key=lambda r:order[(str(r["model_id"]),str(r["evidence_level"]))])
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text("".join(json.dumps(r,ensure_ascii=False,separators=(",",":"))+"\n" for r in selected),encoding="utf-8")
    print("CLAIM_SMOKE_SUBSET=PASS"); print(f"SOURCE_IR_ID={chosen}"); print("ROWS=18"); print("MODEL_LEVEL_CELLS=18")
if __name__=="__main__": main()
