#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.python.common_xai.evidence_certification import certify_freddie_m15

def main()->int:
 p=argparse.ArgumentParser(description="Certify Freddie M15 S0-S5 evidence and separability."); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--canonical-bundle",type=Path,required=True); p.add_argument("--m14-receipt",type=Path,required=True); p.add_argument("--dataset-profile",type=Path,default=ROOT/"config/research/datasets/freddie_sflld_2024_v1.json"); a=p.parse_args(); r=certify_freddie_m15(workspace=a.workspace,dataset_profile_path=a.dataset_profile,canonical_bundle_path=a.canonical_bundle,m14_receipt_path=a.m14_receipt); x=r.report; print(f"PASS cases={x.case_count} packages={x.package_count}"); print(f"PASS S1_S3_equal={x.s1_s3_equal_rate:.6f} S3_S4_equal={x.s3_s4_equal_rate:.6f} S1_S4_equal={x.s1_s4_equal_rate:.6f}"); print(f"PASS semantic_unknown_concept_rate={x.unknown_concept_rate:.6f} semantic_items={x.semantic_item_count} semantic_unknown={x.semantic_unknown_concept_count}"); print(f"PASS S1_raw_items={x.s1_raw_item_count} S1_concept_exposure={x.s1_concept_exposure_count}"); print(f"FREDDIE_M15_RECEIPT={r.receipt_path}"); print("EVIDENCE_CONDITION_SEPARABILITY=PASS"); print("FREDDIE_SFLLD_M15_EVIDENCE=PASS"); return 0
if __name__=="__main__": raise SystemExit(main())
