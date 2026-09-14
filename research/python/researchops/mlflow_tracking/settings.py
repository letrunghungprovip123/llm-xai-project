from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .exceptions import MLflowConfigurationError


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MLflowConfigurationError(f"Missing required environment variable {name}")
    return value


def _redact_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.password is None:
        return value
    username = parts.username or ""
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit((parts.scheme, f"{username}:***@{host}{port}", parts.path, parts.query, parts.fragment))


@dataclass(frozen=True)
class MLflowSettings:
    tracking_uri: str
    internal_tracking_uri: str
    backend_store_uri: str
    artifacts_destination: str
    s3_endpoint_url: str
    s3_bucket: str
    allowed_hosts: str
    expected_version: str = "3.14.0"

    @classmethod
    def from_environment(cls) -> "MLflowSettings":
        tracking_uri = _required("MLFLOW_TRACKING_URI").rstrip("/")
        internal_uri = os.getenv("MLFLOW_INTERNAL_TRACKING_URI", tracking_uri).rstrip("/")
        backend = _required("MLFLOW_BACKEND_STORE_URI")
        destination = _required("MLFLOW_ARTIFACTS_DESTINATION")
        endpoint = _required("MLFLOW_S3_ENDPOINT_URL").rstrip("/")
        bucket = _required("MLFLOW_S3_BUCKET")
        allowed = _required("MLFLOW_ALLOWED_HOSTS")
        expected = os.getenv("MLFLOW_VERSION", "3.14.0")
        if not tracking_uri.startswith(("http://", "https://")):
            raise MLflowConfigurationError("MLFLOW_TRACKING_URI must be HTTP(S)")
        if not backend.startswith("postgresql+"):
            raise MLflowConfigurationError("MLflow backend store must use PostgreSQL")
        if destination != f"s3://{bucket}/mlartifacts":
            raise MLflowConfigurationError(
                "MLFLOW_ARTIFACTS_DESTINATION must be the dedicated bucket's /mlartifacts prefix"
            )
        if not allowed.strip():
            raise MLflowConfigurationError("MLFLOW_ALLOWED_HOSTS must not be blank")
        return cls(
            tracking_uri=tracking_uri,
            internal_tracking_uri=internal_uri,
            backend_store_uri=backend,
            artifacts_destination=destination,
            s3_endpoint_url=endpoint,
            s3_bucket=bucket,
            allowed_hosts=allowed,
            expected_version=expected,
        )

    def redacted_dict(self) -> dict[str, str]:
        return {
            "tracking_uri": self.tracking_uri,
            "internal_tracking_uri": self.internal_tracking_uri,
            "backend_store_uri": _redact_url(self.backend_store_uri),
            "artifacts_destination": self.artifacts_destination,
            "s3_endpoint_url": self.s3_endpoint_url,
            "s3_bucket": self.s3_bucket,
            "allowed_hosts": self.allowed_hosts,
            "expected_version": self.expected_version,
        }


def write_local_environment(path: Path, *, overwrite: bool = False) -> Path:
    if path.exists() and not overwrite:
        raise MLflowConfigurationError(f"Refusing to overwrite existing file: {path}")
    db_password = secrets.token_hex(32)
    s3_secret = secrets.token_urlsafe(36).replace("=", "")
    content = f"""# Generated local MLflow ResearchOps configuration\nMLFLOW_VERSION=3.14.0\nMLFLOW_TRACKING_URI=http://127.0.0.1:5000\nMLFLOW_INTERNAL_TRACKING_URI=http://researchops-mlflow:5000\nMLFLOW_POSTGRES_DB=mlflow\nMLFLOW_POSTGRES_USER=mlflow_app\nMLFLOW_POSTGRES_PASSWORD={db_password}\nMLFLOW_BACKEND_STORE_URI=postgresql+psycopg://mlflow_app:{db_password}@researchops-postgres:5432/mlflow\nMLFLOW_S3_BUCKET=llm-xai-mlflow\nMLFLOW_S3_ACCESS_KEY=mlflow-app\nMLFLOW_S3_SECRET_KEY={s3_secret}\nMLFLOW_S3_ENDPOINT_URL=http://researchops-minio:9000\nMLFLOW_ARTIFACTS_DESTINATION=s3://llm-xai-mlflow/mlartifacts\nAWS_DEFAULT_REGION=us-east-1\nMLFLOW_ALLOWED_HOSTS=localhost:*,127.0.0.1:*,researchops-mlflow:*\n"""
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path
