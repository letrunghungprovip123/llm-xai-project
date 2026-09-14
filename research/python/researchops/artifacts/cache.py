from __future__ import annotations

import shutil
from pathlib import Path

from .exceptions import ArtifactIntegrityError
from .verifier import verify_package_directory


class VerifiedArtifactCache:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, release_id: str, manifest_sha256: str) -> Path:
        return self.root / release_id / manifest_sha256

    def get_verified(self, release_id: str, manifest_sha256: str) -> Path | None:
        path = self.path_for(release_id, manifest_sha256)
        if not path.is_dir():
            return None
        result = verify_package_directory(path)
        if result.passed and result.manifest_sha256 == manifest_sha256:
            return path
        shutil.rmtree(path, ignore_errors=True)
        return None

    def install(self, release_id: str, manifest_sha256: str, package_path: Path) -> Path:
        result = verify_package_directory(package_path)
        if not result.passed or result.manifest_sha256 != manifest_sha256:
            raise ArtifactIntegrityError("Cannot cache an unverified artifact package")
        target = self.path_for(release_id, manifest_sha256)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(package_path, target)
        return target
