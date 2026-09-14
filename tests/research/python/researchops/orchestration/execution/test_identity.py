from research.python.researchops.orchestration.flow_catalog.loader import load_flow_catalog
from research.python.researchops.orchestration.identity import (
    ArtifactIdentity,
    flow_orchestration_key,
    stage_orchestration_key,
)
from research.python.researchops.stage_registry.loader import load_stage_registry


def test_flow_and_stage_keys_are_canonical_and_sensitive():
    flow = load_flow_catalog().by_id()["register_verified_training_release"]
    stage = load_stage_registry().by_id()["ops.mlflow_register"]
    artifact = ArtifactIdentity("artifact_trained_model_01J00000000000000000000000", "trained_model", "a" * 64)
    first = flow_orchestration_key(
        flow=flow,
        flow_catalog_sha256="b" * 64,
        stage_registry_sha256="c" * 64,
        input_artifacts={"trained_models": artifact},
        parameters={"z": 1, "a": True},
        source_commit="d" * 40,
        dependency_lock_sha256="e" * 64,
    )
    reordered = flow_orchestration_key(
        flow=flow,
        flow_catalog_sha256="b" * 64,
        stage_registry_sha256="c" * 64,
        input_artifacts={"trained_models": artifact},
        parameters={"a": True, "z": 1},
        source_commit="d" * 40,
        dependency_lock_sha256="e" * 64,
    )
    assert first == reordered
    assert len(first) == 64
    second = stage_orchestration_key(
        flow_key=first,
        node_id="mlflow_register",
        stage=stage,
        input_artifacts={"trained_models": artifact},
        parameters={},
    )
    changed = stage_orchestration_key(
        flow_key=first,
        node_id="mlflow_register",
        stage=stage,
        input_artifacts={"trained_models": artifact},
        parameters={"allow_existing_outputs": True},
    )
    assert second != changed
