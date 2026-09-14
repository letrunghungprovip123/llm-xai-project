from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JSON_DOCUMENT


class OrchestrationBinding(Base):
    __tablename__ = "orchestration_bindings"
    __table_args__ = (
        UniqueConstraint(
            "orchestrator",
            "prefect_flow_run_id",
            "prefect_task_run_id",
            "attempt_number",
            name="uq_orchestration_bindings_prefect_run_attempt",
        ),
        UniqueConstraint(
            "orchestrator",
            "orchestration_key",
            "attempt_number",
            name="uq_orchestration_bindings_key_attempt",
        ),
        Index(
            "ix_orchestration_bindings_pipeline_stage",
            "pipeline_run_id",
            "stage_run_id",
        ),
        Index("ix_orchestration_bindings_prefect_flow", "prefect_flow_run_id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    orchestrator: Mapped[str] = mapped_column(String(32), nullable=False)
    orchestrator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False
    )
    stage_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("stage_runs.id", ondelete="CASCADE")
    )
    prefect_flow_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prefect_task_run_id: Mapped[str | None] = mapped_column(String(64))
    deployment_name: Mapped[str | None] = mapped_column(String(255))
    work_pool_name: Mapped[str | None] = mapped_column(String(255))
    work_queue_name: Mapped[str | None] = mapped_column(String(255))
    orchestration_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    binding_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON_DOCUMENT, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class StageRunOutput(Base):
    __tablename__ = "stage_run_outputs"
    __table_args__ = (
        UniqueConstraint(
            "stage_run_id", "artifact_id", name="uq_stage_run_outputs_artifact"
        ),
        Index("ix_stage_run_outputs_artifact", "artifact_id"),
    )

    stage_run_id: Mapped[str] = mapped_column(
        ForeignKey("stage_runs.id", ondelete="CASCADE"), primary_key=True
    )
    output_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    contract: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False
    )
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PipelineRunReceipt(Base):
    __tablename__ = "pipeline_run_receipts"
    __table_args__ = (
        Index("ix_pipeline_run_receipts_artifact", "artifact_id", unique=True),
    )

    pipeline_run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), primary_key=True
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
