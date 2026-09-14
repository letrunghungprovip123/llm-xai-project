from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from research.python.researchops.artifacts.models import ArtifactManifestV3


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelCandidate(StrictModel):
    model_name: str
    model_version: str
    model_family: str
    dataset_branch: str
    artifact_path: str
    best_model_artifact_path: str | None = None
    feature_columns_path: str
    feature_mapping_path: str
    train_rows: int = Field(ge=1)
    feature_count: int = Field(ge=1)
    training_seconds: float = Field(ge=0)
    metadata: dict[str, Any]
    valid_metrics: dict[str, float | int]
    test_metrics: dict[str, float | int] | None
    selected_as_best: bool


class ModelRegistrySnapshot(StrictModel):
    created_at: str | None = None
    artifact_schema_version: str
    batch_name: str | None = None
    task_type: str
    target_column: str
    positive_class: int
    negative_class: int
    model_version: str
    random_state: int
    default_threshold: float
    selection_policy: dict[str, Any]
    best_model: dict[str, Any]
    models: tuple[ModelCandidate, ...]
    evaluation_outputs: dict[str, Any] = Field(default_factory=dict)
    upstream_registries: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def project_model_set_is_complete(self) -> "ModelRegistrySnapshot":
        expected = {"logistic_regression", "random_forest", "hist_gradient_boosting"}
        observed = {item.model_name for item in self.models}
        if observed != expected:
            raise ValueError(f"Expected model set {sorted(expected)}, got {sorted(observed)}")
        selected = [item.model_name for item in self.models if item.selected_as_best]
        if len(selected) != 1:
            raise ValueError("Exactly one model must be selected as best")
        if self.best_model.get("model_name") != selected[0]:
            raise ValueError("best_model does not match selected_as_best")
        return self


@dataclass(frozen=True)
class DownloadedTrainingRelease:
    manifest: ArtifactManifestV3
    manifest_uri: str
    package_root: Path
    registry_path: Path
    training_manifest_path: Path
    registry: ModelRegistrySnapshot
    model_paths: dict[str, Path]
    feature_columns_paths: dict[str, Path]
    feature_mapping_paths: dict[str, Path]
    input_example_paths: dict[str, Path]
    support_artifacts: tuple[Path, ...]


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    status: str
    tags: dict[str, str]


@dataclass(frozen=True)
class TrackedModelRun:
    model_name: str
    run_id: str
    model_uri: str
    tracking_key: str
    selected_as_best: bool
    reused: bool


@dataclass(frozen=True)
class TrainingTrackingResult:
    source_artifact_id: str
    source_manifest_sha256: str
    experiment_id: str
    parent_run_id: str
    parent_reused: bool
    models: tuple[TrackedModelRun, ...]

    @property
    def selected_model(self) -> TrackedModelRun:
        return next(item for item in self.models if item.selected_as_best)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "mlflow_training_tracking_result_v1",
            "source_artifact_id": self.source_artifact_id,
            "source_manifest_sha256": self.source_manifest_sha256,
            "experiment_id": self.experiment_id,
            "parent_run_id": self.parent_run_id,
            "parent_reused": self.parent_reused,
            "selected_model": self.selected_model.model_name,
            "models": [item.__dict__ for item in self.models],
        }
