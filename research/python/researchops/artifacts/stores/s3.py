from __future__ import annotations

import io
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from ..description import StoredArtifactDescription, StoredArtifactFile
from ..exceptions import (
    ArtifactConflictError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactValidationError,
)
from ..hashing import canonical_json_bytes, sha256_canonical_json, sha256_file
from ..models import ArtifactManifestV3, ArtifactPackage, ArtifactReference, ArtifactVerificationResult
from ..paths import safe_join


class S3ArtifactStore:
    """S3-compatible immutable artifact store; compatible with MinIO."""

    def __init__(self, client: Any, *, bucket: str, key_prefix: str = "researchops") -> None:
        self.client = client
        self.bucket = bucket
        self.key_prefix = key_prefix.strip("/")

    def _artifact_prefix(self, manifest: ArtifactManifestV3) -> str:
        return "/".join(
            part for part in (
                self.key_prefix,
                "artifacts",
                manifest.artifact_type,
                manifest.schema_version,
                manifest.artifact_id,
            ) if part
        )

    def _manifest_key(self, manifest: ArtifactManifestV3) -> str:
        return f"{self._artifact_prefix(manifest)}/manifest.json"

    def _file_key(self, manifest: ArtifactManifestV3, relative_path: str) -> str:
        return f"{self._artifact_prefix(manifest)}/files/{relative_path}"

    def _find_manifest_key(self, artifact_id: str) -> str:
        base = "/".join(part for part in (self.key_prefix, "artifacts") if part) + "/"
        token: str | None = None
        matches: list[str] = []
        while True:
            kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": base}
            if token:
                kwargs["ContinuationToken"] = token
            response = self.client.list_objects_v2(**kwargs)
            for item in response.get("Contents", []):
                key = str(item["Key"])
                if key.endswith(f"/{artifact_id}/manifest.json"):
                    matches.append(key)
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
        if not matches:
            raise ArtifactNotFoundError(f"Artifact not found: {artifact_id}")
        if len(matches) != 1:
            raise ArtifactValidationError(f"Artifact ID is ambiguous: {artifact_id}")
        return matches[0]

    def _get_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                raise ArtifactNotFoundError(f"Object not found: s3://{self.bucket}/{key}") from exc
            raise
        body = response["Body"]
        return body.read() if hasattr(body, "read") else bytes(body)

    def _load_manifest_key(self, key: str) -> ArtifactManifestV3:
        return ArtifactManifestV3.model_validate_json(self._get_bytes(key))

    def put_package(self, package: ArtifactPackage) -> ArtifactReference:
        manifest = package.manifest
        manifest_key = self._manifest_key(manifest)
        try:
            existing = self._load_manifest_key(manifest_key)
        except ArtifactNotFoundError:
            existing = None
        if existing is not None:
            if existing.manifest_sha256 != manifest.manifest_sha256:
                raise ArtifactConflictError(
                    f"Immutable artifact ID already exists with different content: {manifest.artifact_id}"
                )
            result = self.verify(manifest.artifact_id)
            if not result.passed:
                raise ArtifactIntegrityError("Existing artifact is corrupt")
            return self._reference(existing, manifest_key)

        # Data objects are uploaded first. The manifest is the commit marker.
        for item in manifest.files:
            source = package.source_files[item.relative_path]
            key = self._file_key(manifest, item.relative_path)
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=source.read_bytes(),
                ContentType=item.media_type,
                Metadata={"sha256": item.sha256, "artifact-id": manifest.artifact_id},
            )
            head = self.client.head_object(Bucket=self.bucket, Key=key)
            if int(head["ContentLength"]) != item.size_bytes:
                raise ArtifactIntegrityError(f"Uploaded size mismatch for {item.relative_path}")
            metadata = {str(k).lower(): str(v) for k, v in head.get("Metadata", {}).items()}
            if metadata.get("sha256") != item.sha256:
                raise ArtifactIntegrityError(f"Uploaded checksum metadata mismatch for {item.relative_path}")

        manifest_bytes = canonical_json_bytes(manifest.canonical_payload())
        self.client.put_object(
            Bucket=self.bucket,
            Key=manifest_key,
            Body=manifest_bytes,
            ContentType="application/json",
            Metadata={"sha256": manifest.manifest_sha256, "artifact-id": manifest.artifact_id},
        )
        result = self.verify(manifest.artifact_id)
        if not result.passed:
            raise ArtifactIntegrityError("; ".join(result.errors))
        return self._reference(manifest, manifest_key)

    def get_manifest(self, artifact_id: str) -> ArtifactManifestV3:
        return self._load_manifest_key(self._find_manifest_key(artifact_id))

    def describe(self, artifact_id: str) -> StoredArtifactDescription:
        manifest_key = self._find_manifest_key(artifact_id)
        manifest = self._load_manifest_key(manifest_key)
        stored_files = []
        for item in manifest.files:
            key = self._file_key(manifest, item.relative_path)
            head = self.client.head_object(Bucket=self.bucket, Key=key)
            stored_files.append(StoredArtifactFile(
                relative_path=item.relative_path,
                uri=f"s3://{self.bucket}/{key}",
                version_id=head.get("VersionId"),
            ))
        return StoredArtifactDescription(
            reference=self._reference(manifest, manifest_key),
            manifest=manifest,
            files=tuple(stored_files),
        )

    def list_artifact_ids(self) -> set[str]:
        base = "/".join(part for part in (self.key_prefix, "artifacts") if part) + "/"
        artifact_ids: set[str] = set()
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": base}
            if token:
                kwargs["ContinuationToken"] = token
            response = self.client.list_objects_v2(**kwargs)
            artifact_ids.update(
                str(item["Key"]).split("/")[-2]
                for item in response.get("Contents", [])
                if str(item["Key"]).endswith("/manifest.json")
            )
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
        return artifact_ids

    def download(self, artifact_id: str, destination: Path) -> Path:
        manifest_key = self._find_manifest_key(artifact_id)
        manifest = self._load_manifest_key(manifest_key)
        target = destination.resolve() / artifact_id
        if target.exists():
            shutil.rmtree(target)
        files_root = target / "files"
        for item in manifest.files:
            path = safe_join(files_root, item.relative_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self._get_bytes(self._file_key(manifest, item.relative_path)))
        (target / "manifest.json").write_bytes(canonical_json_bytes(manifest.canonical_payload()))
        result = _verify_downloaded(target, manifest)
        if not result.passed:
            shutil.rmtree(target, ignore_errors=True)
            raise ArtifactIntegrityError("; ".join(result.errors))
        return target

    def verify(self, artifact_id: str) -> ArtifactVerificationResult:
        manifest_key = self._find_manifest_key(artifact_id)
        manifest = self._load_manifest_key(manifest_key)
        errors: list[str] = []
        for item in manifest.files:
            key = self._file_key(manifest, item.relative_path)
            try:
                response = self.client.get_object(Bucket=self.bucket, Key=key)
            except Exception as exc:
                if _is_not_found(exc):
                    errors.append(f"Missing file: {item.relative_path}")
                    continue
                raise
            body = response["Body"]
            data = body.read() if hasattr(body, "read") else bytes(body)
            import hashlib
            observed = hashlib.sha256(data).hexdigest()
            if len(data) != item.size_bytes:
                errors.append(f"Size mismatch for {item.relative_path}")
            elif observed != item.sha256:
                errors.append(f"SHA-256 mismatch for {item.relative_path}")
        return ArtifactVerificationResult(
            artifact_id=manifest.artifact_id,
            manifest_sha256=manifest.manifest_sha256,
            passed=not errors,
            checked_files=len(manifest.files),
            errors=tuple(errors),
        )

    def exists(self, artifact_id: str) -> bool:
        try:
            self._find_manifest_key(artifact_id)
        except ArtifactNotFoundError:
            return False
        return True

    def _reference(self, manifest: ArtifactManifestV3, manifest_key: str) -> ArtifactReference:
        return ArtifactReference(
            artifact_id=manifest.artifact_id,
            artifact_type=manifest.artifact_type,
            schema_version=manifest.schema_version,
            manifest_sha256=manifest.manifest_sha256,
            uri=f"s3://{self.bucket}/{manifest_key}",
        )


def _is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = str(response.get("Error", {}).get("Code", ""))
        return code in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}
    return isinstance(exc, (KeyError, FileNotFoundError))


def _verify_downloaded(path: Path, manifest: ArtifactManifestV3) -> ArtifactVerificationResult:
    errors: list[str] = []
    for item in manifest.files:
        file_path = safe_join(path / "files", item.relative_path)
        if not file_path.is_file():
            errors.append(f"Missing file: {item.relative_path}")
        elif file_path.stat().st_size != item.size_bytes:
            errors.append(f"Size mismatch for {item.relative_path}")
        elif sha256_file(file_path) != item.sha256:
            errors.append(f"SHA-256 mismatch for {item.relative_path}")
    return ArtifactVerificationResult(
        artifact_id=manifest.artifact_id,
        manifest_sha256=manifest.manifest_sha256,
        passed=not errors,
        checked_files=len(manifest.files),
        errors=tuple(errors),
    )
