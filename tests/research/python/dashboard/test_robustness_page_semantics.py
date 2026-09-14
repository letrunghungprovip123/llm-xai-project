"""Source-level semantic and architecture checks for Page 5."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PAGE_SOURCE = ROOT / "research/python/dashboard/pages/robustness.py"
CALLBACK_SOURCE = ROOT / "research/python/dashboard/callbacks/robustness.py"
COMPONENT_SOURCE = ROOT / "research/python/dashboard/components/robustness.py"
CSS_SOURCE = ROOT / "research/python/dashboard/assets/app.css"


def test_page5_preserves_measurement_and_template_roles() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PAGE_SOURCE, CALLBACK_SOURCE, COMPONENT_SOURCE)
    )
    assert "Candidate" in text
    assert "Sensitivity artifact" in text
    assert "human ground truth" in text
    assert "not a fourth LLM" in text
    assert "excluded from decision ranking" in text
    assert "Measurement floor limited" in text
    assert "paired canonical case" in text


def test_page5_does_not_make_prohibited_claims() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (PAGE_SOURCE, CALLBACK_SOURCE, COMPONENT_SOURCE)
    )
    prohibited = (
        "v4 is more correct",
        "template is the fourth model",
        "human-equivalent",
        "zero-latency advantage",
        "template is a fourth llm",
    )
    assert not any(item in text for item in prohibited)


def test_page5_layout_uses_two_tabs_and_progressive_disclosure() -> None:
    text = PAGE_SOURCE.read_text(encoding="utf-8")
    assert 'label="Measurement robustness"' in text
    assert 'label="Template baseline"' in text
    assert "View all 40 measurement-sensitivity tests" in text
    assert "View all 105 LLM–Template paired tests" in text
    assert "View the 216 template generations" in text
    assert "Explore informational coverage" in text


def test_page5_visual_system_has_real_spacing_and_buttons() -> None:
    css = CSS_SOURCE.read_text(encoding="utf-8")
    assert "PAGE5_ROBUSTNESS_TEMPLATE_BASELINE_START" in css
    assert ".robustness-page" in css
    assert "gap: 24px" in css
    assert ".robustness-action-button" in css
    assert "border-radius: 10px" in css
    assert "padding: 8px 14px" in css


def test_page5_callback_helpers_match_declared_output_arity() -> None:
    tree = ast.parse(CALLBACK_SOURCE.read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }

    measurement_returns = [
        node for node in ast.walk(functions["measurement_updates"])
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple)
    ]
    template_focus_returns = [
        node for node in ast.walk(functions["template_focus_updates"])
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple)
    ]

    assert len(measurement_returns) == 1
    assert len(measurement_returns[0].value.elts) == 5
    assert len(template_focus_returns) == 1
    assert len(template_focus_returns[0].value.elts) == 2


def test_template_focus_controls_are_local_to_paired_comparison() -> None:
    text = PAGE_SOURCE.read_text(encoding="utf-8")
    focus_position = text.index('html.Label("Focused LLM")')
    scope_position = text.index('html.Label("Evidence scope")')
    uplift_position = text.index('graph_id=ROBUSTNESS_TEMPLATE_UPLIFT_ID')
    delta_position = text.index('graph_id=ROBUSTNESS_TEMPLATE_DELTA_ID')

    assert uplift_position < focus_position < delta_position
    assert uplift_position < scope_position < delta_position
    assert 'className="robustness-local-controls-row"' in text
    assert "Updates the case distribution and frozen test summary." in text
    assert "Updates the uplift matrix, case distribution, and frozen test summary." in text


def test_measurement_callback_ignores_stale_click_data_for_control_changes() -> None:
    text = CALLBACK_SOURCE.read_text(encoding="utf-8")
    assert "accept_click=ctx.triggered_id == ROBUSTNESS_MEASUREMENT_SHIFT_ID" in text
    assert "focus = _focus_from_click(click_data) if accept_click else None" in text


def test_template_callbacks_isolate_control_responsibilities() -> None:
    text = CALLBACK_SOURCE.read_text(encoding="utf-8")
    assert "def update_template_progression(metric_id, locale)" in text
    assert "def update_template_uplift(evidence_scope, locale)" in text
    assert "def update_template_focus(metric_id, model_id, evidence_scope, locale)" in text
    focus_block = text[text.index("def update_template_focus"):text.index("def export_robustness")]
    assert "ROBUSTNESS_TEMPLATE_PROGRESSION_ID" not in focus_block
    assert "ROBUSTNESS_TEMPLATE_UPLIFT_ID" not in focus_block
