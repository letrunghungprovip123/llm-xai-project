#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.python.evidence_exposure.subset_certification import build_and_certify_freddie_m16

def main()->int:
 p=argparse.ArgumentParser(description="Freeze the exact Freddie 36-case / 216-package replication cohort."); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--canonical-bundle",type=Path,required=True); p.add_argument("--m15-receipt",type=Path,required=True); p.add_argument("--dataset-profile",type=Path,default=ROOT/"config/research/datasets/freddie_sflld_2024_v1.json"); p.add_argument("--seed",type=int,default=20260711); a=p.parse_args(); r=build_and_certify_freddie_m16(workspace=a.workspace,dataset_profile_path=a.dataset_profile,canonical_bundle_path=a.canonical_bundle,m15_receipt_path=a.m15_receipt,seed=a.seed); print(f"PASS selected_cases={r.selected_case_count} selected_packages={r.selected_package_count}"); print(f"FREDDIE_EVALUATION_SUBSET={r.subset_path}"); print(f"FREDDIE_M16_RECEIPT={r.receipt_path}"); print("FREDDIE_SFLLD_M16_EVALUATION_COHORT=PASS"); return 0
if __name__=="__main__": raise SystemExit(main())
