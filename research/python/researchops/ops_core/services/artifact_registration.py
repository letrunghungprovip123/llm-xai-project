from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from research.python.researchops.artifacts.description import StoredArtifactDescription
from research.python.researchops.artifacts.exceptions import ArtifactIntegrityError, ArtifactValidationError
from research.python.researchops.artifacts.stores.base import ArtifactStore

from ..db.models import ArtifactFileRecord, ArtifactRecord, LineageEdge
from ..repositories.protocols import OpsRepository
from .audit import record_audit


@dataclass(frozen=True)
class ArtifactRegistrationResult:
    artifact_id: str
    manifest_sha256: str
    created: bool


class ArtifactRegistrationService:
    def __init__(self, repository: OpsRepository, artifact_store: ArtifactStore) -> None:
        self.repository = repository
        self.artifact_store = artifact_store

    def register(self, artifact_id: str, *, actor: str, request_id: str | None = None) -> ArtifactRegistrationResult:
        description = self.artifact_store.describe(artifact_id)
        manifest = description.manifest
        verification = self.artifact_store.verify(artifact_id)
        if not verification.passed:
            raise ArtifactIntegrityError("; ".join(verification.errors))
        if manifest.status not in {"VERIFIED", "CERTIFIED"}:
            raise ArtifactValidationError(
                f"Only VERIFIED or CERTIFIED artifacts can be registered: {manifest.status}"
            )
        if verification.manifest_sha256 != manifest.manifest_sha256:
            raise ArtifactIntegrityError("Manifest identity changed during registration")

        existing = self.repository.get_artifact(artifact_id)
        if existing is not None:
            if existing.manifest_sha256 != manifest.manifest_sha256:
                raise ArtifactValidationError("Artifact ID is already registered with a different manifest")
            return ArtifactRegistrationResult(artifact_id, manifest.manifest_sha256, False)
        by_hash = self.repository.get_artifact_by_manifest_hash(manifest.manifest_sha256)
        if by_hash is not None and by_hash.id != artifact_id:
            raise ArtifactValidationError("Manifest hash is already registered under another artifact ID")

        for parent in manifest.parents:
            parent_record = self.repository.get_artifact(parent.artifact_id)
            if parent_record is None:
                raise ArtifactValidationError(
                    f"Parent artifact is not registered: {parent.artifact_id}"
                )
            if parent_record.manifest_sha256 != parent.manifest_sha256:
                raise ArtifactValidationError(
                    f"Parent manifest hash mismatch: {parent.artifact_id}"
                )

        object_files = {item.relative_path: item for item in description.files}
        expected_paths = {item.relative_path for item in manifest.files}
        if set(object_files) != expected_paths:
            raise ArtifactIntegrityError(
                "Stored artifact description does not match manifest file inventory"
            )

        record = ArtifactRecord(
            id=manifest.artifact_id,
            artifact_type=manifest.artifact_type,
            schema_version=manifest.schema_version,
            status=manifest.status,
            manifest_uri=description.reference.uri,
            manifest_sha256=manifest.manifest_sha256,
            producer_stage_run_id=manifest.producer.stage_run_id,
            source_commit=manifest.source.source_commit,
            environment_snapshot_id=manifest.source.environment_snapshot_id,
            limitations=list(manifest.limitations),
            artifact_metadata=dict(manifest.metadata),
            verified_at=datetime.now(timezone.utc),
            certified_at=(
                datetime.now(timezone.utc)
                if manifest.status == "CERTIFIED"
                else None
            ),
        )
        self.repository.add_artifact(record)
        self.repository.flush()
        for item in manifest.files:
            stored = object_files[item.relative_path]
            self.repository.add_artifact_file(ArtifactFileRecord(
                artifact_id=manifest.artifact_id,
                relative_path=item.relative_path,
                object_uri=stored.uri,
                object_version_id=stored.version_id,
                sha256=item.sha256,
                size_bytes=item.size_bytes,
                row_count=item.row_count,
                column_count=item.column_count,
                media_type=item.media_type,
            ))
        for parent in manifest.parents:
            self.repository.add_lineage_edge(LineageEdge(
                parent_artifact_id=parent.artifact_id,
                child_artifact_id=manifest.artifact_id,
                relationship_type=parent.relationship,
            ))
        record_audit(
            self.repository,
            actor=actor,
            action="artifact.registered",
            target_type="artifact",
            target_id=manifest.artifact_id,
            after_state={"status": manifest.status, "manifest_sha256": manifest.manifest_sha256},
            request_id=request_id,
        )
        self.repository.flush()
        return ArtifactRegistrationResult(artifact_id, manifest.manifest_sha256, True)
