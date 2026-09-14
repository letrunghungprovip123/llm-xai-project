"""Static export-contract tests for Page 7."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
EXPORT = ROOT / "research/python/dashboard/export/methods_package.py"


def test_methods_export_contains_required_package_files() -> None:
    source = EXPORT.read_text()
    required = [
        "release_metadata.csv",
        "certified_report_numbers.csv",
        "research_question_registry.csv",
        "metric_visibility_registry.csv",
        "visualization_dictionary.csv",
        "validation_gate_registry.csv",
        "artifact_inventory.csv",
        "limitations_registry.csv",
        "reproduction_steps.csv",
        "methods_manifest.json",
    ]
    for filename in required:
        assert filename in source


def test_methods_export_manifest_is_privacy_and_inference_safe() -> None:
    source = EXPORT.read_text()
    required = [
        '"presentation_is_read_only": True',
        '"browser_recomputes_inference": False',
        '"claim_rows_are_independent_units": False',
        '"template_is_fourth_llm": False',
        '"human_naturalness_evaluated": False',
        '"precise_template_latency_available": False',
        '"raw_applicant_data_included": False',
    ]
    for phrase in required:
        assert phrase in source


def test_methods_export_module_compiles() -> None:
    ast.parse(EXPORT.read_text())
