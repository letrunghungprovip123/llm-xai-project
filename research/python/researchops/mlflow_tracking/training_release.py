from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from research.python.researchops.artifacts.exceptions import (
    ArtifactIntegrityError,
    ArtifactValidationError,
)
from research.python.researchops.artifacts.stores.base import ArtifactStore

from .models import DownloadedTrainingRelease, ModelRegistrySnapshot


_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_PORTABLE_MODEL_NAMES = {
    "logistic_regression",
    "random_forest",
    "hist_gradient_boosting",
}


def _unique_suffix(root: Path, suffix: str, *, required: bool = True) -> Path | None:
    matches = [
        path
        for path in (root / "files").rglob("*")
        if path.is_file() and path.as_posix().endswith(suffix)
    ]
    if not matches and not required:
        return None
    if len(matches) != 1:
        raise ArtifactValidationError(
            f"Expected exactly one package file ending with {suffix!r}, "
            f"found {len(matches)}"
        )
    return matches[0]


def _is_absolute_or_file_uri(value: str) -> bool:
    return (
        value.startswith(("/", "~/", "file:/"))
        or _WINDOWS_ABSOLUTE.match(value) is not None
    )


def _walk_strings(value: Any, path: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _walk_strings(value[key], f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _validate_registry_portability(
    registry: ModelRegistrySnapshot,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    observed = {item.model_name for item in registry.models}
    if observed != _PORTABLE_MODEL_NAMES:
        findings.append(
            {
                "path": "$.models",
                "expected": str(sorted(_PORTABLE_MODEL_NAMES)),
                "observed": str(sorted(observed)),
                "message": "Portable registry model set is incomplete",
            }
        )

    for candidate in registry.models:
        expected_model = f"models/{candidate.model_name}.joblib"
        expected_columns = (
            f"schemas/preprocessed_feature_columns_{candidate.dataset_branch}.json"
        )
        expected_mapping = (
            f"schemas/preprocessed_feature_mapping_{candidate.dataset_branch}.json"
        )
        expected = {
            "artifact_path": expected_model,
            "feature_columns_path": expected_columns,
            "feature_mapping_path": expected_mapping,
        }
        if candidate.selected_as_best:
            expected["best_model_artifact_path"] = expected_model
        elif candidate.best_model_artifact_path is not None:
            expected["best_model_artifact_path"] = "None"

        for field_name, expected_value in expected.items():
            observed_value = getattr(candidate, field_name)
            if expected_value == "None":
                matches = observed_value is None
            else:
                matches = observed_value == expected_value
            if not matches:
                findings.append(
                    {
                        "path": f"$.models[{candidate.model_name}].{field_name}",
                        "expected": expected_value,
                        "observed": repr(observed_value),
                        "message": "Registry path violates artifact-relative contract",
                    }
                )

    selected = next(item for item in registry.models if item.selected_as_best)
    best_path = registry.best_model.get("artifact_path")
    expected_best = f"models/{selected.model_name}.joblib"
    if best_path != expected_best:
        findings.append(
            {
                "path": "$.best_model.artifact_path",
                "expected": expected_best,
                "observed": repr(best_path),
                "message": "Best-model path violates artifact-relative contract",
            }
        )
    if registry.artifact_schema_version != "model_registry_portable_v1":
        findings.append(
            {
                "path": "$.artifact_schema_version",
                "expected": "model_registry_portable_v1",
                "observed": registry.artifact_schema_version,
                "message": "Registry does not declare the portable path contract",
            }
        )
    return findings


def download_training_release(
    store: ArtifactStore,
    artifact_id: str,
    destination: Path,
) -> DownloadedTrainingRelease:
    verification = store.verify(artifact_id)
    if not verification.passed:
        raise ArtifactIntegrityError("; ".join(verification.errors))
    description = store.describe(artifact_id)
    manifest = description.manifest
    if manifest.artifact_type != "trained_model":
        raise ArtifactValidationError("MLflow tracking requires a trained_model artifact")
    if manifest.schema_version != "model_training_release_v1":
        raise ArtifactValidationError("Unsupported training artifact schema")
    package_root = store.download(artifact_id, destination)
    registry_path = _unique_suffix(package_root, "registry/model_registry.json")
    training_manifest = _unique_suffix(
        package_root, "manifests/model_training_manifest.json"
    )
    assert registry_path is not None and training_manifest is not None
    registry = ModelRegistrySnapshot.model_validate_json(
        registry_path.read_text(encoding="utf-8")
    )

    model_paths: dict[str, Path] = {}
    feature_columns: dict[str, Path] = {}
    feature_mappings: dict[str, Path] = {}
    input_examples: dict[str, Path] = {}
    for candidate in registry.models:
        model = _unique_suffix(
            package_root, f"models/{candidate.model_name}.joblib"
        )
        columns = _unique_suffix(
            package_root,
            f"schemas/{Path(candidate.feature_columns_path).name}",
        )
        mapping = _unique_suffix(
            package_root,
            f"schemas/{Path(candidate.feature_mapping_path).name}",
        )
        example = _unique_suffix(
            package_root,
            f"input_examples/{candidate.model_name}.json",
            required=False,
        )
        assert model is not None and columns is not None and mapping is not None
        model_paths[candidate.model_name] = model
        feature_columns[candidate.model_name] = columns
        feature_mappings[candidate.model_name] = mapping
        if example is not None:
            input_examples[candidate.model_name] = example

    excluded = {registry_path, training_manifest, *model_paths.values()}
    support = tuple(
        path
        for path in sorted((package_root / "files").rglob("*"))
        if path.is_file() and path not in excluded
    )
    return DownloadedTrainingRelease(
        manifest=manifest,
        manifest_uri=description.reference.uri,
        package_root=package_root,
        registry_path=registry_path,
        training_manifest_path=training_manifest,
        registry=registry,
        model_paths=model_paths,
        feature_columns_paths=feature_columns,
        feature_mapping_paths=feature_mappings,
        input_example_paths=input_examples,
        support_artifacts=support,
    )


def verify_training_release_portability(
    store: ArtifactStore,
    artifact_id: str,
) -> dict[str, object]:
    """Verify that a training artifact is independently restorable by ID.

    Historical artifacts remain readable for audit, but Phase 5 closure requires
    newly packaged releases to contain only artifact-relative model/schema paths
    and no developer-specific absolute paths in their JSON contracts.
    """

    verification = store.verify(artifact_id)
    if not verification.passed:
        return {
            "schema_version": "training_release_portability_report_v1",
            "artifact_id": artifact_id,
            "manifest_sha256": verification.manifest_sha256,
            "passed": False,
            "checked_json_files": 0,
            "absolute_path_findings": [],
            "contract_findings": [
                {
                    "path": "$",
                    "expected": "verified artifact",
                    "observed": "; ".join(verification.errors),
                    "message": "Artifact integrity verification failed",
                }
            ],
        }

    description = store.describe(artifact_id)
    manifest = description.manifest
    contract_findings: list[dict[str, str]] = []
    absolute_findings: list[dict[str, str]] = []
    checked_json_files = 0

    if manifest.artifact_type != "trained_model":
        contract_findings.append(
            {
                "path": "$.artifact_type",
                "expected": "trained_model",
                "observed": manifest.artifact_type,
                "message": "Artifact is not a training release",
            }
        )
    if manifest.schema_version != "model_training_release_v1":
        contract_findings.append(
            {
                "path": "$.schema_version",
                "expected": "model_training_release_v1",
                "observed": manifest.schema_version,
                "message": "Unsupported training-release schema",
            }
        )
    if manifest.metadata.get("portable_path_contract") != "artifact_relative_paths_v1":
        contract_findings.append(
            {
                "path": "$.metadata.portable_path_contract",
                "expected": "artifact_relative_paths_v1",
                "observed": repr(manifest.metadata.get("portable_path_contract")),
                "message": "Manifest does not declare the portable path contract",
            }
        )

    for path, value in _walk_strings(manifest.canonical_payload()):
        if _is_absolute_or_file_uri(value):
            absolute_findings.append(
                {
                    "file": "manifest.json",
                    "path": path,
                    "value": value,
                }
            )

    with tempfile.TemporaryDirectory(
        prefix="researchops-training-portability-"
    ) as directory:
        package_root = store.download(artifact_id, Path(directory))
        registry_path = _unique_suffix(package_root, "registry/model_registry.json")
        assert registry_path is not None
        registry = ModelRegistrySnapshot.model_validate_json(
            registry_path.read_text(encoding="utf-8")
        )
        contract_findings.extend(_validate_registry_portability(registry))

        for json_path in sorted((package_root / "files").rglob("*.json")):
            checked_json_files += 1
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                contract_findings.append(
                    {
                        "path": json_path.relative_to(package_root).as_posix(),
                        "expected": "valid JSON",
                        "observed": repr(exc),
                        "message": "JSON support artifact is unreadable",
                    }
                )
                continue
            relative = json_path.relative_to(package_root).as_posix()
            for value_path, value in _walk_strings(payload):
                if _is_absolute_or_file_uri(value):
                    absolute_findings.append(
                        {
                            "file": relative,
                            "path": value_path,
                            "value": value,
                        }
                    )

        declared = {item.relative_path for item in manifest.files}
        required = {
            "registry/model_registry.json",
            "manifests/model_training_manifest.json",
            *{
                f"models/{model_name}.joblib"
                for model_name in sorted(_PORTABLE_MODEL_NAMES)
            },
        }
        for relative in sorted(required - declared):
            contract_findings.append(
                {
                    "path": "$.files",
                    "expected": relative,
                    "observed": "missing",
                    "message": "Required portable training-release file is absent",
                }
            )

    return {
        "schema_version": "training_release_portability_report_v1",
        "artifact_id": artifact_id,
        "manifest_sha256": manifest.manifest_sha256,
        "passed": not absolute_findings and not contract_findings,
        "checked_json_files": checked_json_files,
        "absolute_path_findings": absolute_findings,
        "contract_findings": contract_findings,
    }


def load_input_example(release: DownloadedTrainingRelease, model_name: str):
    import pandas as pd

    path = release.input_example_paths.get(model_name)
    if path is not None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list) or not payload:
            raise ArtifactValidationError(f"Invalid input example for {model_name}")
        return pd.DataFrame(payload)
    columns = json.loads(
        release.feature_columns_paths[model_name].read_text(encoding="utf-8")
    )
    if isinstance(columns, dict):
        columns = columns.get("feature_columns") or columns.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ArtifactValidationError(f"Invalid feature columns for {model_name}")
    return pd.DataFrame([{str(column): 0.0 for column in columns}])
