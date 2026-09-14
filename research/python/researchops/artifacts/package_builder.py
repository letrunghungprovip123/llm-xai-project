from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import ArtifactValidationError
from .hashing import sha256_file
from .ids import new_artifact_id
from .models import (
    ArtifactFile,
    ArtifactManifestV3,
    ArtifactPackage,
    ArtifactParent,
    ArtifactProducer,
    ArtifactSource,
)
from .paths import normalize_relative_path


@dataclass(frozen=True)
class _PendingFile:
    source_path: Path
    relative_path: str
    media_type: str
    row_count: int | None
    column_count: int | None


class ArtifactPackageBuilder:
    def __init__(
        self,
        *,
        artifact_type: str,
        schema_version: str,
        producer: ArtifactProducer,
        source: ArtifactSource,
        artifact_id: str | None = None,
        status: str = "VERIFIED",
        parents: list[ArtifactParent] | None = None,
        limitations: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.artifact_type = artifact_type
        self.schema_version = schema_version
        self.producer = producer
        self.source = source
        self.artifact_id = artifact_id or new_artifact_id(artifact_type)
        self.status = status
        self.parents = tuple(parents or ())
        self.limitations = tuple(limitations or ())
        self.metadata = dict(metadata or {})
        self._files: list[_PendingFile] = []

    def add_file(
        self,
        source_path: Path,
        *,
        relative_path: str,
        media_type: str | None = None,
        row_count: int | None = None,
        column_count: int | None = None,
    ) -> "ArtifactPackageBuilder":
        path = source_path.resolve()
        if not path.is_file():
            raise ArtifactValidationError(f"Artifact source file does not exist: {path}")
        relative = normalize_relative_path(relative_path)
        if any(item.relative_path == relative for item in self._files):
            raise ArtifactValidationError(f"Duplicate artifact relative path: {relative}")
        detected = media_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._files.append(
            _PendingFile(path, relative, detected, row_count, column_count)
        )
        return self

    def add_directory(self, source_directory: Path) -> "ArtifactPackageBuilder":
        root = source_directory.resolve()
        if not root.is_dir():
            raise ArtifactValidationError(f"Artifact source directory does not exist: {root}")
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            self.add_file(path, relative_path=path.relative_to(root).as_posix())
        return self

    def build(self) -> ArtifactPackage:
        if not self._files:
            raise ArtifactValidationError("Artifact packages must contain at least one file")
        manifest_files = tuple(
            ArtifactFile(
                relative_path=item.relative_path,
                sha256=sha256_file(item.source_path),
                size_bytes=item.source_path.stat().st_size,
                media_type=item.media_type,
                row_count=item.row_count,
                column_count=item.column_count,
            )
            for item in sorted(self._files, key=lambda value: value.relative_path)
        )
        manifest = ArtifactManifestV3(
            artifact_id=self.artifact_id,
            artifact_type=self.artifact_type,
            schema_version=self.schema_version,
            status=self.status,
            producer=self.producer,
            source=self.source,
            parents=self.parents,
            files=manifest_files,
            limitations=self.limitations,
            metadata=self.metadata,
        )
        return ArtifactPackage(
            manifest=manifest,
            source_files={
                item.relative_path: item.source_path
                for item in self._files
            },
        )
