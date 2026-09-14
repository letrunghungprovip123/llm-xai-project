from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..enums import ReleaseStatus
from ..types import JSON_DOCUMENT

_RELEASE_VALUES = ",".join(f"'{value.value}'" for value in ReleaseStatus)


class ReleaseRecord(Base):
    __tablename__ = "releases"
    __table_args__ = (
        CheckConstraint(f"status IN ({_RELEASE_VALUES})", name="status_allowed"),
        Index("ix_releases_type_status_created", "release_type", "status", "created_at"),
        Index("ix_releases_created_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ReleaseStatus.DRAFT.value)
    manifest_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=False)
    source_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_release_id: Mapped[str | None] = mapped_column(ForeignKey("releases.id", ondelete="RESTRICT"))
    limitations: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    release_metadata: Mapped[dict] = mapped_column("metadata", JSON_DOCUMENT, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReleaseArtifact(Base):
    __tablename__ = "release_artifacts"

    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="RESTRICT"), primary_key=True)
    role: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
