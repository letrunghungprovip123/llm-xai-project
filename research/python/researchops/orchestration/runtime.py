from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from research.python.researchops.artifacts.profiles import load_store
from research.python.researchops.artifacts.stores.base import ArtifactStore
from research.python.researchops.contracts.io import project_root
from research.python.researchops.ops_core.db import (
    create_engine_from_settings,
    create_session_factory,
)
from research.python.researchops.ops_core.settings import DatabaseSettings


@dataclass(frozen=True)
class OrchestrationRuntime:
    root: Path
    execution_root: Path
    artifact_store: ArtifactStore
    session_factory: sessionmaker[Session]


def load_orchestration_runtime() -> OrchestrationRuntime:
    root = project_root().resolve()
    profile = os.getenv("RESEARCHOPS_ARTIFACT_PROFILE", "development-minio")
    settings = DatabaseSettings.from_environment()
    assert settings is not None
    engine = create_engine_from_settings(settings)
    return OrchestrationRuntime(
        root=root,
        execution_root=Path(
            os.getenv("RESEARCHOPS_EXECUTION_ROOT", str(root / ".researchops/runs"))
        ).resolve(),
        artifact_store=load_store(profile),
        session_factory=create_session_factory(engine),
    )
