from pathlib import Path

import pytest

from research.python.researchops.artifacts.exceptions import ArtifactConflictError
from research.python.researchops.artifacts.models import ArtifactManifestV3
from research.python.researchops.artifacts.stores.s3 import S3ArtifactStore

from .fake_s3 import FakeS3Client


def _store():
    client = FakeS3Client()
    client.create_bucket(Bucket="test")
    return client, S3ArtifactStore(client, bucket="test")


def test_s3_put_verify_download_round_trip(tmp_path: Path, sample_package):
    _, store = _store()
    reference = store.put_package(sample_package)
    assert reference.uri.startswith("s3://test/")
    assert store.verify(reference.artifact_id).passed
    description = store.describe(reference.artifact_id)
    assert description.reference == reference
    assert {item.relative_path for item in description.files} == {
        "README.txt", "datasets/data.csv"
    }
    assert store.list_artifact_ids() == {reference.artifact_id}
    destination = store.download(reference.artifact_id, tmp_path)
    assert (destination / "files/datasets/data.csv").read_text() == "a,b\n1,2\n"


def test_s3_identical_put_is_idempotent(sample_package):
    _, store = _store()
    assert store.put_package(sample_package) == store.put_package(sample_package)


def test_s3_conflicting_identity_rejected(sample_package):
    _, store = _store()
    store.put_package(sample_package)
    payload = sample_package.manifest.model_dump(mode="json")
    payload["metadata"] = {"different": True}
    changed = sample_package.model_copy(
        update={"manifest": ArtifactManifestV3.model_validate(payload)}
    )
    with pytest.raises(ArtifactConflictError):
        store.put_package(changed)
