from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from research.python.researchops.gates.contracts import (
    GateAdapterIdentity,
    GateCheck,
    GateEvaluationDraft,
    GatePolicyIdentity,
    GateScope,
    GateSource,
)
from research.python.researchops.gates.service import GateEvaluationService
from research.python.researchops.mlflow_tracking.registry_gateway import ModelVersionSnapshot
from research.python.researchops.ops_core.db.base import Base
from research.python.researchops.ops_core.db.models import (
    Approval,
    ArtifactRecord,
    ReleaseArtifact,
    ReleaseRecord,
)
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
from research.python.researchops.promotion.service import (
    ModelPromotionService,
    PromotionDecisionError,
    PromotionPolicyService,
    ReleasePromotionService,
    WaiverService,
)
from tests.research.python.researchops.mlflow_tracking.test_registry import FakeRegistryGateway


def _repo(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'promotion.db'}")
    Base.metadata.create_all(engine)
    return engine


def _approval(
    *,
    approval_id: str,
    target_type: str,
    target_id: str,
    policy: str,
    expires_delta: timedelta = timedelta(hours=1),
) -> Approval:
    now = datetime.now(timezone.utc)
    return Approval(
        id=approval_id,
        target_type=target_type,
        target_id=target_id,
        policy=policy,
        status="APPROVED",
        requested_by="owner",
        decided_by="reviewer",
        requested_at=now,
        decided_at=now,
        expires_at=now + expires_delta,
        reason="approved",
        details={},
    )


def _record_gate(
    repo: SqlAlchemyOpsRepository,
    *,
    gate_id: str,
    scope_type: str,
    scope_id: str,
    outcome: str,
    adapter_version: int = 1,
):
    passed = outcome == "PASSED"
    return GateEvaluationService(repo).record(
        GateEvaluationDraft(
            gate_id=gate_id,
            scope=GateScope(type=scope_type, id=scope_id),
            outcome=outcome,
            adapter=GateAdapterIdentity(id="scope_projection", version=adapter_version),
            policy=GatePolicyIdentity(id="scientific_quality", version="1"),
            source=GateSource(contract="gate_projection"),
            checks=(GateCheck(check_id="quality", passed=passed),),
            source_contracts=("gate_projection",),
            evaluated_at=datetime.now(timezone.utc),
        ),
        actor="test",
    )


def _seed_release(repo: SqlAlchemyOpsRepository, release_id: str, release_type: str):
    artifact_id = f"artifact_release_metadata_{release_id.replace(':', '_')}"
    repo.add_artifact(
        ArtifactRecord(
            id=artifact_id,
            artifact_type="release_metadata",
            schema_version="release_metadata_v1",
            status="VERIFIED",
            manifest_uri=f"file:///tmp/{artifact_id}/manifest.json",
            manifest_sha256="a" * 64,
            source_commit="b" * 40,
            limitations=[],
            artifact_metadata={},
        )
    )
    repo.add_release(
        ReleaseRecord(
            id=release_id,
            release_type=release_type,
            status="CANDIDATE",
            manifest_artifact_id=artifact_id,
            source_commit="b" * 40,
            limitations=[],
            release_metadata={},
        )
    )
    repo.add_release_artifact(
        ReleaseArtifact(release_id=release_id, artifact_id=artifact_id, role="manifest")
    )
    repo.flush()


def test_required_gate_set_blocks_missing_gate(tmp_path: Path) -> None:
    engine = _repo(tmp_path)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        target = "credit-risk-predictor:3"
        repo.add_approval(
            _approval(
                approval_id="approval-model",
                target_type="model_version",
                target_id=target,
                policy="MODEL_PROMOTION",
            )
        )
        _record_gate(
            repo,
            gate_id="MODEL_READY",
            scope_type="model_version",
            scope_id=target,
            outcome="PASSED",
        )
        _record_gate(
            repo,
            gate_id="MLFLOW_MODEL_REGISTERED",
            scope_type="model_version",
            scope_id=target,
            outcome="PASSED",
        )
        with pytest.raises(PromotionDecisionError, match="missing=.*XAI_QUALITY_READY"):
            PromotionPolicyService(repo).authorize(
                policy=PromotionPolicyService(repo).policy_for(
                    "model_version", "credit-risk-predictor"
                ),
                target_type="model_version",
                target_id=target,
                target_kind="credit-risk-predictor",
                current_state="CANDIDATE",
                target_state="CHAMPION",
                approval_id="approval-model",
            )


def test_waiver_binds_to_current_evaluation_and_new_evaluation_invalidates_it(
    tmp_path: Path,
) -> None:
    engine = _repo(tmp_path)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        release_id = "thesis-report-v1"
        _seed_release(repo, release_id, "thesis_report")
        first = _record_gate(
            repo,
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            outcome="FAILED",
        )
        repo.add_approval(
            _approval(
                approval_id="approval-waiver",
                target_type="gate_result",
                target_id=first.projection.id,
                policy="WAIVER",
                expires_delta=timedelta(hours=3),
            )
        )
        repo.add_approval(
            _approval(
                approval_id="approval-release",
                target_type="release",
                target_id=release_id,
                policy="RELEASE",
            )
        )
        waiver = WaiverService(repo).grant(
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            target_kind="thesis_report",
            policy_id="thesis_report_release_promotion",
            approval_id="approval-waiver",
            requested_by="owner",
            decided_by="reviewer",
            reason="Documented limitation",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        assert waiver.evaluation_id == first.evaluation.id
        policy_service = PromotionPolicyService(repo)
        authorization = policy_service.authorize(
            policy=policy_service.policy_for("release", "thesis_report"),
            target_type="release",
            target_id=release_id,
            target_kind="thesis_report",
            current_state="CANDIDATE",
            target_state="READY_WITH_LIMITATIONS",
            approval_id="approval-release",
        )
        assert authorization.waiver_snapshot[0]["waiver_id"] == waiver.id

        second = _record_gate(
            repo,
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            outcome="FAILED",
            adapter_version=2,
        )
        assert second.evaluation.id != first.evaluation.id
        with pytest.raises(PromotionDecisionError, match="FAILED"):
            policy_service.authorize(
                policy=policy_service.policy_for("release", "thesis_report"),
                target_type="release",
                target_id=release_id,
                target_kind="thesis_report",
                current_state="CANDIDATE",
                target_state="CERTIFIED",
                approval_id="approval-release",
            )


def test_non_waivable_gate_rejects_waiver(tmp_path: Path) -> None:
    engine = _repo(tmp_path)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        release_id = "complete-release-v1"
        _seed_release(repo, release_id, "complete_release_bundle")
        failed = _record_gate(
            repo,
            gate_id="MLFLOW_MODEL_REGISTERED",
            scope_type="release",
            scope_id=release_id,
            outcome="FAILED",
        )
        repo.add_approval(
            _approval(
                approval_id="approval-waiver",
                target_type="gate_result",
                target_id=failed.projection.id,
                policy="WAIVER",
            )
        )
        with pytest.raises(PromotionDecisionError, match="non-waivable"):
            WaiverService(repo).grant(
                gate_id="MLFLOW_MODEL_REGISTERED",
                scope_type="release",
                scope_id=release_id,
                target_kind="complete_release_bundle",
                policy_id="complete_research_release_promotion",
                approval_id="approval-waiver",
                requested_by="owner",
                decided_by="reviewer",
                reason="Must not work",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )


def test_release_promotion_records_snapshot_and_is_idempotent(tmp_path: Path) -> None:
    engine = _repo(tmp_path)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        release_id = "thesis-report-v1"
        _seed_release(repo, release_id, "thesis_report")
        _record_gate(
            repo,
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            outcome="PASSED",
        )
        repo.add_approval(
            _approval(
                approval_id="approval-release",
                target_type="release",
                target_id=release_id,
                policy="RELEASE",
            )
        )
        service = ReleasePromotionService(repo)
        first = service.promote(
            release_id,
            approval_id="approval-release",
            actor="operator",
            reason="certify",
            idempotency_key="1" * 64,
        )
        second = service.promote(
            release_id,
            approval_id="approval-release",
            actor="operator",
            reason="certify",
            idempotency_key="1" * 64,
            expected_status="CANDIDATE",
        )
        assert first.id == second.id
        assert first.execution_status == "COMPLETED"
        assert repo.get_release(release_id).status == "CERTIFIED"
        assert first.gate_snapshot[0]["evaluation_id"]


def test_model_promotion_uses_policy_snapshot_and_alias_saga(tmp_path: Path) -> None:
    engine = _repo(tmp_path)
    gateway = FakeRegistryGateway()
    gateway.versions.append(
        ModelVersionSnapshot(
            "credit-risk-predictor",
            "3",
            "run-3",
            "models:/m-3",
            "READY",
            {"researchops.source_manifest_verified": "PASSED"},
        )
    )
    gateway.set_alias("credit-risk-predictor", "candidate", "3")
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        target = "credit-risk-predictor:3"
        for gate_id in (
            "MODEL_READY",
            "XAI_QUALITY_READY",
            "MLFLOW_MODEL_REGISTERED",
        ):
            _record_gate(
                repo,
                gate_id=gate_id,
                scope_type="model_version",
                scope_id=target,
                outcome="PASSED",
            )
        repo.add_approval(
            _approval(
                approval_id="approval-model",
                target_type="model_version",
                target_id=target,
                policy="MODEL_PROMOTION",
            )
        )
        decision = ModelPromotionService(repo, gateway).promote(
            model_name="credit-risk-predictor",
            version="3",
            approval_id="approval-model",
            actor="operator",
            reason="promote",
            idempotency_key="2" * 64,
        )
        assert decision.execution_status == "COMPLETED"
        assert gateway.alias_version("credit-risk-predictor", "champion") == "3"
        assert decision.new_external_state["champion_version"] == "3"


def test_approval_scope_expiry_and_separation_of_duties_fail_closed(
    tmp_path: Path,
) -> None:
    engine = _repo(tmp_path)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        release_id = "thesis-report-approval-cases"
        _seed_release(repo, release_id, "thesis_report")
        _record_gate(
            repo,
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            outcome="PASSED",
        )
        policy_service = PromotionPolicyService(repo)
        policy = policy_service.policy_for("release", "thesis_report")

        wrong_scope = _approval(
            approval_id="approval-wrong-scope",
            target_type="release",
            target_id="another-release",
            policy="RELEASE",
        )
        expired = _approval(
            approval_id="approval-expired",
            target_type="release",
            target_id=release_id,
            policy="RELEASE",
            expires_delta=timedelta(seconds=-1),
        )
        same_actor = _approval(
            approval_id="approval-same-actor",
            target_type="release",
            target_id=release_id,
            policy="RELEASE",
        )
        same_actor.decided_by = same_actor.requested_by
        repo.add_approval(wrong_scope)
        repo.add_approval(expired)
        repo.add_approval(same_actor)
        repo.flush()

        common = dict(
            policy=policy,
            target_type="release",
            target_id=release_id,
            target_kind="thesis_report",
            current_state="CANDIDATE",
            target_state="CERTIFIED",
        )
        with pytest.raises(PromotionDecisionError, match="scope mismatch"):
            policy_service.authorize(**common, approval_id=wrong_scope.id)
        with pytest.raises(PromotionDecisionError, match="expired"):
            policy_service.authorize(**common, approval_id=expired.id)
        with pytest.raises(PromotionDecisionError, match="separation of duties"):
            policy_service.authorize(**common, approval_id=same_actor.id)


def test_expired_or_revoked_waiver_cannot_authorize_promotion(tmp_path: Path) -> None:
    engine = _repo(tmp_path)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        release_id = "thesis-report-waiver-lifecycle"
        _seed_release(repo, release_id, "thesis_report")
        failed = _record_gate(
            repo,
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            outcome="FAILED",
        )
        repo.add_approval(
            _approval(
                approval_id="approval-waiver-lifecycle",
                target_type="gate_result",
                target_id=failed.projection.id,
                policy="WAIVER",
                expires_delta=timedelta(hours=4),
            )
        )
        repo.add_approval(
            _approval(
                approval_id="approval-release-lifecycle",
                target_type="release",
                target_id=release_id,
                policy="RELEASE",
                expires_delta=timedelta(hours=4),
            )
        )
        waiver_service = WaiverService(repo)
        waiver = waiver_service.grant(
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            target_kind="thesis_report",
            policy_id="thesis_report_release_promotion",
            approval_id="approval-waiver-lifecycle",
            requested_by="owner",
            decided_by="reviewer",
            reason="Temporary documented limitation",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        policy_service = PromotionPolicyService(repo)
        policy = policy_service.policy_for("release", "thesis_report")
        common = dict(
            policy=policy,
            target_type="release",
            target_id=release_id,
            target_kind="thesis_report",
            current_state="CANDIDATE",
            target_state="READY_WITH_LIMITATIONS",
            approval_id="approval-release-lifecycle",
        )
        assert policy_service.authorize(**common).waiver_snapshot

        waiver_service.revoke(
            waiver.id,
            actor="reviewer",
            reason="Limitation can no longer be accepted",
        )
        with pytest.raises(PromotionDecisionError, match="FAILED"):
            policy_service.authorize(**common)

        # Create a new waiver, then authorize after its expiry using an explicit clock.
        second_approval = _approval(
            approval_id="approval-waiver-expiring",
            target_type="gate_result",
            target_id=failed.projection.id,
            policy="WAIVER",
            expires_delta=timedelta(hours=4),
        )
        repo.add_approval(second_approval)
        second = waiver_service.grant(
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            target_kind="thesis_report",
            policy_id="thesis_report_release_promotion",
            approval_id=second_approval.id,
            requested_by="owner",
            decided_by="reviewer",
            reason="Short lived limitation",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        with pytest.raises(PromotionDecisionError, match="INVALID_WAIVER"):
            policy_service.authorize(
                **common,
                now=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
        assert second.status == "EXPIRED"
        assert failed.projection.effective_status == "FAILED"


def test_active_waiver_requires_ready_with_limitations_target(tmp_path: Path) -> None:
    engine = _repo(tmp_path)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        release_id = "thesis-report-waived-target"
        _seed_release(repo, release_id, "thesis_report")
        failed = _record_gate(
            repo,
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            outcome="FAILED",
        )
        repo.add_approval(
            _approval(
                approval_id="approval-waiver-target",
                target_type="gate_result",
                target_id=failed.projection.id,
                policy="WAIVER",
                expires_delta=timedelta(hours=2),
            )
        )
        repo.add_approval(
            _approval(
                approval_id="approval-release-target",
                target_type="release",
                target_id=release_id,
                policy="RELEASE",
                expires_delta=timedelta(hours=2),
            )
        )
        WaiverService(repo).grant(
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            target_kind="thesis_report",
            policy_id="thesis_report_release_promotion",
            approval_id="approval-waiver-target",
            requested_by="owner",
            decided_by="reviewer",
            reason="Accepted limitation",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        policy_service = PromotionPolicyService(repo)
        with pytest.raises(PromotionDecisionError, match="require target state"):
            policy_service.authorize(
                policy=policy_service.policy_for("release", "thesis_report"),
                target_type="release",
                target_id=release_id,
                target_kind="thesis_report",
                current_state="CANDIDATE",
                target_state="CERTIFIED",
                approval_id="approval-release-target",
            )


def test_promotion_idempotency_key_drift_is_rejected(tmp_path: Path) -> None:
    engine = _repo(tmp_path)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        release_id = "thesis-report-idempotency"
        _seed_release(repo, release_id, "thesis_report")
        _record_gate(
            repo,
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id=release_id,
            outcome="PASSED",
        )
        repo.add_approval(
            _approval(
                approval_id="approval-release-idempotency",
                target_type="release",
                target_id=release_id,
                policy="RELEASE",
            )
        )
        service = ReleasePromotionService(repo)
        key = "d" * 64
        service.promote(
            release_id,
            approval_id="approval-release-idempotency",
            actor="operator",
            reason="certify",
            idempotency_key=key,
        )
        with pytest.raises(
            Exception,
            match="idempotency key was reused with different request semantics",
        ):
            service.promote(
                release_id,
                approval_id="approval-release-idempotency",
                actor="operator",
                reason="different reason",
                idempotency_key=key,
                expected_status="CANDIDATE",
            )


class _FailAfterChampionGateway(FakeRegistryGateway):
    def set_version_tags(self, name, version, tags):
        super().set_version_tags(name, version, tags)
        if tags.get("researchops.lifecycle_status") == "CHAMPION":
            raise RuntimeError("simulated post-alias failure")


def test_model_partial_failure_records_reconciliation_state(tmp_path: Path) -> None:
    engine = _repo(tmp_path)
    gateway = _FailAfterChampionGateway()
    gateway.versions.append(
        ModelVersionSnapshot(
            "credit-risk-predictor",
            "3",
            "run-3",
            "models:/m-3",
            "READY",
            {"researchops.source_manifest_verified": "PASSED"},
        )
    )
    gateway.set_alias("credit-risk-predictor", "candidate", "3")
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        target = "credit-risk-predictor:3"
        for gate_id in (
            "MODEL_READY",
            "XAI_QUALITY_READY",
            "MLFLOW_MODEL_REGISTERED",
        ):
            _record_gate(
                repo,
                gate_id=gate_id,
                scope_type="model_version",
                scope_id=target,
                outcome="PASSED",
            )
        repo.add_approval(
            _approval(
                approval_id="approval-model-partial",
                target_type="model_version",
                target_id=target,
                policy="MODEL_PROMOTION",
            )
        )
        with pytest.raises(RuntimeError, match="post-alias failure"):
            ModelPromotionService(repo, gateway).promote(
                model_name="credit-risk-predictor",
                version="3",
                approval_id="approval-model-partial",
                actor="operator",
                reason="promote",
                idempotency_key="e" * 64,
            )
        decision = repo.get_promotion_decision_by_key("e" * 64)
        assert decision is not None
        assert decision.execution_status == "FAILED_PARTIAL"
        assert decision.new_external_state["reconciliation_required"] is True
        assert gateway.alias_version("credit-risk-predictor", "champion") == "3"
