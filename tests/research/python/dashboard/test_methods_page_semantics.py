"""Page-level semantic and callback-ownership checks for Page 7."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PAGE = ROOT / "research/python/dashboard/pages/methods.py"
CALLBACKS = ROOT / "research/python/dashboard/callbacks/methods.py"
INIT = ROOT / "research/python/dashboard/callbacks/__init__.py"


def test_methods_page_has_four_local_tabs_and_export() -> None:
    source = PAGE.read_text()
    for phrase in [
        "Release & Validation",
        "Research Design",
        "Metrics & Denominators",
        "Limitations & Reproduction",
        "Export methods package",
        "methods-page-intro",
        'path="/methods"',
    ]:
        assert phrase in source or phrase in (ROOT / "research/python/dashboard/settings.py").read_text()


def test_methods_page_states_required_boundaries() -> None:
    combined = PAGE.read_text() + (ROOT / "research/python/dashboard/components/methods.py").read_text()
    required = [
        "Canonical case",
        "Template remains a separate deterministic reference, not a fourth LLM",
        "Candidate is primary; V4 is sensitivity-only",
        "Conditional metrics remain missing",
        "Human-perceived quality was not evaluated",
        "They do not create new p-values",
    ]
    for phrase in required:
        assert phrase in combined


def test_methods_callbacks_own_distinct_outputs() -> None:
    tree = ast.parse(CALLBACKS.read_text())
    output_ids = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Output":
            if node.args and isinstance(node.args[0], ast.Name):
                output_ids.append(node.args[0].id)
            elif node.args and isinstance(node.args[0], ast.Constant):
                output_ids.append(str(node.args[0].value))
    assert len(output_ids) == len(set(output_ids))
    assert "register_methods_callbacks(app)" in INIT.read_text()


def test_methods_page_does_not_promote_disabled_metrics() -> None:
    source = (PAGE.read_text() + (ROOT / "research/python/dashboard/components/methods.py").read_text()).lower()
    for phrase in [
        "fully scientifically validated",
        "four models",
        "template has zero latency",
        "human-equivalent",
        "browser-computed p-value",
    ]:
        assert phrase not in source


def test_methods_primary_ui_uses_curated_display_labels() -> None:
    components = (ROOT / "research/python/dashboard/components/methods.py").read_text()
    page = PAGE.read_text()
    labels = (ROOT / "research/python/dashboard/display_labels.py").read_text()
    assert "methods_identifier_label(locale, item)" in page
    assert "localized_reporting_role_label" in components
    assert "research_status_label" in components
    assert "CERTIFIED_HEADLINE" in labels
    assert '.replace("_", " ").title()' not in page


def test_methods_lineage_keeps_technical_gate_codes_in_details() -> None:
    source = (ROOT / "research/python/dashboard/components/methods.py").read_text()
    assert "Technical gate:" in source
    assert "Expected technical gate" in source
    assert "Observed technical gate" in source
    assert "gate_state_label" in source
