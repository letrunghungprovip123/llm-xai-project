from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from research.python.researchops.ops_core.db.base import Base
from research.python.researchops.ops_core.db.models import EnvironmentSnapshot
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
from research.python.researchops.orchestration.approvals.prefect_boundary import (
    ApprovalResumeInput,
    PrefectApprovalBoundary,
)
from research.python.researchops.orchestration.approvals.service import (
    ApprovalDecisionError,
    ApprovalService,
    approval_resume_key,
)
from research.python.researchops.orchestration.execution.errors import PolicyDeniedError
from research.python.researchops.orchestration.ops_bridge.service import OpsBridgeService
from research.python.researchops.orchestration.runtime import OrchestrationRuntime
from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.stage_registry.loader import load_stage_registry


def _runtime(tmp_path: Path) -> tuple[OrchestrationRuntime, str]:
    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    runtime = OrchestrationRuntime(
        root=Path.cwd(),
        execution_root=tmp_path / "executions",
        artifact_store=FilesystemArtifactStore(tmp_path / "store"),
        session_factory=factory,
    )
    with factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        env = EnvironmentSnapshot(
            id="env_01J00000000000000000000000",
            python_version="3.12",
            operating_system="test",
            architecture="arm64",
            dependency_lock_sha256="a" * 64,
            git_commit="b" * 40,
            git_dirty=False,
            details={},
        )
        bridge = OpsBridgeService(repo, orchestrator_version="3.7.8")
        bridge.persist_environment(env)
        handle = bridge.create_or_reuse_pipeline(
            flow_id="prefect_approval_acceptance_fixture",
            flow_key="c" * 64,
            flow_catalog_sha256="d" * 64,
            source_commit="b" * 40,
            environment_snapshot_id=env.id,
            parameters={},
            requested_by="test",
            trigger_type="TEST",
            prefect_flow_run_id="prefect-flow-approval",
            deployment_name="local",
            work_pool_name="researchops-local-process",
            work_queue_name="verification",
        )
        bridge.transition_pipeline(handle.pipeline_run, "RUNNING")
        session.commit()
        return runtime, handle.pipeline_run.id


def test_approval_resume_key_passes_prefect_flow_run_input_validation():
    pytest.importorskip("prefect")
    from prefect.client.schemas.objects import FlowRunInput
    from prefect.input.run_input import keyset_from_base_key

    request_key = "a" * 64
    resume_key = approval_resume_key(request_key)

    assert resume_key == f"approval-{request_key}"
    assert ":" not in resume_key
    for derived_key in keyset_from_base_key(f"suspended-{resume_key}").values():
        payload = FlowRunInput(
            flow_run_id=UUID("11111111-1111-1111-1111-111111111111"),
            key=derived_key,
            value="{}",
        )
        assert payload.key == derived_key


def test_approval_resume_key_rejects_non_prefect_characters():
    with pytest.raises(ApprovalDecisionError, match="canonical SHA-256"):
        approval_resume_key("not:hex")


def test_approval_request_is_idempotent_and_scope_checked(tmp_path: Path):
    runtime, pipeline_id = _runtime(tmp_path)
    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        service = ApprovalService(repo)
        first = service.request(
            pipeline_run_id=pipeline_id,
            node_id="protected",
            stage_id="ops.prefect_approval_acceptance",
            policy="EXPENSIVE",
            requested_by="test",
            prefect_flow_run_id="prefect-flow-approval",
            details={
                "resume_key": "spoofed:invalid",
                "prefect_flow_run_id": "spoofed-flow",
                "note": "preserved",
            },
        )
        second = service.request(
            pipeline_run_id=pipeline_id,
            node_id="protected",
            stage_id="ops.prefect_approval_acceptance",
            policy="EXPENSIVE",
            requested_by="test",
            prefect_flow_run_id="prefect-flow-approval",
        )
        assert second.id == first.id
        assert first.details["resume_key"].startswith("approval-")
        assert ":" not in first.details["resume_key"]
        assert first.details["prefect_flow_run_id"] == "prefect-flow-approval"
        assert first.details["note"] == "preserved"
        service.decide(
            first.id,
            decision="APPROVED",
            decided_by="reviewer",
            reason="accepted",
        )
        service.require_approved(
            first.id,
            pipeline_run_id=pipeline_id,
            node_id="protected",
            stage_id="ops.prefect_approval_acceptance",
            policy="EXPENSIVE",
        )
        with pytest.raises(ApprovalDecisionError, match="scope mismatch"):
            service.require_approved(
                first.id,
                pipeline_run_id=pipeline_id,
                node_id="other",
                stage_id="ops.prefect_approval_acceptance",
                policy="EXPENSIVE",
            )
        session.commit()


def test_prefect_boundary_only_continues_after_database_approval(tmp_path: Path):
    runtime, pipeline_id = _runtime(tmp_path)

    def approve_then_resume(**kwargs):
        assert kwargs["wait_for_input"] is ApprovalResumeInput
        assert kwargs["key"].startswith("approval-")
        assert ":" not in kwargs["key"]
        with runtime.session_factory() as session:
            repo = SqlAlchemyOpsRepository(session)
            approval = repo.list_approvals(status="REQUESTED")[0]
            ApprovalService(repo).decide(
                approval.id,
                decision="APPROVED",
                decided_by="reviewer",
                reason="safe to run",
            )
            session.commit()
            return ApprovalResumeInput(approval_id=approval.id)

    stage = load_stage_registry().by_id()["ops.prefect_approval_acceptance"]
    PrefectApprovalBoundary(
        runtime,
        suspend_callable=approve_then_resume,
        prefect_flow_run_id="prefect-flow-approval",
    ).require(
        stage=stage,
        pipeline_run_id=pipeline_id,
        node_id="protected",
        requested_by="test",
    )
    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        assert repo.get_pipeline_run(pipeline_id).status == "RUNNING"
        approval = repo.list_approvals(pipeline_run_id=pipeline_id)[0]
        assert approval.status == "APPROVED"


def test_prefect_boundary_rejects_resume_without_declared_input(tmp_path: Path):
    runtime, pipeline_id = _runtime(tmp_path)

    def resume_without_input(**kwargs):
        del kwargs
        return None

    stage = load_stage_registry().by_id()["ops.prefect_approval_acceptance"]
    with pytest.raises(PolicyDeniedError, match="without the required approval input"):
        PrefectApprovalBoundary(
            runtime,
            suspend_callable=resume_without_input,
            prefect_flow_run_id="prefect-flow-approval",
        ).require(
            stage=stage,
            pipeline_run_id=pipeline_id,
            node_id="protected",
            requested_by="test",
        )


def test_prefect_boundary_fails_closed_after_rejection(tmp_path: Path):
    runtime, pipeline_id = _runtime(tmp_path)

    def reject_then_resume(**kwargs):
        del kwargs
        with runtime.session_factory() as session:
            repo = SqlAlchemyOpsRepository(session)
            approval = repo.list_approvals(status="REQUESTED")[0]
            ApprovalService(repo).decide(
                approval.id,
                decision="REJECTED",
                decided_by="reviewer",
                reason="unsafe",
            )
            session.commit()
            return ApprovalResumeInput(approval_id=approval.id)

    stage = load_stage_registry().by_id()["ops.prefect_approval_acceptance"]
    with pytest.raises(PolicyDeniedError, match="not approved"):
        PrefectApprovalBoundary(
            runtime,
            suspend_callable=reject_then_resume,
            prefect_flow_run_id="prefect-flow-approval",
        ).require(
            stage=stage,
            pipeline_run_id=pipeline_id,
            node_id="protected",
            requested_by="test",
        )
    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        assert repo.get_pipeline_run(pipeline_id).status == "FAILED"


def test_expired_approval_cannot_be_reused(tmp_path: Path):
    runtime, pipeline_id = _runtime(tmp_path)
    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        service = ApprovalService(repo)
        approval = service.request(
            pipeline_run_id=pipeline_id,
            node_id="protected",
            stage_id="ops.prefect_approval_acceptance",
            policy="EXPENSIVE",
            requested_by="test",
            prefect_flow_run_id="prefect-flow-approval",
        )
        approval.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        service.expire_if_needed(approval, actor="test-clock")
        assert approval.status == "EXPIRED"
        with pytest.raises(ApprovalDecisionError, match="no longer pending"):
            service.decide(
                approval.id,
                decision="APPROVED",
                decided_by="reviewer",
                reason="late",
            )


def test_approved_authorization_must_still_be_within_validity_window(tmp_path: Path):
    runtime, pipeline_id = _runtime(tmp_path)
    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        service = ApprovalService(repo)
        approval = service.request(
            pipeline_run_id=pipeline_id,
            node_id="protected",
            stage_id="ops.prefect_approval_acceptance",
            policy="EXPENSIVE",
            requested_by="test",
            prefect_flow_run_id="prefect-flow-approval",
        )
        service.decide(
            approval.id,
            decision="APPROVED",
            decided_by="reviewer",
            reason="accepted",
        )
        approval.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        with pytest.raises(ApprovalDecisionError, match="authorization has expired"):
            service.require_approved(
                approval.id,
                pipeline_run_id=pipeline_id,
                node_id="protected",
                stage_id="ops.prefect_approval_acceptance",
                policy="EXPENSIVE",
            )
