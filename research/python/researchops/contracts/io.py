"""Deterministic IO helpers for ResearchOps governance contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def project_root() -> Path:
    """Return the repository root without relying on the process CWD."""

    return Path(__file__).resolve().parents[4]


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object and fail when the root value is not an object."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return payload


def canonical_json_bytes(payload: object) -> bytes:
    """Serialize JSON deterministically for hashing and release evidence."""

    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return text.encode("utf-8")


def canonical_json_sha256(payload: object) -> str:
    """Return the SHA-256 of canonical JSON bytes."""

    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
