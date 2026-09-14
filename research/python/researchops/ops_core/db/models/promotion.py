from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JSON_DOCUMENT

_WAIVER_STATUSES = "'ACTIVE','EXPIRED','REVOKED'"
_DECISIONS = "'APPROVED','DENIED'"
_EXECUTION_STATUSES = "'PENDING','COMPLETED','FAILED','FAILED_PARTIAL'"


class GateWaiver(Base):
    __tablename__ = "gate_waivers"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_WAIVER_STATUSES})", name="status_allowed"
        ),
        UniqueConstraint("request_key", name="uq_gate_waivers_request_key"),
        Index(
            "ix_gate_waivers_scope_status",
            "scope_type",
            "scope_id",
            "gate_id",
            "status",
        ),
        Index("ix_gate_waivers_evaluation", "evaluation_id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_result_id: Mapped[str] = mapped_column(
        ForeignKey("gate_results.id", ondelete="CASCADE"), nullable=False
    )
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("gate_evaluations.id", ondelete="RESTRICT"), nullable=False
    )
    gate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[int] = mapped_column(nullable=False)
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approvals.id", ondelete="RESTRICT"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(255))
    revocation_reason: Mapped[str | None] = mapped_column(Text)


class PromotionDecision(Base):
    __tablename__ = "promotion_decisions"
    __table_args__ = (
        CheckConstraint(f"decision IN ({_DECISIONS})", name="decision_allowed"),
        CheckConstraint(
            f"execution_status IN ({_EXECUTION_STATUSES})",
            name="execution_status_allowed",
        ),
        UniqueConstraint("idempotency_key", name="uq_promotion_decisions_key"),
        Index("ix_promotion_decisions_target", "target_type", "target_id"),
        Index("ix_promotion_decisions_policy", "policy_id", "policy_version"),
        Index("ix_promotion_decisions_created_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(160), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[int] = mapped_column(nullable=False)
    policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_state: Mapped[str] = mapped_column(String(64), nullable=False)
    target_state: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_snapshot: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    approval_snapshot: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    waiver_snapshot: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_external_state: Mapped[dict] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict
    )
    new_external_state: Mapped[dict] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict
    )
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    executed_by: Mapped[str | None] = mapped_column(String(255))
    approval_id: Mapped[str | None] = mapped_column(
        ForeignKey("approvals.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
