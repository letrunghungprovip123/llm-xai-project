from __future__ import annotations

from datetime import datetime, timezone

from research.python.researchops.artifacts.exceptions import ArtifactValidationError

from ..db.enums import ReleaseStatus
from ..db.models import ReleaseArtifact, ReleaseRecord
from ..repositories.protocols import OpsRepository
from .state_transitions import StateTransitionService


class ReleaseService:
    def __init__(self, repository: OpsRepository) -> None:
        self.repository = repository
        self.transitions = StateTransitionService(repository)

    def create(
        self,
        record: ReleaseRecord,
        *,
        actor: str,
    ) -> None:
        if self.repository.get_release(record.id) is not None:
            raise ArtifactValidationError("Release already exists")
        if self.repository.get_artifact(record.manifest_artifact_id) is None:
            raise ArtifactValidationError("Release manifest artifact is not registered")
        if record.parent_release_id and self.repository.get_release(record.parent_release_id) is None:
            raise ArtifactValidationError("Parent release does not exist")
        self.repository.add_release(record)
        self.repository.add_release_artifact(ReleaseArtifact(
            release_id=record.id,
            artifact_id=record.manifest_artifact_id,
            role="manifest",
        ))
        from .audit import record_audit
        record_audit(
            self.repository, actor=actor, action="release.created",
            target_type="release", target_id=record.id,
            after_state={"status": record.status},
        )
        self.repository.flush()

    def attach_artifact(
        self, release_id: str, artifact_id: str, *, role: str, actor: str
    ) -> None:
        if self.repository.get_release(release_id) is None:
            raise ArtifactValidationError("Release does not exist")
        if self.repository.get_artifact(artifact_id) is None:
            raise ArtifactValidationError("Artifact does not exist")
        self.repository.add_release_artifact(ReleaseArtifact(
            release_id=release_id, artifact_id=artifact_id, role=role
        ))
        from .audit import record_audit
        record_audit(
            self.repository, actor=actor, action="release.artifact_attached",
            target_type="release", target_id=release_id,
            metadata={"artifact_id": artifact_id, "role": role},
        )
        self.repository.flush()

    def promote(
        self,
        release_id: str,
        *,
        expected_status: str,
        target_status: str,
        actor: str,
        reason: str,
        required_approval_policy: str | None = None,
        approval_id: str | None = None,
        requested_by: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> None:
        from research.python.researchops.promotion import (
            PromotionDecisionError,
            PromotionPolicyService,
            ReleasePromotionService,
            promotion_request_key,
        )

        release = self.repository.get_release(release_id)
        if release is None:
            raise ArtifactValidationError("Release does not exist")
        policy = PromotionPolicyService(self.repository).policy_for(
            "release", release.release_type
        )
        if (
            required_approval_policy is not None
            and required_approval_policy != policy.approval.policy
        ):
            raise ArtifactValidationError(
                "Requested approval policy disagrees with governed promotion policy"
            )
        gate_problems: list[str] = []
        for gate_id in policy.required_gates:
            gate = self.repository.get_gate_result(gate_id, "release", release_id)
            if gate is None:
                gate_problems.append(f"{gate_id}:MISSING")
                continue
            effective = gate.effective_status or gate.status
            if gate.current_evaluation_id is None or gate.evaluation_outcome is None:
                gate_problems.append(f"{gate_id}:NO_CURRENT_EVALUATION")
            elif effective not in {"PASSED", "WAIVED"}:
                gate_problems.append(f"{gate_id}:{effective}")
        if gate_problems:
            raise ArtifactValidationError(
                f"Promotion authorization failed: {sorted(gate_problems)}"
            )
        selected_approval_id = approval_id
        if selected_approval_id is None:
            candidates = [
                item
                for item in self.repository.approvals("release", release_id)
                if item.policy == policy.approval.policy and item.status == "APPROVED"
            ]
            if len(candidates) != 1:
                raise ArtifactValidationError(
                    "Required release approval is missing or ambiguous"
                )
            selected_approval_id = candidates[0].id
        key = idempotency_key or promotion_request_key(
            {
                "target_type": "release",
                "target_id": release_id,
                "expected_status": expected_status,
                "target_status": target_status,
                "approval_id": selected_approval_id,
                "reason": reason,
            }
        )
        try:
            ReleasePromotionService(self.repository).promote(
                release_id,
                approval_id=selected_approval_id,
                actor=actor,
                reason=reason,
                idempotency_key=key,
                expected_status=expected_status,
                target_status=target_status,
            )
        except PromotionDecisionError as exc:
            raise ArtifactValidationError(str(exc)) from exc
