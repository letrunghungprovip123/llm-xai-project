from pathlib import Path

import pytest

from research.python.researchops.artifacts.exceptions import ArtifactConflictError
from research.python.researchops.artifacts.release_pointer import (
    FilesystemReleasePointerStore,
    ReleasePointer,
    S3ReleasePointerStore,
)

from .fake_s3 import FakeS3Client


def _pointer():
    return ReleasePointer(
        release_id="visualization-data-v2",
        artifact_id="artifact_visualization_data_release_01J00000000000000000000000",
        manifest_sha256="a" * 64,
    )


def test_filesystem_pointer_is_immutable(tmp_path: Path):
    store = FilesystemReleasePointerStore(tmp_path)
    store.put(_pointer())
    store.put(_pointer())
    changed = _pointer().model_copy(update={"manifest_sha256": "b" * 64})
    with pytest.raises(ArtifactConflictError):
        store.put(changed)


def test_s3_pointer_round_trip():
    client = FakeS3Client()
    client.create_bucket(Bucket="test")
    store = S3ReleasePointerStore(client, bucket="test")
    store.put(_pointer())
    assert store.get("visualization-data-v2") == _pointer()
