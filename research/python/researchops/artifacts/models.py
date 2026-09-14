from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .catalog import active_stage_ids, artifact_types
from .hashing import sha256_canonical_json
from .exceptions import ArtifactValidationError
from .paths import normalize_relative_path

_ARTIFACT_ID = re.compile(r"^artifact_[a-z][a-z0-9_]*_[0-9A-HJKMNP-TV-Z]{26}$")
_STAGE_RUN_ID = re.compile(r"^stage_run_[0-9A-HJKMNP-TV-Z]{26}$")
_ENV_ID = re.compile(r"^env_[0-9A-HJKMNP-TV-Z]{26}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactProducer(StrictModel):
    stage_id: str
    stage_version: int = Field(ge=1)
    stage_run_id: str | None = None
    registry_sha256: str

    @field_validator("stage_id")
    @classmethod
    def validate_stage_id(cls, value: str) -> str:
        if value not in active_stage_ids():
            raise ValueError(f"Unknown stage_id: {value}")
        return value

    @field_validator("stage_run_id")
    @classmethod
    def validate_stage_run_id(cls, value: str | None) -> str | None:
        if value is not None and not _STAGE_RUN_ID.fullmatch(value):
            raise ValueError("Invalid stage_run_id")
        return value

    @field_validator("registry_sha256")
    @classmethod
    def validate_registry_sha(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("registry_sha256 must be a lower-case SHA-256")
        return value


class ArtifactSource(StrictModel):
    source_commit: str
    environment_snapshot_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("source_commit")
    @classmethod
    def validate_commit(cls, value: str) -> str:
        if not _COMMIT.fullmatch(value):
            raise ValueError("source_commit must be a hexadecimal Git commit")
        return value

    @field_validator("environment_snapshot_id")
    @classmethod
    def validate_environment_id(cls, value: str | None) -> str | None:
        if value is not None and not _ENV_ID.fullmatch(value):
            raise ValueError("Invalid environment_snapshot_id")
        return value

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class ArtifactParent(StrictModel):
    artifact_id: str
    manifest_sha256: str
    relationship: str = "derived_from"

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        if not _ARTIFACT_ID.fullmatch(value):
            raise ValueError("Invalid parent artifact_id")
        return value

    @field_validator("manifest_sha256")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("manifest_sha256 must be a lower-case SHA-256")
        return value

    @field_validator("relationship")
    @classmethod
    def validate_relationship(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("relationship must not be blank")
        return value


class ArtifactFile(StrictModel):
    relative_path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    media_type: str
    row_count: int | None = Field(default=None, ge=0)
    column_count: int | None = Field(default=None, ge=0)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        try:
            return normalize_relative_path(value)
        except ArtifactValidationError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("sha256")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("sha256 must be a lower-case SHA-256")
        return value

    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, value: str) -> str:
        if "/" not in value:
            raise ValueError("media_type must be a valid MIME-like value")
        return value


class ArtifactManifestV3(StrictModel):
    schema_name: Literal["artifact_manifest_v3"] = "artifact_manifest_v3"
    artifact_id: str
    artifact_type: str
    schema_version: str
    status: Literal[
        "DRAFT", "UPLOADED", "VERIFIED", "CERTIFIED", "REJECTED", "SUPERSEDED"
    ] = "VERIFIED"
    producer: ArtifactProducer
    source: ArtifactSource
    parents: tuple[ArtifactParent, ...] = ()
    files: tuple[ArtifactFile, ...]
    limitations: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        if not _ARTIFACT_ID.fullmatch(value):
            raise ValueError("Invalid artifact_id")
        return value

    @field_validator("artifact_type")
    @classmethod
    def validate_artifact_type(cls, value: str) -> str:
        if value not in artifact_types():
            raise ValueError(f"Unknown artifact_type: {value}")
        return value

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if not re.fullmatch(r"^[A-Za-z][A-Za-z0-9_.-]*$", value):
            raise ValueError("Invalid schema_version")
        return value

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("limitations must not contain blank values")
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def validate_identity_and_paths(self) -> "ArtifactManifestV3":
        prefix = f"artifact_{self.artifact_type}_"
        if not self.artifact_id.startswith(prefix):
            raise ValueError("artifact_id type prefix must match artifact_type")
        paths = [item.relative_path for item in self.files]
        if not paths:
            raise ValueError("Artifact manifests must contain at least one file")
        if len(paths) != len(set(paths)):
            raise ValueError("Duplicate artifact relative paths")
        parent_ids = [parent.artifact_id for parent in self.parents]
        if self.artifact_id in parent_ids:
            raise ValueError("An artifact cannot be its own parent")
        if len(parent_ids) != len(set(parent_ids)):
            raise ValueError("Duplicate parent artifact IDs")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=False)

    @property
    def manifest_sha256(self) -> str:
        return sha256_canonical_json(self.canonical_payload())


class ArtifactPackage(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)
    manifest: ArtifactManifestV3
    source_files: dict[str, Path]

    @model_validator(mode="after")
    def validate_source_files(self) -> "ArtifactPackage":
        expected = {item.relative_path for item in self.manifest.files}
        observed = set(self.source_files)
        if expected != observed:
            raise ValueError(
                f"source_files must exactly match manifest files: "
                f"missing={sorted(expected - observed)} extra={sorted(observed - expected)}"
            )
        if any(not path.is_file() for path in self.source_files.values()):
            raise ValueError("All artifact source files must exist")
        return self


class ArtifactReference(StrictModel):
    artifact_id: str
    artifact_type: str
    schema_version: str
    manifest_sha256: str
    uri: str


class ArtifactVerificationResult(StrictModel):
    artifact_id: str
    manifest_sha256: str
    passed: bool
    checked_files: int
    errors: tuple[str, ...] = ()
