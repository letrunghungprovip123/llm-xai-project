from __future__ import annotations

import io
from dataclasses import dataclass


class FakeS3Error(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


@dataclass
class _Object:
    body: bytes
    content_type: str
    metadata: dict[str, str]
    version_id: str


class FakeS3Client:
    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, _Object]] = {}
        self.versioning: dict[str, str] = {}
        self._version = 0

    def head_bucket(self, *, Bucket: str):
        if Bucket not in self.buckets:
            raise FakeS3Error("NoSuchBucket")
        return {}

    def create_bucket(self, *, Bucket: str, **kwargs):
        self.buckets.setdefault(Bucket, {})
        return {}

    def put_bucket_versioning(self, *, Bucket: str, VersioningConfiguration):
        self.versioning[Bucket] = VersioningConfiguration["Status"]
        return {}

    def get_bucket_versioning(self, *, Bucket: str):
        return {"Status": self.versioning.get(Bucket)}

    def put_object(self, *, Bucket: str, Key: str, Body, ContentType=None, Metadata=None):
        if Bucket not in self.buckets:
            raise FakeS3Error("NoSuchBucket")
        data = Body.read() if hasattr(Body, "read") else bytes(Body)
        self._version += 1
        version_id = str(self._version)
        self.buckets[Bucket][Key] = _Object(
            body=data,
            content_type=ContentType or "application/octet-stream",
            metadata={str(k).lower(): str(v) for k, v in (Metadata or {}).items()},
            version_id=version_id,
        )
        return {"VersionId": version_id}

    def get_object(self, *, Bucket: str, Key: str):
        try:
            item = self.buckets[Bucket][Key]
        except KeyError as exc:
            raise FakeS3Error("NoSuchKey") from exc
        return {
            "Body": io.BytesIO(item.body),
            "ContentLength": len(item.body),
            "ContentType": item.content_type,
            "Metadata": dict(item.metadata),
            "VersionId": item.version_id,
        }

    def head_object(self, *, Bucket: str, Key: str):
        response = self.get_object(Bucket=Bucket, Key=Key)
        response.pop("Body")
        return response

    def list_objects_v2(self, *, Bucket: str, Prefix: str, **kwargs):
        if Bucket not in self.buckets:
            raise FakeS3Error("NoSuchBucket")
        keys = sorted(key for key in self.buckets[Bucket] if key.startswith(Prefix))
        return {"Contents": [{"Key": key} for key in keys], "IsTruncated": False}

    def delete_object(self, *, Bucket: str, Key: str):
        self.buckets.get(Bucket, {}).pop(Key, None)
        return {}
