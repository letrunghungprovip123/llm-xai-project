from pathlib import Path

import pytest

from research.python.researchops.artifacts.exceptions import ArtifactConflictError
from research.python.researchops.artifacts.models import ArtifactManifestV3
from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore


def test_put_verify_download_round_trip(tmp_path: Path, sample_package):
    store = FilesystemArtifactStore(tmp_path / "store")
    reference = store.put_package(sample_package)
    assert reference.artifact_id == sample_package.manifest.artifact_id
    assert store.exists(reference.artifact_id)
    assert store.verify(reference.artifact_id).passed
    description = store.describe(reference.artifact_id)
    assert description.reference == reference
    assert store.list_artifact_ids() == {reference.artifact_id}

    destination = store.download(reference.artifact_id, tmp_path / "download")
    assert (destination / "manifest.json").is_file()
    assert (destination / "files/datasets/data.csv").read_text() == "a,b\n1,2\n"


def test_identical_put_is_idempotent(tmp_path: Path, sample_package):
    store = FilesystemArtifactStore(tmp_path / "store")
    first = store.put_package(sample_package)
    second = store.put_package(sample_package)
    assert first == second


def test_different_content_with_same_id_conflicts(tmp_path: Path, sample_package):
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(sample_package)
    payload = sample_package.manifest.model_dump(mode="json")
    payload["metadata"] = {"different": True}
    altered = sample_package.model_copy(
        update={"manifest": ArtifactManifestV3.model_validate(payload)}
    )
    with pytest.raises(ArtifactConflictError):
        store.put_package(altered)


def test_tampering_is_detected(tmp_path: Path, sample_package):
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(sample_package)
    directory = store._find_artifact_directory(sample_package.manifest.artifact_id)
    (directory / "files/datasets/data.csv").write_text("tampered", encoding="utf-8")
    result = store.verify(sample_package.manifest.artifact_id)
    assert not result.passed
    assert result.errors
