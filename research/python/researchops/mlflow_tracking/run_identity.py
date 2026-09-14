from __future__ import annotations

from research.python.researchops.artifacts.hashing import sha256_canonical_json
from research.python.researchops.artifacts.models import ArtifactManifestV3


def tracking_key(manifest: ArtifactManifestV3, *, model_name: str) -> str:
    return sha256_canonical_json({
        "tracking_key_version": "tracking_key_v1",
        "stage_id": manifest.producer.stage_id,
        "stage_version": manifest.producer.stage_version,
        "source_artifact_id": manifest.artifact_id,
        "source_manifest_sha256": manifest.manifest_sha256,
        "source_commit": manifest.source.source_commit,
        "model_name": model_name,
    })
