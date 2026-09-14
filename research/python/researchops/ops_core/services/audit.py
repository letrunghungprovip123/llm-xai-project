from __future__ import annotations

from ..db.models import AuditEvent
from ..repositories.protocols import OpsRepository


def record_audit(
    repository: OpsRepository,
    *,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    before_state: dict | None = None,
    after_state: dict | None = None,
    request_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    repository.add_audit_event(AuditEvent(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        before_state=before_state,
        after_state=after_state,
        event_metadata=metadata or {},
    ))
