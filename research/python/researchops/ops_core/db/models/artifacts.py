from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..enums import ArtifactStatus
from ..types import JSON_DOCUMENT

_BIGINT_PK = BigInteger().with_variant(Integer(), "sqlite")

_ARTIFACT_VALUES = ",".join(f"'{value.value}'" for value in ArtifactStatus)


class ArtifactRecord(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(f"status IN ({_ARTIFACT_VALUES})", name="status_allowed"),
        UniqueConstraint("manifest_sha256", name="uq_artifacts_manifest_sha256"),
        Index("ix_artifacts_type_status_created", "artifact_type", "status", "created_at"),
        Index("ix_artifacts_producer_stage_run", "producer_stage_run_id"),
        Index("ix_artifacts_created_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    artifact_type: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ArtifactStatus.VERIFIED.value)
    manifest_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    producer_stage_run_id: Mapped[str | None] = mapped_column(ForeignKey("stage_runs.id", ondelete="RESTRICT"))
    source_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("environment_snapshots.id", ondelete="RESTRICT"))
    limitations: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    artifact_metadata: Mapped[dict] = mapped_column("metadata", JSON_DOCUMENT, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    certified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ArtifactFileRecord(Base):
    __tablename__ = "artifact_files"
    __table_args__ = (
        UniqueConstraint("artifact_id", "relative_path", name="uq_artifact_files_path"),
    )

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    object_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    object_version_id: Mapped[str | None] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_count: Mapped[int | None] = mapped_column(BigInteger)
    column_count: Mapped[int | None] = mapped_column()
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)


class LineageEdge(Base):
    __tablename__ = "lineage_edges"
    __table_args__ = (
        CheckConstraint("parent_artifact_id <> child_artifact_id", name="no_self_edge"),
        Index("ix_lineage_edges_child", "child_artifact_id"),
    )

    parent_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="RESTRICT"), primary_key=True)
    child_artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="RESTRICT"), primary_key=True)
    relationship_type: Mapped[str] = mapped_column(String(64), primary_key=True, default="derived_from")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
