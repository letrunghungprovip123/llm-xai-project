from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..enums import RunStatus
from ..types import JSON_DOCUMENT

_BIGINT_PK = BigInteger().with_variant(Integer(), "sqlite")

_RUN_VALUES = ",".join(f"'{value.value}'" for value in RunStatus)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_RUN_VALUES})", name="status_allowed"),
        UniqueConstraint("idempotency_key", name="uq_pipeline_runs_idempotency_key"),
        Index("ix_pipeline_runs_status_created", "status", "created_at"),
        Index("ix_pipeline_runs_created_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    flow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RunStatus.PENDING.value)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    registry_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("environment_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class StageRun(Base):
    __tablename__ = "stage_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_RUN_VALUES})", name="status_allowed"),
        UniqueConstraint("pipeline_run_id", "stage_id", "attempt", name="uq_stage_runs_attempt"),
        Index("ix_stage_runs_pipeline_status", "pipeline_run_id", "status"),
        Index("ix_stage_runs_status_retryable", "status", "retryable"),
    )

    id: Mapped[str] = mapped_column(String(72), primary_key=True)
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    stage_id: Mapped[str] = mapped_column(String(128), nullable=False)
    stage_version: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RunStatus.PENDING.value)
    command_snapshot: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    approval_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="NONE")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    stdout_artifact_id: Mapped[str | None] = mapped_column(String(160))
    stderr_artifact_id: Mapped[str | None] = mapped_column(String(160))
    error_type: Mapped[str | None] = mapped_column(String(255))
    error_category: Mapped[str | None] = mapped_column(String(64))
    retryable: Mapped[bool | None] = mapped_column(Boolean)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        Index("ix_run_events_run_occurred", "pipeline_run_id", "occurred_at"),
        Index("ix_run_events_occurred_id", "occurred_at", "id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    stage_run_id: Mapped[str | None] = mapped_column(ForeignKey("stage_runs.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
