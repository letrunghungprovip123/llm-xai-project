from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.python.researchops.artifacts.models import ArtifactProducer, ArtifactSource
from research.python.researchops.artifacts.package_builder import ArtifactPackageBuilder


@pytest.fixture
def registry_sha() -> str:
    payload = json.loads(
        Path("config/platform/generated/stage_registry.lock.json").read_text(encoding="utf-8")
    )
    return str(payload["registry_sha256"])


@pytest.fixture
def training_release_package(tmp_path: Path, registry_sha: str):
    source = tmp_path / "source"
    for directory in ("models", "registry", "manifests", "schemas", "input_examples"):
        (source / directory).mkdir(parents=True, exist_ok=True)
    models = []
    definitions = [
        ("logistic_regression", "linear", False),
        ("random_forest", "tree", False),
        ("hist_gradient_boosting", "tree", True),
    ]
    for name, branch, selected in definitions:
        (source / "models" / f"{name}.joblib").write_bytes(f"model:{name}".encode())
        (source / "input_examples" / f"{name}.json").write_text('[{"f1": 0.0, "f2": 1.0}]\n')
        models.append({
            "model_name": name,
            "model_version": "v1",
            "model_family": branch,
            "dataset_branch": branch,
            "artifact_path": f"/legacy/{name}.joblib",
            "best_model_artifact_path": None,
            "feature_columns_path": f"/legacy/preprocessed_feature_columns_{branch}.json",
            "feature_mapping_path": f"/legacy/preprocessed_feature_mapping_{branch}.json",
            "train_rows": 100,
            "feature_count": 2,
            "training_seconds": 1.5,
            "metadata": {"algorithm": name, "random_state": 42},
            "valid_metrics": {"roc_auc": 0.75, "average_precision": 0.25, "brier_score": 0.18, "threshold": 0.5},
            "test_metrics": {"roc_auc": 0.76, "average_precision": 0.26, "brier_score": 0.17, "threshold": 0.5} if selected else None,
            "selected_as_best": selected,
        })
    registry = {
        "artifact_schema_version": "1.0.0",
        "task_type": "binary_classification",
        "target_column": "TARGET",
        "positive_class": 1,
        "negative_class": 0,
        "model_version": "v1",
        "random_state": 42,
        "default_threshold": 0.5,
        "selection_policy": {"primary_metric": "average_precision"},
        "best_model": {"model_name": "hist_gradient_boosting"},
        "models": models,
    }
    (source / "registry/model_registry.json").write_text(json.dumps(registry))
    (source / "manifests/model_training_manifest.json").write_text(json.dumps({"status": "passed"}))
    for branch in ("linear", "tree"):
        (source / "schemas" / f"preprocessed_feature_columns_{branch}.json").write_text('["f1", "f2"]')
        (source / "schemas" / f"preprocessed_feature_mapping_{branch}.json").write_text('{}')
    builder = ArtifactPackageBuilder(
        artifact_id="artifact_trained_model_01J00000000000000000000000",
        artifact_type="trained_model",
        schema_version="model_training_release_v1",
        producer=ArtifactProducer(stage_id="ml.train", stage_version=1, stage_run_id=None, registry_sha256=registry_sha),
        source=ArtifactSource(source_commit="375cfa9"),
        metadata={"model_input_level": "preprocessed_feature_matrix"},
    )
    builder.add_directory(source)
    return builder.build()
