#!/usr/bin/env python3
from __future__ import annotations
import argparse,ast
from pathlib import Path
from research.python.dashboard.v3.overview_model import build_overview_model
from research.python.dashboard.v3.repository import get_v3_repository

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument('--repo-root',required=True); a=p.parse_args(); root=Path(a.repo_root).resolve(); repo=get_v3_repository(); models=[build_overview_model(repo,s,l) for s in ['HOME_CREDIT','FREDDIE','CROSS_DATASET'] for l in ['vi','en']]
 bad=[]
 for model in models:
  for card in model.cards:
   if not card.report_number_id: bad.append(f'{model.scope}:{card.key}')
 cross=[m for m in models if m.scope=='CROSS_DATASET'][0]
 if cross.robust_recommendation_status!=repo.release.robust_recommendation_status: bad.append('robust_recommendation_status')
 source=(root/'research/python/dashboard/v3/overview_model.py').read_text(); ast.parse(source)
 for token in ['sort_values(','.groupby(','.mean(','scipy','statsmodels','argmax(','idxmax(']:
  if token in source: bad.append(f'forbidden_overview_computation::{token}')
 if bad: raise ValueError(f'M30B overview certification failed: {bad}')
 print(f'MULTIDATASET_M30B_OVERVIEW=PASS scopes=3 locales=2 headline_cards={sum(len(m.cards) for m in models)//2} robust_status={cross.robust_recommendation_status}'); return 0
if __name__=='__main__': raise SystemExit(main())
