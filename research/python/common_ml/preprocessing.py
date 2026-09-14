from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..common.dataframes import count_infinite_values
from ..preprocessing.transforms import build_model_ready_dataset, infer_feature_groups
from .context import CommonMLRunContext
from .split import CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN


@dataclass(frozen=True)
class CommonPreprocessingResult:
    manifest_path: Path
    tree_feature_count: int
    linear_feature_count: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_feature_metadata(path: Path) -> dict[str, dict[str, Any]]:
    df = pd.read_csv(path)
    if "feature_name" not in df.columns:
        raise ValueError("feature_registry.csv is missing feature_name column")
    metadata: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        item: dict[str, Any] = {}
        for column in df.columns:
            value = row[column]
            if pd.isna(value):
                item[column] = None
            elif isinstance(value, np.generic):
                item[column] = value.item()
            else:
                item[column] = value
        metadata[str(row["feature_name"])] = item
    return metadata


def _load_splits(ctx: CommonMLRunContext) -> dict[str, pd.DataFrame]:
    split_dir = ctx.paths.processed_dir / "splits"
    paths = {
        key: split_dir / f"{key}.parquet"
        for key in ("X_train", "y_train", "X_valid", "y_valid", "X_test", "y_test")
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Common preprocessing missing split inputs: {missing}")
    return {key: pd.read_parquet(path) for key, path in paths.items()}


def _validate_inputs(
    *,
    frames: dict[str, pd.DataFrame],
    model_features: list[str],
    target_column: str,
    feature_metadata: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected_x_columns = [CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN, *model_features]

    for split in ("train", "valid", "test"):
        X = frames[f"X_{split}"]
        y = frames[f"y_{split}"]
        if list(X.columns) != expected_x_columns:
            errors.append(f"{split}: X columns differ from canonical split schema")
        expected_y_columns = [CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN, target_column]
        if list(y.columns) != expected_y_columns:
            errors.append(f"{split}: y columns differ from canonical target schema")
        if len(X) != len(y):
            errors.append(f"{split}: X/y row mismatch")
        if CASE_ID_COLUMN in X.columns and CASE_ID_COLUMN in y.columns:
            if X[CASE_ID_COLUMN].tolist() != y[CASE_ID_COLUMN].tolist():
                errors.append(f"{split}: X/y case_id row order mismatch")
            if X[CASE_ID_COLUMN].duplicated().any() or y[CASE_ID_COLUMN].duplicated().any():
                errors.append(f"{split}: duplicate case_id")
        if target_column not in y.columns:
            errors.append(f"{split}: target column missing")
        elif sorted(y[target_column].dropna().unique().tolist()) != [0, 1]:
            errors.append(f"{split}: canonical target must contain [0, 1]")
        if target_column in X.columns:
            errors.append(f"{split}: target leaked into X")

    missing_metadata = sorted(set(model_features) - set(feature_metadata))
    if missing_metadata:
        errors.append(f"model features missing feature metadata: {missing_metadata[:50]}")
    extra_metadata = sorted(set(feature_metadata) - set(model_features))
    if extra_metadata:
        warnings.append(f"registry contains non-model features: {extra_metadata[:50]}")

    return {
        "status": "passed" if not errors else "blocked",
        "errors": errors,
        "warnings": warnings,
        "model_feature_count": len(model_features),
    }


def _validate_model_ready(
    *,
    X_train: pd.DataFrame,
    X_valid: pd.DataFrame,
    X_test: pd.DataFrame,
    pipeline_type: str,
) -> dict[str, Any]:
    errors: list[str] = []
    if list(X_train.columns) != list(X_valid.columns):
        errors.append(f"{pipeline_type}: valid columns differ from train")
    if list(X_train.columns) != list(X_test.columns):
        errors.append(f"{pipeline_type}: test columns differ from train")
    if X_train.columns.duplicated().any():
        errors.append(f"{pipeline_type}: duplicate model-ready columns")
    for split, frame in (("train", X_train), ("valid", X_valid), ("test", X_test)):
        forbidden = [c for c in (CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN) if c in frame.columns]
        if forbidden:
            errors.append(f"{pipeline_type}/{split}: identity columns found in model matrix: {forbidden}")
        missing = int(frame.isna().sum().sum())
        inf = count_infinite_values(frame)
        object_columns = frame.select_dtypes(include=["object", "string", "category"]).columns.tolist()
        if missing:
            errors.append(f"{pipeline_type}/{split}: missing values remain: {missing}")
        if inf:
            errors.append(f"{pipeline_type}/{split}: infinite values remain: {inf}")
        if object_columns:
            errors.append(f"{pipeline_type}/{split}: non-numeric columns remain: {object_columns[:20]}")
    return {
        "status": "passed" if not errors else "blocked",
        "errors": errors,
        "preprocessed_feature_count": int(X_train.shape[1]),
        "train_shape": [int(X_train.shape[0]), int(X_train.shape[1])],
        "valid_shape": [int(X_valid.shape[0]), int(X_valid.shape[1])],
        "test_shape": [int(X_test.shape[0]), int(X_test.shape[1])],
    }


def run_common_preprocessing(ctx: CommonMLRunContext) -> CommonPreprocessingResult:
    ctx.create_workspace()
    split_manifest = ctx.paths.manifest_dir / "common_ml_split_manifest.json"
    if not split_manifest.is_file():
        raise FileNotFoundError("Run common split before common preprocessing")

    frames = _load_splits(ctx)
    model_features = [str(item) for item in _read_json(ctx.paths.registry_dir / "model_feature_columns.json")]
    target_column = str(_read_json(ctx.paths.registry_dir / "target_column.json"))
    feature_metadata = _load_feature_metadata(ctx.paths.registry_dir / "feature_registry.csv")

    validation = _validate_inputs(
        frames=frames,
        model_features=model_features,
        target_column=target_column,
        feature_metadata=feature_metadata,
    )
    if validation["status"] != "passed":
        _write_json(ctx.paths.manifest_dir / "common_ml_preprocessing_input_failed.json", validation)
        raise RuntimeError(f"Common preprocessing input validation failed: {validation['errors']}")

    train_model = frames["X_train"][model_features].copy()
    valid_model = frames["X_valid"][model_features].copy()
    test_model = frames["X_test"][model_features].copy()
    groups = infer_feature_groups(
        X_train=train_model,
        model_feature_columns=model_features,
        feature_metadata=feature_metadata,
    )

    tree = build_model_ready_dataset(
        X_train=train_model,
        X_valid=valid_model,
        X_test=test_model,
        numeric_features=groups["numeric_features"],
        categorical_features=groups["categorical_features"],
        binary_features=groups["binary_features"],
        feature_metadata=feature_metadata,
        pipeline_type="tree",
    )
    linear = build_model_ready_dataset(
        X_train=train_model,
        X_valid=valid_model,
        X_test=test_model,
        numeric_features=groups["numeric_features"],
        categorical_features=groups["categorical_features"],
        binary_features=groups["binary_features"],
        feature_metadata=feature_metadata,
        pipeline_type="linear",
    )
    train_tree, valid_tree, test_tree, tree_artifact, tree_mapping = tree
    train_linear, valid_linear, test_linear, linear_artifact, linear_mapping = linear

    tree_validation = _validate_model_ready(
        X_train=train_tree, X_valid=valid_tree, X_test=test_tree, pipeline_type="tree"
    )
    linear_validation = _validate_model_ready(
        X_train=train_linear, X_valid=valid_linear, X_test=test_linear, pipeline_type="linear"
    )
    if tree_validation["status"] != "passed" or linear_validation["status"] != "passed":
        raise RuntimeError(
            "Common preprocessing model-ready validation failed: "
            f"tree={tree_validation['errors']}; linear={linear_validation['errors']}"
        )

    tree_dir = ctx.paths.processed_dir / "model_ready" / "tree"
    linear_dir = ctx.paths.processed_dir / "model_ready" / "linear"
    output_files: dict[str, str] = {}
    for name, frame, path in (
        ("X_train_tree", train_tree, tree_dir / "X_train_tree.parquet"),
        ("X_valid_tree", valid_tree, tree_dir / "X_valid_tree.parquet"),
        ("X_test_tree", test_tree, tree_dir / "X_test_tree.parquet"),
        ("X_train_linear", train_linear, linear_dir / "X_train_linear.parquet"),
        ("X_valid_linear", valid_linear, linear_dir / "X_valid_linear.parquet"),
        ("X_test_linear", test_linear, linear_dir / "X_test_linear.parquet"),
    ):
        frame.to_parquet(path, index=False)
        output_files[name] = str(path)

    for branch, directory in (("tree", tree_dir), ("linear", linear_dir)):
        for split in ("train", "valid", "test"):
            path = directory / f"y_{split}.parquet"
            frames[f"y_{split}"].to_parquet(path, index=False)
            output_files[f"y_{split}_{branch}"] = str(path)

    import joblib

    tree_preprocessor = ctx.paths.artifact_dir / "preprocessing" / "tree_preprocessor.joblib"
    linear_preprocessor = ctx.paths.artifact_dir / "preprocessing" / "linear_preprocessor.joblib"
    joblib.dump(tree_artifact, tree_preprocessor)
    joblib.dump(linear_artifact, linear_preprocessor)

    _write_json(
        ctx.paths.registry_dir / "preprocessed_feature_columns_tree.json",
        tree_artifact["preprocessed_feature_columns"],
    )
    _write_json(
        ctx.paths.registry_dir / "preprocessed_feature_columns_linear.json",
        linear_artifact["preprocessed_feature_columns"],
    )
    _write_json(ctx.paths.registry_dir / "preprocessed_feature_mapping_tree.json", tree_mapping)
    _write_json(ctx.paths.registry_dir / "preprocessed_feature_mapping_linear.json", linear_mapping)

    manifest = {
        "schema_version": "common_ml_preprocessing_manifest_v1",
        "created_at_utc": _utc_now(),
        **ctx.common_provenance(),
        "fit_policy": "train_only",
        "canonical_target_column": target_column,
        "input_feature_count": len(model_features),
        "feature_groups": groups,
        "validation": {
            "input": validation,
            "tree": tree_validation,
            "linear": linear_validation,
        },
        "output_files": output_files,
        "artifacts": {
            "tree_preprocessor": str(tree_preprocessor),
            "linear_preprocessor": str(linear_preprocessor),
        },
        "status": "passed",
    }
    manifest_path = ctx.paths.manifest_dir / "common_ml_preprocessing_manifest.json"
    _write_json(manifest_path, manifest)
    return CommonPreprocessingResult(
        manifest_path=manifest_path,
        tree_feature_count=tree_validation["preprocessed_feature_count"],
        linear_feature_count=linear_validation["preprocessed_feature_count"],
    )
