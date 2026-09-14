from pathlib import Path

from research.python.dashboard.v3.final_certification import PAGE_CONTENT_IDS, i18n_audit, source_isolation_audit, static_precheck, traceability_audit
from research.python.common.paths import DEFAULT_PATHS


def test_all_seven_pages_are_real_final_routes():
    assert set(PAGE_CONTENT_IDS)=={'/','/effectiveness','/mechanisms','/decision','/robustness','/cases','/methods'}
    source=Path('research/python/dashboard/v3/pages/__init__.py').read_text(encoding='utf-8')
    assert '_placeholder' not in source
    assert 'register_page()' in source


def test_final_static_precheck_is_fully_green():
    result=static_precheck(DEFAULT_PATHS.project_root)
    assert result['passed'],result
    assert result['source_isolation']['passed']
    assert result['i18n']['passed']
    assert result['traceability']['passed']


def test_final_source_isolation_rejects_no_v2_or_science_engine_imports():
    result=source_isolation_audit(DEFAULT_PATHS.project_root)
    assert result['passed'],result


def test_final_traceability_keeps_all_headlines_source_backed():
    result=traceability_audit()
    assert result['passed'],result
    assert result['report_number_backed_overview_cards']==16


def test_final_i18n_certifies_vietnamese_only_product_contract():
    result=i18n_audit()
    assert result['passed'],result
    assert result['locales']==['vi']
