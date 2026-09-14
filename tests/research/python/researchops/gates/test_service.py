from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from research.python.researchops.gates import (
    GateAdapterIdentity,
    GateCheck,
    GateEvaluationDraft,
    GateEvaluationIdentityDrift,
    GateEvaluationService,
    GatePolicyIdentity,
    GateScope,
    GateSource,
)
from research.python.researchops.ops_core.db.base import Base
from research.python.researchops.ops_core.db.models import Approval, ArtifactRecord, AuditEvent, GateWaiver
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository


def _artifact(artifact_id: str, artifact_type: str, sha: str) -> ArtifactRecord:
    return ArtifactRecord(
        id=artifact_id,
        artifact_type=artifact_type,
        schema_version=f"{artifact_type}_v1",
        status="VERIFIED",
        manifest_uri=f"file:///tmp/{artifact_id}/manifest.json",
        manifest_sha256=sha,
        source_commit="b" * 40,
        limitations=[],
        artifact_metadata={},
        verified_at=datetime.now(timezone.utc),
    )


def _draft(
    artifact_id: str,
    sha: str,
    *,
    outcome: str = "PASSED",
    adapter_version: int = 1,
) -> GateEvaluationDraft:
    passed = outcome == "PASSED"
    return GateEvaluationDraft(
        gate_id="MODEL_READY",
        scope=GateScope(type="artifact", id=artifact_id),
        outcome=outcome,
        adapter=GateAdapterIdentity(
            id="model_ready_report_v1", version=adapter_version
        ),
        policy=GatePolicyIdentity(id="scientific_quality", version="1"),
        source=GateSource(
            artifact_id=artifact_id,
            manifest_sha256=sha,
            contract="model_ready_report",
        ),
        checks=(GateCheck(check_id="status", passed=passed),),
        source_contracts=("model_ready_report",),
        evaluated_at=datetime.now(timezone.utc),
    )


def test_evaluation_is_immutable_idempotent_and_projects_current_state(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'gates.db'}")
    Base.metadata.create_all(engine)
    artifact_id = "artifact_model_ready_report_test"
    sha = "a" * 64
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        repo.add_artifact(_artifact(artifact_id, "model_ready_report", sha))
        session.flush()
        service = GateEvaluationService(repo)

        first = service.record(_draft(artifact_id, sha), actor="test")
        second = service.record(_draft(artifact_id, sha), actor="test")
        assert first.created is True
        assert second.created is False
        assert second.evaluation.id == first.evaluation.id
        assert second.projection.current_evaluation_id == first.evaluation.id
        assert second.projection.effective_status == "PASSED"
        assert len(repo.list_gate_evaluations("MODEL_READY", "artifact", artifact_id)) == 1

        changed_adapter = service.record(
            _draft(artifact_id, sha, outcome="FAILED", adapter_version=2),
            actor="test",
        )
        assert changed_adapter.created is True
        assert changed_adapter.evaluation.id != first.evaluation.id
        assert changed_adapter.projection.current_evaluation_id == changed_adapter.evaluation.id
        assert changed_adapter.projection.effective_status == "FAILED"
        assert len(repo.list_gate_evaluations("MODEL_READY", "artifact", artifact_id)) == 2


def test_same_identity_with_different_semantics_fails_closed(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'drift.db'}")
    Base.metadata.create_all(engine)
    artifact_id = "artifact_model_ready_report_drift"
    sha = "c" * 64
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        repo.add_artifact(_artifact(artifact_id, "model_ready_report", sha))
        session.flush()
        service = GateEvaluationService(repo)
        service.record(_draft(artifact_id, sha), actor="test")
        with pytest.raises(GateEvaluationIdentityDrift):
            service.record(_draft(artifact_id, sha, outcome="FAILED"), actor="test")


def test_manifest_hash_binding_is_enforced(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'hash.db'}")
    Base.metadata.create_all(engine)
    artifact_id = "artifact_model_ready_report_hash"
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        repo.add_artifact(_artifact(artifact_id, "model_ready_report", "d" * 64))
        session.flush()
        with pytest.raises(Exception, match="manifest SHA-256 mismatch"):
            GateEvaluationService(repo).record(
                _draft(artifact_id, "e" * 64), actor="test"
            )



def test_new_current_evaluation_revokes_active_waiver(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'waiver-revocation.db'}")
    Base.metadata.create_all(engine)
    artifact_id = "artifact_model_ready_report_waiver"
    sha = "f" * 64
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        repo.add_artifact(_artifact(artifact_id, "model_ready_report", sha))
        approval = Approval(
            id="approval-waiver-test",
            target_type="gate_result",
            target_id="pending",
            policy="WAIVER",
            status="APPROVED",
            requested_by="owner",
            decided_by="reviewer",
            decided_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        repo.add_approval(approval)
        session.flush()
        service = GateEvaluationService(repo)
        first = service.record(
            _draft(artifact_id, sha, outcome="FAILED", adapter_version=1),
            actor="validator",
        )
        approval.target_id = first.projection.id
        waiver = GateWaiver(
            id="waiver-test",
            request_key="1" * 64,
            gate_result_id=first.projection.id,
            evaluation_id=first.evaluation.id,
            gate_id=first.projection.gate_id,
            scope_type=first.projection.scope_type,
            scope_id=first.projection.scope_id,
            policy_id="model_release_policy",
            policy_version=1,
            approval_id=approval.id,
            requested_by="owner",
            decided_by="reviewer",
            reason="Temporary known limitation",
            status="ACTIVE",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        repo.add_gate_waiver(waiver)
        first.projection.status = "WAIVED"
        first.projection.effective_status = "WAIVED"
        session.flush()

        second = service.record(
            _draft(artifact_id, sha, outcome="FAILED", adapter_version=2),
            actor="validator-v2",
            request_id="request-new-evaluation",
        )
        session.flush()

        assert second.projection.current_evaluation_id == second.evaluation.id
        assert second.projection.effective_status == "FAILED"
        assert waiver.status == "REVOKED"
        assert waiver.revoked_by == "validator-v2"
        assert waiver.revoked_at is not None
        assert "current evaluation changed" in (waiver.revocation_reason or "")
        events = list(session.scalars(select(AuditEvent)))
        assert any(
            event.action == "gate.waiver_invalidated" and event.target_id == waiver.id
            for event in events
        )
