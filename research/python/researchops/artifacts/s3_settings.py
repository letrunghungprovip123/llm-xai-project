from __future__ import annotations

from dataclasses import dataclass
import os

from .exceptions import ArtifactValidationError


@dataclass(frozen=True)
class S3StoreSettings:
    bucket: str
    region: str = "us-east-1"
    endpoint_url: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    use_ssl: bool = True
    key_prefix: str = "researchops"

    @classmethod
    def from_environment(cls, prefix: str = "RESEARCHOPS_S3_") -> "S3StoreSettings":
        bucket = os.getenv(f"{prefix}BUCKET")
        if not bucket:
            raise ArtifactValidationError(f"Missing required environment variable {prefix}BUCKET")
        endpoint = os.getenv(f"{prefix}ENDPOINT") or None
        return cls(
            bucket=bucket,
            region=os.getenv(f"{prefix}REGION", "us-east-1"),
            endpoint_url=endpoint,
            access_key_id=os.getenv(f"{prefix}ACCESS_KEY") or None,
            secret_access_key=os.getenv(f"{prefix}SECRET_KEY") or None,
            use_ssl=os.getenv(f"{prefix}USE_SSL", "true").lower() in {"1", "true", "yes"},
            key_prefix=os.getenv(f"{prefix}KEY_PREFIX", "researchops").strip("/"),
        )

    def create_client(self):
        import boto3

        kwargs = {
            "service_name": "s3",
            "region_name": self.region,
            "endpoint_url": self.endpoint_url,
            "use_ssl": self.use_ssl,
        }
        if self.access_key_id:
            kwargs["aws_access_key_id"] = self.access_key_id
        if self.secret_access_key:
            kwargs["aws_secret_access_key"] = self.secret_access_key
        return boto3.client(**kwargs)
