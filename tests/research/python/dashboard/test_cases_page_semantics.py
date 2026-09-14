"""Source-level semantics and callback-locality tests for Page 6."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PAGE = ROOT / "research/python/dashboard/pages/cases.py"
CALLBACKS = ROOT / "research/python/dashboard/callbacks/cases.py"
COMPONENTS = ROOT / "research/python/dashboard/components/cases.py"
CSS = ROOT / "research/python/dashboard/assets/app.css"
CALLBACK_REGISTRY = ROOT / "research/python/dashboard/callbacks/__init__.py"


def test_page6_preserves_research_and_privacy_boundaries() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PAGE, CALLBACKS, COMPONENTS)
    )
    required = (
        "single case is descriptive evidence",
        "not statistical evidence",
        "Template is not a fourth LLM",
        "Candidate is the primary measurement artifact",
        "V4 is sensitivity-only",
        "Human naturalness is not measured",
        "No raw applicant record",
        "missing, not zero",
    )
    lowered = text.lower()
    assert all(item.lower() in lowered for item in required)


def test_page6_does_not_make_prohibited_case_claims() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (PAGE, CALLBACKS, COMPONENTS)
    )
    prohibited = (
        "representative case",
        "best case",
        "worst case",
        "v4 is more correct",
        "template model",
        "human-quality score",
        "zero-latency advantage",
    )
    assert not any(item in text for item in prohibited)


def test_page6_control_locality_matches_the_plan() -> None:
    text = PAGE.read_text(encoding="utf-8")
    matrix_control = text.index('html.Label("Matrix metric")')
    matrix_chart = text.index('graph_id=CASES_MATRIX_ID')
    evidence_control = text.index('html.Label("Evidence condition")')
    evidence_panel = text.index('id=CASES_EVIDENCE_PACKAGE_ID')
    focused_model = text.index('html.Label("Focused LLM")')
    utilization_chart = text.index('graph_id=CASES_UTILIZATION_ID')

    assert matrix_control < matrix_chart
    assert matrix_chart < evidence_control < evidence_panel
    assert evidence_panel < focused_model < utilization_chart
    assert "Focused LLM changes utilization, claims, structure and paired comparisons; it does not change the evidence package above." in text


def test_page6_callback_helpers_have_stable_output_arity() -> None:
    tree = ast.parse(CALLBACKS.read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    expected = {
        "cohort_updates": 4,
        "case_identity_updates": 2,
        "matrix_updates": 2,
        "focused_diagnostics_updates": 5,
    }
    for name, arity in expected.items():
        returns = [
            node for node in ast.walk(functions[name])
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple)
        ]
        assert len(returns) == 1
        assert len(returns[0].value.elts) == arity


def test_evidence_package_callback_does_not_depend_on_focused_model() -> None:
    tree = ast.parse(CALLBACKS.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "evidence_package_update"
    )
    assert [argument.arg for argument in function.args.args] == [
        "case_id", "evidence_level", "locale"
    ]


def test_template_matrix_click_preserves_focused_llm() -> None:
    text = CALLBACKS.read_text(encoding="utf-8")
    assert 'if generator_family == "TEMPLATE" or generator_id == "template_baseline":' in text
    assert "return None, evidence_level" in text
    assert "return no_update, evidence_level" in text


def test_page6_visual_system_has_spacing_buttons_and_responsive_grids() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "PAGE6_CASE_EXPLORER_START" in css
    assert ".cases-page" in css
    assert "gap: 24px" in css
    assert ".cases-export-button" in css
    assert "border-radius: 10px" in css
    assert "padding: 8px 14px" in css
    assert "@media (max-width: 1120px)" in css



def test_page6_url_state_uses_duplicate_safe_location_output() -> None:
    text = CALLBACKS.read_text(encoding="utf-8")
    assert 'Output(APP_LOCATION_ID, "search", allow_duplicate=True)' in text
    assert "prevent_initial_call=True" in text

def test_page6_callbacks_are_registered() -> None:
    text = CALLBACK_REGISTRY.read_text(encoding="utf-8")
    assert "from .cases import register_case_callbacks" in text
    assert "register_case_callbacks(app)" in text
