from __future__ import annotations

import json

from .catalog import project_root
from .exceptions import ArtifactValidationError
from .s3_settings import S3StoreSettings
from .stores.filesystem import FilesystemArtifactStore
from .stores.s3 import S3ArtifactStore


def load_store(profile: str = "development-filesystem"):
    path = project_root() / "config/platform/artifact_store_profiles_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        config = payload["profiles"][profile]
    except KeyError as exc:
        raise ArtifactValidationError(f"Unknown artifact store profile: {profile}") from exc
    backend = config["backend"]
    if backend == "filesystem":
        root = project_root() / config["root"]
        return FilesystemArtifactStore(root, read_only=bool(config.get("read_only", False)))
    if backend == "s3":
        prefix = str(config.get("environment_prefix", "RESEARCHOPS_S3_"))
        settings = S3StoreSettings.from_environment(prefix)
        return S3ArtifactStore(
            settings.create_client(),
            bucket=settings.bucket,
            key_prefix=settings.key_prefix,
        )
    raise ArtifactValidationError(f"Unsupported artifact backend: {backend}")
