"""Load Stage Registry YAML and supporting platform catalogs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from research.python.researchops.contracts.io import load_json, project_root

from .models import StageRegistry


DEFAULT_REGISTRY_PATH = Path("config/platform/stages.yaml")
DEFAULT_LOCK_PATH = Path("config/platform/generated/stage_registry.lock.json")


def registry_path(root: Path | None = None) -> Path:
    return (root or project_root()) / DEFAULT_REGISTRY_PATH


def lock_path(root: Path | None = None) -> Path:
    return (root or project_root()) / DEFAULT_LOCK_PATH


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping in {path}.")
    return payload


def load_stage_registry(
    path: Path | None = None,
    *,
    root: Path | None = None,
) -> StageRegistry:
    resolved = path or registry_path(root)
    return StageRegistry.model_validate(load_yaml_mapping(resolved))


def load_artifact_catalog(root: Path | None = None) -> dict[str, Any]:
    resolved_root = root or project_root()
    return load_json(resolved_root / "config/platform/artifact_types_v1.json")


def load_gate_catalog(root: Path | None = None) -> dict[str, Any]:
    resolved_root = root or project_root()
    return load_json(resolved_root / "config/platform/gate_catalog_v1.json")
