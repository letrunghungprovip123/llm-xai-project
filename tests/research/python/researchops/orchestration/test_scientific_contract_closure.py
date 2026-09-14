from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.python.researchops.stage_registry.loader import load_gate_catalog, load_stage_registry


def test_all_stage_contracts_declare_execution_and_semantic_evidence() -> None:
    registry = load_stage_registry()
    catalog = {
        item["gate_id"] for item in load_gate_catalog()["gates"]
    }
    assert len(registry.stages) == 42
    for stage in registry.stages:
        verification = stage.verification
        assert verification.execution_gate == "STAGE_EXECUTION_SUCCEEDED"
        assert verification.execution_gate in catalog
        assert verification.success_gate in catalog
        assert verification.adapter_id
        assert verification.adapter_version >= 1
        assert verification.report_glob
        for output in stage.outputs:
            assert output.discovery_patterns
            assert len(output.discovery_patterns) == len(set(output.discovery_patterns))


def test_machine_readable_scientific_contract_matrix_is_complete() -> None:
    payload = json.loads(
        Path("config/platform/scientific_stage_contracts_v1.json").read_text()
    )
    registry = load_stage_registry()
    assert payload["schema_version"] == "scientific_stage_contracts_v1"
    assert payload["stage_count"] == len(registry.stages) == 42
    assert {item["stage_id"] for item in payload["stages"]} == {
        stage.id for stage in registry.stages
    }


def test_active_source_tree_contains_no_one_off_backup_files() -> None:
    forbidden = []
    for root in (Path("research"), Path("tests")):
        for path in root.rglob("*"):
            if path.is_file() and (".bak" in path.name or ".before-" in path.name):
                forbidden.append(path.as_posix())
    assert forbidden == []


@pytest.mark.parametrize(
    ("module_name", "manifest_path", "payload", "expected"),
    [
        (
            "data_audit",
            "data/manifests/batch_1_summary.json",
            {
                "step_statuses": [
                    {"status": "raw_verified"},
                    {"status": "schema_audit_passed"},
                    {"status": "relationship_audit_passed"},
                ]
            },
            0,
        ),
        (
            "feature_engineering",
            "data/manifests/batch_b_feature_engineering_summary.json",
            {"pipeline_group_status": "blocked"},
            1,
        ),
    ],
)
def test_early_scientific_cli_returns_manifest_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    manifest_path: str,
    payload: dict,
    expected: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / manifest_path
    target.parent.mkdir(parents=True, exist_ok=True)

    if module_name == "data_audit":
        from research.python.data_audit import main as cli
        from research.python.data_audit import pipeline

        monkeypatch.setattr(
            pipeline,
            "run_data_audit",
            lambda: target.write_text(json.dumps(payload), encoding="utf-8"),
        )
    else:
        from research.python.feature_engineering import main as cli
        from research.python.feature_engineering import pipeline

        monkeypatch.setattr(
            pipeline,
            "run_feature_engineering",
            lambda: target.write_text(json.dumps(payload), encoding="utf-8"),
        )

    assert cli.main([]) == expected
