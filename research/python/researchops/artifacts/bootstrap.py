from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class S3BootstrapResult:
    bucket: str
    created: bool
    versioning_enabled: bool
    read_write_probe_passed: bool


def bootstrap_s3_bucket(client: Any, *, bucket: str, region: str = "us-east-1") -> S3BootstrapResult:
    created = False
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        kwargs = {"Bucket": bucket}
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        client.create_bucket(**kwargs)
        created = True
    client.put_bucket_versioning(
        Bucket=bucket,
        VersioningConfiguration={"Status": "Enabled"},
    )
    status = client.get_bucket_versioning(Bucket=bucket).get("Status")
    key = f"researchops/bootstrap/{uuid.uuid4().hex}.txt"
    payload = b"researchops-storage-probe\n"
    client.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="text/plain")
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    observed = body.read() if hasattr(body, "read") else bytes(body)
    client.delete_object(Bucket=bucket, Key=key)
    return S3BootstrapResult(
        bucket=bucket,
        created=created,
        versioning_enabled=status == "Enabled",
        read_write_probe_passed=observed == payload,
    )
