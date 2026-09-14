#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.python.evidence_exposure.package_builder import build_all_packages_for_ir
from research.python.evidence_exposure.select_evaluation_subset import validate_case_matrix,build_case_rows,select_balanced_cases

def main()->int:
 p=argparse.ArgumentParser(description="Verify the generalized 36-case selector reproduces the frozen Home Credit cohort."); p.add_argument("--historical-ir",type=Path,required=True); p.add_argument("--historical-selected-csv",type=Path,required=True); p.add_argument("--seed",type=int,default=20260711); a=p.parse_args(); irs=[json.loads(x) for x in a.historical_ir.read_text(encoding="utf-8").splitlines() if x.strip()]; packages=[]
 for ir in irs: packages.extend(build_all_packages_for_ir(ir))
 selected=select_balanced_cases(build_case_rows(validate_case_matrix(packages),a.seed),6); actual=[(r["case_id"],r["stratum"],r["difficulty_group"],round(float(r["difficulty_score"]),8)) for r in selected]
 with a.historical_selected_csv.open(encoding="utf-8") as h: expected=[(r["case_id"],r["stratum"],r["difficulty_group"],round(float(r["difficulty_score"]),8)) for r in csv.DictReader(h)]
 if actual != expected: raise SystemExit("HOME_CREDIT_36_SELECTOR_PARITY=FAIL")
 print(f"PASS ir_records={len(irs)} reconstructed_packages={len(packages)} selected_cases={len(selected)}"); print("HOME_CREDIT_36_SELECTOR_PARITY=PASS"); return 0
if __name__=="__main__": raise SystemExit(main())
