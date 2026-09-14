from __future__ import annotations

from pathlib import Path

import sys
import types

import joblib
import pandas as pd
import pytest

from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.mlflow_tracking.contracts import load_tracking_contract
from research.python.researchops.mlflow_tracking.models import RunSnapshot
from research.python.researchops.mlflow_tracking.exceptions import MLflowIntegrityError
from research.python.researchops.mlflow_tracking.tracking import (
    _default_model_loader,
    _default_signature_builder,
    track_training_release,
)


class FakeGateway:
    def __init__(self):
        self.runs = {}
        self.params = {}
        self.metrics = {}
        self.artifacts = []
        self.models = []
        self.counter = 0

    def experiment_id(self, name):
        assert name == "credit-risk-modeling"
        return "1"

    def find_runs(self, experiment_id, tracking_key):
        return tuple(
            RunSnapshot(run_id, data["status"], dict(data["tags"]))
            for run_id, data in self.runs.items()
            if data["tags"].get("researchops.tracking_key") == tracking_key
        )

    def create_run(self, experiment_id, run_name, tags):
        self.counter += 1
        run_id = f"run-{self.counter}"
        self.runs[run_id] = {"status": "RUNNING", "tags": dict(tags), "name": run_name}
        return run_id

    def set_tags(self, run_id, tags): self.runs[run_id]["tags"].update({k: str(v) for k, v in tags.items()})
    def log_params(self, run_id, params): self.params.setdefault(run_id, {}).update(params)
    def log_metrics(self, run_id, metrics): self.metrics.setdefault(run_id, {}).update(metrics)
    def log_artifact(self, run_id, path, artifact_path): self.artifacts.append((run_id, Path(path).name, artifact_path))
    def log_sklearn_model(self, run_id, model, *, artifact_path, input_example, signature):
        uri = f"models:/m-{run_id}"
        self.models.append((run_id, model, tuple(input_example.columns), signature))
        return uri
    def resolve_logged_model_uri(self, run_id, artifact_path):
        return f"models:/m-{run_id}" if any(item[0] == run_id for item in self.models) else None
    def terminate(self, run_id, status="FINISHED"): self.runs[run_id]["status"] = status


def test_tracking_creates_parent_and_three_idempotent_children(tmp_path, training_release_package):
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(training_release_package)
    gateway = FakeGateway()
    loader = lambda path: path.name
    signature = lambda model, example: {"model": model, "columns": list(example.columns)}
    first = track_training_release(
        store=store,
        artifact_id=training_release_package.manifest.artifact_id,
        gateway=gateway,
        contract=load_tracking_contract(),
        model_loader=loader,
        signature_builder=signature,
    )
    second = track_training_release(
        store=store,
        artifact_id=training_release_package.manifest.artifact_id,
        gateway=gateway,
        contract=load_tracking_contract(),
        model_loader=loader,
        signature_builder=signature,
    )
    assert len(gateway.runs) == 4
    assert len(gateway.models) == 3
    assert first.parent_run_id == second.parent_run_id
    assert all(item.reused for item in second.models)
    assert first.selected_model.model_name == "hist_gradient_boosting"
    child = next(item for item in first.models if item.model_name == "logistic_regression")
    assert gateway.metrics[child.run_id]["validation_auroc"] == 0.75
    assert gateway.runs[child.run_id]["tags"]["mlflow.parentRunId"] == first.parent_run_id


class PredictingEstimator:
    def predict(self, frame):
        return [1 for _ in range(len(frame))]

    def predict_proba(self, frame):
        return [[0.25, 0.75] for _ in range(len(frame))]


def test_default_model_loader_unwraps_governed_joblib_bundle(tmp_path):
    path = tmp_path / "logistic_regression.joblib"
    estimator = PredictingEstimator()
    joblib.dump(
        {
            "artifact_schema_version": "model_artifact_v1",
            "artifact_type": "trained_model",
            "model_name": "logistic_regression",
            "model_version": "1",
            "dataset_branch": "model_ready",
            "feature_columns": ["feature_a", "feature_b"],
            "estimator": estimator,
        },
        path,
    )

    loaded = _default_model_loader(path)

    assert isinstance(loaded, PredictingEstimator)
    assert loaded.predict(pd.DataFrame({"feature_a": [1], "feature_b": [2]})) == [1]


def test_default_model_loader_rejects_bundle_without_estimator(tmp_path):
    path = tmp_path / "invalid.joblib"
    joblib.dump(
        {
            "model_name": "logistic_regression",
            "feature_columns": ["feature_a"],
        },
        path,
    )

    with pytest.raises(MLflowIntegrityError, match="missing keys.*estimator"):
        _default_model_loader(path)


def test_default_signature_builder_uses_predict_not_predict_proba(monkeypatch):
    calls = []
    estimator = PredictingEstimator()
    frame = pd.DataFrame({"feature_a": [1], "feature_b": [2]})

    def fake_infer_signature(inputs, outputs):
        calls.append((inputs, outputs))
        return {"outputs": outputs}

    fake_models = types.ModuleType("mlflow.models")
    fake_models.infer_signature = fake_infer_signature
    fake_mlflow = types.ModuleType("mlflow")
    fake_mlflow.models = fake_models
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)
    monkeypatch.setitem(sys.modules, "mlflow.models", fake_models)

    signature = _default_signature_builder(estimator, frame)

    assert calls[0][1] == [1]
    assert signature == {"outputs": [1]}


def test_real_gateway_uses_model_info_uri_and_resolves_logged_model_id():
    from types import SimpleNamespace

    from research.python.researchops.mlflow_tracking.tracking_gateway import (
        RealTrackingGateway,
    )

    class RunContext:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Sklearn:
        @staticmethod
        def log_model(**_kwargs):
            return SimpleNamespace(model_uri="models:/m-model-123", model_id="m-model-123")

    class Mlflow:
        sklearn = Sklearn()

        @staticmethod
        def start_run(run_id):
            assert run_id == "run-1"
            return RunContext()

        @staticmethod
        def search_logged_models(**kwargs):
            assert kwargs["experiment_ids"] == ["1"]
            assert kwargs["filter_string"] == "source_run_id='run-1'"
            assert kwargs["max_results"] == 50
            return [SimpleNamespace(name="model", model_id="m-model-123")]

    class Client:
        @staticmethod
        def get_run(run_id):
            assert run_id == "run-1"
            return SimpleNamespace(info=SimpleNamespace(experiment_id="1"))

    gateway = RealTrackingGateway.__new__(RealTrackingGateway)
    gateway.mlflow = Mlflow()
    gateway.client = Client()

    uri = gateway.log_sklearn_model(
        "run-1",
        object(),
        artifact_path="model",
        input_example=object(),
        signature=object(),
    )

    assert uri == "models:/m-model-123"
    assert gateway.resolve_logged_model_uri("run-1", "model") == uri
