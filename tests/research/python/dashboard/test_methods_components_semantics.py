"""Static semantic and visual-system checks for Page 7 components."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
COMPONENTS = ROOT / "research/python/dashboard/components/methods.py"
CSS = ROOT / "research/python/dashboard/assets/app.css"
FIGURE = ROOT / "research/python/dashboard/figures/methods.py"


def test_methods_components_include_required_scientific_boundaries() -> None:
    source = COMPONENTS.read_text()
    required = [
        "Template remains a separate deterministic reference, not a fourth LLM",
        "Complete 18-condition cases",
        "Cases with structured missingness",
        "Template baseline population",
        "Candidate is primary; V4 is sensitivity-only",
        "Conditional metrics remain missing",
        "Human-perceived quality was not evaluated",
        "utility is not probability or statistical significance",
        "Browser controls select existing tests and never create replacement p-values",
    ]
    for phrase in required:
        assert phrase in source


def test_methods_components_avoid_forbidden_promotions() -> None:
    source = COMPONENTS.read_text().lower()
    forbidden = [
        "fully scientifically validated",
        "four models",
        "template has zero latency",
        "human-equivalent",
        "browser-computed p-value",
    ]
    for phrase in forbidden:
        assert phrase not in source


def test_methods_css_has_responsive_audit_layout() -> None:
    css = CSS.read_text()
    assert "PAGE7_REPRODUCIBILITY_METHODS_START" in css
    assert ".methods-release-hero" in css
    assert ".methods-lineage" in css
    assert ".methods-denominator-grid" in css
    assert "PAGE7_FINAL_VISUAL_CONTENT_POLISH_START" in css
    assert "position: sticky" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    assert "rgba(15, 118, 110, 0.14)" in css
    assert "@media (max-width: 1120px)" in css
    assert "@media (max-width: 760px)" in css


def test_methods_visibility_figure_uses_no_colorbar_or_3d() -> None:
    source = FIGURE.read_text()
    assert "go.Bar" in source
    assert "colorbar" not in source
    assert "Scatter3d" not in source
    assert "Sankey" not in source
