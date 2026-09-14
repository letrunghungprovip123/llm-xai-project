from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from research.python.researchops.artifacts.exceptions import ArtifactValidationError
from research.python.researchops.artifacts.ids import new_ulid
from research.python.researchops.mlflow_tracking.registry_gateway import RegistryGateway
from research.python.researchops.ops_core.db.enums import GateStatus, ReleaseStatus
from research.python.researchops.ops_core.db.models import (
    Approval,
    GateResult,
    GateWaiver,
    PromotionDecision,
)
from research.python.researchops.ops_core.repositories.protocols import OpsRepository
from research.python.researchops.ops_core.services.audit import record_audit
from research.python.researchops.ops_core.services.state_transitions import StateTransitionService

from .contracts import (
    PromotionPolicy,
    PromotionPolicyCatalog,
    load_promotion_policies,
    promotion_policy_sha256,
)


class PromotionDecisionError(ArtifactValidationError):
    """Promotion or waiver authorization failed closed."""


class PromotionIdentityDrift(PromotionDecisionError):
    """An idempotency key was reused with different promotion semantics."""


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical_sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def promotion_request_key(payload: dict[str, Any]) -> str:
    return _canonical_sha(payload)


@dataclass(frozen=True)
class PromotionAuthorization:
    policy: PromotionPolicy
    approval: Approval
    target_state: str
    gate_snapshot: tuple[dict[str, Any], ...]
    waiver_snapshot: tuple[dict[str, Any], ...]


class PromotionPolicyService:
    def __init__(
        self,
        repository: OpsRepository,
        *,
        catalog: PromotionPolicyCatalog | None = None,
    ) -> None:
        self.repository = repository
        self.catalog = catalog or load_promotion_policies()

    def policy_for(self, target_type: str, target_kind: str) -> PromotionPolicy:
        try:
            return self.catalog.for_target(target_type, target_kind)
        except ValueError as exc:
            raise PromotionDecisionError(str(exc)) from exc

    def authorize(
        self,
        *,
        policy: PromotionPolicy,
        target_type: str,
        target_id: str,
        target_kind: str,
        current_state: str,
        target_state: str,
        approval_id: str,
        now: datetime | None = None,
    ) -> PromotionAuthorization:
        now = now or datetime.now(timezone.utc)
        if policy.target_type != target_type or target_kind not in policy.target_kinds:
            raise PromotionDecisionError("Promotion target does not match policy")
        if current_state not in policy.from_states:
            raise PromotionDecisionError(
                f"Promotion state is not eligible: {current_state}; "
                f"allowed={list(policy.from_states)}"
            )
        gate_snapshot: list[dict[str, Any]] = []
        waiver_snapshot: list[dict[str, Any]] = []
        missing: list[str] = []
        unsatisfied: list[str] = []
        for gate_id in policy.required_gates:
            result = self.repository.get_gate_result(gate_id, target_type, target_id)
            if result is None:
                missing.append(gate_id)
                continue
            if result.current_evaluation_id is None or result.evaluation_outcome is None:
                unsatisfied.append(f"{gate_id}:NO_CURRENT_EVALUATION")
                continue
            item = {
                "gate_id": gate_id,
                "gate_result_id": result.id,
                "evaluation_id": result.current_evaluation_id,
                "evaluation_outcome": result.evaluation_outcome,
                "effective_status": result.effective_status or result.status,
            }
            effective = result.effective_status or result.status
            if effective == GateStatus.PASSED.value:
                gate_snapshot.append(item)
                continue
            if effective == GateStatus.WAIVED.value:
                waiver = self._active_current_waiver(result, now=now)
                if gate_id in policy.non_waivable_gates:
                    unsatisfied.append(f"{gate_id}:NON_WAIVABLE")
                elif waiver is None:
                    unsatisfied.append(f"{gate_id}:INVALID_WAIVER")
                else:
                    gate_snapshot.append(item)
                    waiver_snapshot.append(self._waiver_snapshot(waiver))
                continue
            unsatisfied.append(f"{gate_id}:{effective}")
        if missing or unsatisfied:
            raise PromotionDecisionError(
                "Promotion gates are not satisfied: "
                f"missing={sorted(missing)} unsatisfied={sorted(unsatisfied)}"
            )
        if waiver_snapshot:
            if policy.waiver_mode == "FORBIDDEN":
                raise PromotionDecisionError("Promotion policy forbids waivers")
            if target_state != policy.waived_to_state:
                raise PromotionDecisionError(
                    f"Active waivers require target state {policy.waived_to_state}"
                )
        elif target_state != policy.to_state:
            raise PromotionDecisionError(
                f"Promotion without waivers requires target state {policy.to_state}"
            )
        approval = self._require_approval(
            approval_id=approval_id,
            target_type=target_type,
            target_id=target_id,
            policy=policy,
            now=now,
        )
        return PromotionAuthorization(
            policy=policy,
            approval=approval,
            target_state=target_state,
            gate_snapshot=tuple(gate_snapshot),
            waiver_snapshot=tuple(waiver_snapshot),
        )

    def _require_approval(
        self,
        *,
        approval_id: str,
        target_type: str,
        target_id: str,
        policy: PromotionPolicy,
        now: datetime,
    ) -> Approval:
        approval = self.repository.get_approval(approval_id)
        if approval is None:
            raise PromotionDecisionError("Required approval does not exist")
        expected = (target_type, target_id, policy.approval.policy)
        observed = (approval.target_type, approval.target_id, approval.policy)
        if observed != expected:
            raise PromotionDecisionError(
                f"Approval scope mismatch: expected={expected} observed={observed}"
            )
        if approval.status != "APPROVED":
            raise PromotionDecisionError(
                f"Approval is not approved: {approval.status}"
            )
        expires_at = _utc(approval.expires_at)
        if expires_at is not None and expires_at <= now:
            raise PromotionDecisionError("Approval has expired")
        if not approval.decided_by:
            raise PromotionDecisionError("Approval has no decision actor")
        if (
            policy.approval.separation_of_duties
            and approval.requested_by == approval.decided_by
        ):
            raise PromotionDecisionError(
                "Approval violates separation of duties"
            )
        return approval

    def _active_current_waiver(
        self, result: GateResult, *, now: datetime
    ) -> GateWaiver | None:
        if result.current_evaluation_id is None:
            return None
        waiver = self.repository.active_gate_waiver(
            result.id, result.current_evaluation_id
        )
        if waiver is None:
            return None
        expires_at = _utc(waiver.expires_at)
        if expires_at is None or expires_at <= now:
            waiver.status = "EXPIRED"
            if result.current_evaluation_id == waiver.evaluation_id:
                result.status = result.evaluation_outcome or GateStatus.FAILED.value
                result.effective_status = result.evaluation_outcome
            self.repository.flush()
            return None
        return waiver

    @staticmethod
    def _waiver_snapshot(waiver: GateWaiver) -> dict[str, Any]:
        return {
            "waiver_id": waiver.id,
            "gate_id": waiver.gate_id,
            "evaluation_id": waiver.evaluation_id,
            "policy_id": waiver.policy_id,
            "policy_version": waiver.policy_version,
            "approval_id": waiver.approval_id,
            "expires_at": _utc(waiver.expires_at).isoformat(),
        }


class WaiverService:
    def __init__(
        self,
        repository: OpsRepository,
        *,
        policies: PromotionPolicyService | None = None,
    ) -> None:
        self.repository = repository
        self.policies = policies or PromotionPolicyService(repository)

    def grant(
        self,
        *,
        gate_id: str,
        scope_type: str,
        scope_id: str,
        target_kind: str,
        policy_id: str,
        approval_id: str,
        requested_by: str,
        decided_by: str,
        reason: str,
        expires_at: datetime,
        request_key: str | None = None,
        now: datetime | None = None,
    ) -> GateWaiver:
        now = now or datetime.now(timezone.utc)
        expires_at = _utc(expires_at)
        if expires_at is None or expires_at <= now:
            raise PromotionDecisionError("Waiver expiry must be in the future")
        if not reason.strip():
            raise PromotionDecisionError("Waiver reason must not be blank")
        policy = self.policies.catalog.by_id().get(policy_id)
        if policy is None:
            raise PromotionDecisionError(f"Unknown promotion policy: {policy_id}")
        if policy.target_type != scope_type or target_kind not in policy.target_kinds:
            raise PromotionDecisionError("Waiver target does not match policy")
        if gate_id not in policy.required_gates:
            raise PromotionDecisionError("Gate is not required by the policy")
        if policy.waiver_mode == "FORBIDDEN":
            raise PromotionDecisionError("Promotion policy forbids waivers")
        if gate_id in policy.non_waivable_gates:
            raise PromotionDecisionError(f"Gate is non-waivable: {gate_id}")
        result = self.repository.get_gate_result(gate_id, scope_type, scope_id)
        if result is None:
            raise PromotionDecisionError("Cannot waive a missing gate")
        if result.current_evaluation_id is None:
            raise PromotionDecisionError("Cannot waive a gate without an evaluation")
        if result.evaluation_outcome != GateStatus.FAILED.value:
            raise PromotionDecisionError("Only a current FAILED evaluation may be waived")
        approval = self._require_waiver_approval(
            approval_id=approval_id,
            gate_result_id=result.id,
            policy=policy,
            requested_by=requested_by,
            now=now,
        )
        if decided_by != approval.decided_by:
            raise PromotionDecisionError(
                "Waiver decision actor must match the approval decision actor"
            )
        approval_expiry = _utc(approval.expires_at)
        if approval_expiry is not None and expires_at > approval_expiry:
            raise PromotionDecisionError("Waiver cannot outlive its approval")
        identity = {
            "gate_result_id": result.id,
            "evaluation_id": result.current_evaluation_id,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "approval_id": approval_id,
            "requested_by": requested_by,
            "decided_by": decided_by,
            "reason": reason.strip(),
            "expires_at": expires_at.isoformat(),
        }
        key = request_key or _canonical_sha(identity)
        existing = self.repository.get_gate_waiver_by_request_key(key)
        if existing is not None:
            observed = {
                "gate_result_id": existing.gate_result_id,
                "evaluation_id": existing.evaluation_id,
                "policy_id": existing.policy_id,
                "policy_version": existing.policy_version,
                "approval_id": existing.approval_id,
                "requested_by": existing.requested_by,
                "decided_by": existing.decided_by,
                "reason": existing.reason,
                "expires_at": _utc(existing.expires_at).isoformat(),
            }
            if observed != identity:
                raise PromotionIdentityDrift(
                    "Waiver request key was reused with different semantics"
                )
            return existing
        active = self.repository.active_gate_waiver(
            result.id, result.current_evaluation_id
        )
        if active is not None and _utc(active.expires_at) > now:
            raise PromotionDecisionError("A current active waiver already exists")
        waiver = GateWaiver(
            id=f"waiver_{new_ulid()}",
            request_key=key,
            gate_result_id=result.id,
            evaluation_id=result.current_evaluation_id,
            gate_id=gate_id,
            scope_type=scope_type,
            scope_id=scope_id,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            approval_id=approval_id,
            requested_by=requested_by,
            decided_by=decided_by,
            reason=reason.strip(),
            status="ACTIVE",
            created_at=now,
            expires_at=expires_at,
        )
        self.repository.add_gate_waiver(waiver)
        result.status = GateStatus.WAIVED.value
        result.effective_status = GateStatus.WAIVED.value
        record_audit(
            self.repository,
            actor=decided_by,
            action="gate.waiver_granted",
            target_type=scope_type,
            target_id=scope_id,
            before_state={
                "gate_id": gate_id,
                "effective_status": GateStatus.FAILED.value,
                "evaluation_id": result.current_evaluation_id,
            },
            after_state={
                "gate_id": gate_id,
                "effective_status": GateStatus.WAIVED.value,
                "waiver_id": waiver.id,
                "expires_at": expires_at.isoformat(),
            },
        )
        self.repository.flush()
        return waiver

    def _require_waiver_approval(
        self,
        *,
        approval_id: str,
        gate_result_id: str,
        policy: PromotionPolicy,
        requested_by: str,
        now: datetime,
    ) -> Approval:
        approval = self.repository.get_approval(approval_id)
        if approval is None:
            raise PromotionDecisionError("Waiver approval does not exist")
        expected = ("gate_result", gate_result_id, policy.waiver_approval_policy)
        observed = (approval.target_type, approval.target_id, approval.policy)
        if observed != expected:
            raise PromotionDecisionError(
                f"Waiver approval scope mismatch: expected={expected} observed={observed}"
            )
        if approval.status != "APPROVED":
            raise PromotionDecisionError("Waiver approval is not approved")
        expires_at = _utc(approval.expires_at)
        if expires_at is not None and expires_at <= now:
            raise PromotionDecisionError("Waiver approval has expired")
        if approval.requested_by != requested_by:
            raise PromotionDecisionError(
                "Waiver requester does not match approval requester"
            )
        if not approval.decided_by or approval.requested_by == approval.decided_by:
            raise PromotionDecisionError(
                "Waiver approval requires separation of duties"
            )
        return approval

    def revoke(
        self, waiver_id: str, *, actor: str, reason: str, now: datetime | None = None
    ) -> GateWaiver:
        waiver = self.repository.get_gate_waiver(waiver_id)
        if waiver is None:
            raise PromotionDecisionError("Waiver does not exist")
        if waiver.status != "ACTIVE":
            raise PromotionDecisionError(f"Waiver is not active: {waiver.status}")
        waiver.status = "REVOKED"
        waiver.revoked_at = now or datetime.now(timezone.utc)
        waiver.revoked_by = actor
        waiver.revocation_reason = reason
        result = self.repository.get_gate_result(
            waiver.gate_id, waiver.scope_type, waiver.scope_id
        )
        if result is not None and result.current_evaluation_id == waiver.evaluation_id:
            result.status = result.evaluation_outcome or GateStatus.FAILED.value
            result.effective_status = result.evaluation_outcome
        record_audit(
            self.repository,
            actor=actor,
            action="gate.waiver_revoked",
            target_type=waiver.scope_type,
            target_id=waiver.scope_id,
            before_state={"waiver_id": waiver.id, "status": "ACTIVE"},
            after_state={"waiver_id": waiver.id, "status": "REVOKED"},
            metadata={"reason": reason},
        )
        self.repository.flush()
        return waiver


class _DecisionService:
    def __init__(self, repository: OpsRepository) -> None:
        self.repository = repository

    def reuse_existing(
        self,
        *,
        idempotency_key: str,
        target_type: str,
        target_id: str,
        target_kind: str,
        policy: PromotionPolicy,
        expected_state: str,
        target_state: str,
        requested_by: str,
        reason: str,
        approval_id: str,
    ) -> PromotionDecision | None:
        existing = self.repository.get_promotion_decision_by_key(idempotency_key)
        if existing is None:
            return None
        observed = {
            "target_type": existing.target_type,
            "target_id": existing.target_id,
            "target_kind": existing.target_kind,
            "policy_id": existing.policy_id,
            "policy_version": existing.policy_version,
            "expected_state": existing.expected_state,
            "target_state": existing.target_state,
            "requested_by": existing.requested_by,
            "reason": existing.reason,
            "approval_id": existing.approval_id,
        }
        expected = {
            "target_type": target_type,
            "target_id": target_id,
            "target_kind": target_kind,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "expected_state": expected_state,
            "target_state": target_state,
            "requested_by": requested_by,
            "reason": reason,
            "approval_id": approval_id,
        }
        if observed != expected:
            raise PromotionIdentityDrift(
                "Promotion idempotency key was reused with different request semantics"
            )
        return existing

    def create_or_reuse(
        self,
        *,
        idempotency_key: str,
        target_type: str,
        target_id: str,
        target_kind: str,
        policy: PromotionPolicy,
        expected_state: str,
        target_state: str,
        authorization: PromotionAuthorization,
        requested_by: str,
        reason: str,
    ) -> tuple[PromotionDecision, bool]:
        payload = {
            "target_type": target_type,
            "target_id": target_id,
            "target_kind": target_kind,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "expected_state": expected_state,
            "target_state": target_state,
            "approval_id": authorization.approval.id,
            "gate_snapshot": list(authorization.gate_snapshot),
            "waiver_snapshot": list(authorization.waiver_snapshot),
            "requested_by": requested_by,
            "reason": reason,
        }
        payload_sha = _canonical_sha(payload)
        existing = self.repository.get_promotion_decision_by_key(idempotency_key)
        if existing is not None:
            if existing.payload_sha256 != payload_sha:
                raise PromotionIdentityDrift(
                    "Promotion idempotency key was reused with different semantics"
                )
            return existing, False
        decision = PromotionDecision(
            id=f"promotion_{new_ulid()}",
            idempotency_key=idempotency_key,
            payload_sha256=payload_sha,
            target_type=target_type,
            target_id=target_id,
            target_kind=target_kind,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            policy_sha256=promotion_policy_sha256(),
            expected_state=expected_state,
            target_state=target_state,
            gate_snapshot=list(authorization.gate_snapshot),
            approval_snapshot={
                "approval_id": authorization.approval.id,
                "policy": authorization.approval.policy,
                "requested_by": authorization.approval.requested_by,
                "decided_by": authorization.approval.decided_by,
                "expires_at": (
                    _utc(authorization.approval.expires_at).isoformat()
                    if authorization.approval.expires_at is not None
                    else None
                ),
            },
            waiver_snapshot=list(authorization.waiver_snapshot),
            decision="APPROVED",
            execution_status="PENDING",
            reason=reason,
            previous_external_state={},
            new_external_state={},
            requested_by=requested_by,
            approval_id=authorization.approval.id,
        )
        self.repository.add_promotion_decision(decision)
        record_audit(
            self.repository,
            actor=requested_by,
            action="promotion.decision_recorded",
            target_type=target_type,
            target_id=target_id,
            after_state={
                "decision_id": decision.id,
                "policy_id": policy.policy_id,
                "execution_status": "PENDING",
            },
        )
        self.repository.flush()
        return decision, True


class ReleasePromotionService:
    def __init__(
        self,
        repository: OpsRepository,
        *,
        policies: PromotionPolicyService | None = None,
    ) -> None:
        self.repository = repository
        self.policies = policies or PromotionPolicyService(repository)
        self.decisions = _DecisionService(repository)
        self.transitions = StateTransitionService(repository)

    def promote(
        self,
        release_id: str,
        *,
        approval_id: str,
        actor: str,
        reason: str,
        idempotency_key: str,
        expected_status: str | None = None,
        target_status: str | None = None,
    ) -> PromotionDecision:
        release = self.repository.get_release(release_id)
        if release is None:
            raise PromotionDecisionError("Release does not exist")
        if self.repository.get_artifact(release.manifest_artifact_id) is None:
            raise PromotionDecisionError("Release manifest artifact is missing")
        if not self.repository.release_artifact_ids(release_id):
            raise PromotionDecisionError("Release contains no registered artifacts")
        policy = self.policies.policy_for("release", release.release_type)
        expected = expected_status or release.status
        target = target_status or policy.to_state
        approval_record = self.repository.get_approval(approval_id)
        approval_requester = (
            approval_record.requested_by if approval_record is not None else actor
        )
        existing = self.decisions.reuse_existing(
            idempotency_key=idempotency_key,
            target_type="release",
            target_id=release_id,
            target_kind=release.release_type,
            policy=policy,
            expected_state=expected,
            target_state=target,
            requested_by=approval_requester,
            reason=reason,
            approval_id=approval_id,
        )
        if existing is not None:
            return existing
        if release.status != expected:
            raise PromotionDecisionError(
                f"Release status changed: expected={expected} observed={release.status}"
            )
        authorization = self.policies.authorize(
            policy=policy,
            target_type="release",
            target_id=release_id,
            target_kind=release.release_type,
            current_state=release.status,
            target_state=target,
            approval_id=approval_id,
        )
        decision, created = self.decisions.create_or_reuse(
            idempotency_key=idempotency_key,
            target_type="release",
            target_id=release_id,
            target_kind=release.release_type,
            policy=policy,
            expected_state=expected,
            target_state=target,
            authorization=authorization,
            requested_by=authorization.approval.requested_by,
            reason=reason,
        )
        if not created:
            return decision
        try:
            self.transitions.release(
                release_id,
                expected=expected,
                target=target,
                actor=actor,
                reason=reason,
            )
            if target in {
                ReleaseStatus.READY_WITH_LIMITATIONS.value,
                ReleaseStatus.CERTIFIED.value,
            }:
                release.promoted_at = datetime.now(timezone.utc)
            decision.execution_status = "COMPLETED"
            decision.executed_by = actor
            decision.executed_at = datetime.now(timezone.utc)
            decision.previous_external_state = {"status": expected}
            decision.new_external_state = {"status": target}
            record_audit(
                self.repository,
                actor=actor,
                action="release.promoted_by_policy",
                target_type="release",
                target_id=release_id,
                before_state={"status": expected},
                after_state={
                    "status": target,
                    "decision_id": decision.id,
                    "policy_id": policy.policy_id,
                },
            )
            self.repository.flush()
            return decision
        except BaseException:
            decision.execution_status = "FAILED"
            decision.executed_by = actor
            decision.executed_at = datetime.now(timezone.utc)
            self.repository.flush()
            raise


class ModelPromotionService:
    def __init__(
        self,
        repository: OpsRepository,
        gateway: RegistryGateway,
        *,
        policies: PromotionPolicyService | None = None,
    ) -> None:
        self.repository = repository
        self.gateway = gateway
        self.policies = policies or PromotionPolicyService(repository)
        self.decisions = _DecisionService(repository)

    def promote(
        self,
        *,
        model_name: str,
        version: str,
        approval_id: str,
        actor: str,
        reason: str,
        idempotency_key: str,
        request_id: str | None = None,
    ) -> PromotionDecision:
        policy = self.policies.policy_for("model_version", model_name)
        target_id = f"{model_name}:{version}"
        approval_record = self.repository.get_approval(approval_id)
        approval_requester = (
            approval_record.requested_by if approval_record is not None else actor
        )
        existing = self.decisions.reuse_existing(
            idempotency_key=idempotency_key,
            target_type="model_version",
            target_id=target_id,
            target_kind=model_name,
            policy=policy,
            expected_state="CANDIDATE",
            target_state=policy.to_state,
            requested_by=approval_requester,
            reason=reason,
            approval_id=approval_id,
        )
        if existing is not None:
            return existing
        current = self.gateway.get_version(model_name, version)
        if current is None:
            raise PromotionDecisionError("Model version does not exist")
        candidate_alias = policy.side_effects.mlflow_candidate_alias
        champion_alias = policy.side_effects.mlflow_champion_alias
        archive_alias = policy.side_effects.mlflow_archive_alias
        assert candidate_alias and champion_alias and archive_alias
        candidate = self.gateway.alias_version(model_name, candidate_alias)
        if candidate != version:
            raise PromotionDecisionError("Only the current candidate may be promoted")
        if current.tags.get("researchops.source_manifest_verified") != "PASSED":
            raise PromotionDecisionError("Candidate source manifest is not verified")
        authorization = self.policies.authorize(
            policy=policy,
            target_type="model_version",
            target_id=target_id,
            target_kind=model_name,
            current_state="CANDIDATE",
            target_state=policy.to_state,
            approval_id=approval_id,
        )
        decision, created = self.decisions.create_or_reuse(
            idempotency_key=idempotency_key,
            target_type="model_version",
            target_id=target_id,
            target_kind=model_name,
            policy=policy,
            expected_state="CANDIDATE",
            target_state=policy.to_state,
            authorization=authorization,
            requested_by=authorization.approval.requested_by,
            reason=reason,
        )
        if not created:
            return decision
        previous = self.gateway.alias_version(model_name, champion_alias)
        decision.previous_external_state = {
            "candidate_version": candidate,
            "champion_version": previous,
        }
        self.repository.flush()
        try:
            if self.gateway.alias_version(model_name, candidate_alias) != version:
                raise PromotionDecisionError(
                    "Candidate alias changed during promotion authorization"
                )
            if previous is not None and previous != version:
                self.gateway.set_alias(model_name, archive_alias, previous)
                self.gateway.set_version_tags(
                    model_name,
                    previous,
                    {"researchops.historical_champion": "true"},
                )
            self.gateway.set_alias(model_name, champion_alias, version)
            self.gateway.set_version_tags(
                model_name,
                version,
                {
                    "researchops.lifecycle_status": "CHAMPION",
                    "researchops.approval_id": approval_id,
                    "researchops.promotion_decision_id": decision.id,
                    "researchops.gate_status": "PASSED",
                },
            )
            observed = self.gateway.alias_version(model_name, champion_alias)
            if observed != version:
                raise PromotionDecisionError("Champion alias assignment did not persist")
            decision.execution_status = "COMPLETED"
            decision.executed_by = actor
            decision.executed_at = datetime.now(timezone.utc)
            decision.new_external_state = {
                "candidate_version": version,
                "champion_version": observed,
                "archived_reference": (
                    previous if previous is not None and previous != version else None
                ),
            }
            record_audit(
                self.repository,
                actor=actor,
                action="mlflow.champion_promoted",
                target_type="model_version",
                target_id=target_id,
                before_state=decision.previous_external_state,
                after_state={
                    **decision.new_external_state,
                    "approval_id": approval_id,
                    "decision_id": decision.id,
                    "policy_id": policy.policy_id,
                },
                request_id=request_id,
            )
            self.repository.flush()
            return decision
        except BaseException:
            observed = self.gateway.alias_version(model_name, champion_alias)
            decision.execution_status = (
                "FAILED_PARTIAL" if observed != previous else "FAILED"
            )
            decision.executed_by = actor
            decision.executed_at = datetime.now(timezone.utc)
            decision.new_external_state = {
                "champion_version": observed,
                "reconciliation_required": observed != previous,
            }
            record_audit(
                self.repository,
                actor=actor,
                action="mlflow.promotion_failed",
                target_type="model_version",
                target_id=target_id,
                before_state=decision.previous_external_state,
                after_state=decision.new_external_state,
                request_id=request_id,
            )
            self.repository.flush()
            raise
