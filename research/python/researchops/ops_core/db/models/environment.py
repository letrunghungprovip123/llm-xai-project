from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JSON_DOCUMENT


class EnvironmentSnapshot(Base):
    __tablename__ = "environment_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    python_version: Mapped[str] = mapped_column(String(64), nullable=False)
    node_version: Mapped[str | None] = mapped_column(String(64))
    operating_system: Mapped[str] = mapped_column(String(128), nullable=False)
    architecture: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_lock_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    container_image_digest: Mapped[str | None] = mapped_column(String(255))
    git_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    git_dirty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
