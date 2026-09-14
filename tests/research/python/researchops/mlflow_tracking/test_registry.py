from __future__ import annotations

from research.python.researchops.mlflow_tracking.contracts import load_registry_policy
from research.python.researchops.mlflow_tracking.models import RunSnapshot, TrackedModelRun, TrainingTrackingResult
from research.python.researchops.mlflow_tracking.registry import register_training_models
from research.python.researchops.mlflow_tracking.registry_gateway import ModelVersionSnapshot


class FakeRegistryGateway:
    def __init__(self):
        self.models = set()
        self.versions = []
        self.aliases = {}
        self.runs = {}
        self.counter = 0

    def ensure_registered_model(self, name, description): self.models.add(name)
    def list_versions(self, name): return tuple(item for item in self.versions if item.name == name)
    def create_version(self, name, *, source, run_id, description, tags):
        self.counter += 1
        item = ModelVersionSnapshot(name, str(self.counter), run_id, source, "READY", dict(tags))
        self.versions.append(item)
        return item
    def set_version_tags(self, name, version, tags):
        for index, item in enumerate(self.versions):
            if item.name == name and item.version == version:
                self.versions[index] = ModelVersionSnapshot(item.name, item.version, item.run_id, item.source, item.status, {**item.tags, **{k:str(v) for k,v in tags.items()}})
    def set_alias(self, name, alias, version): self.aliases[(name, alias)] = str(version)
    def alias_version(self, name, alias): return self.aliases.get((name, alias))
    def get_version(self, name, version): return next((item for item in self.versions if item.name == name and item.version == str(version)), None)
    def get_run(self, run_id): return self.runs.get(run_id)
    def set_run_tags(self, run_id, tags):
        current = self.runs.get(run_id, RunSnapshot(run_id, "FINISHED", {}))
        self.runs[run_id] = RunSnapshot(run_id, current.status, {**current.tags, **{k:str(v) for k,v in tags.items()}})


def tracking_result(package):
    names = ("logistic_regression", "random_forest", "hist_gradient_boosting")
    models = tuple(
        TrackedModelRun(
            model_name=name,
            run_id=f"run-{index}",
            model_uri=f"models:/m-run-{index}",
            tracking_key=f"{index:064x}",
            selected_as_best=name == "hist_gradient_boosting",
            reused=False,
        )
        for index, name in enumerate(names, start=1)
    )
    return TrainingTrackingResult(
        source_artifact_id=package.manifest.artifact_id,
        source_manifest_sha256=package.manifest.manifest_sha256,
        experiment_id="1",
        parent_run_id="parent-run",
        parent_reused=False,
        models=models,
    )


def test_registry_registration_is_idempotent_and_assigns_only_candidate(training_release_package):
    gateway = FakeRegistryGateway()
    tracking = tracking_result(training_release_package)
    first = register_training_models(
        tracking=tracking,
        source_manifest=training_release_package.manifest,
        gateway=gateway,
        policy=load_registry_policy(),
    )
    second = register_training_models(
        tracking=tracking,
        source_manifest=training_release_package.manifest,
        gateway=gateway,
        policy=load_registry_policy(),
    )
    assert len(gateway.versions) == 3
    assert first.candidate.version == second.candidate.version == "3"
    assert gateway.alias_version("credit-risk-predictor", "candidate") == "3"
    assert gateway.alias_version("credit-risk-predictor", "champion") is None
    assert all(item.reused for item in second.versions)
    assert gateway.runs["run-3"].tags["researchops.integration_state"] == "CANDIDATE_EVALUATED"


def test_real_gateway_create_version_uses_synchronous_create_response():
    from types import SimpleNamespace

    from research.python.researchops.mlflow_tracking.registry_gateway import RealRegistryGateway

    class Client:
        def __init__(self):
            self.kwargs = None

        def create_model_version(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                name=kwargs["name"],
                version="1",
                run_id=kwargs["run_id"],
                source=kwargs["source"],
                status="READY",
                tags=kwargs["tags"],
            )

        def get_model_version(self, *_args, **_kwargs):
            raise AssertionError("create_version must not issue a follow-up GET")

    gateway = RealRegistryGateway.__new__(RealRegistryGateway)
    gateway.client = Client()

    snapshot = gateway.create_version(
        "credit-risk-predictor",
        source="models:/m-run-1",
        run_id="run-1",
        description="test",
        tags={"researchops.tracking_key": "abc"},
    )

    assert snapshot.version == "1"
    assert snapshot.status == "READY"
    assert gateway.client.kwargs["await_creation_for"] == 0
    assert gateway.client.kwargs["model_id"] == "m-run-1"


def test_real_gateway_missing_alias_is_normal_absent_state():
    from research.python.researchops.mlflow_tracking.registry_gateway import RealRegistryGateway

    class FakeMlflowException(Exception):
        def __init__(self, message, error_code):
            super().__init__(message)
            self.error_code = error_code

    class Client:
        def get_model_version_by_alias(self, name, alias):
            raise FakeMlflowException(
                f"Registered model alias {alias} not found.",
                "INVALID_PARAMETER_VALUE",
            )

    gateway = RealRegistryGateway.__new__(RealRegistryGateway)
    gateway.client = Client()
    gateway._mlflow_exception = FakeMlflowException

    assert gateway.alias_version("credit-risk-predictor", "candidate") is None


def test_real_gateway_does_not_hide_unrelated_invalid_parameter_errors():
    import pytest

    from research.python.researchops.mlflow_tracking.registry_gateway import RealRegistryGateway

    class FakeMlflowException(Exception):
        def __init__(self, message, error_code):
            super().__init__(message)
            self.error_code = error_code

    class Client:
        def get_model_version_by_alias(self, name, alias):
            raise FakeMlflowException(
                "Alias name contains unsupported characters.",
                "INVALID_PARAMETER_VALUE",
            )

    gateway = RealRegistryGateway.__new__(RealRegistryGateway)
    gateway.client = Client()
    gateway._mlflow_exception = FakeMlflowException

    with pytest.raises(FakeMlflowException):
        gateway.alias_version("credit-risk-predictor", "candidate")


def test_registry_migrates_legacy_run_uri_version_without_mutating_history(
    training_release_package,
):
    gateway = FakeRegistryGateway()
    tracking = tracking_result(training_release_package)

    for index, tracked in enumerate(tracking.models, start=1):
        gateway.versions.append(
            ModelVersionSnapshot(
                "credit-risk-predictor",
                str(index),
                tracked.run_id,
                f"runs:/{tracked.run_id}/model",
                "READY",
                {
                    "researchops.project": "llm-xai",
                    "researchops.tracking_key": tracked.tracking_key,
                },
            )
        )
    gateway.counter = 3
    gateway.aliases[("credit-risk-predictor", "candidate")] = "3"

    result = register_training_models(
        tracking=tracking,
        source_manifest=training_release_package.manifest,
        gateway=gateway,
        policy=load_registry_policy(),
    )

    assert [item.version for item in result.versions] == ["4", "5", "6"]
    assert result.candidate.version == "6"
    assert gateway.alias_version("credit-risk-predictor", "candidate") == "6"
    old = gateway.versions[:3]
    assert all(
        item.tags["researchops.registry_record_status"] == "SUPERSEDED_SOURCE_URI"
        for item in old
    )
    assert all(item.tags["researchops.candidate_status"] == "SUPERSEDED" for item in old)


def test_registry_rejects_new_run_artifact_uri(training_release_package):
    import pytest

    from research.python.researchops.mlflow_tracking.exceptions import MLflowIntegrityError

    gateway = FakeRegistryGateway()
    tracking = tracking_result(training_release_package)
    first = tracking.models[0]
    invalid = TrainingTrackingResult(
        source_artifact_id=tracking.source_artifact_id,
        source_manifest_sha256=tracking.source_manifest_sha256,
        experiment_id=tracking.experiment_id,
        parent_run_id=tracking.parent_run_id,
        parent_reused=False,
        models=(
            TrackedModelRun(
                model_name=first.model_name,
                run_id=first.run_id,
                model_uri=f"runs:/{first.run_id}/model",
                tracking_key=first.tracking_key,
                selected_as_best=first.selected_as_best,
                reused=False,
            ),
            *tracking.models[1:],
        ),
    )

    with pytest.raises(MLflowIntegrityError, match="models:/m-"):
        register_training_models(
            tracking=invalid,
            source_manifest=training_release_package.manifest,
            gateway=gateway,
            policy=load_registry_policy(),
        )
