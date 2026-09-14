from research.python.dashboard.v3.release_guard import get_v3_release_guard
from research.python.dashboard.v3.repository import get_v3_repository
from research.python.dashboard.v3.settings import DATASET_SCOPES

def test_v3_guard_accepts_only_certified_v3():
 g=get_v3_release_guard(); assert g.ready,g.errors; assert g.release.release_id=='visualization-data-v3'

def test_repository_has_three_explicit_scopes():
 r=get_v3_repository(); assert DATASET_SCOPES==('HOME_CREDIT','FREDDIE','CROSS_DATASET'); assert r.study_overview('HOME_CREDIT').dataset_scope=='HOME_CREDIT'; assert r.study_overview('FREDDIE').dataset_scope=='FREDDIE'; assert r.cross_overview().replication_scope

def test_cross_dataset_is_not_a_fake_case_dataset():
 r=get_v3_repository()
 import pytest
 with pytest.raises(ValueError,match='comparison scope'): r.study_overview('CROSS_DATASET')

def test_v3_runtime_has_no_visualization_v2_fallback():
 from pathlib import Path
 paths=[Path('research/python/dashboard/app_v3.py'),*Path('research/python/dashboard/v3').rglob('*.py')]
 for path in paths:
  source=path.read_text(encoding='utf-8')
  assert 'visualization_v2' not in source
  assert 'get_dashboard_repository' not in source
