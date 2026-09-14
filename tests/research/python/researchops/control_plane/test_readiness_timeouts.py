from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient

from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.control_plane.app import create_app
from research.python.researchops.control_plane.composition import ControlPlaneComposition
from research.python.researchops.control_plane.settings import ControlPlaneSettings


class HangingGateway:
    async def health(self):
        await asyncio.sleep(60)
        return {"passed": True}


class HangingArtifactStore:
    def list_artifact_ids(self):
        time.sleep(0.25)
        return []


def _settings(
    *,
    external_timeout: float = 0.05,
    critical_timeout: float = 1.0,
) -> ControlPlaneSettings:
    return ControlPlaneSettings(
        cursor_secret="x" * 64,
        auth_mode="local",
        dependency_timeout_seconds=external_timeout,
        critical_dependency_timeout_seconds=critical_timeout,
    )


def test_external_dependency_timeouts_are_bounded_and_degraded(db, tmp_path):
    composition = ControlPlaneComposition(
        session_factory=db,
        artifact_store=FilesystemArtifactStore(tmp_path / "store"),
        prefect_gateway=HangingGateway(),
        mlflow_gateway=HangingGateway(),
        artifact_profile="test-filesystem",
        prefect_control_gateway=None,
    )
    app = create_app(settings=_settings(), composition=composition)

    started = time.monotonic()
    with TestClient(app) as client:
        response = client.get("/readyz")
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < 1.5
    payload = response.json()
    assert payload["ready"] is True, payload
    assert payload["dependencies"]["ops_database"]["status"] == "READY"
    assert payload["dependencies"]["governance_locks"]["status"] == "READY"
    assert payload["dependencies"]["artifact_store"]["status"] == "READY"
    assert payload["dependencies"]["prefect"]["status"] == "DEGRADED"
    assert payload["dependencies"]["mlflow"]["status"] == "DEGRADED"
    assert "timeout" in payload["dependencies"]["prefect"]["detail"]


def test_critical_artifact_timeout_fails_readiness_without_hanging(db):
    composition = ControlPlaneComposition(
        session_factory=db,
        artifact_store=HangingArtifactStore(),
        prefect_gateway=None,
        mlflow_gateway=None,
        artifact_profile="hanging-test-store",
        prefect_control_gateway=None,
    )
    app = create_app(
        settings=_settings(critical_timeout=0.05),
        composition=composition,
    )

    started = time.monotonic()
    with TestClient(app) as client:
        response = client.get("/readyz")
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < 1.0
    payload = response.json()
    assert payload["ready"] is False
    assert payload["dependencies"]["artifact_store"]["status"] == "FAILED"
    assert "timeout" in payload["dependencies"]["artifact_store"]["detail"]


def test_timeout_settings_are_independent():
    settings = _settings(external_timeout=0.1, critical_timeout=2.0)
    assert settings.dependency_timeout_seconds == 0.1
    assert settings.critical_dependency_timeout_seconds == 2.0
