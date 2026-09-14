from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from research.python.researchops.artifacts.hashing import sha256_file
from research.python.researchops.artifacts.models import (
    ArtifactPackage,
    ArtifactProducer,
    ArtifactSource,
)
from research.python.researchops.artifacts.package_builder import ArtifactPackageBuilder
from research.python.researchops.contracts.io import project_root


MODEL_NAMES = ("logistic_regression", "random_forest", "hist_gradient_boosting")


@dataclass
class TrainingReleaseBuild:
    package: ArtifactPackage
    temporary_directory: tempfile.TemporaryDirectory[str]

    def cleanup(self) -> None:
        self.temporary_directory.cleanup()

    def __enter__(self) -> "TrainingReleaseBuild":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.cleanup()


def _source_commit(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def _registry_sha(root: Path) -> str:
    payload = json.loads(
        (root / "config/platform/generated/stage_registry.lock.json").read_text(
            encoding="utf-8"
        )
    )
    return str(payload["registry_sha256"])


def _feature_columns(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [str(value) for value in payload]
    for key in ("feature_columns", "columns"):
        if isinstance(payload.get(key), list):
            return [str(value) for value in payload[key]]
    raise ValueError(f"Unsupported feature-column file: {path}")


def _write_input_examples(root: Path, temporary: Path) -> dict[str, Path]:
    import pandas as pd

    examples: dict[str, Path] = {}
    branches = {
        "logistic_regression": (
            "linear",
            root / "data/processed/model_ready/linear/X_valid_linear.parquet",
        ),
        "random_forest": (
            "tree",
            root / "data/processed/model_ready/tree/X_valid_tree.parquet",
        ),
        "hist_gradient_boosting": (
            "tree",
            root / "data/processed/model_ready/tree/X_valid_tree.parquet",
        ),
    }
    for model_name, (branch, matrix_path) in branches.items():
        columns_path = root / f"ml/registry/preprocessed_feature_columns_{branch}.json"
        columns = _feature_columns(columns_path)
        if matrix_path.is_file():
            frame = pd.read_parquet(matrix_path, columns=columns).head(1)
        else:
            frame = pd.DataFrame([{column: 0.0 for column in columns}])
        target = temporary / f"{model_name}.json"
        target.write_text(
            frame.to_json(orient="records", double_precision=15) + "\n",
            encoding="utf-8",
        )
        examples[model_name] = target
    return examples


def _resolve_model_path(
    root: Path,
    *,
    model_name: str,
    model_source_dir: Path | None,
) -> tuple[Path, str]:
    canonical_directory = root / "artifacts/models"
    source_directory = (
        model_source_dir.expanduser().resolve()
        if model_source_dir is not None
        else canonical_directory.resolve()
    )
    candidate = source_directory / f"{model_name}.joblib"
    if not candidate.is_file():
        raise FileNotFoundError(
            f"Missing trained model {model_name!r}: {candidate}. "
            "The package command no longer follows absolute paths embedded in "
            "legacy model_registry.json files. Place models under "
            "<project>/artifacts/models or pass --model-source-dir explicitly."
        )
    mode = (
        "current_root_canonical"
        if source_directory == canonical_directory.resolve()
        else "explicit_external_import"
    )
    return candidate.resolve(), mode


def _portable_registry(
    registry: dict[str, Any],
    temporary: Path,
) -> Path:
    portable = json.loads(json.dumps(registry))
    for item in portable.get("models", []):
        model_name = str(item["model_name"])
        branch = str(item["dataset_branch"])
        item["artifact_path"] = f"models/{model_name}.joblib"
        item["best_model_artifact_path"] = (
            f"models/{model_name}.joblib" if item.get("selected_as_best") else None
        )
        item["feature_columns_path"] = (
            f"schemas/preprocessed_feature_columns_{branch}.json"
        )
        item["feature_mapping_path"] = (
            f"schemas/preprocessed_feature_mapping_{branch}.json"
        )
    best_model = portable.get("best_model")
    if isinstance(best_model, dict) and best_model.get("model_name"):
        best_model["artifact_path"] = (
            f"models/{best_model['model_name']}.joblib"
        )
    portable["artifact_schema_version"] = "model_registry_portable_v1"
    target = temporary / "model_registry.portable.json"
    target.write_text(
        json.dumps(portable, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _looks_absolute_path(value: str) -> bool:
    return (
        value.startswith(("/", "~/", "file:/"))
        or (len(value) >= 3 and value[1:3] in {":\\", ":/"})
    )


def _normalize_json_paths(
    value: Any,
    *,
    root: Path,
    model_source_dir: Path,
    rewrites: dict[str, str],
) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_json_paths(
                item,
                root=root,
                model_source_dir=model_source_dir,
                rewrites=rewrites,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _normalize_json_paths(
                item,
                root=root,
                model_source_dir=model_source_dir,
                rewrites=rewrites,
            )
            for item in value
        ]
    if not isinstance(value, str) or not _looks_absolute_path(value):
        return value

    raw = Path(value.removeprefix("file://")).expanduser()
    try:
        relative = raw.resolve().relative_to(root)
        replacement = PurePosixPath(relative).as_posix()
    except (OSError, ValueError):
        try:
            relative = raw.resolve().relative_to(model_source_dir)
            replacement = f"models/{PurePosixPath(relative).name}"
        except (OSError, ValueError):
            replacement = f"legacy_external_reference/{raw.name}"
    rewrites[value] = replacement
    return replacement


def _portable_training_manifest(
    source: Path,
    temporary: Path,
    *,
    root: Path,
    model_source_dir: Path,
) -> tuple[Path, dict[str, str]]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    rewrites: dict[str, str] = {}
    portable = _normalize_json_paths(
        payload,
        root=root,
        model_source_dir=model_source_dir,
        rewrites=rewrites,
    )
    target = temporary / "model_training_manifest.portable.json"
    target.write_text(
        json.dumps(portable, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target, rewrites


def build_training_release_package(
    *,
    dataset_release_id: str = "UNREGISTERED_LEGACY",
    feature_matrix_artifact_id: str = "UNREGISTERED_LEGACY",
    split_artifact_id: str = "UNREGISTERED_LEGACY",
    preprocessor_artifact_id: str = "UNREGISTERED_LEGACY",
    environment_snapshot_id: str | None = None,
    model_source_dir: Path | None = None,
    root: Path | None = None,
) -> TrainingReleaseBuild:
    resolved = (root or project_root()).resolve()
    registry_path = resolved / "ml/registry/model_registry.json"
    training_manifest = resolved / "data/manifests/model_training_manifest.json"
    if not registry_path.is_file() or not training_manifest.is_file():
        raise FileNotFoundError("Model registry or model training manifest is missing")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    expected = set(MODEL_NAMES)
    registry_models = {
        str(item["model_name"]): item for item in registry.get("models", [])
    }
    observed = set(registry_models)
    if observed != expected:
        raise ValueError(f"Training registry model set mismatch: {sorted(observed)}")

    source_directory = (
        model_source_dir.expanduser().resolve()
        if model_source_dir is not None
        else (resolved / "artifacts/models").resolve()
    )
    model_paths: dict[str, Path] = {}
    model_source_resolution: dict[str, str] = {}
    for model_name in MODEL_NAMES:
        model_path, resolution_mode = _resolve_model_path(
            resolved,
            model_name=model_name,
            model_source_dir=model_source_dir,
        )
        model_paths[model_name] = model_path
        model_source_resolution[model_name] = resolution_mode

    temporary = tempfile.TemporaryDirectory(prefix="researchops-model-release-")
    temporary_root = Path(temporary.name)
    input_examples = _write_input_examples(resolved, temporary_root)
    portable_registry = _portable_registry(registry, temporary_root)
    portable_training_manifest, path_rewrites = _portable_training_manifest(
        training_manifest,
        temporary_root,
        root=resolved,
        model_source_dir=source_directory,
    )

    limitations: list[str] = []
    upstream_values = {
        "dataset_release_id": dataset_release_id,
        "feature_matrix_artifact_id": feature_matrix_artifact_id,
        "split_artifact_id": split_artifact_id,
        "preprocessor_artifact_id": preprocessor_artifact_id,
    }
    if any(value == "UNREGISTERED_LEGACY" for value in upstream_values.values()):
        limitations.append("legacy_upstream_artifact_ids_not_registered")
    if any(
        mode == "explicit_external_import"
        for mode in model_source_resolution.values()
    ):
        limitations.append("external_model_binaries_imported_once_into_portable_artifact")
    if any(
        replacement.startswith("legacy_external_reference/")
        for replacement in path_rewrites.values()
    ):
        limitations.append("unpackaged_legacy_manifest_paths_normalized_as_references")

    builder = ArtifactPackageBuilder(
        artifact_type="trained_model",
        schema_version="model_training_release_v1",
        producer=ArtifactProducer(
            stage_id="ml.train",
            stage_version=1,
            stage_run_id=None,
            registry_sha256=_registry_sha(resolved),
        ),
        source=ArtifactSource(
            source_commit=_source_commit(resolved),
            environment_snapshot_id=environment_snapshot_id,
        ),
        limitations=limitations,
        metadata={
            **upstream_values,
            "preprocessing_version": "legacy_model_ready_v1",
            "training_contract_version": "model_training_release_v1",
            "model_input_contract_version": "preprocessed_feature_matrix_v1",
            "model_input_level": "preprocessed_feature_matrix",
            "selected_model": registry["best_model"]["model_name"],
            "model_count": len(MODEL_NAMES),
            "portable_path_contract": "artifact_relative_paths_v1",
            "model_source_resolution": model_source_resolution,
            "source_registry_sha256": sha256_file(registry_path),
            "source_training_manifest_sha256": sha256_file(training_manifest),
            "normalized_path_count": len(path_rewrites),
            "model_ready_audit_status": json.loads(
                (
                    resolved / "data/manifests/model_ready_audit_manifest.json"
                ).read_text(encoding="utf-8")
            ).get("status", "unknown")
            if (
                resolved / "data/manifests/model_ready_audit_manifest.json"
            ).is_file()
            else "missing",
        },
    )
    builder.add_file(
        portable_registry,
        relative_path="registry/model_registry.json",
    )
    builder.add_file(
        portable_training_manifest,
        relative_path="manifests/model_training_manifest.json",
    )

    for model_name in MODEL_NAMES:
        builder.add_file(
            model_paths[model_name],
            relative_path=f"models/{model_name}.joblib",
        )
        builder.add_file(
            input_examples[model_name],
            relative_path=f"input_examples/{model_name}.json",
        )

    for name in (
        "preprocessed_feature_columns_linear.json",
        "preprocessed_feature_columns_tree.json",
        "preprocessed_feature_mapping_linear.json",
        "preprocessed_feature_mapping_tree.json",
    ):
        builder.add_file(
            resolved / "ml/registry" / name,
            relative_path=f"schemas/{name}",
        )

    optional = {
        "data/manifests/model_ready_audit_manifest.json": "audits/model_ready_audit_manifest.json",
        "data/reports/model_ready_audit_summary.md": "audits/model_ready_audit_summary.md",
        "data/reports/model_metrics_summary.csv": "evaluation/model_metrics_summary.csv",
        "data/reports/model_training_report.md": "reports/model_training_report.md",
        "data/reports/model_threshold_analysis_valid.csv": "evaluation/model_threshold_analysis_valid.csv",
        "data/reports/model_feature_importance.csv": "evaluation/model_feature_importance.csv",
    }
    for source, relative in optional.items():
        path = resolved / source
        if path.is_file():
            builder.add_file(path, relative_path=relative)

    return TrainingReleaseBuild(
        package=builder.build(),
        temporary_directory=temporary,
    )
