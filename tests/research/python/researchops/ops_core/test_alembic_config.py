from alembic.config import Config

from research.python.researchops.ops_core.db.alembic_config import (
    apply_resolved_database_url,
    resolve_database_url,
    set_explicit_database_url,
)


def _config(url: str = "postgresql+psycopg://ini@localhost/ini") -> Config:
    config = Config()
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_explicit_invocation_url_beats_operational_environment(monkeypatch):
    config = _config()
    monkeypatch.setenv(
        "RESEARCHOPS_DATABASE_URL",
        "postgresql+psycopg://primary@localhost/llm_xai_ops",
    )
    test_url = "postgresql+psycopg://test@localhost/llm_xai_ops_test"

    set_explicit_database_url(config, test_url)

    assert resolve_database_url(config) == test_url
    assert apply_resolved_database_url(config) == test_url
    assert config.get_main_option("sqlalchemy.url") == test_url


def test_environment_url_is_used_when_no_explicit_override(monkeypatch):
    config = _config()
    environment_url = "postgresql+psycopg://primary@localhost/llm_xai_ops"
    monkeypatch.setenv("RESEARCHOPS_DATABASE_URL", environment_url)

    assert resolve_database_url(config) == environment_url


def test_ini_url_is_final_fallback(monkeypatch):
    config = _config()
    monkeypatch.delenv("RESEARCHOPS_DATABASE_URL", raising=False)

    assert resolve_database_url(config) == "postgresql+psycopg://ini@localhost/ini"
