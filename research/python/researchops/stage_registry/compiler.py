"""Deterministic Stage Registry compiler and lock verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from research.python.researchops.contracts.io import (
    canonical_json_sha256,
    project_root,
)

from .loader import DEFAULT_REGISTRY_PATH, load_stage_registry, lock_path, registry_path
from .models import StageDefinition, StageRegistry


def _binding_payload(binding: Any) -> dict[str, Any]:
    return binding.model_dump(mode="json", exclude_none=True)


def _stage_payload(stage: StageDefinition) -> dict[str, Any]:
    payload = stage.model_dump(mode="json", exclude_none=True)
    payload["tags"] = sorted(payload.get("tags", []))
    payload["secrets"] = sorted(payload.get("secrets", []))
    payload["notes"] = list(payload.get("notes", []))
    payload["inputs"] = [_binding_payload(item) for item in stage.inputs]
    payload["outputs"] = [_binding_payload(item) for item in stage.outputs]
    return payload


def normalized_registry_payload(registry: StageRegistry) -> dict[str, Any]:
    return {
        "schema_version": registry.schema_version,
        "status": registry.status,
        "stages": [
            _stage_payload(stage)
            for stage in sorted(registry.stages, key=lambda item: item.id)
        ],
    }


def compile_payload(root: Path | None = None) -> dict[str, Any]:
    resolved_root = root or project_root()
    source_path = registry_path(resolved_root)
    source_bytes = source_path.read_bytes()
    registry = load_stage_registry(source_path)
    normalized = normalized_registry_payload(registry)
    return {
        "schema_version": "stage_registry_lock_v1",
        "source_path": str(DEFAULT_REGISTRY_PATH),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "registry_sha256": canonical_json_sha256(normalized),
        "stage_count": len(registry.stages),
        "registry": normalized,
    }


def write_lock(
    root: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    resolved_root = root or project_root()
    target = output_path or lock_path(resolved_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(compile_payload(resolved_root), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return target


def lock_matches(root: Path | None = None) -> bool:
    resolved_root = root or project_root()
    target = lock_path(resolved_root)
    if not target.is_file():
        return False
    committed = json.loads(target.read_text(encoding="utf-8"))
    return committed == compile_payload(resolved_root)
