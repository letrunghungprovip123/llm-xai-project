from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from research.python.dashboard.v3.cases_model import (
    build_cases_model,
    canonical_cases_state,
    control_cases_intent,
    initial_cases_intent,
    landscape_cases_intent,
    url_cases_intent,
)
from research.python.dashboard.v3.exports import build_page_export, resolve_export_scope
from research.python.dashboard.v3.methods_model import build_methods_model
from research.python.dashboard.v3.repository import get_v3_repository


CONTROL_IDS = ("DATASET_ID", "STRATUM_ID", "CASE_ID", "MODEL_ID", "EVIDENCE_ID", "TABS_ID")


def _case_callbacks_source() -> str:
    source = Path("research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    return source.split("def register_cases_callbacks(app):", 1)[1].split("def register_methods_callbacks(app):", 1)[0]


def _resolver_decorator(source: str) -> str:
    return source.split("def cases_resolve_state", 1)[0].rsplit("@app.callback", 1)[1]


def test_0059_case_state_has_one_canonical_owner_and_no_cross_callback_cycle():
    source = _case_callbacks_source()
    assert "def cases_capture_intent" not in source
    assert "STATE_INTENT_STORE_ID" not in source
    assert "allow_duplicate=True" not in source

    resolver = _resolver_decorator(source)
    assert 'State(HYDRATED_STORE_ID, "data"' in resolver
    assert 'State(SELECTED_GENERATION_STORE_ID, "data"' in resolver
    assert 'Input(LOCATION, "pathname")' in resolver
    assert 'Input(LOCATION, "search")' in resolver
    assert 'Input(LANDSCAPE_SELECTION_STORE_ID, "data"' in resolver

    # Dash supports circular synchronization within one callback.  Every Case
    # control is intentionally read/written only by this resolver, never by a
    # second callback, which would create an unsupported cross-callback cycle.
    for control in CONTROL_IDS:
        assert f'Input({control}, "value"' in resolver
        assert f'Output({control}, "value")' in resolver
        assert source.count(f'Output({control}, "value")') == 1

    assert "initial_cases_intent" in source
    assert "url_cases_intent" in source
    assert "control_cases_intent" in source
    assert "landscape_cases_intent" in source
    assert "len(control_triggers) != 1" in source
    assert "if SCOPE_STORE in triggered_ids" in source


def test_0059_case_transition_rules_are_deterministic_and_ignore_echoes():
    repo = get_v3_repository()
    target = repo.study_table("case_generation_metrics", "FREDDIE").loc[
        lambda x: x["selection_stratum"].astype(str).eq("false_negative")
        & x["model_id"].astype(str).eq("qwen3_8b")
        & x["evidence_level"].astype(str).eq("S4")
    ].iloc[0]
    search = f"?dataset=FREDDIE&case={target['case_id']}&model=qwen3_8b&evidence=S4&tab=claims"

    first = initial_cases_intent("HOME_CREDIT", search)
    assert first["dataset"] == "FREDDIE"
    assert first["case_id"] == str(target["case_id"])
    assert first["stratum"] is None

    model = build_cases_model(
        repo,
        "FREDDIE",
        "vi",
        case_id=str(target["case_id"]),
        model_id="qwen3_8b",
        evidence_level="S4",
        tab="claims",
    )
    canonical = canonical_cases_state(model)
    assert canonical["generation_id"] == str(target["generation_id"])
    assert canonical["stratum"] == "false_negative"

    # Resolver-owned echoes and transient None values are not user intent.
    assert control_cases_intent("dataset", canonical["dataset"], canonical) is None
    assert control_cases_intent("stratum", canonical["stratum"], canonical) is None
    assert control_cases_intent("case_id", canonical["case_id"], canonical) is None
    assert control_cases_intent("model_id", canonical["model_id"], canonical) is None
    assert control_cases_intent("evidence_level", canonical["evidence_level"], canonical) is None
    assert control_cases_intent("tab", canonical["tab"], canonical) is None
    for field in ("dataset", "stratum", "case_id", "model_id", "evidence_level", "tab"):
        assert control_cases_intent(field, None, canonical) is None

    dataset_change = control_cases_intent("dataset", "HOME_CREDIT", canonical)
    assert dataset_change is not None
    assert dataset_change["dataset"] == "HOME_CREDIT"
    assert dataset_change["case_id"] is None and dataset_change["stratum"] is None

    stratum_change = control_cases_intent("stratum", "near_threshold", canonical)
    assert stratum_change is not None
    assert stratum_change["stratum"] == "near_threshold" and stratum_change["case_id"] is None

    model_change = control_cases_intent("model_id", "deepseek_v4_flash", canonical)
    assert model_change is not None
    assert model_change["model_id"] == "deepseek_v4_flash"
    assert model_change["dataset"] == "FREDDIE" and model_change["case_id"] == canonical["case_id"]

    url_intent = url_cases_intent(search, canonical)
    assert url_intent is not None and url_intent["dataset"] == "FREDDIE"

    alternate = next(
        row for row in model.generation_rows
        if not bool(row["is_unusable"]) and str(row["generation_id"]) != canonical["generation_id"]
    )
    selection = {
        "usable": "USABLE",
        "dataset": "FREDDIE",
        "case_id": model.selected_case_id,
        "model_id": str(alternate["model_id"]),
        "evidence_level": str(alternate["evidence_level"]),
        "generation_id": str(alternate["generation_id"]),
    }
    landscape = landscape_cases_intent(selection, canonical)
    assert landscape is not None
    assert landscape["dataset"] == "FREDDIE"
    assert landscape["case_id"] == model.selected_case_id
    assert landscape["model_id"] == str(alternate["model_id"])
    assert landscape["evidence_level"] == str(alternate["evidence_level"])


def test_0059_shell_scope_is_session_memory_not_hidden_localstorage():
    shell = Path("research/python/dashboard/v3/shell.py").read_text(encoding="utf-8")
    assert 'dcc.Store(id=SCOPE_STORE, data=DEFAULT_DATASET_SCOPE, storage_type="memory")' in shell
    assert 'dcc.Store(id=SCOPE_STORE, data=DEFAULT_DATASET_SCOPE, storage_type="local")' not in shell


def test_0059_case_header_claim_fallback_and_export_callback_use_canonical_case_identity():
    page = Path("research/python/dashboard/v3/pages/cases.py").read_text(encoding="utf-8")
    callbacks = Path("research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    assert 'id=HEADER_DATASET_VALUE_ID' in page
    assert 'Output(HEADER_DATASET_VALUE_ID, "children")' in callbacks
    assert 'row_data.get("claim_id")' in callbacks
    assert 'State(SELECTED_GENERATION_STORE_ID, "data", allow_optional=True)' in callbacks
    assert 'resolve_export_scope(route, scope, case_identity)' in callbacks
    assert 'if route == "/cases":' in callbacks
    assert 'local_dataset not in {"HOME_CREDIT", "FREDDIE"}' in callbacks


def test_0059_page_aware_export_scope_and_payload_match_visible_semantics():
    repo = get_v3_repository()
    assert resolve_export_scope("/cases", "HOME_CREDIT", {"dataset": "FREDDIE"}) == "FREDDIE"
    assert resolve_export_scope("/methods", "HOME_CREDIT", {"dataset": "FREDDIE"}) == "CROSS_DATASET"
    with pytest.raises(ValueError):
        resolve_export_scope("/cases", "HOME_CREDIT", None)

    case_name, case_bytes = build_page_export(repo, "/cases", "FREDDIE", "vi")
    assert case_name == "llm_xai_cases_freddie.zip"
    with zipfile.ZipFile(io.BytesIO(case_bytes)) as zf:
        case_index = pd.read_csv(zf.open("tables/case_index.csv"))
        case_generations = pd.read_csv(zf.open("tables/case_generation_metrics.csv"))
        case_claims = pd.read_csv(zf.open("tables/case_claim_diagnostics.csv"))
    assert len(case_index) == 36
    assert len(case_generations) == 648
    assert len(case_claims) == 12309

    methods_name, methods_bytes = build_page_export(repo, "/methods", "CROSS_DATASET", "vi")
    assert methods_name == "llm_xai_methods_cross_dataset.zip"
    with zipfile.ZipFile(io.BytesIO(methods_bytes)) as zf:
        reports = pd.read_csv(zf.open("tables/report_source_index.csv"))
        findings = pd.read_csv(zf.open("tables/findings.csv"))
    assert len(reports) == 275
    assert len(findings) == 8


def test_0059_methods_metric_deeplink_uses_unique_composite_identity():
    repo = get_v3_repository()
    exact = "end_to_end_faithfulness_yield::DATASET_SUMMARY::PRIMARY"
    model = build_methods_model(repo, "vi", search=f"?tab=metrics&metric_key={exact}")
    assert model.selected_metric_key == exact

    default = build_methods_model(repo, "vi")
    ambiguous = build_methods_model(repo, "vi", search="?tab=metrics&metric=end_to_end_faithfulness_yield")
    rows = [row for row in ambiguous.metric_dictionary if row["metric_id"] == "end_to_end_faithfulness_yield"]
    assert len(rows) == 2
    assert ambiguous.selected_metric_key == default.selected_metric_key


def test_0059_browser_gates_wait_for_exact_semantic_identity_and_capture_errors():
    cases = Path("scripts/research/dashboard_cases_visual_0055.py").read_text(encoding="utf-8")
    methods = Path("scripts/research/dashboard_methods_visual_0056.py").read_text(encoding="utf-8")
    assert "CASE_BROWSER_DEEP_LINK_IDENTITY=PASS" in cases
    assert "CASE_BROWSER_PLOTLY_CLICK=PASS" in cases
    assert "CASE_BROWSER_DASH_STATE_TRANSITION=PASS" in cases
    assert "CASE_BROWSER_LOCAL_EXPORT_SCOPE=PASS" in cases
    assert "data-generation-id" in cases and "data-case-id" in cases
    assert "metric_key" in methods
    assert "data-metric-key" in methods
    assert "data-report-number-id" in methods
    assert "data-finding-id" in methods
    assert methods.count('page.on("pageerror"') >= 3
    assert methods.count('page.on("requestfailed"') >= 3


def test_0059_final_certification_is_vi_only_and_covers_exact_page67_semantics():
    source = Path("research/python/dashboard/v3/final_certification.py").read_text(encoding="utf-8")
    assert '"locales":["vi"]' in source
    assert "Case Explorer exact Freddie deep-link" in source
    assert 'data-generation-id' in source
    assert 'data-report-number-id' in source
    assert 'llm_xai_methods_cross_dataset.zip' in source
