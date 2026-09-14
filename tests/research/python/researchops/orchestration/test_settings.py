from __future__ import annotations

from pathlib import Path

import pytest

from research.python.researchops.orchestration.settings import (
    PrefectConfigurationError,
    PrefectSettings,
    write_local_environment,
)


ENV = {
    "PREFECT_API_URL": "http://127.0.0.1:4200/api",
    "PREFECT_INTERNAL_API_URL": "http://researchops-prefect-server:4200/api",
    "PREFECT_API_DATABASE_CONNECTION_URL": (
        "postgresql+asyncpg://prefect_app:secret@researchops-postgres:5432/prefect"
    ),
    "PREFECT_REDIS_MESSAGING_URL": (
        "redis://:redis-secret@researchops-prefect-redis:6379/0"
    ),
    "PREFECT_SERVER_DOCKET_URL": (
        "redis://:redis-secret@researchops-prefect-redis:6379/1"
    ),
    "PREFECT_WORK_POOL_NAME": "researchops-local-process",
    "PREFECT_VERSION": "3.7.8",
}


def _set_env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


def test_settings_validate_and_redact_secrets(monkeypatch):
    _set_env(monkeypatch)
    settings = PrefectSettings.from_environment()
    redacted = settings.redacted_dict()

    assert settings.expected_version == "3.7.8"
    assert "secret" not in redacted["database_connection_url"]
    assert "redis-secret" not in redacted["redis_messaging_url"]
    assert "***" in redacted["database_connection_url"]


def test_settings_reject_same_messaging_and_docket_database(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setenv(
        "PREFECT_SERVER_DOCKET_URL",
        ENV["PREFECT_REDIS_MESSAGING_URL"],
    )

    with pytest.raises(PrefectConfigurationError, match="separate Redis"):
        PrefectSettings.from_environment()


def test_write_local_environment_is_private_and_not_overwritten(tmp_path: Path):
    path = tmp_path / ".env.researchops-prefect.local"
    write_local_environment(path)

    content = path.read_text(encoding="utf-8")
    assert "PREFECT_VERSION=3.7.8" in content
    assert "PREFECT_WORK_POOL_NAME=researchops-local-process" in content
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(PrefectConfigurationError, match="Refusing to overwrite"):
        write_local_environment(path)
