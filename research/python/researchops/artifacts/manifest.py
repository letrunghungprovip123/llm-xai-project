from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .exceptions import ArtifactValidationError
from .hashing import canonical_json_bytes
from .models import ArtifactManifestV3


def load_manifest(path: Path) -> ArtifactManifestV3:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ArtifactManifestV3.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ArtifactValidationError(f"Invalid artifact manifest {path}: {exc}") from exc


def write_manifest(path: Path, manifest: ArtifactManifestV3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(manifest.canonical_payload()))
