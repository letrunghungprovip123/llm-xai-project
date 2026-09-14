from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from research.python.researchops.artifacts.profiles import load_store
from research.python.researchops.artifacts.stores.base import ArtifactStore
from research.python.researchops.ops_core.db import create_engine_from_settings, create_session_factory
from research.python.researchops.ops_core.settings import DatabaseSettings

from .gateways import MLflowReadGateway, PrefectControlGateway, PrefectReadGateway, RealMLflowReadGateway, RealPrefectControlGateway


@dataclass(frozen=True)
class ControlPlaneComposition:
    session_factory: sessionmaker[Session]
    artifact_store: ArtifactStore
    prefect_gateway: PrefectReadGateway | None
    mlflow_gateway: MLflowReadGateway | None
    artifact_profile: str
    prefect_control_gateway: PrefectControlGateway | None = None


def build_default_composition() -> ControlPlaneComposition:
    database = DatabaseSettings.from_environment()
    assert database is not None
    engine = create_engine_from_settings(database)
    profile = os.getenv("RESEARCHOPS_ARTIFACT_PROFILE", "development-minio")
    prefect = RealPrefectControlGateway() if os.getenv("PREFECT_API_URL") else None
    tracking_uri = os.getenv("MLFLOW_INTERNAL_TRACKING_URI") or os.getenv("MLFLOW_TRACKING_URI")
    mlflow = RealMLflowReadGateway(tracking_uri) if tracking_uri else None
    return ControlPlaneComposition(
        session_factory=create_session_factory(engine),
        artifact_store=load_store(profile),
        prefect_gateway=prefect,
        prefect_control_gateway=prefect,
        mlflow_gateway=mlflow,
        artifact_profile=profile,
    )
