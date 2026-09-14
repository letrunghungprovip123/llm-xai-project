from __future__ import annotations

import pytest
from pydantic import ValidationError

from research.python.researchops.artifacts.models import ArtifactFile, ArtifactManifestV3


def test_manifest_has_deterministic_hash(sample_package):
    manifest = sample_package.manifest
    assert manifest.manifest_sha256 == manifest.manifest_sha256
    assert len(manifest.manifest_sha256) == 64


def test_artifact_id_type_must_match(sample_package):
    payload = sample_package.manifest.model_dump(mode="json")
    payload["artifact_id"] = "artifact_trained_model_01J00000000000000000000000"
    with pytest.raises(ValidationError, match="type prefix"):
        ArtifactManifestV3.model_validate(payload)


def test_unknown_artifact_type_rejected(sample_package):
    payload = sample_package.manifest.model_dump(mode="json")
    payload["artifact_type"] = "not_registered"
    payload["artifact_id"] = "artifact_not_registered_01J00000000000000000000000"
    with pytest.raises(ValidationError, match="Unknown artifact_type"):
        ArtifactManifestV3.model_validate(payload)


def test_unsafe_relative_paths_rejected():
    with pytest.raises(ValidationError):
        ArtifactFile(
            relative_path="../secret.txt",
            sha256="0" * 64,
            size_bytes=1,
            media_type="text/plain",
        )
