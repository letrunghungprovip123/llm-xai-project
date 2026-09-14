from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from .exceptions import ArtifactConflictError, ArtifactNotFoundError
from .hashing import canonical_json_bytes


class ReleasePointer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_name: str = "release_pointer_v1"
    release_id: str
    artifact_id: str
    manifest_sha256: str

    @field_validator("release_id")
    @classmethod
    def validate_release_id(cls, value: str) -> str:
        if re.fullmatch(r"^[a-z][a-z0-9_-]*[-_]v[0-9]+$", value) is None:
            raise ValueError("Invalid release_id")
        return value

    @field_validator("manifest_sha256")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        if re.fullmatch(r"^[0-9a-f]{64}$", value) is None:
            raise ValueError("Invalid manifest_sha256")
        return value


class ReleasePointerStore(Protocol):
    def put(self, pointer: ReleasePointer) -> None: ...
    def get(self, release_id: str) -> ReleasePointer: ...


class FilesystemReleasePointerStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, pointer: ReleasePointer) -> None:
        path = self.root / f"{pointer.release_id}.json"
        if path.exists():
            existing = ReleasePointer.model_validate_json(path.read_bytes())
            if existing != pointer:
                raise ArtifactConflictError(f"Release pointer is immutable: {pointer.release_id}")
            return
        path.write_bytes(canonical_json_bytes(pointer.model_dump(mode="json")))

    def get(self, release_id: str) -> ReleasePointer:
        path = self.root / f"{release_id}.json"
        if not path.is_file():
            raise ArtifactNotFoundError(f"Release pointer not found: {release_id}")
        return ReleasePointer.model_validate_json(path.read_bytes())


class S3ReleasePointerStore:
    def __init__(self, client: Any, *, bucket: str, key_prefix: str = "researchops") -> None:
        self.client = client
        self.bucket = bucket
        self.key_prefix = key_prefix.strip("/")

    def _key(self, release_id: str) -> str:
        prefix = f"{self.key_prefix}/" if self.key_prefix else ""
        return f"{prefix}release-pointers/{release_id}.json"

    def put(self, pointer: ReleasePointer) -> None:
        key = self._key(pointer.release_id)
        try:
            existing = self.get(pointer.release_id)
        except ArtifactNotFoundError:
            existing = None
        if existing is not None:
            if existing != pointer:
                raise ArtifactConflictError(f"Release pointer is immutable: {pointer.release_id}")
            return
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=canonical_json_bytes(pointer.model_dump(mode="json")),
            ContentType="application/json",
            Metadata={"manifest-sha256": pointer.manifest_sha256},
        )

    def get(self, release_id: str) -> ReleasePointer:
        key = self._key(release_id)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            from .stores.s3 import _is_not_found
            if _is_not_found(exc):
                raise ArtifactNotFoundError(f"Release pointer not found: {release_id}") from exc
            raise
        body = response["Body"]
        return ReleasePointer.model_validate_json(body.read() if hasattr(body, "read") else body)
