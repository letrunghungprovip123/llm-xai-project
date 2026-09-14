from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JSON_DOCUMENT


_BIGINT_PK = BigInteger().with_variant(Integer(), "sqlite")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_target_occurred", "target_type", "target_id", "occurred_at"),
        Index("ix_audit_events_occurred_id", "occurred_at", "id"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(160), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))
    before_state: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    after_state: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON_DOCUMENT, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
