from __future__ import annotations

from research.python.researchops.contracts.io import project_root
from research.python.researchops.stage_registry.command_renderer import (
    resolve_command,
)
from research.python.researchops.stage_registry.compiler import (
    compile_payload,
    lock_matches,
)
from research.python.researchops.stage_registry.graph import topological_order
from research.python.researchops.stage_registry.loader import load_stage_registry
from research.python.researchops.stage_registry.validator import (
    dispatcher_stage_names,
    validate_stage_registry,
)


def test_stage_registry_is_valid() -> None:
    report = validate_stage_registry()
    assert report.passed, report.to_dict()
    assert report.stage_count == 42
    assert report.dispatcher_stage_count == 25


def test_compiled_lock_is_current_and_deterministic() -> None:
    assert lock_matches()
    first = compile_payload()
    second = compile_payload()
    assert first == second
    assert first["stage_count"] == 42
    assert len(first["registry_sha256"]) == 64


def test_every_typescript_dispatcher_stage_is_registered_once() -> None:
    root = project_root()
    registry = load_stage_registry(root=root)
    expected = dispatcher_stage_names(root)
    observed = [
        stage.legacy_dispatcher_stage
        for stage in registry.stages
        if stage.legacy_dispatcher_stage is not None
    ]
    assert set(observed) == expected
    assert len(observed) == len(set(observed))


def test_stage_graph_is_acyclic_and_reaches_dashboard_certification() -> None:
    registry = load_stage_registry()
    ordered = topological_order(registry)
    assert len(ordered) == len(registry.stages)
    assert ordered.index("data.audit") < ordered.index("ml.train")
    assert ordered.index("ml.train") < ordered.index("xai.generate")
    assert ordered.index("release.visualization_data") < ordered.index(
        "dashboard.i18n_certification"
    )


def test_provider_stages_are_explicitly_approved_and_secret_named() -> None:
    registry = load_stage_registry()
    provider_stages = [
        stage for stage in registry.stages if stage.behavior.provider_required
    ]
    assert {stage.id for stage in provider_stages} == {
        "llm.generate",
        "claims.extract",
    }
    for stage in provider_stages:
        assert stage.behavior.approval_policy == "PROVIDER"
        assert stage.secrets


def test_commands_resolve_against_current_repository() -> None:
    root = project_root()
    registry = load_stage_registry(root=root)
    failures = []
    for stage in registry.stages:
        resolution = resolve_command(stage, root)
        if not resolution.structurally_valid:
            failures.append((stage.id, resolution.details))
    assert failures == []


def test_stage_registry_does_not_store_secret_values() -> None:
    registry = load_stage_registry()
    allowed_names = {
        "DEEPSEEK_API_KEY",
        "VLLM_API_KEY",
        "RESEARCHOPS_ARTIFACT_PROFILE",
        "RESEARCHOPS_DATABASE_URL",
        "RESEARCHOPS_S3_BUCKET",
        "RESEARCHOPS_S3_ENDPOINT",
        "RESEARCHOPS_S3_ACCESS_KEY",
        "RESEARCHOPS_S3_SECRET_KEY",
        "RESEARCHOPS_S3_REGION",
        "RESEARCHOPS_S3_USE_SSL",
        "RESEARCHOPS_S3_KEY_PREFIX",
        "MLFLOW_VERSION",
        "MLFLOW_TRACKING_URI",
        "MLFLOW_INTERNAL_TRACKING_URI",
        "MLFLOW_BACKEND_STORE_URI",
        "MLFLOW_ARTIFACTS_DESTINATION",
        "MLFLOW_S3_ENDPOINT_URL",
        "MLFLOW_S3_BUCKET",
        "MLFLOW_S3_ACCESS_KEY",
        "MLFLOW_S3_SECRET_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "MLFLOW_ALLOWED_HOSTS",
    }
    observed = {secret for stage in registry.stages for secret in stage.secrets}
    assert observed <= allowed_names
