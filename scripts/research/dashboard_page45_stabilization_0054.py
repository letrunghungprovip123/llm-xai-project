#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.python.dashboard.v3.decision_model import build_decision_model
from research.python.dashboard.v3.repository import get_v3_repository
from research.python.dashboard.v3.robustness_model import build_robustness_model

ROOT = PROJECT_ROOT


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def data_gate() -> None:
    repo = get_v3_repository()
    decision = build_decision_model(repo, "CROSS_DATASET", "vi")
    robustness = build_robustness_model(repo, "CROSS_DATASET", "vi")

    if decision.primary_margin != 0.03:
        raise RuntimeError("Decision primary margin drift")
    if decision.robust_status != "NO_ROBUST_RECOMMENDATION":
        raise RuntimeError("Decision robust status drift")
    if decision.decision_counts.get("robust_eligible") != 0:
        raise RuntimeError("Decision robust eligible count drift")
    if len(decision.options) != 18 or len(decision.ni_rows) != 30 or len(decision.scenarios) != 5:
        raise RuntimeError("Decision topology drift")

    lanes = {round(float(row["margin"]), 2): row for row in robustness.margin_rows}
    if set(lanes) != {0.02, 0.03, 0.05}:
        raise RuntimeError("Robustness margin registry drift")
    if lanes[0.03]["analysis_status"] != "PRIMARY_CERTIFIED":
        raise RuntimeError("Robustness primary margin role drift")
    if lanes[0.02]["analysis_status"] != "SENSITIVITY_ONLY" or lanes[0.05]["analysis_status"] != "SENSITIVITY_ONLY":
        raise RuntimeError("Robustness sensitivity lane role drift")
    if robustness.validator_status != "NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3":
        raise RuntimeError("Validator capability state drift")
    if robustness.template_status != "NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3":
        raise RuntimeError("Template capability state drift")
    print("DASHBOARD_PAGE45_0054_DATA=PASS decision=certified robustness=primary_vs_sensitivity_preserved")


def source_gate() -> None:
    decision_page = _read("research/python/dashboard/v3/pages/decision.py")
    robustness_page = _read("research/python/dashboard/v3/pages/robustness.py")
    decision_model = _read("research/python/dashboard/v3/decision_model.py")
    robustness_model = _read("research/python/dashboard/v3/robustness_model.py")
    callbacks = _read("research/python/dashboard/v3/callbacks.py")
    figures = _read("research/python/dashboard/v3/figures.py")
    exports = _read("research/python/dashboard/v3/exports.py")
    css = _read("research/python/dashboard/assets/app.css")
    all_source = "\n".join((decision_page, robustness_page, decision_model, robustness_model, callbacks, figures))

    forbidden = (
        "import scipy",
        "from scipy",
        "statsmodels",
        "wilcoxon(",
        "multipletests(",
        "visualization_v2",
        "get_dashboard_repository",
        "idxmax(",
        "argmax(",
    )
    for token in forbidden:
        if token in all_source:
            raise RuntimeError(f"Scientific/legacy token leaked into Page 4/5: {token}")

    for page, name in ((decision_page, "Decision"), (robustness_page, "Robustness")):
        if "dmc.Tabs" in page:
            raise RuntimeError(f"{name} uses unapproved Tabs runtime")
        if 'columnSize="sizeToFit"' in page:
            raise RuntimeError(f"{name} hidden grid uses sizeToFit")
        if 'component="a"' in page and "dmc.Button" in page:
            raise RuntimeError(f"{name} contains legacy DMC Button anchor pattern")

    required = (
        "decision-detail-drawer-title-content",
        "decision-detail-drawer-body-content",
        'data-testid": "decision-drawer-content"',
        "robustness-detail-drawer-title-content",
        "robustness-detail-drawer-body-content",
        'data-testid": "robustness-drawer-content"',
    )
    joined_pages = decision_page + robustness_page
    for token in required:
        if token not in joined_pages:
            raise RuntimeError(f"Missing portal-safe/test-owned selector: {token}")

    if callbacks.count('Input(LOCATION, "pathname")') < 5 or callbacks.count('Input(LOCATION, "search")') < 5:
        raise RuntimeError("Page render URL state is not first-class")
    if "with_drill_dataset" not in decision_page or "with_drill_dataset" not in callbacks:
        raise RuntimeError("Decision dataset drill-through reconciliation is missing")
    if ".rank(" in robustness_page or ".rank(" in robustness_model:
        raise RuntimeError("Robustness presentation attempts to rerank filtered options")

    for table in (
        "decision_option_assessment",
        "noninferiority_results",
        "scenario_options",
        "population_effect_sensitivity",
        "population_contrast_sensitivity",
        "metric_sensitivity",
        "margin_sensitivity_summary",
    ):
        if table not in exports:
            raise RuntimeError(f"Page 4/5 export provenance missing certified table: {table}")

    if ".decision-page--golden" not in css or ".robustness-page--golden" not in css:
        raise RuntimeError("Page 4/5 CSS is not page-scoped")

    print("DASHBOARD_PAGE45_0054_SOURCE=PASS url_state=first-class drill=preserved portal=clean science=read-only")


def main() -> int:
    data_gate()
    source_gate()
    print("DASHBOARD_PAGE45_STABILIZATION_0054=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
