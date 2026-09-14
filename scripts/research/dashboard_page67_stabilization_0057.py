#!/usr/bin/env python3
from __future__ import annotations

import importlib
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.python.dashboard.v3.cases_model import (
    build_cases_model,
    canonical_cases_state,
    control_cases_intent,
    initial_cases_intent,
    landscape_cases_intent,
    url_cases_intent,
)
from research.python.dashboard.v3.exports import PAGE_TABLES, resolve_export_scope
from research.python.dashboard.v3.methods_model import CAPABILITY_GAP, build_methods_model
from research.python.dashboard.v3.repository import get_v3_repository

ROOT = PROJECT_ROOT
CONTROL_IDS = ("DATASET_ID", "STRATUM_ID", "CASE_ID", "MODEL_ID", "EVIDENCE_ID", "TABS_ID")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def app_construction_gate() -> None:
    module = importlib.import_module("research.python.dashboard.app_v3")
    if getattr(module, "app", None) is None:
        raise RuntimeError("app_v3 module did not construct Dash app")
    create = getattr(module, "create_app_v3", None)
    if not callable(create) or create() is None:
        raise RuntimeError("create_app_v3 construction regression")
    print("DASHBOARD_PAGE67_0057_APP_CONSTRUCTION=PASS")


def data_gate() -> None:
    repo = get_v3_repository()
    case_counts = []
    for scope in ("HOME_CREDIT", "FREDDIE"):
        model = build_cases_model(repo, scope, "vi")
        case_counts.append(len(model.case_ids))
        if len(model.generation_rows) != 18:
            raise RuntimeError(f"{scope}: selected Case must expose exactly 18 generations")

    target = repo.study_table("case_generation_metrics", "FREDDIE").loc[
        lambda x: x["selection_stratum"].astype(str).eq("false_negative")
        & x["model_id"].astype(str).eq("qwen3_8b")
        & x["evidence_level"].astype(str).eq("S4")
    ].iloc[0]
    query = f"?dataset=FREDDIE&case={target['case_id']}&model=qwen3_8b&evidence=S4&tab=claims"
    initial = initial_cases_intent("HOME_CREDIT", query)
    if initial["dataset"] != "FREDDIE" or initial["case_id"] != str(target["case_id"]) or initial["stratum"] is not None:
        raise RuntimeError("Case initial URL precedence/identity intent drift")

    target_model = build_cases_model(repo, "FREDDIE", "vi", case_id=str(target["case_id"]), model_id="qwen3_8b", evidence_level="S4", tab="claims")
    canonical = canonical_cases_state(target_model)
    for field, value in (
        ("dataset", canonical["dataset"]),
        ("stratum", canonical["stratum"]),
        ("case_id", canonical["case_id"]),
        ("model_id", canonical["model_id"]),
        ("evidence_level", canonical["evidence_level"]),
        ("tab", canonical["tab"]),
    ):
        if control_cases_intent(field, value, canonical) is not None:
            raise RuntimeError(f"Case canonical control echo was not suppressed: {field}")
        if control_cases_intent(field, None, canonical) is not None:
            raise RuntimeError(f"Case transient None was treated as user intent: {field}")

    dataset_change = control_cases_intent("dataset", "HOME_CREDIT", canonical)
    if not dataset_change or dataset_change["case_id"] is not None or dataset_change["stratum"] is not None:
        raise RuntimeError("Case dataset transition retained stale case/stratum")
    stratum_change = control_cases_intent("stratum", "near_threshold", canonical)
    if not stratum_change or stratum_change["case_id"] is not None:
        raise RuntimeError("Case stratum transition retained stale case")
    if url_cases_intent(query, canonical) is None:
        raise RuntimeError("Case explicit in-page URL intent disappeared")

    alternate = next(row for row in target_model.generation_rows if str(row["generation_id"]) != target_model.selected_generation_id and not bool(row["is_unusable"]))
    landscape = landscape_cases_intent({
        "dataset": "FREDDIE",
        "case_id": target_model.selected_case_id,
        "model_id": alternate["model_id"],
        "evidence_level": alternate["evidence_level"],
        "generation_id": alternate["generation_id"],
        "usable": "USABLE",
    }, canonical)
    if landscape is None:
        raise RuntimeError("Case usable landscape selection did not become intent")

    if resolve_export_scope("/cases", "HOME_CREDIT", canonical) != "FREDDIE":
        raise RuntimeError("Case export does not honor local canonical dataset")
    if resolve_export_scope("/methods", "HOME_CREDIT", canonical) != "CROSS_DATASET":
        raise RuntimeError("Methods export is incorrectly filtered by global scope")

    methods = build_methods_model(repo, "vi")
    exact_metric_key = "end_to_end_faithfulness_yield::DATASET_SUMMARY::PRIMARY"
    methods_exact = build_methods_model(repo, "vi", search=f"?metric_key={exact_metric_key}")
    methods_ambiguous = build_methods_model(repo, "vi", search="?metric=end_to_end_faithfulness_yield")
    if methods_exact.selected_metric_key != exact_metric_key:
        raise RuntimeError("Methods composite metric identity deep-link drift")
    matching_e2e = [row for row in methods.metric_dictionary if row["metric_id"] == "end_to_end_faithfulness_yield"]
    if len(matching_e2e) != 2 or methods_ambiguous.selected_metric_key != methods.selected_metric_key:
        raise RuntimeError("Methods ambiguous bare metric-id guard drift")

    if tuple(case_counts) != (36, 36):
        raise RuntimeError(f"Case universe drift: {case_counts}")
    if (len(methods.research_questions), len(methods.metric_dictionary), len(methods.report_source_index), len(methods.table_names), len(methods.visualization_dictionary), len(methods.findings), len(methods.limitations)) != (6, 41, 275, 31, 560, 8, 11):
        raise RuntimeError("Methods audit topology drift")
    if {methods.method_evidence[k] for k in ("metric_formula_capability", "validator_readiness_capability", "template_readiness_capability")} != {CAPABILITY_GAP}:
        raise RuntimeError("Methods capability-gap contract drift")
    print("DASHBOARD_PAGE67_0057_DATA=PASS cases=72 audit_registry=complete capabilities=explicit")


def source_gate() -> None:
    files = {
        "cases_model": _read("research/python/dashboard/v3/cases_model.py"),
        "methods_model": _read("research/python/dashboard/v3/methods_model.py"),
        "cases_page": _read("research/python/dashboard/v3/pages/cases.py"),
        "methods_page": _read("research/python/dashboard/v3/pages/methods.py"),
        "callbacks": _read("research/python/dashboard/v3/callbacks.py"),
        "figures": _read("research/python/dashboard/v3/figures.py"),
        "css": _read("research/python/dashboard/assets/app.css"),
        "exports": _read("research/python/dashboard/v3/exports.py"),
        "shell": _read("research/python/dashboard/v3/shell.py"),
    }
    runtime = "\n".join(files.values())
    for forbidden in (
        "visualization_v2", "get_dashboard_repository", "research.python.claim_validation",
        "research.python.statistical_analysis", "research.python.decision_support", "statsmodels", "scipy", ".rank(",
    ):
        if forbidden in runtime:
            raise RuntimeError(f"Scientific/legacy token leaked into Page 6/7: {forbidden}")
    for name in ("cases_page", "methods_page"):
        source = files[name]
        if "dmc.Tabs" in source or 'columnSize="sizeToFit"' in source or ('dmc.Button' in source and 'href=' in source):
            raise RuntimeError(f"Known runtime-danger component pattern in {name}")

    callbacks = files["callbacks"]
    try:
        cases_callbacks = callbacks.split("def register_cases_callbacks(app):", 1)[1].split("def register_methods_callbacks(app):", 1)[0]
        methods_callbacks = callbacks.split("def register_methods_callbacks(app):", 1)[1].split("def register_export_callbacks(app):", 1)[0]
    except IndexError as exc:
        raise RuntimeError("Page 6/7 callback registration blocks are missing") from exc

    for route_name, route_callbacks in (("cases", cases_callbacks), ("methods", methods_callbacks)):
        if 'Input(LOCATION, "pathname")' not in route_callbacks or 'Input(LOCATION, "search")' not in route_callbacks:
            raise RuntimeError(f"{route_name}: URL pathname/search are not both first-class Inputs")

    # One callback owns every canonical Case control.  Circular synchronization
    # is intentionally local to that callback; no intent-store/cross-callback
    # dependency cycle is permitted.
    if "def cases_capture_intent" in cases_callbacks or "STATE_INTENT_STORE_ID" in cases_callbacks:
        raise RuntimeError("Unsupported multi-callback Case state cycle reintroduced")
    resolver_decorator = cases_callbacks.split("def cases_resolve_state", 1)[0].rsplit("@app.callback", 1)[1]
    if 'State(HYDRATED_STORE_ID, "data"' not in resolver_decorator or 'State(SELECTED_GENERATION_STORE_ID, "data"' not in resolver_decorator:
        raise RuntimeError("Case resolver lacks hydration/canonical state guards")
    for control in CONTROL_IDS:
        if f'Input({control}, "value"' not in resolver_decorator or f'Output({control}, "value")' not in resolver_decorator:
            raise RuntimeError(f"Case canonical resolver does not own/read {control}")
        if cases_callbacks.count(f'Output({control}, "value")') != 1:
            raise RuntimeError(f"Case control has more than one callback owner: {control}")
    for token in ("initial_cases_intent", "url_cases_intent", "control_cases_intent", "landscape_cases_intent", "len(control_triggers) != 1"):
        if token not in cases_callbacks:
            raise RuntimeError(f"Case deterministic transition guard missing: {token}")
    if "allow_duplicate=True" in cases_callbacks:
        raise RuntimeError("Case state reintroduced duplicate callback outputs")

    click_block = cases_callbacks.split("def cases_landscape_selection", 1)[1].split("@app.callback", 1)[0]
    if '"event_seq": prior_seq + 1' not in click_block:
        raise RuntimeError("Cases landscape event lacks event sequence identity")
    if 'row_data.get("claim_id")' not in cases_callbacks:
        raise RuntimeError("Case claim drawer lacks AG Grid data.claim_id fallback")
    if "HEADER_DATASET_VALUE_ID" not in cases_callbacks or "cases-header-dataset-value" not in files["cases_page"]:
        raise RuntimeError("Case header dataset context is not synchronized")
    if 'dcc.Store(id=SCOPE_STORE, data=DEFAULT_DATASET_SCOPE, storage_type="memory")' not in files["shell"]:
        raise RuntimeError("Global scope Store is not session-memory scoped")
    if "resolve_export_scope" not in files["exports"]:
        raise RuntimeError("Page-aware export scope resolver missing")
    if '"metric_key": _query_value(raw, "metric_key")' not in files["methods_model"] or "len(matching) == 1" not in files["methods_model"]:
        raise RuntimeError("Methods canonical metric-key / ambiguity guard missing")
    if 'name="Certified usable generation"' not in files["figures"]:
        raise RuntimeError("Cases deterministic SVG click layer missing")
    if PAGE_TABLES["/cases"] != ("case_index", "case_generation_metrics", "case_claim_diagnostics", "case_detail_capabilities"):
        raise RuntimeError("Cases export escaped certified table contract")
    if PAGE_TABLES["/methods"] != ("metric_dictionary", "research_questions", "findings", "limitations", "report_source_index", "visualization_dictionary"):
        raise RuntimeError("Methods export escaped certified table contract")
    if ".cases-page--golden" not in files["css"] or ".methods-page--golden" not in files["css"] or "overflow-wrap: anywhere" not in files["css"]:
        raise RuntimeError("Page 6/7 scoped CSS/long-identifier guards missing")
    print("DASHBOARD_PAGE67_0057_SOURCE=PASS url_state=first-class identity=stable portal=clean science=read-only")


def main() -> int:
    app_construction_gate()
    data_gate()
    source_gate()
    print("DASHBOARD_PAGES_6_7_STABILIZATION_0057=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
