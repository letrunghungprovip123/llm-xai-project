#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.python.dashboard.v3.decision_model import SCENARIO_ORDER,build_decision_model
from research.python.dashboard.v3.robustness_model import build_robustness_model
from research.python.dashboard.v3.repository import get_v3_repository

def main()->int:
    repo=get_v3_repository()
    for scope in ('HOME_CREDIT','FREDDIE','CROSS_DATASET'):
        build_robustness_model(repo,scope,'en')
    cross=build_decision_model(repo,'CROSS_DATASET','en')
    if cross.primary_margin!=0.03: raise RuntimeError('Primary NI margin drift')
    if cross.robust_status!='NO_ROBUST_RECOMMENDATION': raise RuntimeError('Certified robust status drift')
    if tuple(r['scenario_id'] for r in cross.scenarios)!=SCENARIO_ORDER: raise RuntimeError('Scenario registry drift')
    print('MULTIDATASET_M30D_DECISION_ROBUSTNESS=PASS scenarios=5 margin=0.03 robust_status=NO_ROBUST_RECOMMENDATION')
    return 0
if __name__=='__main__': raise SystemExit(main())
