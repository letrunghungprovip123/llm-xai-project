from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from research.python.researchops.artifacts.ids import new_ulid
from research.python.researchops.contracts.io import project_root
from research.python.researchops.ops_core.db.models import EnvironmentSnapshot


@dataclass(frozen=True)
class CapturedEnvironment:
    record: EnvironmentSnapshot
    source_commit: str
    dependency_lock_sha256: str


def _run_text(args: list[str], *, cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _sha256_files(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    observed = False
    for path in sorted((item for item in paths if item.is_file()), key=str):
        observed = True
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    if not observed:
        digest.update(b"NO_LOCK_FILES")
    return digest.hexdigest()


def dependency_lock_sha256(root: Path | None = None) -> str:
    resolved = (root or project_root()).resolve()
    candidates = [
        resolved / "research/python/requirements-researchops.txt",
        resolved / "research/python/requirements.txt",
        resolved / "package-lock.json",
        resolved / "pyproject.toml",
    ]
    return _sha256_files(candidates)


def capture_environment(root: Path | None = None) -> CapturedEnvironment:
    resolved = (root or project_root()).resolve()
    commit = _run_text(["git", "rev-parse", "HEAD"], cwd=resolved) or "0" * 40
    dirty_output = _run_text(["git", "status", "--porcelain"], cwd=resolved)
    node_version = _run_text(["node", "--version"], cwd=resolved)
    lock_sha = dependency_lock_sha256(resolved)
    details = {
        "python_executable": sys.executable,
        "python_implementation": platform.python_implementation(),
        "hostname": platform.node(),
        "containerized": Path("/.dockerenv").exists(),
        "cwd": str(resolved),
        "prefect_version": os.getenv("PREFECT_VERSION"),
    }
    record = EnvironmentSnapshot(
        id=f"env_{new_ulid()}",
        python_version=platform.python_version(),
        node_version=node_version,
        operating_system=f"{platform.system()} {platform.release()}",
        architecture=platform.machine(),
        dependency_lock_sha256=lock_sha,
        container_image_digest=os.getenv("RESEARCHOPS_CONTAINER_IMAGE_DIGEST"),
        git_commit=commit,
        git_dirty=bool(dirty_output),
        details=details,
    )
    return CapturedEnvironment(
        record=record,
        source_commit=commit,
        dependency_lock_sha256=lock_sha,
    )
