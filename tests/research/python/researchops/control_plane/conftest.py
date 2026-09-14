from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.control_plane.app import create_app
from research.python.researchops.control_plane.composition import ControlPlaneComposition
from research.python.researchops.control_plane.settings import ControlPlaneSettings
from research.python.researchops.ops_core.db.base import Base
from research.python.researchops.ops_core.db.engine import create_session_factory
from research.python.researchops.ops_core.db.models import (
    Approval,
    ArtifactFileRecord,
    ArtifactRecord,
    EnvironmentSnapshot,
    GateEvaluation,
    GateResult,
    GateWaiver,
    LineageEdge,
    OrchestrationBinding,
    PipelineRun,
    PromotionDecision,
    ReleaseArtifact,
    ReleaseRecord,
    RunEvent,
    StageRun,
    StageRunOutput,
)


class FakePrefect:
    def __init__(self):
        self.submissions = []
        self.cancellations = []

    async def health(self):
        return {"passed": True, "client_version": "3.7.8", "server_version": "3.7.8"}

    async def submit_deployment(self, deployment_name, *, parameters, idempotency_key):
        from research.python.researchops.control_plane.gateways.prefect import PrefectSubmission
        value = PrefectSubmission(
            flow_run_id=f"prefect-submission-{len(self.submissions)+1}",
            deployment_name=deployment_name,
            state_name="SCHEDULED",
        )
        self.submissions.append((deployment_name, parameters, idempotency_key))
        return value

    async def cancel_flow_run(self, flow_run_id, *, reason):
        self.cancellations.append((flow_run_id, reason))
        return {"flow_run_id": flow_run_id, "accepted": True, "status": "ACCEPT"}

    async def flow_run(self, flow_run_id):
        return {"flow_run_id": flow_run_id, "state_name": "RUNNING", "state_type": "RUNNING"}


class FakeMLflow:
    def __init__(self):
        self.versions = {
            "credit-risk": [{
                "model_name": "credit-risk", "version": "1", "aliases": ["candidate"],
                "status": "READY", "source": "models:/m-123", "run_id": "run-mlflow", "tags": {},
            }],
            "credit-risk-predictor": [{
                "model_name": "credit-risk-predictor", "version": "1", "aliases": ["candidate"],
                "status": "READY", "source": "models:/m-456", "run_id": "run-mlflow-predictor",
                "tags": {"researchops.source_manifest_verified": "PASSED"},
            }],
        }

    async def health(self):
        return {"passed": True, "version": "3.14.0"}

    def list_models(self, *, max_results=100):
        return [
            {"name": name, "aliases": {"candidate": "1"}, "tags": {}}
            for name in sorted(self.versions)[:max_results]
        ]

    def list_versions(self, model_name: str):
        return [dict(item) for item in self.versions.get(model_name, [])]


@pytest.fixture()
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'control-plane.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version(version_num) VALUES ('0008_control_plane_operations')"))
    factory = create_session_factory(engine)
    now = datetime.now(timezone.utc)
    with factory() as session, session.begin():
        session.add(EnvironmentSnapshot(
            id="env_01J00000000000000000000000", python_version="3.12", node_version="v22",
            operating_system="test", architecture="arm64", dependency_lock_sha256="d"*64,
            git_commit="a"*40, git_dirty=False, details={},
        ))
        for index in range(3):
            run_id = f"run_01J0000000000000000000000{index}"
            created = now - timedelta(minutes=index)
            session.add(PipelineRun(
                id=run_id, flow_id="verify_source_environment", status="SUCCEEDED",
                trigger_type="manual", requested_by="tester", registry_sha256="b"*64,
                source_commit="a"*40, environment_snapshot_id="env_01J00000000000000000000000",
                idempotency_key=f"key-{index}", parameters={"index": index},
                started_at=created, ended_at=created, created_at=created, updated_at=created,
            ))
            stage_id = f"stage_run_01J00000000000000000000{index}"
            session.add(StageRun(
                id=stage_id, pipeline_run_id=run_id, stage_id="ops.verify_source_environment",
                stage_version=2, attempt=1, status="SUCCEEDED", command_snapshot={},
                approval_policy="NONE", started_at=created, ended_at=created, exit_code=0,
                created_at=created, updated_at=created,
            ))
            session.add(RunEvent(
                pipeline_run_id=run_id, stage_run_id=stage_id,
                event_type="stage.succeeded", payload={"index": index}, occurred_at=created,
            ))
        session.add(OrchestrationBinding(
            id="binding_01J00000000000000000000000", orchestrator="prefect",
            orchestrator_version="3.7.8", pipeline_run_id="run_01J00000000000000000000000",
            stage_run_id=None, prefect_flow_run_id="prefect-flow-1", prefect_task_run_id=None,
            deployment_name="verify-source-environment/local", work_pool_name="pool",
            work_queue_name="verification", orchestration_key="c"*64, attempt_number=1,
            binding_metadata={},
        ))
        session.add(ArtifactRecord(
            id="artifact_test_01J00000000000000000000000", artifact_type="test_artifact",
            schema_version="test_v1", status="VERIFIED", manifest_uri="s3://secret/path/manifest.json",
            manifest_sha256="1"*64, producer_stage_run_id="stage_run_01J000000000000000000000",
            source_commit="a"*40, environment_snapshot_id="env_01J00000000000000000000000",
            limitations=[], artifact_metadata={"safe": True}, created_at=now, verified_at=now,
        ))
        session.add(ArtifactRecord(
            id="artifact_parent_01J0000000000000000000000", artifact_type="parent",
            schema_version="v1", status="VERIFIED", manifest_uri="file:///secret/manifest.json",
            manifest_sha256="2"*64, source_commit="a"*40,
            environment_snapshot_id="env_01J00000000000000000000000",
            limitations=[], artifact_metadata={}, created_at=now-timedelta(days=1), verified_at=now,
        ))
        session.add(ArtifactFileRecord(
            artifact_id="artifact_test_01J00000000000000000000000",
            relative_path="payload/report.json", object_uri="s3://bucket/user:password@host/report.json",
            sha256="3"*64, size_bytes=100, row_count=1, column_count=2, media_type="application/json",
        ))
        session.add(LineageEdge(
            parent_artifact_id="artifact_parent_01J0000000000000000000000",
            child_artifact_id="artifact_test_01J00000000000000000000000",
            relationship_type="derived_from", created_at=now,
        ))
        evaluation_id="gate_eval_01J00000000000000000000000"
        session.add(GateEvaluation(
            id=evaluation_id, evaluation_key="4"*64, payload_sha256="5"*64,
            gate_id="XAI_QUALITY_READY", scope_type="artifact",
            scope_id="artifact_test_01J00000000000000000000000", outcome="FAILED",
            blocking=True, severity="ERROR", adapter_id="xai_quality_report_v1",
            adapter_version=1, policy_id="quality", policy_version="1",
            source_artifact_id="artifact_test_01J00000000000000000000000",
            source_manifest_sha256="1"*64, source_contract="test_v1",
            expected={"passed": True}, observed={"passed": False}, checks=[], limitations=[],
            source_contracts=[], source_evaluation_ids=[], evaluated_at=now,
        ))
        session.add(GateResult(
            id="gate_result_01J0000000000000000000000", gate_id="XAI_QUALITY_READY",
            scope_type="artifact", scope_id="artifact_test_01J00000000000000000000000",
            status="WAIVED", evaluation_outcome="FAILED", effective_status="WAIVED",
            current_evaluation_id=evaluation_id, blocking=True, severity="ERROR",
            expected={}, observed={}, details={}, source_contracts=[], created_at=now, updated_at=now,
        ))
        session.add(Approval(
            id="approval_01J00000000000000000000000", target_type="gate_result",
            target_id="gate_result_01J0000000000000000000000", policy="WAIVER",
            status="APPROVED", requested_by="requester", requested_at=now,
            decided_by="approver", decided_at=now, reason="accepted", expires_at=now+timedelta(days=1), details={},
        ))
        session.add(GateWaiver(
            id="waiver_01J000000000000000000000000", request_key="6"*64,
            gate_result_id="gate_result_01J0000000000000000000000", evaluation_id=evaluation_id,
            gate_id="XAI_QUALITY_READY", scope_type="artifact",
            scope_id="artifact_test_01J00000000000000000000000",
            policy_id="complete_release_certification", policy_version=1,
            approval_id="approval_01J00000000000000000000000", requested_by="requester",
            decided_by="approver", reason="known limitation", status="ACTIVE",
            created_at=now, expires_at=now+timedelta(days=1),
        ))
        session.add(ReleaseRecord(
            id="release_test_v1", release_type="complete_research_release", status="READY_WITH_LIMITATIONS",
            manifest_artifact_id="artifact_test_01J00000000000000000000000", source_commit="a"*40,
            limitations=["waived gate"], release_metadata={"language": "vi"}, created_at=now,
        ))
        session.add(ReleaseArtifact(
            release_id="release_test_v1", artifact_id="artifact_test_01J00000000000000000000000",
            role="manifest", created_at=now,
        ))
    return factory


@pytest.fixture()
def app(db, tmp_path: Path):
    prefect = FakePrefect()
    composition = ControlPlaneComposition(
        session_factory=db,
        artifact_store=FilesystemArtifactStore(tmp_path / "store"),
        prefect_gateway=prefect,
        mlflow_gateway=FakeMLflow(),
        artifact_profile="test-filesystem",
        prefect_control_gateway=prefect,
    )
    settings = ControlPlaneSettings(cursor_secret="x"*64, auth_mode="local")
    return create_app(settings=settings, composition=composition)


@pytest.fixture()
def client(app):
    with TestClient(app) as value:
        yield value
