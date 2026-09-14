from research.python.researchops.artifacts.bootstrap import bootstrap_s3_bucket

from .fake_s3 import FakeS3Client


def test_bootstrap_is_idempotent_and_enables_versioning():
    client = FakeS3Client()
    first = bootstrap_s3_bucket(client, bucket="artifacts")
    second = bootstrap_s3_bucket(client, bucket="artifacts")
    assert first.created
    assert not second.created
    assert first.versioning_enabled
    assert first.read_write_probe_passed
