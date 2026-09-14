"""Pure filter-contract tests for Page 7 callbacks."""

from __future__ import annotations

import ast
from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
CALLBACKS = ROOT / "research/python/dashboard/callbacks/methods.py"
DATA = ROOT / "data/reports/llm_validation/validation_v1/analysis/visualization_v2"


def _load_pure_functions():
    tree = ast.parse(CALLBACKS.read_text())
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"filter_certified_numbers", "filter_dictionary", "filter_limitations"}
    ]
    module = ast.Module(body=selected, type_ignores=[])
    namespace = {
        "pd": pd,
        "METHODS_REPORT_SECTION_ALL": "ALL",
        "METHODS_DICTIONARY_DATASET_ALL": "ALL",
        "METHODS_DICTIONARY_TIER_ALL": "ALL",
        "METHODS_DICTIONARY_ROLE_ALL": "ALL",
        "DICTIONARY_DASHBOARD_ENABLED": "DASHBOARD_ENABLED",
        "LIMITATION_ALL": "ALL",
    }
    exec(compile(module, str(CALLBACKS), "exec"), namespace)
    return namespace


def test_headline_filter_preserves_frozen_rows() -> None:
    functions = _load_pure_functions()
    frame = pd.read_csv(DATA / "certified_report_numbers.csv")
    all_rows = functions["filter_certified_numbers"](frame, "ALL")
    selected = functions["filter_certified_numbers"](frame, "denominator")
    assert len(all_rows) == 18
    assert set(selected["report_section"]) == {"denominator"}


def test_dictionary_defaults_exclude_internal_and_identifiers() -> None:
    functions = _load_pure_functions()
    frame = pd.read_csv(DATA / "visualization_dictionary.csv")
    selected = functions["filter_dictionary"](
        frame,
        search=None,
        dataset="ALL",
        tier="DASHBOARD_ENABLED",
        role="ALL",
        include_internal=[],
    )
    assert set(selected["visibility_tier"]) <= {"A_HEADLINE", "B_EXPLANATORY"}
    assert not selected["is_identifier"].astype(bool).any()


def test_dictionary_can_explicitly_include_disabled_fields() -> None:
    functions = _load_pure_functions()
    frame = pd.read_csv(DATA / "visualization_dictionary.csv")
    selected = functions["filter_dictionary"](
        frame,
        search="human_naturalness",
        dataset="ALL",
        tier="ALL",
        role="ALL",
        include_internal=["INCLUDE"],
    )
    assert not selected.empty
    assert selected["field_name"].astype(str).str.contains("human_naturalness").any()


def test_limitation_filter_is_local() -> None:
    functions = _load_pure_functions()
    frame = pd.DataFrame(
        [
            {"category": "A", "limitation": "one"},
            {"category": "B", "limitation": "two"},
        ]
    )
    selected = functions["filter_limitations"](frame, "B")
    assert selected["limitation"].tolist() == ["two"]


def test_dictionary_include_toggle_exposes_internal_tiers() -> None:
    functions = _load_pure_functions()
    frame = pd.read_csv(DATA / "visualization_dictionary.csv")
    selected = functions["filter_dictionary"](
        frame,
        search=None,
        dataset="ALL",
        tier="DASHBOARD_ENABLED",
        role="ALL",
        include_internal=["INCLUDE"],
    )
    assert {"C_INTERNAL_VALIDATION", "D_DISABLED_UNTIL_BETTER_DATA"} & set(
        selected["visibility_tier"]
    )
    assert selected["is_identifier"].astype(bool).any()
