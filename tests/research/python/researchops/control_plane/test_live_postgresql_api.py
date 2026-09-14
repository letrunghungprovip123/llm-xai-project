from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.control_plane.app import create_app
from research.python.researchops.control_plane.composition import ControlPlaneComposition
from research.python.researchops.control_plane.settings import ControlPlaneSettings
from research.python.researchops.artifacts.ids import new_ulid
from research.python.researchops.ops_core.db import create_engine_from_settings, create_session_factory
from research.python.researchops.ops_core.db.models import Approval, AuditEvent
from research.python.researchops.ops_core.settings import DatabaseSettings


@pytest.mark.skipif(
    not os.getenv("RESEARCHOPS_TEST_DATABASE_URL"),
    reason="Set RESEARCHOPS_TEST_DATABASE_URL for live FastAPI PostgreSQL acceptance",
)
def test_live_postgresql_read_control_plane(tmp_path: Path):
    url = os.environ["RESEARCHOPS_TEST_DATABASE_URL"]
    engine = create_engine_from_settings(DatabaseSettings(url=url))
    composition = ControlPlaneComposition(
        session_factory=create_session_factory(engine),
        artifact_store=FilesystemArtifactStore(tmp_path / "artifacts"),
        prefect_gateway=None,
        mlflow_gateway=None,
        artifact_profile="test-filesystem",
    )
    app = create_app(
        settings=ControlPlaneSettings(cursor_secret="x" * 64, auth_mode="local"),
        composition=composition,
    )
    with TestClient(app) as client:
        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["ready"] is True
        assert ready.json()["dependencies"]["ops_database"]["status"] == "READY"
        assert client.get("/version").json()["database_revision"] == "0008_control_plane_operations"
        assert client.get("/api/v1/runs").status_code == 200
        assert client.get("/api/v1/artifacts").status_code == 200
        assert client.get("/api/v1/gates").status_code == 200


@pytest.mark.skipif(
    not os.getenv("RESEARCHOPS_TEST_DATABASE_URL"),
    reason="Set RESEARCHOPS_TEST_DATABASE_URL for live FastAPI PostgreSQL acceptance",
)
def test_live_postgresql_mutation_idempotency_and_audit(tmp_path: Path):
    url = os.environ["RESEARCHOPS_TEST_DATABASE_URL"]
    engine = create_engine_from_settings(DatabaseSettings(url=url))
    session_factory = create_session_factory(engine)
    composition = ControlPlaneComposition(
        session_factory=session_factory,
        artifact_store=FilesystemArtifactStore(tmp_path / "artifacts-mutation"),
        prefect_gateway=None,
        mlflow_gateway=None,
        artifact_profile="test-filesystem",
    )
    app = create_app(
        settings=ControlPlaneSettings(cursor_secret="x" * 64, auth_mode="local"),
        composition=composition,
    )
    suffix = new_ulid()
    approval_id = f"approval_{suffix}"
    idempotency_key = f"live-approval-{suffix}"
    request_id = f"req-live-{suffix}"
    now = datetime.now(timezone.utc)
    with session_factory() as session, session.begin():
        session.add(Approval(
            id=approval_id,
            target_type="release",
            target_id=f"release_live_{suffix}",
            policy="RELEASE",
            status="REQUESTED",
            requested_by="live-requester",
            requested_at=now,
            expires_at=now + timedelta(hours=1),
            details={"acceptance": True},
        ))

    try:
        with TestClient(app) as client:
            body = {"expected_status": "REQUESTED", "reason": "live database acceptance"}
            headers = {"Idempotency-Key": idempotency_key, "X-Request-ID": request_id}
            first = client.post(f"/api/v1/approvals/{approval_id}/approve", json=body, headers=headers)
            assert first.status_code == 200, first.text
            assert first.json()["status"] == "APPROVED"
            second = client.post(f"/api/v1/approvals/{approval_id}/approve", json=body, headers=headers)
            assert second.status_code == 200, second.text
            assert second.json()["replayed"] is True

        inspector = inspect(engine)
        assert {"error_category", "retryable"}.issubset(
            {column["name"] for column in inspector.get_columns("stage_runs")}
        )
        assert {"api_idempotency_requests", "control_operations"}.issubset(
            set(inspector.get_table_names())
        )
        with session_factory() as session:
            approval = session.get(Approval, approval_id)
            assert approval is not None and approval.status == "APPROVED"
            audits = list(
                session.query(AuditEvent).filter(
                    AuditEvent.target_id == approval_id,
                    AuditEvent.request_id == request_id,
                )
            )
            assert any(event.action == "api.approval_decided" for event in audits)
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM audit_events WHERE target_id = :target_id"),
                {"target_id": approval_id},
            )
            connection.execute(
                text("DELETE FROM api_idempotency_requests WHERE idempotency_key = :key"),
                {"key": idempotency_key},
            )
            connection.execute(
                text("DELETE FROM approvals WHERE id = :approval_id"),
                {"approval_id": approval_id},
            )
