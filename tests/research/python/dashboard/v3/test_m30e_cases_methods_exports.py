import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from research.python.dashboard.v3.cases_model import build_cases_model
from research.python.dashboard.v3.exports import PAGE_TABLES,build_page_export
from research.python.dashboard.v3.i18n import _TEXT
from research.python.dashboard.v3.methods_model import build_methods_model
from research.python.dashboard.v3.repository import get_v3_repository


def test_case_explorer_is_study_only_and_preserves_unavailable_raw_text():
    repo=get_v3_repository()
    with pytest.raises(ValueError,match='comparison scope'):
        build_cases_model(repo,'CROSS_DATASET','en')
    for scope in ('HOME_CREDIT','FREDDIE'):
        model=build_cases_model(repo,scope,'vi')
        assert len(model.case_ids)==36
        assert model.generation['end_to_end_faithfulness_yield_display']
        assert set(model.capabilities[k] for k in ('raw_generation_text','raw_claim_text','evidence_source_text'))=={'NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE'}


def test_case_explorer_preserves_unusable_and_conditional_null_semantics():
    repo=get_v3_repository()
    frame=repo.study_table('case_generation_metrics','HOME_CREDIT')
    unusable=frame.loc[frame['is_unusable'].astype(bool)]
    assert not unusable.empty
    row=unusable.iloc[0]
    model=build_cases_model(repo,'HOME_CREDIT','en',case_id=str(row['case_id']),model_id=str(row['model_id']),evidence_level=str(row['evidence_level']))
    assert bool(model.generation['is_unusable'])
    assert float(model.generation['end_to_end_faithfulness_yield'])==0.0
    assert model.generation['resolved_faithfulness_display']=='—'


def test_methods_exposes_all_certified_limitations_and_lineage_without_reconstruction():
    repo=get_v3_repository(); model=build_methods_model(repo,'en')
    assert len(model.limitations)==len(repo.table('limitations'))
    assert model.release['parent_release_id']=='certified_multidataset_analytical_release_v1'
    assert model.release['release_id']=='visualization-data-v3'
    assert model.method_evidence['replication_scope']=='MODEL_REVISION_UNKNOWN'
    assert model.method_evidence['metric_formula_capability']=='NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3'


def test_every_page_has_deterministic_certified_export_package():
    repo=get_v3_repository()
    for path in PAGE_TABLES:
        filename,payload=build_page_export(repo,path,'CROSS_DATASET','en')
        assert filename.endswith('.zip') and payload.startswith(b'PK')
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names=set(zf.namelist())
            assert 'release_metadata.json' in names and 'README.txt' in names
            assert all(f'tables/{name}.csv' in names for name in PAGE_TABLES[path])


def test_v3_localization_catalogs_have_identical_keys():
    assert set(_TEXT['vi'])==set(_TEXT['en'])


def test_m30e_source_has_no_upstream_or_v2_escape_hatch():
    paths=[Path('research/python/dashboard/v3/cases_model.py'),Path('research/python/dashboard/v3/methods_model.py'),Path('research/python/dashboard/v3/exports.py'),Path('research/python/dashboard/v3/pages/cases.py'),Path('research/python/dashboard/v3/pages/methods.py')]
    forbidden=('visualization_v2','get_dashboard_repository','claims_v3','validation_results.jsonl','scipy','statsmodels')
    for path in paths:
        source=path.read_text(encoding='utf-8')
        for token in forbidden: assert token not in source
