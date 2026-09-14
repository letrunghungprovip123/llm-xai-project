"""Load the declarative flow catalog and its deterministic lock."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from research.python.researchops.contracts.io import project_root

from .models import FlowCatalog

DEFAULT_CATALOG_PATH = Path("config/platform/flows.yaml")
DEFAULT_LOCK_PATH = Path("config/platform/generated/flow_catalog.lock.json")


def catalog_path(root: Path | None = None) -> Path:
    return (root or project_root()) / DEFAULT_CATALOG_PATH


def lock_path(root: Path | None = None) -> Path:
    return (root or project_root()) / DEFAULT_LOCK_PATH


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return payload


def load_flow_catalog(
    path: Path | None = None,
    *,
    root: Path | None = None,
) -> FlowCatalog:
    resolved = path or catalog_path(root)
    return FlowCatalog.model_validate(load_yaml_mapping(resolved))
