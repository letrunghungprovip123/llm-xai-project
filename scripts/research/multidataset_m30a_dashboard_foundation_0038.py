#!/usr/bin/env python3
from __future__ import annotations
import argparse,ast
from pathlib import Path
from research.python.dashboard.v3.release_guard import get_v3_release_guard
from research.python.dashboard.v3.repository import get_v3_repository
from research.python.dashboard.v3.settings import DATASET_SCOPES

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument('--repo-root',required=True); a=p.parse_args(); root=Path(a.repo_root).resolve(); guard=get_v3_release_guard()
 if not guard.ready: raise ValueError(f'M30A release guard failed: {guard.errors}')
 repo=get_v3_repository(); [repo.validate_scope(s) for s in DATASET_SCOPES]; repo.study_overview('HOME_CREDIT'); repo.study_overview('FREDDIE'); repo.cross_overview()
 forbidden=('scipy','statsmodels','metric_engineering','statistical_analysis','robustness.build','decision_support')
 bad=[]
 for q in sorted((root/'research/python/dashboard/v3').rglob('*.py')):
  text=q.read_text(); ast.parse(text)
  for token in forbidden:
   if token in text: bad.append(f'{q.relative_to(root)}::{token}')
 if bad: raise ValueError(f'M30A forbidden scientific dependency: {bad}')
 print(f'MULTIDATASET_M30A_DASHBOARD_FOUNDATION=PASS scopes={len(DATASET_SCOPES)} tables={guard.release.table_count} release={guard.release.release_id}'); return 0
if __name__=='__main__': raise SystemExit(main())
