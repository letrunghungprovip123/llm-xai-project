from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
PAGES = ROOT / "research" / "python" / "dashboard" / "v3" / "pages"


def _is_dmc_button(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "dmc"
        and func.attr == "Button"
    )


def test_dmc_button_is_not_used_as_anchor() -> None:
    violations: list[str] = []
    for path in sorted(PAGES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_dmc_button(node):
                continue
            keywords = {kw.arg for kw in node.keywords if kw.arg}
            if "href" in keywords or "component" in keywords:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert violations == [], (
        "dash-mantine-components 2.8.0 Button does not accept href/component anchor props: "
        + ", ".join(violations)
    )


def test_page2_page3_internal_navigation_uses_dash_links() -> None:
    effectiveness = (PAGES / "effectiveness.py").read_text(encoding="utf-8")
    mechanisms = (PAGES / "mechanisms.py").read_text(encoding="utf-8")
    assert 'dcc.Link("Mở Mechanisms"' in effectiveness
    assert 'dcc.Link("Mở Case Explorer"' in effectiveness
    assert 'dcc.Link("Mở Effectiveness"' in mechanisms
    assert 'dcc.Link("Mở Case Explorer"' in mechanisms
