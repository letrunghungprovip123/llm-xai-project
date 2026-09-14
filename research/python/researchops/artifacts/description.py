from __future__ import annotations

from pydantic import ConfigDict, BaseModel

from .models import ArtifactManifestV3, ArtifactReference


class StoredArtifactFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    relative_path: str
    uri: str
    version_id: str | None = None


class StoredArtifactDescription(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reference: ArtifactReference
    manifest: ArtifactManifestV3
    files: tuple[StoredArtifactFile, ...]
