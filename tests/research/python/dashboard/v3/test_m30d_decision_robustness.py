from pathlib import Path

from research.python.dashboard.v3.decision_model import SCENARIO_ORDER, build_decision_model
from research.python.dashboard.v3.repository import get_v3_repository
from research.python.dashboard.v3.robustness_model import build_robustness_model


def test_decision_preserves_frozen_roles_and_no_winner():
    repo=get_v3_repository()
    cross=build_decision_model(repo,'CROSS_DATASET','en')
    assert cross.primary_margin==0.03
    assert cross.robust_status=='NO_ROBUST_RECOMMENDATION'
    assert tuple(r['scenario_id'] for r in cross.scenarios)==SCENARIO_ORDER
    assert all(r['status']=='NO_ROBUST_RECOMMENDATION' for r in cross.scenarios)
    roles={r['evidence_level']:r['option_role'] for r in cross.options}
    assert roles['S0']=='CONTROL'
    assert roles['S5']=='FALLBACK_ONLY'
    assert all(not bool(r['robust_eligible']) for r in cross.options)


def test_dataset_decisions_use_certified_recommendation_and_ni():
    repo=get_v3_repository()
    hc=build_decision_model(repo,'HOME_CREDIT','vi')
    fr=build_decision_model(repo,'FREDDIE','en')
    assert len(hc.recommendations)==len(fr.recommendations)==1
    assert hc.recommendations[0]['status']=='SELECTED' and fr.recommendations[0]['status']=='SELECTED'
    assert hc.recommendations[0]['option_id'] in {r['option_id'] for r in hc.options}
    assert fr.recommendations[0]['option_id'] in {r['option_id'] for r in fr.options}
    assert len(hc.options)==len(fr.options)==18
    assert all('ni_status' in r for r in hc.options+fr.options)


def test_robustness_keeps_primary_and_sensitivity_lanes_distinct():
    model=build_robustness_model(get_v3_repository(),'CROSS_DATASET','en')
    lanes={r['margin_lane_id']:r for r in model.margin_rows}
    assert lanes['PRIMARY_003']['analysis_status']=='PRIMARY_CERTIFIED'
    assert lanes['PRIMARY_003']['margin']==0.03
    assert lanes['STRICT_002']['analysis_status']=='SENSITIVITY_ONLY'
    assert lanes['RELAXED_005']['analysis_status']=='SENSITIVITY_ONLY'
    assert int(lanes['PRIMARY_003']['robust_primary_candidate_count'])==0
    assert str(lanes['PRIMARY_003']['active_pool_mode'])=='NONE'
    assert model.validator_status=='NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3'
    assert model.template_status=='NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3'


def test_m30d_source_never_imports_decision_or_statistics_engines():
    paths=[Path('research/python/dashboard/v3/decision_model.py'),Path('research/python/dashboard/v3/robustness_model.py'),Path('research/python/dashboard/v3/pages/decision.py'),Path('research/python/dashboard/v3/pages/robustness.py')]
    forbidden=('scipy','statsmodels','bootstrap(','pareto(','noninferiority','visualization_v2','get_dashboard_repository','idxmax(','argmax(')
    for path in paths:
        source=path.read_text(encoding='utf-8')
        for token in forbidden:
            # noninferiority_results is a certified table name and is allowed.
            if token=='noninferiority' and 'noninferiority_results' in source:
                continue
            assert token not in source
