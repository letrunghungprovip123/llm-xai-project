"""Load and validate dataset/experiment/canonical-bundle profiles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import CanonicalDatasetBundle, DatasetProfile, ExperimentProfile


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_json(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def load_dataset_profile(path: Path) -> DatasetProfile:
    return DatasetProfile.from_dict(load_json_object(path))


def load_experiment_profile(path: Path) -> ExperimentProfile:
    return ExperimentProfile.from_dict(load_json_object(path))


def load_canonical_bundle(path: Path) -> CanonicalDatasetBundle:
    return CanonicalDatasetBundle.from_dict(load_json_object(path))
