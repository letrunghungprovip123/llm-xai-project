"""Repository-root discovery without requiring legacy data directories to exist."""

from __future__ import annotations

from pathlib import Path


def find_repository_root(start_path: Path) -> Path:
    resolved = start_path.resolve()
    current = resolved.parent if resolved.is_file() else resolved
    for candidate in (current, *current.parents):
        if (candidate / "package.json").is_file() and (candidate / "research").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate repository root from: {start_path}")
