#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from research.python.robustness.common import read_json, sha256_file
from research.python.visualization_v3.common import stable_json
from research.python.visualization_v3.input_lock import build_input_lock

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--repo-root",required=True); p.add_argument("--protocol",required=True); p.add_argument("--output",required=True); a=p.parse_args(); root=Path(a.repo_root).resolve(); protocol=Path(a.protocol).resolve(); out=Path(a.output).resolve(); lock=build_input_lock(root,protocol)
 if out.exists():
  old=read_json(out)
  if old!=lock: raise ValueError("Existing M29A input lock differs from current certified inputs/source identity.")
  print(f"MULTIDATASET_M29A_VISUALIZATION_INPUT_LOCK=ALREADY_CERTIFIED sources={len(lock['authorized_sources'])} report_numbers={lock['m28_report_number_count']}"); return 0
 out.parent.mkdir(parents=True,exist_ok=True); stable_json(out,lock)
 print(f"MULTIDATASET_M29A_VISUALIZATION_INPUT_LOCK=PASS sources={len(lock['authorized_sources'])} report_numbers={lock['m28_report_number_count']} scope={lock['m28_replication_scope']}"); return 0
if __name__=="__main__": raise SystemExit(main())
