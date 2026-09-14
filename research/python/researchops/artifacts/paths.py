from __future__ import annotations

from pathlib import Path, PurePosixPath

from .exceptions import ArtifactValidationError


def normalize_relative_path(value: str) -> str:
    if not value or "\\" in value:
        raise ArtifactValidationError(
            "Artifact relative paths must be non-empty POSIX paths"
        )
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ArtifactValidationError(f"Unsafe artifact relative path: {value!r}")
    return path.as_posix()


def safe_join(root: Path, relative_path: str) -> Path:
    normalized = normalize_relative_path(relative_path)
    resolved_root = root.resolve()
    target = (resolved_root / Path(*PurePosixPath(normalized).parts)).resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise ArtifactValidationError(f"Path escapes artifact root: {relative_path!r}")
    return target
