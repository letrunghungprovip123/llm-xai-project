from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from research.python.researchops.artifacts.exceptions import ArtifactValidationError
from research.python.researchops.artifacts.ids import new_ulid
from research.python.researchops.ops_core.db.models import Approval
from research.python.researchops.ops_core.repositories.protocols import OpsRepository
from research.python.researchops.ops_core.services.audit import record_audit
from research.python.researchops.ops_core.services.state_transitions import LifecyclePolicy


class ApprovalDecisionError(ArtifactValidationError):
    """Raised when an approval is missing, stale, rejected, or out of scope."""


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def approval_request_key(
    *, pipeline_run_id: str, node_id: str, stage_id: str, policy: str
) -> str:
    payload = {
        "node_id": node_id,
        "pipeline_run_id": pipeline_run_id,
        "policy": policy,
        "stage_id": stage_id,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


_APPROVAL_REQUEST_KEY_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_PREFECT_RESUME_KEY_PATTERN = re.compile(r"^[a-z0-9-]+$")


def approval_resume_key(request_key: str) -> str:
    """Return a Prefect-safe pause key for an approval request.

    Prefect derives flow-run input keys from the pause key and validates those
    keys against a lowercase alphanumeric-and-dash contract. Keep the boundary
    explicit so an invalid key cannot strand a run in PAUSED before its input
    schema is persisted.
    """

    if _APPROVAL_REQUEST_KEY_PATTERN.fullmatch(request_key) is None:
        raise ApprovalDecisionError(
            f"Approval request key is not a canonical SHA-256 digest: {request_key!r}"
        )
    key = f"approval-{request_key}"
    if _PREFECT_RESUME_KEY_PATTERN.fullmatch(key) is None:
        raise ApprovalDecisionError(
            f"Approval resume key is not Prefect-compatible: {key!r}"
        )
    return key


class ApprovalService:
    def __init__(self, repository: OpsRepository) -> None:
        self.repository = repository
        self.lifecycle = LifecyclePolicy()

    def request(
        self,
        *,
        pipeline_run_id: str,
        node_id: str,
        stage_id: str,
        policy: str,
        requested_by: str,
        prefect_flow_run_id: str,
        timeout_seconds: int | None = 86400,
        details: dict[str, Any] | None = None,
    ) -> Approval:
        if self.repository.get_pipeline_run(pipeline_run_id) is None:
            raise ApprovalDecisionError("Approval pipeline run does not exist")
        key = approval_request_key(
            pipeline_run_id=pipeline_run_id,
            node_id=node_id,
            stage_id=stage_id,
            policy=policy,
        )
        existing = self.repository.get_approval_by_request_key(key)
        if existing is not None:
            if existing.status == "REQUESTED":
                self.expire_if_needed(existing, actor="approval-system")
            return existing
        now = datetime.now(timezone.utc)
        record = Approval(
            id=f"approval_{new_ulid()}",
            target_type="pipeline_stage",
            target_id=f"{pipeline_run_id}:{node_id}",
            policy=policy,
            status="REQUESTED",
            requested_by=requested_by,
            requested_at=now,
            expires_at=(
                now + timedelta(seconds=timeout_seconds)
                if timeout_seconds is not None
                else None
            ),
            pipeline_run_id=pipeline_run_id,
            node_id=node_id,
            stage_id=stage_id,
            request_key=key,
            details={
                **dict(details or {}),
                "prefect_flow_run_id": prefect_flow_run_id,
                "resume_key": approval_resume_key(key),
            },
        )
        self.repository.add_approval(record)
        record_audit(
            self.repository,
            actor=requested_by,
            action="approval.requested",
            target_type="approval",
            target_id=record.id,
            after_state={
                "status": record.status,
                "pipeline_run_id": pipeline_run_id,
                "node_id": node_id,
                "stage_id": stage_id,
                "policy": policy,
            },
        )
        self.repository.flush()
        return record


    def request_target(
        self,
        *,
        target_type: str,
        target_id: str,
        policy: str,
        requested_by: str,
        timeout_seconds: int | None = 86400,
        details: dict[str, Any] | None = None,
    ) -> Approval:
        payload = {
            "target_type": target_type,
            "target_id": target_id,
            "policy": policy,
        }
        key = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        existing = self.repository.get_approval_by_request_key(key)
        if existing is not None:
            if existing.status == "REQUESTED":
                self.expire_if_needed(existing, actor="approval-system")
            return existing
        now = datetime.now(timezone.utc)
        record = Approval(
            id=f"approval_{new_ulid()}",
            target_type=target_type,
            target_id=target_id,
            policy=policy,
            status="REQUESTED",
            requested_by=requested_by,
            requested_at=now,
            expires_at=(
                now + timedelta(seconds=timeout_seconds)
                if timeout_seconds is not None
                else None
            ),
            request_key=key,
            details=dict(details or {}),
        )
        self.repository.add_approval(record)
        record_audit(
            self.repository,
            actor=requested_by,
            action="approval.requested",
            target_type="approval",
            target_id=record.id,
            after_state={
                "status": record.status,
                "target_type": target_type,
                "target_id": target_id,
                "policy": policy,
            },
        )
        self.repository.flush()
        return record

    def require_target_approved(
        self,
        approval_id: str,
        *,
        target_type: str,
        target_id: str,
        policy: str,
    ) -> Approval:
        record = self.repository.get_approval(approval_id)
        if record is None:
            raise ApprovalDecisionError("Approval does not exist")
        self.expire_if_needed(record, actor="approval-system")
        expected = (target_type, target_id, policy)
        observed = (record.target_type, record.target_id, record.policy)
        if observed != expected:
            raise ApprovalDecisionError(
                f"Approval scope mismatch: expected={expected} observed={observed}"
            )
        if record.status != "APPROVED":
            raise ApprovalDecisionError(f"Approval is not approved: {record.status}")
        expires_at = _utc(record.expires_at)
        if expires_at is not None and expires_at <= datetime.now(timezone.utc):
            raise ApprovalDecisionError("Approved authorization has expired")
        return record

    def decide(
        self,
        approval_id: str,
        *,
        decision: str,
        decided_by: str,
        reason: str,
    ) -> Approval:
        record = self.repository.get_approval(approval_id)
        if record is None:
            raise ApprovalDecisionError("Approval does not exist")
        self.expire_if_needed(record, actor="approval-system")
        if record.status != "REQUESTED":
            raise ApprovalDecisionError(
                f"Approval is no longer pending: {record.status}"
            )
        target = decision.upper()
        if target not in {"APPROVED", "REJECTED"}:
            raise ApprovalDecisionError(f"Unsupported approval decision: {decision}")
        self.lifecycle.require_allowed("approval", record.status, target)
        before = {"status": record.status}
        record.status = target
        record.decided_by = decided_by
        record.decided_at = datetime.now(timezone.utc)
        record.reason = reason
        record_audit(
            self.repository,
            actor=decided_by,
            action=f"approval.{target.lower()}",
            target_type="approval",
            target_id=record.id,
            before_state=before,
            after_state={"status": target, "reason": reason},
        )
        self.repository.flush()
        return record

    def expire_if_needed(self, record: Approval, *, actor: str) -> Approval:
        expires_at = _utc(record.expires_at)
        if (
            record.status == "REQUESTED"
            and expires_at is not None
            and expires_at <= datetime.now(timezone.utc)
        ):
            self.lifecycle.require_allowed("approval", record.status, "EXPIRED")
            record.status = "EXPIRED"
            record.decided_by = actor
            record.decided_at = datetime.now(timezone.utc)
            record.reason = "Approval validity window elapsed"
            record_audit(
                self.repository,
                actor=actor,
                action="approval.expired",
                target_type="approval",
                target_id=record.id,
                before_state={"status": "REQUESTED"},
                after_state={"status": "EXPIRED"},
            )
            self.repository.flush()
        return record

    def require_approved(
        self,
        approval_id: str,
        *,
        pipeline_run_id: str,
        node_id: str,
        stage_id: str,
        policy: str,
    ) -> Approval:
        record = self.repository.get_approval(approval_id)
        if record is None:
            raise ApprovalDecisionError("Approval does not exist")
        self.expire_if_needed(record, actor="approval-system")
        expected = (pipeline_run_id, node_id, stage_id, policy)
        observed = (
            record.pipeline_run_id,
            record.node_id,
            record.stage_id,
            record.policy,
        )
        if observed != expected:
            raise ApprovalDecisionError(
                f"Approval scope mismatch: expected={expected} observed={observed}"
            )
        if record.status != "APPROVED":
            raise ApprovalDecisionError(
                f"Approval is not approved: {record.status}"
            )
        expires_at = _utc(record.expires_at)
        if expires_at is not None and expires_at <= datetime.now(timezone.utc):
            raise ApprovalDecisionError("Approved authorization has expired")
        return record
