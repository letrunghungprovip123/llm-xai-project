from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class PrefectConfigurationError(ValueError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise PrefectConfigurationError(
            f"Missing required environment variable {name}"
        )
    return value


def _redact_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.password is None:
        return value
    username = parts.username or ""
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit(
        (
            parts.scheme,
            f"{username}:***@{host}{port}",
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


@dataclass(frozen=True)
class PrefectSettings:
    api_url: str
    internal_api_url: str
    database_connection_url: str
    redis_messaging_url: str
    docket_url: str
    work_pool_name: str
    expected_version: str = "3.7.8"

    @classmethod
    def from_environment(cls) -> "PrefectSettings":
        api_url = _required("PREFECT_API_URL").rstrip("/")
        internal_api_url = os.getenv(
            "PREFECT_INTERNAL_API_URL", api_url
        ).rstrip("/")
        database_url = _required("PREFECT_API_DATABASE_CONNECTION_URL")
        messaging_url = _required("PREFECT_REDIS_MESSAGING_URL")
        docket_url = _required("PREFECT_SERVER_DOCKET_URL")
        pool_name = _required("PREFECT_WORK_POOL_NAME")
        expected_version = os.getenv("PREFECT_VERSION", "3.7.8")

        for name, value in (
            ("PREFECT_API_URL", api_url),
            ("PREFECT_INTERNAL_API_URL", internal_api_url),
        ):
            if not value.startswith(("http://", "https://")) or not value.endswith(
                "/api"
            ):
                raise PrefectConfigurationError(
                    f"{name} must be an HTTP(S) URL ending with /api"
                )
        if not database_url.startswith("postgresql+asyncpg://"):
            raise PrefectConfigurationError(
                "Prefect database URL must use postgresql+asyncpg"
            )
        if not messaging_url.startswith(("redis://", "rediss://")):
            raise PrefectConfigurationError("Prefect messaging must use Redis")
        if not docket_url.startswith(("redis://", "rediss://")):
            raise PrefectConfigurationError("Prefect Docket must use Redis")
        if messaging_url == docket_url:
            raise PrefectConfigurationError(
                "Messaging and Docket must use separate Redis databases"
            )
        if expected_version != "3.7.8":
            raise PrefectConfigurationError("Phase 6A pins Prefect 3.7.8")
        return cls(
            api_url=api_url,
            internal_api_url=internal_api_url,
            database_connection_url=database_url,
            redis_messaging_url=messaging_url,
            docket_url=docket_url,
            work_pool_name=pool_name,
            expected_version=expected_version,
        )

    def redacted_dict(self) -> dict[str, str]:
        return {
            "api_url": self.api_url,
            "internal_api_url": self.internal_api_url,
            "database_connection_url": _redact_url(
                self.database_connection_url
            ),
            "redis_messaging_url": _redact_url(self.redis_messaging_url),
            "docket_url": _redact_url(self.docket_url),
            "work_pool_name": self.work_pool_name,
            "expected_version": self.expected_version,
        }


def write_local_environment(path: Path, *, overwrite: bool = False) -> Path:
    if path.exists() and not overwrite:
        raise PrefectConfigurationError(
            f"Refusing to overwrite existing file: {path}"
        )
    db_password = secrets.token_hex(32)
    redis_password = secrets.token_hex(32)
    content = f"""# Generated local Prefect ResearchOps configuration
PREFECT_VERSION=3.7.8
PREFECT_API_URL=http://127.0.0.1:4200/api
PREFECT_INTERNAL_API_URL=http://researchops-prefect-server:4200/api
PREFECT_POSTGRES_DB=prefect
PREFECT_POSTGRES_USER=prefect_app
PREFECT_POSTGRES_PASSWORD={db_password}
PREFECT_API_DATABASE_CONNECTION_URL=postgresql+asyncpg://prefect_app:{db_password}@researchops-postgres:5432/prefect
PREFECT_REDIS_PASSWORD={redis_password}
PREFECT_REDIS_MESSAGING_URL=redis://:{redis_password}@researchops-prefect-redis:6379/0
PREFECT_SERVER_DOCKET_URL=redis://:{redis_password}@researchops-prefect-redis:6379/1
PREFECT_WORK_POOL_NAME=researchops-local-process
PREFECT_WORKER_LIMIT=4
"""
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path
