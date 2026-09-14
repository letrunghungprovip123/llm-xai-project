#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.python.dashboard.v3.effectiveness_model import build_effectiveness_model
from research.python.dashboard.v3.mechanisms_model import build_mechanisms_model
from research.python.dashboard.v3.repository import get_v3_repository

def main()->int:
    repo=get_v3_repository()
    for scope in ('HOME_CREDIT','FREDDIE','CROSS_DATASET'):
        e=build_effectiveness_model(repo,scope,'en'); m=build_mechanisms_model(repo,scope,'en')
        if len(e.option_rows)!=18: raise RuntimeError(f'{scope}: expected 18 option identities')
        if not m.loss_rows: raise RuntimeError(f'{scope}: missing mechanism loss rows')
    print('MULTIDATASET_M30C_EFFECTIVENESS_MECHANISMS=PASS scopes=3 options=18')
    return 0
if __name__=='__main__': raise SystemExit(main())
