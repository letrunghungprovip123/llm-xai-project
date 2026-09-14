from pathlib import Path
import json
from research.python.visualization_v3.build import build_tables
from research.python.visualization_v3.input_lock import build_input_lock
from research.python.visualization_v3.validate import validate_tables

def _state():
 root=Path.cwd(); protocol=json.loads((root/'config/research/replication/multidataset_visualization_v3.json').read_text()); lock=build_input_lock(root,root/'config/research/replication/multidataset_visualization_v3.json'); return root,protocol,lock

def test_m29_tables_are_pure_certified_views():
 root,p,l=_state(); tables=build_tables(root,l); v=validate_tables(root,p,l,tables)
 assert v['passed'], v
 assert len(tables['study_summary'])==2
 assert len(tables['option_performance'])==36
 assert len(tables['planned_contrasts'])==66
 assert len(tables['case_generation_metrics'])==1296
 assert len(tables['case_index'])==72
 assert 'mean_e2e' not in tables['case_index'].columns
 assert set(tables['case_detail_capabilities']['raw_generation_text'])=={'NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE'}

def test_no_robust_recommendation_is_not_nullified():
 root,p,l=_state(); tables=build_tables(root,l)
 if l['m28_robust_recommendation_status']=='NO_ROBUST_RECOMMENDATION':
  x=tables['recommendations'].query("recommendation_scope == 'CROSS_DATASET_ROBUST'")
  assert len(x)>=1 and set(x.status.astype(str))=={'NO_ROBUST_RECOMMENDATION'}

def test_option_mean_e2e_retains_m28_provenance():
 root,p,l=_state(); x=build_tables(root,l)['option_performance']
 assert x['mean_e2e_report_number_id'].notna().all()
 assert x['analysis_lane'].eq('PRIMARY').all()
