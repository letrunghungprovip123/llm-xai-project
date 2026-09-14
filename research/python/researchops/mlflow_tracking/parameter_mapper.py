from __future__ import annotations

import json
from typing import Any

from .models import DownloadedTrainingRelease, ModelCandidate


def _scalar(value: Any) -> str | int | float | bool:
    if value is None:
        return "NONE"
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def common_parameters(release: DownloadedTrainingRelease) -> dict[str, str | int | float | bool]:
    metadata = release.manifest.metadata
    return {
        "dataset_release_id": _scalar(metadata.get("dataset_release_id", "UNREGISTERED_LEGACY")),
        "feature_matrix_artifact_id": _scalar(metadata.get("feature_matrix_artifact_id", "UNREGISTERED_LEGACY")),
        "split_artifact_id": _scalar(metadata.get("split_artifact_id", "UNREGISTERED_LEGACY")),
        "preprocessor_artifact_id": _scalar(metadata.get("preprocessor_artifact_id", "UNREGISTERED_LEGACY")),
        "preprocessing_version": _scalar(metadata.get("preprocessing_version", "legacy_model_ready_v1")),
        "training_contract_version": _scalar(metadata.get("training_contract_version", "model_training_release_v1")),
        "model_input_contract_version": _scalar(metadata.get("model_input_contract_version", "preprocessed_feature_matrix_v1")),
        "source_commit": release.manifest.source.source_commit,
        "environment_snapshot_id": _scalar(release.manifest.source.environment_snapshot_id or "UNAVAILABLE"),
        "stage_registry_sha256": release.manifest.producer.registry_sha256,
        "stage_id": release.manifest.producer.stage_id,
        "stage_version": release.manifest.producer.stage_version,
        "random_seed": release.registry.random_state,
    }


def model_parameters(candidate: ModelCandidate) -> dict[str, str | int | float | bool]:
    result: dict[str, str | int | float | bool] = {
        "algorithm": _scalar(candidate.metadata.get("algorithm", candidate.model_name)),
        "algorithm_version": candidate.model_version,
        "model_name": candidate.model_name,
        "model_family": candidate.model_family,
        "dataset_branch": candidate.dataset_branch,
        "train_rows": candidate.train_rows,
        "feature_count": candidate.feature_count,
        "selected_as_best": candidate.selected_as_best,
    }
    for key, value in sorted(candidate.metadata.items()):
        result[f"model__{key}"] = _scalar(value)
    return result
