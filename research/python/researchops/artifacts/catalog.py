from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


@lru_cache(maxsize=1)
def artifact_types() -> frozenset[str]:
    path = project_root() / "config/platform/artifact_types_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(item["artifact_type"] for item in payload["artifact_types"])


@lru_cache(maxsize=1)
def active_stage_ids() -> frozenset[str]:
    from research.python.researchops.stage_registry.loader import load_stage_registry

    return frozenset(stage.id for stage in load_stage_registry().stages)
