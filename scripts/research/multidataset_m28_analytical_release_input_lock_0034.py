#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from research.python.analytical_release.input_lock import build_input_lock

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--repo-root",required=True); p.add_argument("--protocol",required=True); p.add_argument("--m27-lock",required=True); p.add_argument("--m27-dir",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    root=Path(a.repo_root).resolve(); out=Path(a.output).resolve(); lock=build_input_lock(root,Path(a.protocol).resolve(),Path(a.m27_lock).resolve(),Path(a.m27_dir).resolve()); encoded=json.dumps(lock,ensure_ascii=False,indent=2,sort_keys=True)+"\n"; out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():
        if out.read_text(encoding="utf-8")==encoded: print(f"MULTIDATASET_M28A_ANALYTICAL_RELEASE_INPUT_LOCK=ALREADY_CERTIFIED sources={lock['source_identity']['file_count']}"); return 0
        raise SystemExit(f"Refusing to overwrite different M28 input lock: {out}")
    out.write_text(encoded,encoding="utf-8"); print(f"MULTIDATASET_M28A_ANALYTICAL_RELEASE_INPUT_LOCK=PASS sources={lock['source_identity']['file_count']} parents={len(lock['parent_artifacts'])}"); return 0
if __name__=="__main__": raise SystemExit(main())
