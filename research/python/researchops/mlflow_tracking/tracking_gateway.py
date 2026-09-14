from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .exceptions import MLflowIntegrityError
from .models import RunSnapshot
from .model_uri import require_canonical_logged_model_uri


class TrackingGateway(Protocol):
    def experiment_id(self, name: str) -> str: ...
    def find_runs(self, experiment_id: str, tracking_key: str) -> tuple[RunSnapshot, ...]: ...
    def create_run(self, experiment_id: str, run_name: str, tags: dict[str, str]) -> str: ...
    def set_tags(self, run_id: str, tags: dict[str, str]) -> None: ...
    def log_params(self, run_id: str, params: dict[str, Any]) -> None: ...
    def log_metrics(self, run_id: str, metrics: dict[str, float]) -> None: ...
    def log_artifact(self, run_id: str, path: Path, artifact_path: str) -> None: ...
    def log_sklearn_model(
        self,
        run_id: str,
        model: Any,
        *,
        artifact_path: str,
        input_example: Any,
        signature: Any,
    ) -> str: ...
    def resolve_logged_model_uri(self, run_id: str, artifact_path: str) -> str | None: ...
    def terminate(self, run_id: str, status: str = "FINISHED") -> None: ...


class RealTrackingGateway:
    def __init__(self, tracking_uri: str) -> None:
        try:
            import mlflow
            from mlflow.tracking import MlflowClient
        except ImportError as exc:
            raise RuntimeError("MLflow is not installed") from exc
        mlflow.set_tracking_uri(tracking_uri)
        self.mlflow = mlflow
        self.client = MlflowClient(tracking_uri=tracking_uri)

    def experiment_id(self, name: str) -> str:
        experiment = self.client.get_experiment_by_name(name)
        if experiment is None:
            raise RuntimeError(f"MLflow experiment is missing: {name}")
        return str(experiment.experiment_id)

    def find_runs(self, experiment_id: str, tracking_key: str) -> tuple[RunSnapshot, ...]:
        runs = self.client.search_runs(
            experiment_ids=[experiment_id],
            filter_string=f"tags.`researchops.tracking_key` = '{tracking_key}'",
            max_results=10,
        )
        return tuple(
            RunSnapshot(str(run.info.run_id), str(run.info.status), dict(run.data.tags))
            for run in runs
        )

    def create_run(self, experiment_id: str, run_name: str, tags: dict[str, str]) -> str:
        payload = dict(tags)
        payload["mlflow.runName"] = run_name
        return str(self.client.create_run(experiment_id, tags=payload).info.run_id)

    def set_tags(self, run_id: str, tags: dict[str, str]) -> None:
        for key, value in tags.items():
            self.client.set_tag(run_id, key, str(value))

    def log_params(self, run_id: str, params: dict[str, Any]) -> None:
        for key, value in params.items():
            self.client.log_param(run_id, key, str(value))

    def log_metrics(self, run_id: str, metrics: dict[str, float]) -> None:
        for key, value in metrics.items():
            self.client.log_metric(run_id, key, float(value))

    def log_artifact(self, run_id: str, path: Path, artifact_path: str) -> None:
        self.client.log_artifact(run_id, str(path), artifact_path=artifact_path)

    def log_sklearn_model(
        self,
        run_id: str,
        model: Any,
        *,
        artifact_path: str,
        input_example: Any,
        signature: Any,
    ) -> str:
        with self.mlflow.start_run(run_id=run_id):
            model_info = self.mlflow.sklearn.log_model(
                sk_model=model,
                name=artifact_path,
                input_example=input_example,
                signature=signature,
            )
        model_id = str(getattr(model_info, "model_id", "") or "")
        if not model_id:
            logged_model = getattr(model_info, "logged_model", None)
            model_id = str(getattr(logged_model, "model_id", "") or "")
        if not model_id:
            raise MLflowIntegrityError(
                "MLflow 3 did not return a logged model_id for run "
                f"{run_id}; refusing to create a legacy runs:/ model identity"
            )
        return require_canonical_logged_model_uri(f"models:/{model_id}")

    def resolve_logged_model_uri(self, run_id: str, artifact_path: str) -> str | None:
        run = self.client.get_run(run_id)
        experiment_id = str(run.info.experiment_id)
        models = self.mlflow.search_logged_models(
            experiment_ids=[experiment_id],
            filter_string=f"source_run_id='{run_id}'",
            max_results=50,
            output_format="list",
        )
        matches = [
            item
            for item in models
            if str(getattr(item, "name", "")) == artifact_path
        ]
        if not matches:
            return None
        if len(matches) > 1:
            identities = sorted(str(getattr(item, "model_id", "")) for item in matches)
            raise MLflowIntegrityError(
                f"Multiple logged models named {artifact_path!r} exist for run "
                f"{run_id}: {identities}"
            )
        model_id = str(getattr(matches[0], "model_id", "") or "")
        if not model_id:
            raise MLflowIntegrityError(
                f"Logged model for run {run_id} has no model_id"
            )
        return require_canonical_logged_model_uri(f"models:/{model_id}")

    def terminate(self, run_id: str, status: str = "FINISHED") -> None:
        self.client.set_terminated(run_id, status=status)
