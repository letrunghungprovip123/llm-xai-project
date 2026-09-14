"""Stable dataset-aware scientific identities for new multi-dataset artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _stable_digest(payload: dict[str, Any], length: int = 20) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def canonical_case_id(dataset_id: str, entity_type: str, source_entity_id: Any) -> str:
    """Return a collision-resistant case ID without exposing raw ID structure.

    The raw source ID remains available separately in provenance/IR metadata.  The
    canonical identifier deliberately includes dataset identity so Dataset B can
    reuse the same numeric source ID without colliding with Home Credit.
    """

    dataset_id = str(dataset_id).strip()
    entity_type = str(entity_type).strip()
    if not dataset_id or not entity_type:
        raise ValueError("dataset_id and entity_type must be non-empty")
    if source_entity_id is None or str(source_entity_id).strip() == "":
        raise ValueError("source_entity_id must be non-empty")
    digest = _stable_digest(
        {
            "dataset_id": dataset_id,
            "entity_type": entity_type,
            "source_entity_id": str(source_entity_id),
        }
    )
    return f"case_{dataset_id}_{entity_type}_{digest}"


def dataset_scoped_id(kind: str, dataset_id: str, experiment_id: str, local_id: str) -> str:
    """Create a stable namespace for new IR/evidence/generation identities."""

    parts = [str(value).strip() for value in (kind, dataset_id, experiment_id, local_id)]
    if any(not value for value in parts):
        raise ValueError("kind, dataset_id, experiment_id, and local_id must be non-empty")
    digest = _stable_digest(
        {
            "kind": parts[0],
            "dataset_id": parts[1],
            "experiment_id": parts[2],
            "local_id": parts[3],
        }
    )
    return f"{parts[0]}_{parts[1]}_{parts[2]}_{digest}"
