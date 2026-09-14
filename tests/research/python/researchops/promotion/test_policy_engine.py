from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from research.python.researchops.ops_core.db.models import (
    Approval,
    ArtifactRecord,
    GateResult,
    ReleaseArtifact,
    ReleaseRecord,
)
from research.python.researchops.promotion import (
    PromotionDecisionError,
    PromotionIdentityDrift,
    PromotionPolicyService,
    ReleasePromotionService,
    WaiverService,
    load_promotion_policies,
    promotion_request_key,
)
from tests.research.python.researchops.ops_core.fakes import FakeRepository


def _approval(
    *,
    approval_id: str,
    target_type: str,
    target_id: str,
    policy: str,
    requested_by: str = "owner",
    decided_by: str = "reviewer",
) -> Approval:
    return Approval(
        id=approval_id,
        target_type=target_type,
        target_id=target_id,
        policy=policy,
        status="APPROVED",
        requested_by=requested_by,
        decided_by=decided_by,
        decided_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )


def _gate(
    gate_id: str,
    *,
    scope_type: str,
    scope_id: str,
    outcome: str,
    suffix: str = "1",
) -> GateResult:
    return GateResult(
        id=f"gate-{gate_id.lower()}-{suffix}",
        gate_id=gate_id,
        scope_type=scope_type,
        scope_id=scope_id,
        status=outcome,
        evaluation_outcome=outcome,
        effective_status=outcome,
        current_evaluation_id=f"gate_eval_{gate_id.lower()}_{suffix}",
        blocking=True,
        severity="ERROR",
        expected={},
        observed={},
        details={},
        source_contracts=[],
    )


def _release_repo() -> FakeRepository:
    repo = FakeRepository()
    artifact_id = "artifact_thesis_report_release_01J00000000000000000000000"
    repo.artifacts[artifact_id] = ArtifactRecord(
        id=artifact_id,
        artifact_type="thesis_report_release",
        schema_version="v1",
        status="VERIFIED",
        manifest_uri="file:///manifest.json",
        manifest_sha256="a" * 64,
        source_commit="b" * 40,
        limitations=[],
        artifact_metadata={},
    )
    repo.releases["release-thesis"] = ReleaseRecord(
        id="release-thesis",
        release_type="thesis_report_release",
        status="CANDIDATE",
        manifest_artifact_id=artifact_id,
        source_commit="b" * 40,
        limitations=[],
        release_metadata={},
    )
    repo.release_members.append(
        ReleaseArtifact(
            release_id="release-thesis", artifact_id=artifact_id, role="manifest"
        )
    )
    return repo


def test_catalog_has_unique_target_mappings_and_strict_model_policy():
    catalog = load_promotion_policies()
    model = catalog.for_target("model_version", "credit-risk-predictor")
    assert model.waiver_mode == "FORBIDDEN"
    assert set(model.non_waivable_gates) == set(model.required_gates)
    complete = catalog.for_target("release", "complete_release_bundle")
    assert "COMPLETE_RELEASE_BUNDLE_READY" in complete.required_gates
    assert complete.waived_to_state == "READY_WITH_LIMITATIONS"


def test_missing_required_gate_fails_closed_before_approval():
    repo = _release_repo()
    repo.approval_items.append(
        _approval(
            approval_id="approval-release",
            target_type="release",
            target_id="release-thesis",
            policy="RELEASE",
        )
    )
    policy = PromotionPolicyService(repo).policy_for(
        "release", "thesis_report_release"
    )
    with pytest.raises(PromotionDecisionError, match="missing=.*REPORT_WRITING_READY"):
        PromotionPolicyService(repo).authorize(
            policy=policy,
            target_type="release",
            target_id="release-thesis",
            target_kind="thesis_report_release",
            current_state="CANDIDATE",
            target_state="CERTIFIED",
            approval_id="approval-release",
        )


def test_waiver_is_evaluation_bound_and_only_allows_limited_release():
    repo = _release_repo()
    failed = _gate(
        "REPORT_WRITING_READY",
        scope_type="release",
        scope_id="release-thesis",
        outcome="FAILED",
    )
    repo.gates.append(failed)
    repo.approval_items.extend(
        [
            _approval(
                approval_id="approval-waiver",
                target_type="gate_result",
                target_id=failed.id,
                policy="WAIVER",
            ),
            _approval(
                approval_id="approval-release",
                target_type="release",
                target_id="release-thesis",
                policy="RELEASE",
            ),
        ]
    )
    waiver = WaiverService(repo).grant(
        gate_id="REPORT_WRITING_READY",
        scope_type="release",
        scope_id="release-thesis",
        target_kind="thesis_report_release",
        policy_id="thesis_report_release_promotion",
        approval_id="approval-waiver",
        requested_by="owner",
        decided_by="reviewer",
        reason="Known limitation documented in the thesis",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert waiver.evaluation_id == failed.current_evaluation_id
    assert failed.evaluation_outcome == "FAILED"
    assert failed.effective_status == "WAIVED"

    service = ReleasePromotionService(repo)
    with pytest.raises(PromotionDecisionError, match="READY_WITH_LIMITATIONS"):
        service.promote(
            "release-thesis",
            approval_id="approval-release",
            actor="release-manager",
            reason="certify",
            idempotency_key=promotion_request_key({"case": "wrong-target"}),
            expected_status="CANDIDATE",
            target_status="CERTIFIED",
        )

    decision = service.promote(
        "release-thesis",
        approval_id="approval-release",
        actor="release-manager",
        reason="publish with documented limitation",
        idempotency_key=promotion_request_key({"case": "limited-target"}),
        expected_status="CANDIDATE",
        target_status="READY_WITH_LIMITATIONS",
    )
    assert decision.execution_status == "COMPLETED"
    assert repo.releases["release-thesis"].status == "READY_WITH_LIMITATIONS"
    assert decision.waiver_snapshot[0]["evaluation_id"] == waiver.evaluation_id


def test_waiver_does_not_follow_a_new_evaluation():
    repo = _release_repo()
    failed = _gate(
        "REPORT_WRITING_READY",
        scope_type="release",
        scope_id="release-thesis",
        outcome="FAILED",
    )
    repo.gates.append(failed)
    repo.approval_items.extend(
        [
            _approval(
                approval_id="approval-waiver",
                target_type="gate_result",
                target_id=failed.id,
                policy="WAIVER",
            ),
            _approval(
                approval_id="approval-release",
                target_type="release",
                target_id="release-thesis",
                policy="RELEASE",
            ),
        ]
    )
    WaiverService(repo).grant(
        gate_id=failed.gate_id,
        scope_type=failed.scope_type,
        scope_id=failed.scope_id,
        target_kind="thesis_report_release",
        policy_id="thesis_report_release_promotion",
        approval_id="approval-waiver",
        requested_by="owner",
        decided_by="reviewer",
        reason="temporary limitation",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    failed.current_evaluation_id = "gate_eval_new_failure"
    failed.status = "WAIVED"
    failed.effective_status = "WAIVED"
    policy = PromotionPolicyService(repo).policy_for(
        "release", "thesis_report_release"
    )
    with pytest.raises(PromotionDecisionError, match="INVALID_WAIVER"):
        PromotionPolicyService(repo).authorize(
            policy=policy,
            target_type="release",
            target_id="release-thesis",
            target_kind="thesis_report_release",
            current_state="CANDIDATE",
            target_state="READY_WITH_LIMITATIONS",
            approval_id="approval-release",
        )


def test_promotion_decision_is_idempotent_and_detects_request_drift():
    repo = _release_repo()
    repo.gates.append(
        _gate(
            "REPORT_WRITING_READY",
            scope_type="release",
            scope_id="release-thesis",
            outcome="PASSED",
        )
    )
    repo.approval_items.append(
        _approval(
            approval_id="approval-release",
            target_type="release",
            target_id="release-thesis",
            policy="RELEASE",
        )
    )
    key = promotion_request_key({"release": "release-thesis", "revision": 1})
    service = ReleasePromotionService(repo)
    first = service.promote(
        "release-thesis",
        approval_id="approval-release",
        actor="release-manager",
        reason="certify",
        idempotency_key=key,
        expected_status="CANDIDATE",
        target_status="CERTIFIED",
    )
    second = service.promote(
        "release-thesis",
        approval_id="approval-release",
        actor="release-manager",
        reason="certify",
        idempotency_key=key,
        expected_status="CANDIDATE",
        target_status="CERTIFIED",
    )
    assert second.id == first.id
    assert len(repo.promotion_decisions) == 1
    with pytest.raises(PromotionIdentityDrift):
        service.promote(
            "release-thesis",
            approval_id="approval-release",
            actor="release-manager",
            reason="different semantics",
            idempotency_key=key,
            expected_status="CANDIDATE",
            target_status="CERTIFIED",
        )
