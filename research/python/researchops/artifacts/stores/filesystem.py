from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from ..exceptions import (
    ArtifactConflictError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactValidationError,
)
from ..description import StoredArtifactDescription, StoredArtifactFile
from ..manifest import load_manifest, write_manifest
from ..models import ArtifactManifestV3, ArtifactPackage, ArtifactReference, ArtifactVerificationResult
from ..paths import safe_join
from ..verifier import verify_package_directory


class FilesystemArtifactStore:
    def __init__(self, root: Path, *, read_only: bool = False) -> None:
        self.root = root.resolve()
        self.read_only = read_only
        self.root.mkdir(parents=True, exist_ok=True)

    def _artifact_directory_from_manifest(self, manifest: ArtifactManifestV3) -> Path:
        return (
            self.root
            / manifest.artifact_type
            / manifest.schema_version
            / manifest.artifact_id
        )

    def _find_artifact_directory(self, artifact_id: str) -> Path:
        matches = list(self.root.glob(f"*/*/{artifact_id}"))
        if not matches:
            raise ArtifactNotFoundError(f"Artifact not found: {artifact_id}")
        if len(matches) != 1:
            raise ArtifactValidationError(f"Artifact ID is ambiguous: {artifact_id}")
        return matches[0]

    def put_package(self, package: ArtifactPackage) -> ArtifactReference:
        if self.read_only:
            raise ArtifactValidationError("Artifact store is read-only")
        manifest = package.manifest
        destination = self._artifact_directory_from_manifest(manifest)
        if destination.exists():
            existing = load_manifest(destination / "manifest.json")
            if existing.manifest_sha256 == manifest.manifest_sha256:
                result = verify_package_directory(destination)
                if not result.passed:
                    raise ArtifactIntegrityError("Existing artifact is corrupt")
                return self._reference(existing, destination)
            raise ArtifactConflictError(
                f"Immutable artifact ID already exists with different content: "
                f"{manifest.artifact_id}"
            )

        source_map = package.source_files
        final_manifest = manifest

        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{manifest.artifact_id}.", dir=destination.parent))
        try:
            files_root = staging / "files"
            for item in final_manifest.files:
                source = source_map[item.relative_path]
                target = safe_join(files_root, item.relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            # Manifest is intentionally written last as the package commit marker.
            write_manifest(staging / "manifest.json", final_manifest)
            result = verify_package_directory(staging)
            if not result.passed:
                raise ArtifactIntegrityError("; ".join(result.errors))
            os.replace(staging, destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return self._reference(final_manifest, destination)

    def get_manifest(self, artifact_id: str) -> ArtifactManifestV3:
        return load_manifest(self._find_artifact_directory(artifact_id) / "manifest.json")

    def describe(self, artifact_id: str) -> StoredArtifactDescription:
        directory = self._find_artifact_directory(artifact_id)
        manifest = load_manifest(directory / "manifest.json")
        return StoredArtifactDescription(
            reference=self._reference(manifest, directory),
            manifest=manifest,
            files=tuple(
                StoredArtifactFile(
                    relative_path=item.relative_path,
                    uri=safe_join(directory / "files", item.relative_path).as_uri(),
                    version_id=None,
                )
                for item in manifest.files
            ),
        )

    def list_artifact_ids(self) -> set[str]:
        return {
            path.parent.name
            for path in self.root.glob("*/*/*/manifest.json")
            if path.is_file()
        }

    def download(self, artifact_id: str, destination: Path) -> Path:
        source = self._find_artifact_directory(artifact_id)
        target = destination.resolve() / artifact_id
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        result = verify_package_directory(target)
        if not result.passed:
            shutil.rmtree(target, ignore_errors=True)
            raise ArtifactIntegrityError("; ".join(result.errors))
        return target

    def verify(self, artifact_id: str) -> ArtifactVerificationResult:
        return verify_package_directory(self._find_artifact_directory(artifact_id))

    def exists(self, artifact_id: str) -> bool:
        try:
            self._find_artifact_directory(artifact_id)
        except ArtifactNotFoundError:
            return False
        return True

    @staticmethod
    def _reference(manifest: ArtifactManifestV3, path: Path) -> ArtifactReference:
        return ArtifactReference(
            artifact_id=manifest.artifact_id,
            artifact_type=manifest.artifact_type,
            schema_version=manifest.schema_version,
            manifest_sha256=manifest.manifest_sha256,
            uri=path.as_uri(),
        )
