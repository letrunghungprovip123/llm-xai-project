from pathlib import Path

from research.python.researchops.artifacts.cache import VerifiedArtifactCache
from research.python.researchops.artifacts.release_pointer import (
    FilesystemReleasePointerStore,
    ReleasePointer,
)
from research.python.researchops.artifacts.release_resolver import CertifiedReleaseResolver
from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore


def test_release_resolver_downloads_verifies_and_caches(tmp_path: Path, sample_package):
    store = FilesystemArtifactStore(tmp_path / "store")
    reference = store.put_package(sample_package)
    pointers = FilesystemReleasePointerStore(tmp_path / "pointers")
    pointers.put(ReleasePointer(
        release_id="visualization-data-v2",
        artifact_id=reference.artifact_id,
        manifest_sha256=reference.manifest_sha256,
    ))
    checks: list[Path] = []
    resolver = CertifiedReleaseResolver(
        store,
        pointers,
        VerifiedArtifactCache(tmp_path / "cache"),
        acceptance_check=checks.append,
    )
    first = resolver.resolve("visualization-data-v2")
    second = resolver.resolve("visualization-data-v2")
    assert first == second
    assert (first / "manifest.json").is_file()
    assert len(checks) == 2
