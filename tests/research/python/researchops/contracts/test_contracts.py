from __future__ import annotations

import json
from pathlib import Path

from research.python.researchops.contracts.io import (
    canonical_json_sha256,
    project_root,
)
from research.python.researchops.contracts.validation import validate_all_contracts


def test_phase1_governance_contracts_are_valid() -> None:
    report = validate_all_contracts()
    assert report.passed, report.to_dict()
    assert len(report.checked_contracts) == 6


def test_contract_hashing_is_order_independent() -> None:
    left = {"b": [2, 1], "a": {"value": True}}
    right = {"a": {"value": True}, "b": [2, 1]}
    assert canonical_json_sha256(left) == canonical_json_sha256(right)


def test_dashboard_composition_covers_nine_sections_once() -> None:
    root = project_root()
    source = json.loads(
        (root / "config/research/dashboard_contract_v2.json").read_text(
            encoding="utf-8"
        )
    )
    composition = json.loads(
        (
            root
            / "config/research/dashboard_route_composition_v1.json"
        ).read_text(encoding="utf-8")
    )
    expected = [page["page_id"] for page in source["pages"]]
    observed = [
        section
        for page in composition["physical_pages"]
        for section in page["conceptual_sections"]
    ]
    assert len(composition["physical_pages"]) == 7
    assert sorted(observed) == sorted(expected)
    assert len(observed) == len(set(observed)) == 9


def test_certified_artifact_cannot_transition_back_to_draft() -> None:
    payload = json.loads(
        (
            project_root() / "config/platform/lifecycle_states_v1.json"
        ).read_text(encoding="utf-8")
    )
    artifact = next(
        item for item in payload["resources"] if item["resource"] == "artifact"
    )
    transitions = {
        (item["from"], item["to"]) for item in artifact["transitions"]
    }
    assert ("CERTIFIED", "DRAFT") not in transitions
    assert ("CERTIFIED", "SUPERSEDED") in transitions


def test_new_platform_contracts_are_project_relative() -> None:
    root = project_root()
    for path in sorted((root / "config/platform").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert "/Users/" not in text
        assert "C:\\Users\\" not in text
