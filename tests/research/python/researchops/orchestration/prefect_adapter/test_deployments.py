from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from research.python.researchops.orchestration.prefect_adapter.deployments import (
    deployment_lock_matches,
    load_deployment_catalog,
    render_prefect_yaml,
    validate_deployment_catalog,
    validate_deployment_imports,
)


def test_deployment_catalog_maps_every_flow_once_and_is_manual_only():
    report = validate_deployment_catalog()
    assert report["passed"], report["errors"]
    assert report["flow_count"] == 15
    assert report["deployment_count"] == 15
    assert report["missing_flow_ids"] == []
    assert report["unknown_flow_ids"] == []
    assert report["manual_only"] is True


def test_prefect_yaml_is_deterministic_and_schedule_free():
    payload = render_prefect_yaml()
    assert payload["prefect-version"] == "3.7.8"
    assert payload["build"] is None
    assert payload["push"] is None
    assert payload["pull"] == [
        {
            "prefect.deployments.steps.set_working_directory": {
                "directory": "/workspace"
            }
        }
    ]
    deployments = payload["deployments"]
    assert len(deployments) == 15
    assert all(item["schedules"] == [] for item in deployments)
    assert all("manual-only" in item["tags"] for item in deployments)
    assert len({item["entrypoint"] for item in deployments}) == 15
    assert all(":" not in item["entrypoint"] for item in deployments)
    assert all(
        item["entrypoint"].startswith(
            "research.python.researchops.orchestration.prefect_adapter.flows."
        )
        for item in deployments
    )

    checked_in = yaml.safe_load(Path("prefect.yaml").read_text(encoding="utf-8"))
    assert checked_in == payload
    assert deployment_lock_matches()


def test_deployment_catalog_schema_is_strict():
    catalog = load_deployment_catalog()
    assert catalog.work_pool_name == "researchops-local-process"
    assert catalog.source_directory == "/workspace"
    assert {item.work_queue_name for item in catalog.deployments} == {
        "verification",
        "cpu-heavy",
        "provider-llm",
        "release",
    }
    lock = json.loads(
        Path("config/platform/generated/prefect_deployments.lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock["deployment_count"] == 15


def test_all_module_entrypoints_pass_prefect_import_preflight():
    loaded: list[str] = []

    def fake_loader(entrypoint: str):
        loaded.append(entrypoint)
        function_name = entrypoint.rsplit(".", 1)[1]
        return SimpleNamespace(name=function_name.replace("_", "-"))

    report = validate_deployment_imports(loader=fake_loader)
    assert report["passed"], report["errors"]
    assert report["loaded_count"] == 15
    assert len(loaded) == 15
    assert all(":" not in item for item in loaded)


def test_import_preflight_reports_user_import_failure():
    def failing_loader(entrypoint: str):
        if entrypoint.endswith(".build_xai_release"):
            raise ImportError("fixture import failure")
        function_name = entrypoint.rsplit(".", 1)[1]
        return SimpleNamespace(name=function_name.replace("_", "-"))

    report = validate_deployment_imports(loader=failing_loader)
    assert not report["passed"]
    assert report["loaded_count"] == 14
    assert any("build_xai_release" in item for item in report["errors"])
    assert any("fixture import failure" in item for item in report["errors"])
