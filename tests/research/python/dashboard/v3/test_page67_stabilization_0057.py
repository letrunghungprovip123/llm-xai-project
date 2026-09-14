from __future__ import annotations

import importlib
from pathlib import Path

from research.python.dashboard.v3.cases_model import (
    build_cases_model,
    canonical_cases_state,
    control_cases_intent,
    initial_cases_intent,
    parse_cases_search,
)
from research.python.dashboard.v3.exports import PAGE_TABLES, resolve_export_scope
from research.python.dashboard.v3.figures import cases_performance_landscape
from research.python.dashboard.v3.methods_model import build_methods_model
from research.python.dashboard.v3.pages import cases as cases_page
from research.python.dashboard.v3.pages import methods as methods_page
from research.python.dashboard.v3.repository import get_v3_repository


def test_app_v3_constructs_after_page67_callback_registration():
    module = importlib.import_module("research.python.dashboard.app_v3")
    assert getattr(module, "app", None) is not None


def test_page67_runtime_source_avoids_all_known_page23_page45_failure_patterns():
    cases_source = Path(cases_page.__file__).read_text(encoding="utf-8")
    methods_source = Path(methods_page.__file__).read_text(encoding="utf-8")
    callbacks_source = Path("research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    source = cases_source + methods_source
    assert "dmc.Tabs" not in source
    assert 'columnSize="sizeToFit"' not in source
    assert 'component="a"' not in source
    assert "dmc.Button" not in source or "href=" not in source
    cases_callbacks = callbacks_source.split("def register_cases_callbacks(app):", 1)[1].split("def register_methods_callbacks(app):", 1)[0]
    methods_callbacks = callbacks_source.split("def register_methods_callbacks(app):", 1)[1].split("def register_export_callbacks(app):", 1)[0]
    for route_name, route_callbacks in (("cases", cases_callbacks), ("methods", methods_callbacks)):
        assert 'Input(LOCATION, "pathname")' in route_callbacks, f"{route_name}: pathname must be first-class Input"
        assert 'Input(LOCATION, "search")' in route_callbacks, f"{route_name}: search must be first-class Input"


def test_page67_drawer_ids_are_portal_safe_and_test_owned_selectors_exist():
    assert cases_page.DETAIL_DRAWER_TITLE_ID != f"{cases_page.DETAIL_DRAWER_ID}-title"
    assert cases_page.DETAIL_DRAWER_BODY_ID != f"{cases_page.DETAIL_DRAWER_ID}-body"
    cases_source = Path(cases_page.__file__).read_text(encoding="utf-8")
    methods_source = Path(methods_page.__file__).read_text(encoding="utf-8")
    assert 'data-testid": "cases-claim-drawer-content"' in cases_source
    assert 'data-testid": "methods-provenance-detail"' in methods_source
    assert 'data-testid": "methods-finding-detail"' in methods_source


def test_page67_science_source_is_read_only_and_never_falls_back_to_legacy():
    paths = [
        Path("research/python/dashboard/v3/cases_model.py"),
        Path("research/python/dashboard/v3/methods_model.py"),
        Path("research/python/dashboard/v3/pages/cases.py"),
        Path("research/python/dashboard/v3/pages/methods.py"),
    ]
    forbidden = (
        "visualization_v2", "get_dashboard_repository", "research.python.claim_validation",
        "research.python.statistical_analysis", "research.python.decision_support", "statsmodels", "scipy", ".rank(",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path}: forbidden {token}"


def test_case_drill_parser_remains_backward_compatible_with_pages_2_to_5():
    assert parse_cases_search("?dataset=FREDDIE&model=qwen3_8b&evidence=S4") == ("FREDDIE", None, "qwen3_8b", "S4")
    model = build_cases_model(get_v3_repository(), "FREDDIE", "vi", model_id="qwen3_8b", evidence_level="S4")
    assert model.scope == "FREDDIE" and model.selected_model_id == "qwen3_8b" and model.selected_evidence_level == "S4"


def test_cases_landscape_uses_real_svg_click_targets_and_single_callback_state_owner():
    model = build_cases_model(get_v3_repository(), "FREDDIE", "vi")
    figure = cases_performance_landscape(model.generation_rows, selected_generation_id=model.selected_generation_id)
    assert len(figure.data) == 2
    assert figure.data[0].type == "heatmap"
    assert figure.data[1].type == "scatter"
    click_ids = {str(custom[4]) for custom in figure.data[1].customdata}
    unusable_ids = {str(row["generation_id"]) for row in model.generation_rows if bool(row["is_unusable"])}
    assert click_ids and click_ids.isdisjoint(unusable_ids)

    callbacks = Path("research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    cases_callbacks = callbacks.split("def register_cases_callbacks(app):", 1)[1].split("def register_methods_callbacks(app):", 1)[0]
    assert "def cases_capture_intent" not in cases_callbacks
    assert "STATE_INTENT_STORE_ID" not in cases_callbacks
    assert "HYDRATED_STORE_ID" in cases_callbacks
    resolver = cases_callbacks.split("def cases_resolve_state", 1)[0].rsplit("@app.callback", 1)[1]
    for token in ("DATASET_ID", "STRATUM_ID", "CASE_ID", "MODEL_ID", "EVIDENCE_ID", "TABS_ID"):
        assert f'Input({token}, "value"' in resolver
        assert f'Output({token}, "value")' in resolver
        assert cases_callbacks.count(f'Output({token}, "value")') == 1
    assert 'State(HYDRATED_STORE_ID, "data"' in resolver
    assert 'State(SELECTED_GENERATION_STORE_ID, "data"' in resolver
    assert "len(control_triggers) != 1" in cases_callbacks
    click_block = cases_callbacks.split("def cases_landscape_selection", 1)[1].split("@app.callback", 1)[0]
    assert '"event_seq": prior_seq + 1' in click_block
    assert "allow_duplicate=True" not in click_block


def test_page67_export_contract_keeps_certified_tables_only():
    assert PAGE_TABLES["/cases"] == ("case_index", "case_generation_metrics", "case_claim_diagnostics", "case_detail_capabilities")
    assert PAGE_TABLES["/methods"] == ("metric_dictionary", "research_questions", "findings", "limitations", "report_source_index", "visualization_dictionary")


def test_methods_capability_gaps_are_owned_by_model_not_reconstructed_in_page():
    model = build_methods_model(get_v3_repository(), "vi")
    assert model.method_evidence["metric_formula_capability"] == "NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3"
    assert model.method_evidence["validator_readiness_capability"] == "NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3"
    assert model.method_evidence["template_readiness_capability"] == "NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3"


def test_page67_css_is_scoped_and_contains_long_identifier_overflow_guards():
    css = Path("research/python/dashboard/assets/app.css").read_text(encoding="utf-8")
    assert ".cases-page--golden" in css
    assert ".methods-page--golden" in css
    assert "overflow-wrap: anywhere" in css
    assert ".methods-provenance-layout" in css


def test_cases_first_paint_url_outranks_global_scope_and_control_echo_is_suppressed():
    repo = get_v3_repository()
    target = repo.study_table("case_generation_metrics", "FREDDIE").loc[
        lambda x: x.model_id.astype(str).eq("qwen3_8b") & x.evidence_level.astype(str).eq("S4")
    ].iloc[0]
    search = f"?dataset=FREDDIE&case={target['case_id']}&model=qwen3_8b&evidence=S4&tab=claims"
    intent = initial_cases_intent("HOME_CREDIT", search)
    assert intent["dataset"] == "FREDDIE"
    assert intent["case_id"] == str(target["case_id"])
    assert intent["stratum"] is None
    model = build_cases_model(repo, "FREDDIE", "vi", case_id=str(target["case_id"]), model_id="qwen3_8b", evidence_level="S4", tab="claims")
    canonical = canonical_cases_state(model)
    for field, value in (
        ("dataset", canonical["dataset"]), ("stratum", canonical["stratum"]), ("case_id", canonical["case_id"]),
        ("model_id", canonical["model_id"]), ("evidence_level", canonical["evidence_level"]), ("tab", canonical["tab"]),
    ):
        assert control_cases_intent(field, value, canonical) is None
        assert control_cases_intent(field, None, canonical) is None


def test_page67_export_scope_uses_page_semantic_authority():
    identity = {"dataset": "FREDDIE"}
    assert resolve_export_scope("/cases", "HOME_CREDIT", identity) == "FREDDIE"
    assert resolve_export_scope("/methods", "HOME_CREDIT", identity) == "CROSS_DATASET"
    assert resolve_export_scope("/decision", "HOME_CREDIT", identity) == "HOME_CREDIT"


def test_v3_global_scope_store_cannot_revive_stale_localstorage_state():
    source = Path("research/python/dashboard/v3/shell.py").read_text(encoding="utf-8")
    assert 'dcc.Store(id=SCOPE_STORE, data=DEFAULT_DATASET_SCOPE, storage_type="memory")' in source


def test_case_header_and_claim_event_fallback_are_runtime_synchronized():
    page_source = Path(cases_page.__file__).read_text(encoding="utf-8")
    callbacks = Path("research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    assert 'id=HEADER_DATASET_VALUE_ID' in page_source
    assert 'Output(HEADER_DATASET_VALUE_ID, "children")' in callbacks
    assert 'row_data.get("claim_id")' in callbacks
