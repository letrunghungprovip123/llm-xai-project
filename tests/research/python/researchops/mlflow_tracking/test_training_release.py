from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.python.researchops.artifacts.models import (
    ArtifactProducer,
    ArtifactSource,
)
from research.python.researchops.artifacts.package_builder import ArtifactPackageBuilder
from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.mlflow_tracking.package_training import (
    _portable_registry,
    _portable_training_manifest,
    _resolve_model_path,
)
from research.python.researchops.mlflow_tracking.training_release import (
    download_training_release,
    verify_training_release_portability,
)


def test_download_training_release_keeps_historical_artifact_readable(
    tmp_path,
    training_release_package,
):
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(training_release_package)
    release = download_training_release(
        store,
        training_release_package.manifest.artifact_id,
        tmp_path / "download",
    )
    assert release.registry.best_model["model_name"] == "hist_gradient_boosting"
    assert set(release.model_paths) == {
        "logistic_regression",
        "random_forest",
        "hist_gradient_boosting",
    }
    assert all(path.is_file() for path in release.model_paths.values())


def test_resolve_model_path_prefers_current_root_canonical(tmp_path):
    canonical = tmp_path / "artifacts/models/logistic_regression.joblib"
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b"canonical")

    resolved, mode = _resolve_model_path(
        tmp_path,
        model_name="logistic_regression",
        model_source_dir=None,
    )

    assert resolved == canonical.resolve()
    assert mode == "current_root_canonical"


def test_resolve_model_path_allows_only_explicit_external_import(tmp_path):
    root = tmp_path / "refactor"
    external = tmp_path / "legacy-models"
    external.mkdir(parents=True)
    model = external / "random_forest.joblib"
    model.write_bytes(b"legacy")

    resolved, mode = _resolve_model_path(
        root,
        model_name="random_forest",
        model_source_dir=external,
    )

    assert resolved == model.resolve()
    assert mode == "explicit_external_import"


def test_resolve_model_path_does_not_follow_registry_or_sibling_repo(tmp_path):
    root = tmp_path / "refactor"
    legacy = tmp_path / "legacy/random_forest.joblib"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy")

    with pytest.raises(FileNotFoundError, match="--model-source-dir explicitly") as error:
        _resolve_model_path(
            root,
            model_name="random_forest",
            model_source_dir=None,
        )

    assert str((root / "artifacts/models/random_forest.joblib").resolve()) in str(
        error.value
    )
    assert str(legacy.resolve()) not in str(error.value)


def _legacy_registry() -> dict[str, object]:
    models = []
    for model_name, branch, selected in (
        ("logistic_regression", "linear", False),
        ("random_forest", "tree", False),
        ("hist_gradient_boosting", "tree", True),
    ):
        models.append(
            {
                "model_name": model_name,
                "model_version": "v1",
                "model_family": branch,
                "dataset_branch": branch,
                "artifact_path": f"/Users/example/legacy/{model_name}.joblib",
                "best_model_artifact_path": (
                    f"/Users/example/legacy/{model_name}.joblib"
                    if selected
                    else None
                ),
                "feature_columns_path": (
                    f"/Users/example/repo/ml/registry/"
                    f"preprocessed_feature_columns_{branch}.json"
                ),
                "feature_mapping_path": (
                    f"/Users/example/repo/ml/registry/"
                    f"preprocessed_feature_mapping_{branch}.json"
                ),
                "train_rows": 100,
                "feature_count": 2,
                "training_seconds": 1.0,
                "metadata": {},
                "valid_metrics": {
                    "roc_auc": 0.75,
                    "average_precision": 0.25,
                    "brier_score": 0.18,
                },
                "test_metrics": None,
                "selected_as_best": selected,
            }
        )
    return {
        "artifact_schema_version": "1.0.0",
        "task_type": "binary_classification",
        "target_column": "TARGET",
        "positive_class": 1,
        "negative_class": 0,
        "model_version": "v1",
        "random_state": 42,
        "default_threshold": 0.5,
        "selection_policy": {"primary_metric": "average_precision"},
        "best_model": {
            "model_name": "hist_gradient_boosting",
            "artifact_path": (
                "/Users/example/legacy/hist_gradient_boosting.joblib"
            ),
        },
        "models": models,
    }


def test_portable_registry_rewrites_all_model_and_schema_paths(tmp_path):
    target = _portable_registry(_legacy_registry(), tmp_path)
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["artifact_schema_version"] == "model_registry_portable_v1"
    for model in payload["models"]:
        expected_model = f"models/{model['model_name']}.joblib"
        assert model["artifact_path"] == expected_model
        assert model["feature_columns_path"].startswith("schemas/")
        assert model["feature_mapping_path"].startswith("schemas/")
        if model["selected_as_best"]:
            assert model["best_model_artifact_path"] == expected_model
        else:
            assert model["best_model_artifact_path"] is None
    assert (
        payload["best_model"]["artifact_path"]
        == "models/hist_gradient_boosting.joblib"
    )


def test_portable_training_manifest_normalizes_absolute_paths(tmp_path):
    root = tmp_path / "repo"
    external = tmp_path / "external-models"
    root.mkdir()
    external.mkdir()
    source = root / "training.json"
    source.write_text(
        json.dumps(
            {
                "project": str(root / "data/input.parquet"),
                "model": str(external / "random_forest.joblib"),
                "unknown": "/removed/developer/report.json",
                "relative": "data/relative.json",
            }
        ),
        encoding="utf-8",
    )

    target, rewrites = _portable_training_manifest(
        source,
        tmp_path,
        root=root,
        model_source_dir=external,
    )
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["project"] == "data/input.parquet"
    assert payload["model"] == "models/random_forest.joblib"
    assert payload["unknown"] == "legacy_external_reference/report.json"
    assert payload["relative"] == "data/relative.json"
    assert len(rewrites) == 3


def _build_portable_package(tmp_path: Path, registry_sha: str):
    source = tmp_path / "portable-source"
    for directory in (
        "models",
        "registry",
        "manifests",
        "schemas",
        "input_examples",
    ):
        (source / directory).mkdir(parents=True, exist_ok=True)

    registry = _legacy_registry()
    portable_registry = _portable_registry(registry, tmp_path)
    (source / "registry/model_registry.json").write_bytes(
        portable_registry.read_bytes()
    )
    (source / "manifests/model_training_manifest.json").write_text(
        json.dumps({"status": "passed", "source": "data/processed/train.parquet"}),
        encoding="utf-8",
    )
    for model in registry["models"]:
        name = str(model["model_name"])
        branch = str(model["dataset_branch"])
        (source / "models" / f"{name}.joblib").write_bytes(name.encode())
        (source / "input_examples" / f"{name}.json").write_text(
            '[{"f1": 0.0}]\n',
            encoding="utf-8",
        )
        (source / "schemas" / f"preprocessed_feature_columns_{branch}.json").write_text(
            '["f1"]\n',
            encoding="utf-8",
        )
        (source / "schemas" / f"preprocessed_feature_mapping_{branch}.json").write_text(
            "{}\n",
            encoding="utf-8",
        )

    builder = ArtifactPackageBuilder(
        artifact_id="artifact_trained_model_01J11111111111111111111111",
        artifact_type="trained_model",
        schema_version="model_training_release_v1",
        producer=ArtifactProducer(
            stage_id="ml.train",
            stage_version=1,
            stage_run_id=None,
            registry_sha256=registry_sha,
        ),
        source=ArtifactSource(source_commit="375cfa9"),
        metadata={"portable_path_contract": "artifact_relative_paths_v1"},
    )
    builder.add_directory(source)
    return builder.build()


def test_portability_verifier_rejects_historical_absolute_paths(
    tmp_path,
    training_release_package,
):
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(training_release_package)

    report = verify_training_release_portability(
        store,
        training_release_package.manifest.artifact_id,
    )

    assert report["passed"] is False
    assert report["absolute_path_findings"]
    assert report["contract_findings"]


def test_portability_verifier_accepts_artifact_relative_release(
    tmp_path,
    registry_sha,
):
    package = _build_portable_package(tmp_path, registry_sha)
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(package)

    report = verify_training_release_portability(
        store,
        package.manifest.artifact_id,
    )

    assert report["passed"] is True, report
    assert report["absolute_path_findings"] == []
    assert report["contract_findings"] == []
    assert report["checked_json_files"] >= 7
