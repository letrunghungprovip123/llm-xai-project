from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import urlopen

from .exceptions import MLflowConfigurationError
from .settings import MLflowSettings


class ExperimentGateway(Protocol):
    def get_experiment_by_name(self, name: str) -> Any | None: ...
    def create_experiment(self, name: str, tags: dict[str, str]) -> str: ...
    def set_experiment_tag(self, experiment_id: str, key: str, value: str) -> None: ...


@dataclass(frozen=True)
class VersionReport:
    expected_version: str
    client_version: str
    server_version: str

    @property
    def passed(self) -> bool:
        return self.expected_version == self.client_version == self.server_version

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "mlflow_version_report_v1",
            "passed": self.passed,
            "expected_version": self.expected_version,
            "client_version": self.client_version,
            "server_version": self.server_version,
        }


class RealMLflowGateway:
    def __init__(self, settings: MLflowSettings) -> None:
        try:
            import mlflow
            from mlflow.tracking import MlflowClient
        except ImportError as exc:
            raise MLflowConfigurationError(
                "MLflow is not installed; install research/python/requirements-researchops.txt"
            ) from exc
        mlflow.set_tracking_uri(settings.tracking_uri)
        self._mlflow = mlflow
        self.client = MlflowClient(tracking_uri=settings.tracking_uri)
        self.settings = settings

    @property
    def client_version(self) -> str:
        return str(self._mlflow.__version__)

    def server_version(self) -> str:
        with urlopen(f"{self.settings.tracking_uri}/version", timeout=10) as response:
            payload = response.read().decode("utf-8").strip()
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return str(parsed.get("version") or parsed.get("mlflow_version"))
            if isinstance(parsed, str):
                return parsed
        except json.JSONDecodeError:
            pass
        return payload.strip('"')

    def version_report(self) -> VersionReport:
        return VersionReport(
            expected_version=self.settings.expected_version,
            client_version=self.client_version,
            server_version=self.server_version(),
        )

    def get_experiment_by_name(self, name: str) -> Any | None:
        return self.client.get_experiment_by_name(name)

    def create_experiment(self, name: str, tags: dict[str, str]) -> str:
        return str(self.client.create_experiment(name=name, tags=tags))

    def set_experiment_tag(self, experiment_id: str, key: str, value: str) -> None:
        self.client.set_experiment_tag(experiment_id, key, value)
