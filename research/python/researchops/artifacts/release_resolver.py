from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from .cache import VerifiedArtifactCache
from .exceptions import ArtifactIntegrityError
from .release_pointer import ReleasePointerStore
from .stores.base import ArtifactStore


class CertifiedReleaseResolver:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        pointer_store: ReleasePointerStore,
        cache: VerifiedArtifactCache,
        *,
        acceptance_check: Callable[[Path], None] | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.pointer_store = pointer_store
        self.cache = cache
        self.acceptance_check = acceptance_check

    def resolve(self, release_id: str) -> Path:
        pointer = self.pointer_store.get(release_id)
        cached = self.cache.get_verified(release_id, pointer.manifest_sha256)
        if cached is not None:
            if self.acceptance_check:
                self.acceptance_check(cached)
            return cached
        with tempfile.TemporaryDirectory(prefix="researchops-release-") as temp:
            downloaded = self.artifact_store.download(pointer.artifact_id, Path(temp))
            result = self.artifact_store.verify(pointer.artifact_id)
            if not result.passed or result.manifest_sha256 != pointer.manifest_sha256:
                raise ArtifactIntegrityError("Release pointer does not match verified artifact")
            installed = self.cache.install(
                release_id, pointer.manifest_sha256, downloaded
            )
        if self.acceptance_check:
            self.acceptance_check(installed)
        return installed
