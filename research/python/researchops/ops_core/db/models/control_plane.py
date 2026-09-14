from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JSON_DOCUMENT

_IDEMPOTENCY_STATUSES = "'PROCESSING','COMPLETED','FAILED'"
_OPERATION_STATUSES = "'PENDING','RUNNING','SUCCEEDED','FAILED','FAILED_PARTIAL','CANCELLED'"


class ApiIdempotencyRequest(Base):
    __tablename__ = "api_idempotency_requests"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_IDEMPOTENCY_STATUSES})", name="status_allowed"
        ),
        UniqueConstraint(
            "principal_subject",
            "http_method",
            "route_template",
            "idempotency_key",
            name="uq_api_idempotency_request_scope",
        ),
        Index("ix_api_idempotency_created_id", "created_at", "id"),
        Index("ix_api_idempotency_resource", "resource_type", "resource_id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    principal_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    http_method: Mapped[str] = mapped_column(String(16), nullable=False)
    route_template: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROCESSING")
    response_status: Mapped[int | None] = mapped_column()
    response_body: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(160))
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ControlOperation(Base):
    __tablename__ = "control_operations"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_OPERATION_STATUSES})", name="status_allowed"
        ),
        Index("ix_control_operations_status_created", "status", "created_at"),
        Index("ix_control_operations_target", "target_type", "target_id"),
        Index("ix_control_operations_prefect", "prefect_flow_run_id"),
        Index("ix_control_operations_created_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(160), nullable=False)
    prefect_flow_run_id: Mapped[str | None] = mapped_column(String(96))
    pipeline_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    promotion_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("promotion_decisions.id", ondelete="SET NULL")
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_request_id: Mapped[str] = mapped_column(
        ForeignKey("api_idempotency_requests.id", ondelete="RESTRICT"), nullable=False
    )
    request_payload: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
