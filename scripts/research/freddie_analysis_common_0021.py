#!/usr/bin/env python3
"""Shared fail-closed helpers for Freddie deterministic analysis stages."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            rows.append(value)
    if not rows:
        raise ValueError(f"Required JSONL artifact is empty: {path}")
    return rows


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def artifact_path(repo_root: Path, record: dict[str, Any]) -> Path:
    raw = str(record["path"])
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else repo_root / candidate


def verify_artifact(repo_root: Path, record: dict[str, Any], label: str) -> Path:
    path = artifact_path(repo_root, record).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    observed = sha256(path)
    expected = str(record["sha256"])
    if observed != expected:
        raise ValueError(
            f"{label} SHA-256 mismatch: expected={expected}, observed={observed}, path={path}"
        )
    if "byte_count" in record and path.stat().st_size != int(record["byte_count"]):
        raise ValueError(f"{label} byte_count mismatch: {path}")
    return path


def verify_lock_artifacts(
    repo_root: Path,
    lock: dict[str, Any],
    keys: Iterable[str],
) -> dict[str, Path]:
    artifacts = lock.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("Analysis input lock has no artifacts mapping.")
    resolved: dict[str, Path] = {}
    for key in keys:
        record = artifacts.get(key)
        if not isinstance(record, dict):
            raise ValueError(f"Analysis input lock missing artifact: {key}")
        resolved[key] = verify_artifact(repo_root, record, key)
    return resolved


def file_record(repo_root: Path, path: Path, row_count: int | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        display = str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        display = str(resolved)
    value: dict[str, Any] = {
        "path": display,
        "sha256": sha256(resolved),
        "byte_count": resolved.stat().st_size,
    }
    if row_count is not None:
        value["row_count"] = int(row_count)
    return value


def prepare_staging(output_dir: Path) -> Path:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp_", dir=output_dir.parent))


def promote_directory(staging: Path, output_dir: Path) -> str:
    """Atomically promote a validated directory, never overwrite different bytes."""
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"Output exists and is not a directory: {output_dir}")
        existing = directory_digest(output_dir)
        candidate = directory_digest(staging)
        if existing == candidate:
            shutil.rmtree(staging)
            return "ALREADY_CERTIFIED"
        raise ValueError(
            f"Refusing to overwrite different certified output: {output_dir}; "
            f"existing_digest={existing}, candidate_digest={candidate}"
        )
    os.replace(staging, output_dir)
    return "PASS"


def directory_digest(root: Path) -> str:
    items: list[tuple[str, str]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        items.append((str(path.relative_to(root)), sha256(path)))
    encoded = json.dumps(items, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()
