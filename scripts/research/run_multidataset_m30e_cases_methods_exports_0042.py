#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.python.dashboard.v3.cases_model import build_cases_model
from research.python.dashboard.v3.exports import PAGE_TABLES,build_page_export
from research.python.dashboard.v3.i18n import _TEXT
from research.python.dashboard.v3.methods_model import build_methods_model
from research.python.dashboard.v3.repository import get_v3_repository

def main()->int:
    repo=get_v3_repository(); total_cases=0
    for scope in ('HOME_CREDIT','FREDDIE'):
        model=build_cases_model(repo,scope,'en'); total_cases+=len(model.case_ids)
    methods=build_methods_model(repo,'en')
    if len(methods.limitations)!=len(repo.table('limitations')): raise RuntimeError('Limitation registry incomplete')
    if set(_TEXT['vi'])!=set(_TEXT['en']): raise RuntimeError('v3 localization key mismatch')
    for path in PAGE_TABLES:
        _,payload=build_page_export(repo,path,'CROSS_DATASET','en')
        if not payload.startswith(b'PK'): raise RuntimeError(f'Invalid export package: {path}')
    print(f'MULTIDATASET_M30E_CASE_METHODS_EXPORT=PASS cases={total_cases} locales=2 exports={len(PAGE_TABLES)} limitations={len(methods.limitations)}')
    return 0
if __name__=='__main__': raise SystemExit(main())
