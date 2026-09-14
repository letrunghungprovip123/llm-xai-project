#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from research.python.common_xai.certification import certify_freddie_m14

def main()->int:
    p=argparse.ArgumentParser(description="Certify Freddie M14 XAI + Explanation IR v3.")
    p.add_argument("--workspace",type=Path,required=True); p.add_argument("--canonical-bundle",type=Path,required=True); p.add_argument("--m13-receipt",type=Path,required=True)
    p.add_argument("--dataset-profile",type=Path,default=REPO_ROOT/"config/research/datasets/freddie_sflld_2024_v1.json")
    a=p.parse_args(); r=certify_freddie_m14(workspace=a.workspace,dataset_profile_path=a.dataset_profile,canonical_bundle_path=a.canonical_bundle,m13_receipt_path=a.m13_receipt)
    s=r.summary; print(f"PASS cases={s['case_count']} features={s['feature_count']} explainer={s['explainer_type']}"); print(f"PASS ir_warnings={s['ir_warnings']}"); print(f"FREDDIE_M14_RECEIPT={r.receipt_path}"); print("FREDDIE_SFLLD_M14_XAI_IR=PASS"); return 0
if __name__=="__main__": raise SystemExit(main())
