import pytest

from research.python.researchops.ops_core.settings import DatabaseSettings


def test_settings_redacts_password(monkeypatch):
    monkeypatch.setenv(
        "RESEARCHOPS_DATABASE_URL",
        "postgresql+psycopg://user:secret@localhost:5433/llm_xai_ops",
    )
    settings = DatabaseSettings.from_environment()
    assert settings is not None
    assert "secret" not in settings.redacted_url
    assert "***" in settings.redacted_url


def test_non_postgresql_database_is_rejected(monkeypatch):
    monkeypatch.setenv("RESEARCHOPS_DATABASE_URL", "sqlite:///test.db")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        DatabaseSettings.from_environment()
