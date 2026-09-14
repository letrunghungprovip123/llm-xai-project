from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..enums import ApprovalStatus, GateStatus
from ..types import JSON_DOCUMENT

_GATE_VALUES = ",".join(f"'{value.value}'" for value in GateStatus)
_APPROVAL_VALUES = ",".join(f"'{value.value}'" for value in ApprovalStatus)
_EVALUATION_OUTCOMES = "'PASSED','FAILED'"


class GateEvaluation(Base):
    __tablename__ = "gate_evaluations"
    __table_args__ = (
        CheckConstraint(f"outcome IN ({_EVALUATION_OUTCOMES})", name="outcome_allowed"),
        UniqueConstraint("evaluation_key", name="uq_gate_evaluations_key"),
        Index("ix_gate_evaluations_scope_time", "gate_id", "scope_type", "scope_id", "evaluated_at"),
        Index("ix_gate_evaluations_source_artifact", "source_artifact_id"),
        Index("ix_gate_evaluations_evidence_artifact", "evidence_artifact_id"),
        Index("ix_gate_evaluations_adapter_policy", "adapter_id", "adapter_version", "policy_id", "policy_version"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    evaluation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(160), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_id: Mapped[str] = mapped_column(String(128), nullable=False)
    adapter_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="RESTRICT")
    )
    source_manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    source_contract: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="RESTRICT")
    )
    evidence_manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    expected: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    observed: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    checks: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    limitations: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    source_contracts: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    source_evaluation_ids: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    origin_pipeline_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    origin_stage_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("stage_runs.id", ondelete="SET NULL")
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GateResult(Base):
    __tablename__ = "gate_results"
    __table_args__ = (
        CheckConstraint(f"status IN ({_GATE_VALUES})", name="status_allowed"),
        CheckConstraint(
            f"effective_status IS NULL OR effective_status IN ({_GATE_VALUES})",
            name="effective_status_allowed",
        ),
        CheckConstraint(
            f"evaluation_outcome IS NULL OR evaluation_outcome IN ({_EVALUATION_OUTCOMES})",
            name="evaluation_outcome_allowed",
        ),
        UniqueConstraint("gate_id", "scope_type", "scope_id", name="uq_gate_results_scope"),
        Index("ix_gate_results_scope_blocking_status", "scope_type", "scope_id", "blocking", "status"),
        Index("ix_gate_results_updated_id", "updated_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    gate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=GateStatus.PENDING.value)
    evaluation_outcome: Mapped[str | None] = mapped_column(String(32))
    effective_status: Mapped[str | None] = mapped_column(String(32))
    current_evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("gate_evaluations.id", ondelete="RESTRICT")
    )
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    expected: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    observed: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    details: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    source_contracts: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(f"status IN ({_APPROVAL_VALUES})", name="status_allowed"),
        Index("ix_approvals_status_requested", "status", "requested_at"),
        Index("ix_approvals_pipeline_status", "pipeline_run_id", "status"),
        Index("ix_approvals_requested_id", "requested_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(160), nullable=False)
    policy: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ApprovalStatus.REQUESTED.value)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pipeline_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE")
    )
    node_id: Mapped[str | None] = mapped_column(String(128))
    stage_id: Mapped[str | None] = mapped_column(String(128))
    request_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    details: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
