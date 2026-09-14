from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import RunSnapshot


@dataclass(frozen=True)
class ModelVersionSnapshot:
    name: str
    version: str
    run_id: str
    source: str
    status: str
    tags: dict[str, str]


class RegistryGateway(Protocol):
    def ensure_registered_model(self, name: str, description: str) -> None: ...
    def list_versions(self, name: str) -> tuple[ModelVersionSnapshot, ...]: ...
    def create_version(
        self,
        name: str,
        *,
        source: str,
        run_id: str,
        description: str,
        tags: dict[str, str],
    ) -> ModelVersionSnapshot: ...
    def set_version_tags(self, name: str, version: str, tags: dict[str, str]) -> None: ...
    def set_alias(self, name: str, alias: str, version: str) -> None: ...
    def alias_version(self, name: str, alias: str) -> str | None: ...
    def get_version(self, name: str, version: str) -> ModelVersionSnapshot | None: ...
    def get_run(self, run_id: str) -> RunSnapshot | None: ...
    def set_run_tags(self, run_id: str, tags: dict[str, str]) -> None: ...


class RealRegistryGateway:
    def __init__(self, tracking_uri: str) -> None:
        try:
            import mlflow
            from mlflow.exceptions import MlflowException
            from mlflow.tracking import MlflowClient
        except ImportError as exc:
            raise RuntimeError("MLflow is not installed") from exc
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient(tracking_uri=tracking_uri)
        self._mlflow_exception = MlflowException

    def _missing(self, exc: Exception) -> bool:
        return getattr(exc, "error_code", None) == "RESOURCE_DOES_NOT_EXIST"

    def _missing_alias(self, exc: Exception) -> bool:
        if self._missing(exc):
            return True
        if getattr(exc, "error_code", None) != "INVALID_PARAMETER_VALUE":
            return False
        message = str(exc).lower()
        return (
            "registered model alias" in message
            and "not found" in message
        )

    @staticmethod
    def _snapshot(item) -> ModelVersionSnapshot:
        return ModelVersionSnapshot(
            name=str(item.name),
            version=str(item.version),
            run_id=str(item.run_id or ""),
            source=str(item.source or ""),
            status=str(item.status or "UNKNOWN"),
            tags={str(key): str(value) for key, value in dict(item.tags or {}).items()},
        )

    def ensure_registered_model(self, name: str, description: str) -> None:
        try:
            self.client.get_registered_model(name)
        except self._mlflow_exception as exc:
            if not self._missing(exc):
                raise
            self.client.create_registered_model(name, description=description)

    def list_versions(self, name: str) -> tuple[ModelVersionSnapshot, ...]:
        items = self.client.search_model_versions(filter_string=f"name='{name}'")
        return tuple(self._snapshot(item) for item in items)

    def create_version(
        self,
        name: str,
        *,
        source: str,
        run_id: str,
        description: str,
        tags: dict[str, str],
    ) -> ModelVersionSnapshot:
        create_kwargs = {
            "name": name,
            "source": source,
            "run_id": run_id,
            "description": description,
            "tags": tags,
            # The local SQL registry creates versions synchronously in READY
            # state. Avoid an unnecessary follow-up GET, which also exposed an
            # MLflow 3.14 PostgreSQL INTEGER/VARCHAR comparison bug.
            "await_creation_for": 0,
        }
        if source.startswith("models:/"):
            model_id = source.removeprefix("models:/")
            if "/" not in model_id and model_id:
                create_kwargs["model_id"] = model_id
        item = self.client.create_model_version(**create_kwargs)
        return self._snapshot(item)

    def set_version_tags(self, name: str, version: str, tags: dict[str, str]) -> None:
        for key, value in tags.items():
            self.client.set_model_version_tag(name, version, key, str(value))

    def set_alias(self, name: str, alias: str, version: str) -> None:
        self.client.set_registered_model_alias(name, alias, version)

    def alias_version(self, name: str, alias: str) -> str | None:
        try:
            item = self.client.get_model_version_by_alias(name, alias)
        except self._mlflow_exception as exc:
            # MLflow 3.14 reports a missing alias as INVALID_PARAMETER_VALUE
            # instead of RESOURCE_DOES_NOT_EXIST. A first candidate assignment
            # must treat that response as the normal "no alias yet" state.
            if not self._missing_alias(exc):
                raise
            return None
        return str(item.version)

    def get_version(self, name: str, version: str) -> ModelVersionSnapshot | None:
        try:
            return self._snapshot(self.client.get_model_version(name, version))
        except self._mlflow_exception as exc:
            if not self._missing(exc):
                raise
            return None

    def get_run(self, run_id: str) -> RunSnapshot | None:
        try:
            item = self.client.get_run(run_id)
        except self._mlflow_exception as exc:
            if not self._missing(exc):
                raise
            return None
        return RunSnapshot(
            run_id=str(item.info.run_id),
            status=str(item.info.status),
            tags={str(key): str(value) for key, value in dict(item.data.tags).items()},
        )

    def set_run_tags(self, run_id: str, tags: dict[str, str]) -> None:
        for key, value in tags.items():
            self.client.set_tag(run_id, key, str(value))
