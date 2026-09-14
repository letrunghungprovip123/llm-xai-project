import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from research.python.researchops.artifacts.stores.filesystem import (
    FilesystemArtifactStore,
)
from research.python.researchops.ops_core.db.alembic_config import (
    set_explicit_database_url,
)
from research.python.researchops.ops_core.repositories.sqlalchemy import (
    SqlAlchemyOpsRepository,
)
from research.python.researchops.ops_core.services.artifact_registration import (
    ArtifactRegistrationService,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("RESEARCHOPS_TEST_DATABASE_URL"),
    reason="Set RESEARCHOPS_TEST_DATABASE_URL for live PostgreSQL integration tests",
)


def _config(url: str) -> Config:
    config = Config("alembic.ini")
    set_explicit_database_url(config, url)
    return config


def test_live_postgresql_migration_and_artifact_registration(
    tmp_path: Path, sample_package
):
    url = os.environ["RESEARCHOPS_TEST_DATABASE_URL"]
    config = _config(url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert "artifacts" in tables
    assert "pipeline_runs" in tables
    assert "orchestration_bindings" in tables
    assert "stage_run_outputs" in tables

    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(sample_package)
    with Session(engine) as session, session.begin():
        result = ArtifactRegistrationService(
            SqlAlchemyOpsRepository(session), store
        ).register(sample_package.manifest.artifact_id, actor="integration-test")
        assert result.created
    with Session(engine) as session:
        repository = SqlAlchemyOpsRepository(session)
        assert repository.get_artifact(sample_package.manifest.artifact_id) is not None

    command.downgrade(config, "base")
