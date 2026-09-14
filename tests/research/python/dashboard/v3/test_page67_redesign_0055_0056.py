from __future__ import annotations

from pathlib import Path

from dash import dcc

from research.python.dashboard.v3.cases_model import (
    build_cases_model,
    canonical_cases_state,
    generation_from_landscape_click,
    parse_cases_state,
)
from research.python.dashboard.v3.figures import cases_performance_landscape
from research.python.dashboard.v3.methods_model import (
    CAPABILITY_GAP,
    build_methods_model,
    finding_by_id,
    metric_by_key,
    report_by_id,
    schema_for_table,
)
from research.python.dashboard.v3.pages import cases as cases_page
from research.python.dashboard.v3.pages import methods as methods_page
from research.python.dashboard.v3.repository import get_v3_repository


def _walk(component):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for item in component:
            yield from _walk(item)
        return
    yield component
    children = getattr(component, "children", None)
    if children is not None:
        yield from _walk(children)


def _by_id(component, target):
    matches = [item for item in _walk(component) if getattr(item, "id", None) == target]
    assert len(matches) == 1, f"{target}: expected 1 component, found {len(matches)}"
    return matches[0]


def test_cases_certified_universe_and_identity_are_complete_per_study():
    repo = get_v3_repository()
    for scope in ("HOME_CREDIT", "FREDDIE"):
        model = build_cases_model(repo, scope, "vi")
        assert len(model.case_ids) == 36
        assert len(model.strata) == 6
        assert len(model.stratum_case_ids) == 6
        assert len(model.generation_rows) == 18
        assert {row["model_id"] for row in model.generation_rows} == {"qwen3_8b", "deepseek_v4_flash", "phi4_mini_instruct"}
        assert {row["evidence_level"] for row in model.generation_rows} == {f"S{i}" for i in range(6)}
        assert sum(int(row["claim_count"]) for row in model.status_counts) == int(model.generation["claim_count"])
        assert len(model.claims) == int(model.generation["claim_count"])
        assert model.selected_identity["generation_id"] == model.generation["generation_id"]
        assert {model.capabilities[key] for key in ("raw_generation_text", "raw_claim_text", "evidence_source_text")} == {"NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE"}


def test_cases_direct_deep_link_resolves_exact_case_stratum_generation_and_tab():
    repo = get_v3_repository()
    row = repo.study_table("case_generation_metrics", "FREDDIE").loc[
        lambda x: x["selection_stratum"].astype(str).eq("false_negative")
        & x["model_id"].astype(str).eq("qwen3_8b")
        & x["evidence_level"].astype(str).eq("S4")
    ].iloc[0]
    model = build_cases_model(
        repo,
        "FREDDIE",
        "vi",
        search=f"?dataset=FREDDIE&case={row['case_id']}&model=qwen3_8b&evidence=S4&tab=claims",
    )
    assert model.selected_case_id == str(row["case_id"])
    assert model.selected_stratum == "false_negative"
    assert model.selected_model_id == "qwen3_8b"
    assert model.selected_evidence_level == "S4"
    assert model.selected_generation_id == str(row["generation_id"])
    assert model.initial_tab == "claims"


def test_cases_landscape_is_exact_3x6_and_unusable_cells_are_not_visualized_as_zero():
    repo = get_v3_repository()
    generation_frame = repo.study_table("case_generation_metrics", "HOME_CREDIT")
    unusable = generation_frame.loc[generation_frame["is_unusable"].astype(bool)].iloc[0]
    model = build_cases_model(
        repo,
        "HOME_CREDIT",
        "vi",
        case_id=str(unusable["case_id"]),
        model_id=str(unusable["model_id"]),
        evidence_level=str(unusable["evidence_level"]),
    )
    figure = cases_performance_landscape(model.generation_rows, selected_generation_id=model.selected_generation_id)
    assert len(figure.data) == 2
    heatmap, click_layer = figure.data
    assert heatmap.type == "heatmap"
    assert click_layer.type == "scatter"
    assert len(heatmap.z) == 3 and all(len(row) == 6 for row in heatmap.z)
    model_index = {"qwen3_8b": 0, "deepseek_v4_flash": 1, "phi4_mini_instruct": 2}[str(unusable["model_id"])]
    evidence_index = int(str(unusable["evidence_level"]).replace("S", ""))
    assert heatmap.z[model_index][evidence_index] is None
    assert heatmap.text[model_index][evidence_index] == "N/A"
    overlay_generation_ids = {str(row[4]) for row in click_layer.customdata}
    assert str(unusable["generation_id"]) not in overlay_generation_ids
    assert len(overlay_generation_ids) == len({str(row["generation_id"]) for row in model.generation_rows if not bool(row["is_unusable"]) and row.get("end_to_end_faithfulness_yield") is not None and str(row.get("end_to_end_faithfulness_yield")).lower() != "nan"})


def test_cases_heatmap_customdata_resolves_stable_generation_identity():
    repo = get_v3_repository()
    model = build_cases_model(repo, "HOME_CREDIT", "vi")
    figure = cases_performance_landscape(model.generation_rows, selected_generation_id=model.selected_generation_id)
    click_layer = figure.data[1]
    target = next(
        list(custom) for custom in click_layer.customdata
        if str(custom[2]) == "deepseek_v4_flash" and str(custom[3]) == "S4"
    )
    payload = {"points": [{"customdata": target}]}
    resolved = generation_from_landscape_click(payload)
    assert resolved is not None
    assert resolved["dataset"] == "HOME_CREDIT"
    assert resolved["case_id"] == model.selected_case_id
    assert resolved["model_id"] == "deepseek_v4_flash"
    assert resolved["evidence_level"] == "S4"
    assert resolved["generation_id"] == target[4]
    assert resolved["usable"] == "USABLE"


def test_cases_page_has_stable_shell_portal_safe_drawer_and_exact_claim_grid():
    model = build_cases_model(get_v3_repository(), "HOME_CREDIT", "vi")
    page = cases_page.render(model)
    assert cases_page.DETAIL_DRAWER_TITLE_ID != f"{cases_page.DETAIL_DRAWER_ID}-title"
    assert cases_page.DETAIL_DRAWER_BODY_ID != f"{cases_page.DETAIL_DRAWER_ID}-body"
    assert _by_id(page, cases_page.SELECTED_GENERATION_STORE_ID).data == canonical_cases_state(model)
    assert _by_id(page, cases_page.LANDSCAPE_SELECTION_STORE_ID).data is None
    assert len(_by_id(page, cases_page.CLAIM_GRID_ID).rowData) == len(model.claims)
    assert _by_id(page, cases_page.TABS_ID).value == "landscape"
    source = Path(cases_page.__file__).read_text(encoding="utf-8")
    assert 'data-testid": "cases-selected-generation"' in source
    assert 'data-testid": "cases-claim-drawer-content"' in source
    assert "Certified diagnostic source span" in source
    assert "Original generation" not in source


def test_cases_click_event_has_dedicated_callback_and_does_not_compete_with_canonical_resolver():
    source = Path("research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    cases_block = source.split("def register_cases_callbacks(app):", 1)[1].split("def register_methods_callbacks(app):", 1)[0]
    resolver = cases_block.split("def cases_resolve_state", 1)[0]
    assert 'Input(LANDSCAPE_ID, "clickData"' not in resolver
    assert "def cases_landscape_selection" in cases_block
    click_block = cases_block.split("def cases_landscape_selection", 1)[1].split("@app.callback", 1)[0]
    assert 'clicked.get("usable") != "USABLE"' in click_block
    assert '"event_seq": prior_seq + 1' in click_block
    assert 'Output(LANDSCAPE_SELECTION_STORE_ID, "data")' in cases_block
    assert 'Input(LANDSCAPE_SELECTION_STORE_ID, "data"' in cases_block
    assert 'allow_duplicate=True' not in click_block


def test_methods_model_exposes_complete_certified_audit_surface():
    model = build_methods_model(get_v3_repository(), "vi")
    assert len(model.research_questions) == 6
    assert len(model.metric_dictionary) == 41
    assert len(model.report_source_index) == 275
    assert len(model.table_names) == 31
    assert len(model.visualization_dictionary) == 560
    assert len(model.findings) == 8
    assert len(model.limitations) == 11
    assert model.release["scientific_recomputation_allowed"] is False
    assert model.method_evidence["metric_formula_capability"] == CAPABILITY_GAP
    assert model.method_evidence["validator_readiness_capability"] == CAPABILITY_GAP
    assert model.method_evidence["template_readiness_capability"] == CAPABILITY_GAP


def test_methods_deep_links_resolve_exact_metric_report_table_and_finding():
    repo = get_v3_repository()
    report_id = "dataset::HOME_CREDIT::mean_e2e"
    model = build_methods_model(
        repo,
        "vi",
        search=f"?tab=traceability&report={report_id}&table=case_generation_metrics&finding=F_ROBUSTNESS_MARGIN&metric_key=end_to_end_faithfulness_yield::DATASET_SUMMARY::PRIMARY",
    )
    assert model.initial_tab == "traceability"
    assert model.selected_report_id == report_id
    assert model.selected_table_name == "case_generation_metrics"
    assert model.selected_finding_id == "F_ROBUSTNESS_MARGIN"
    assert model.selected_metric_key == "end_to_end_faithfulness_yield::DATASET_SUMMARY::PRIMARY"
    assert metric_by_key(model, model.selected_metric_key)["metric_id"] == "end_to_end_faithfulness_yield"
    report = report_by_id(model, report_id)
    assert report["source_artifact_id"] == "home_credit_generation_metrics"
    assert len(str(report["source_sha256"])) == 64
    assert schema_for_table(model, "case_generation_metrics")
    finding = finding_by_id(model, "F_ROBUSTNESS_MARGIN")
    assert finding["supporting_report_refs"] == ("robustness::margin::status",)
    assert tuple(row["limitation_id"] for row in finding["limitations"]) == ("M27_MARGIN_SENSITIVITY",)


def test_methods_page_is_a_stable_audit_shell_not_a_documentation_dump():
    model = build_methods_model(get_v3_repository(), "vi")
    page = methods_page.render(model)
    assert _by_id(page, methods_page.TABS_ID).value == "study"
    assert len(_by_id(page, methods_page.REPORT_GRID_ID).rowData) == 275
    assert len(_by_id(page, methods_page.SCHEMA_GRID_ID).rowData) > 0
    assert len(_by_id(page, methods_page.LIMITATIONS_GRID_ID).rowData) == 11
    links = [item for item in _walk(page) if isinstance(item, dcc.Link)]
    # Finding evidence chains use self-deep-links to canonical report provenance.
    finding = methods_page.finding_detail(model, "F_ROBUSTNESS_MARGIN")
    finding_links = [item.href for item in _walk(finding) if isinstance(item, dcc.Link)]
    assert any(href.startswith("/methods?tab=traceability") and "robustness%3A%3Amargin%3A%3Astatus" in href for href in finding_links)
    source = Path(methods_page.__file__).read_text(encoding="utf-8")
    assert "Formula capability" not in source
    assert "NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3" not in source  # comes from model contract, not duplicated literal
    assert 'data-testid": "methods-provenance-detail"' in source


def test_page67_query_parsers_sanitize_invalid_state():
    state = parse_cases_state("?dataset=CROSS_DATASET&stratum=wat&model=wat&evidence=S9&tab=wat")
    assert state == {"dataset": None, "case_id": None, "model_id": None, "evidence": None, "stratum": None, "tab": None}
