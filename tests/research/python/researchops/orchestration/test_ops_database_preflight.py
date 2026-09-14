from __future__ import annotations

from research.python.researchops.ops_core.settings import DatabaseSettings
from research.python.researchops.orchestration.ops_database_preflight import (
    check_ops_database,
)


class _Result:
    def scalar_one(self) -> int:
        return 1


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _statement):
        return _Result()


class _Engine:
    def __init__(self) -> None:
        self.disposed = False

    def connect(self):
        return _Connection()

    def dispose(self) -> None:
        self.disposed = True


def test_ops_database_preflight_redacts_password_and_disposes_engine():
    engine = _Engine()
    settings = DatabaseSettings(
        url=(
            "postgresql+psycopg://researchops:super-secret@"
            "researchops-postgres:5432/llm_xai_ops"
        )
    )

    report = check_ops_database(
        settings=settings,
        engine_factory=lambda _settings: engine,  # type: ignore[arg-type]
    )

    assert report["passed"] is True
    assert report["probe"] == "SELECT 1"
    assert "super-secret" not in report["database_url"]
    assert "***" in report["database_url"]
    assert engine.disposed is True
