from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ml.scripts.xai_layer.config import (
    BEST_MODEL_PATH,
    DEFAULT_THRESHOLD_FALLBACK,
    EXPECTED_BEST_MODEL_NAME,
    EXPECTED_DATASET_BRANCH,
    ID_COLUMN,
    MODEL_REGISTRY_PATH,
    POSITIVE_CLASS,
    RUN_MODE_EVALUATION,
    RUN_MODE_INFERENCE,
    TARGET_COLUMN,
    TREE_FEATURE_COLUMNS_PATH,
    TREE_FEATURE_MAPPING_PATH,
    FEATURE_REGISTRY_CSV_PATH,
    CONCEPT_REGISTRY_PATH,
    XAI_CONFIG,
    get_predictions_path_for_mode,
    get_x_data_path_for_mode,
    get_y_data_path_for_mode,
    mode_has_ground_truth,
    validate_required_inputs_exist,
    validate_run_mode,
)


@dataclass(frozen=True)
class XAIModelBundle:
    bundle: dict[str, Any]
    estimator: Any
    feature_columns: list[str]
    model_name: str
    model_version: str
    model_family: str
    dataset_branch: str
    default_threshold: float
    feature_count: int


@dataclass(frozen=True)
class XAIInputs:
    run_mode: str
    has_ground_truth: bool
    model_bundle: XAIModelBundle
    model_registry: dict[str, Any]
    X: pd.DataFrame
    y: pd.DataFrame | None
    predictions: pd.DataFrame
    tree_feature_columns: list[str]
    feature_mapping: dict[str, Any]
    feature_registry: pd.DataFrame
    concept_registry: dict[str, Any]

    @property
    def X_test(self) -> pd.DataFrame:
        return self.X

    @property
    def y_test(self) -> pd.DataFrame | None:
        return self.y

    @property
    def predictions_test(self) -> pd.DataFrame:
        return self.predictions


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to read YAML registry files. "
            "Install it with: pip install pyyaml"
        ) from exc

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a dictionary: {path}")

    return data


def load_model_registry(path: Path = MODEL_REGISTRY_PATH) -> dict[str, Any]:
    registry = read_json(path)

    if not isinstance(registry, dict):
        raise ValueError("Model registry must be a JSON object.")

    return registry


def validate_model_bundle_dict(bundle: Any) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        raise TypeError(
            "Model artifact must be a joblib bundle dictionary, "
            f"got {type(bundle).__name__}."
        )

    required_keys = [
        "estimator",
        "feature_columns",
        "model_name",
        "model_version",
        "model_family",
        "dataset_branch",
    ]

    missing = [key for key in required_keys if key not in bundle]

    if missing:
        raise KeyError(
            "Model bundle is missing required keys: "
            f"{missing}"
        )

    if not hasattr(bundle["estimator"], "predict_proba"):
        raise TypeError(
            "The estimator inside the model bundle must support predict_proba()."
        )

    feature_columns = bundle["feature_columns"]

    if not isinstance(feature_columns, list):
        raise TypeError("bundle['feature_columns'] must be a list.")

    if not feature_columns:
        raise ValueError("bundle['feature_columns'] must not be empty.")

    if any(not isinstance(column, str) for column in feature_columns):
        raise TypeError("All feature columns in bundle['feature_columns'] must be strings.")

    return bundle


def load_model_bundle(path: Path) -> XAIModelBundle:
    raw_bundle = joblib.load(path)
    bundle = validate_model_bundle_dict(raw_bundle)

    model_name = str(bundle["model_name"])
    dataset_branch = str(bundle["dataset_branch"])

    if model_name != EXPECTED_BEST_MODEL_NAME:
        raise ValueError(
            "Loaded model is not the expected best model. "
            f"Expected {EXPECTED_BEST_MODEL_NAME!r}, got {model_name!r}."
        )

    if dataset_branch != EXPECTED_DATASET_BRANCH:
        raise ValueError(
            "Loaded model dataset branch is not expected. "
            f"Expected {EXPECTED_DATASET_BRANCH!r}, got {dataset_branch!r}."
        )

    feature_columns = list(bundle["feature_columns"])

    default_threshold = float(
        bundle.get("threshold", DEFAULT_THRESHOLD_FALLBACK)
    )

    return XAIModelBundle(
        bundle=bundle,
        estimator=bundle["estimator"],
        feature_columns=feature_columns,
        model_name=model_name,
        model_version=str(bundle["model_version"]),
        model_family=str(bundle["model_family"]),
        dataset_branch=dataset_branch,
        default_threshold=default_threshold,
        feature_count=len(feature_columns),
    )


def load_tree_feature_columns(
    path: Path = TREE_FEATURE_COLUMNS_PATH,
) -> list[str]:
    columns = read_json(path)

    if not isinstance(columns, list):
        raise TypeError("Tree feature columns registry must contain a list.")

    if not columns:
        raise ValueError("Tree feature columns registry is empty.")

    if any(not isinstance(column, str) for column in columns):
        raise TypeError("All tree feature columns must be strings.")

    return columns


def load_feature_mapping(
    path: Path = TREE_FEATURE_MAPPING_PATH,
) -> dict[str, Any]:
    mapping = read_json(path)

    if not isinstance(mapping, dict):
        raise TypeError("Feature mapping registry must contain a dictionary.")

    if not mapping:
        raise ValueError("Feature mapping registry is empty.")

    return mapping


def load_feature_registry(
    path: Path = FEATURE_REGISTRY_CSV_PATH,
) -> pd.DataFrame:
    dataframe = pd.read_csv(path)

    if dataframe.empty:
        raise ValueError(f"Feature registry CSV is empty: {path}")

    return dataframe


def load_concept_registry(
    path: Path = CONCEPT_REGISTRY_PATH,
) -> dict[str, Any]:
    registry = read_yaml(path)

    if not registry:
        raise ValueError(f"Concept registry is empty: {path}")

    return registry


def load_x_data(path: Path) -> pd.DataFrame:
    dataframe = pd.read_parquet(path)

    if dataframe.empty:
        raise ValueError(f"X data is empty: {path}")

    if ID_COLUMN in dataframe.columns:
        raise ValueError(
            f"X data must not contain ID column {ID_COLUMN!r}. "
            "ID must stay in y/predictions metadata, not model features."
        )

    if TARGET_COLUMN in dataframe.columns:
        raise ValueError(
            f"X data must not contain target column {TARGET_COLUMN!r}."
        )

    if dataframe.columns.duplicated().any():
        duplicated = dataframe.columns[dataframe.columns.duplicated()].tolist()
        raise ValueError(f"X data contains duplicated columns: {duplicated}")

    if np.isinf(dataframe.select_dtypes(include=[np.number])).any().any():
        raise ValueError("X data contains infinite numeric values.")

    return dataframe


def load_y_data(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None

    dataframe = pd.read_parquet(path)

    if dataframe.empty:
        raise ValueError(f"y data is empty: {path}")

    required_columns = [ID_COLUMN, TARGET_COLUMN]
    missing = [
        column for column in required_columns
        if column not in dataframe.columns
    ]

    if missing:
        raise ValueError(
            f"y data is missing required columns: {missing}"
        )

    if dataframe[ID_COLUMN].duplicated().any():
        raise ValueError(f"y data contains duplicated {ID_COLUMN} values.")

    return dataframe


def find_prediction_label_column(predictions: pd.DataFrame) -> str:
    exact_candidates = [
        "y_pred",
        "prediction",
        "predicted_label",
        "y_pred_default_threshold_0_5",
    ]

    for candidate in exact_candidates:
        if candidate in predictions.columns:
            return candidate

    prefix_candidates = [
        column
        for column in predictions.columns
        if column.startswith("y_pred")
    ]

    if prefix_candidates:
        return sorted(prefix_candidates)[0]

    raise ValueError(
        "Could not find prediction label column. Expected one of "
        "y_pred, prediction, predicted_label, or a column starting with y_pred."
    )


def find_prediction_probability_column(predictions: pd.DataFrame) -> str:
    exact_candidates = [
        "y_proba",
        "probability",
        "predicted_probability",
        "positive_class_probability",
        "proba_positive",
    ]

    for candidate in exact_candidates:
        if candidate in predictions.columns:
            return candidate

    probability_candidates = [
        column
        for column in predictions.columns
        if "proba" in column.lower() or "prob" in column.lower()
    ]

    if probability_candidates:
        return sorted(probability_candidates)[0]

    raise ValueError(
        "Could not find prediction probability column. Expected y_proba "
        "or another probability-like column."
    )


def normalize_predictions_columns(
    predictions: pd.DataFrame,
    *,
    require_y_true: bool,
) -> pd.DataFrame:
    predictions = predictions.copy()

    label_column = find_prediction_label_column(predictions)
    probability_column = find_prediction_probability_column(predictions)

    if label_column != "y_pred":
        predictions["y_pred"] = predictions[label_column]

    if probability_column != "y_proba":
        predictions["y_proba"] = predictions[probability_column]

    if require_y_true and "y_true" not in predictions.columns:
        raise ValueError(
            "Predictions must contain y_true in evaluation mode."
        )

    required_columns = [
        ID_COLUMN,
        "row_index",
        "y_proba",
        "y_pred",
    ]

    missing = [
        column for column in required_columns
        if column not in predictions.columns
    ]

    if missing:
        raise ValueError(
            f"Predictions are missing required columns: {missing}"
        )

    predictions[ID_COLUMN] = predictions[ID_COLUMN].astype(int)
    predictions["row_index"] = predictions["row_index"].astype(int)
    predictions["y_proba"] = predictions["y_proba"].astype(float)
    predictions["y_pred"] = predictions["y_pred"].astype(int)

    if "y_true" in predictions.columns:
        predictions["y_true"] = predictions["y_true"].astype(int)

    if not predictions["y_proba"].between(0, 1).all():
        raise ValueError("Predictions y_proba must be in [0, 1].")

    if predictions[ID_COLUMN].duplicated().any():
        raise ValueError(f"Predictions contain duplicated {ID_COLUMN} values.")

    return predictions


def load_predictions(
    path: Path,
    *,
    require_y_true: bool,
) -> pd.DataFrame:
    predictions = pd.read_csv(path)

    if predictions.empty:
        raise ValueError(f"Predictions file is empty: {path}")

    return normalize_predictions_columns(
        predictions,
        require_y_true=require_y_true,
    )


def validate_X_matches_model_features(
    *,
    X: pd.DataFrame,
    model_bundle: XAIModelBundle,
    tree_feature_columns: list[str],
) -> None:
    model_columns = model_bundle.feature_columns
    X_columns = X.columns.tolist()

    if X_columns != model_columns:
        raise ValueError(
            "X columns do not exactly match model feature columns. "
            "The order must be identical."
        )

    if model_columns != tree_feature_columns:
        raise ValueError(
            "Model bundle feature columns do not match tree feature columns registry."
        )

    if len(X_columns) != model_bundle.feature_count:
        raise ValueError(
            "X feature count does not match model bundle feature count. "
            f"{len(X_columns)} != {model_bundle.feature_count}"
        )


def validate_predictions_alignment(
    *,
    X: pd.DataFrame,
    y: pd.DataFrame | None,
    predictions: pd.DataFrame,
    run_mode: str,
    has_ground_truth: bool,
) -> None:
    if predictions["row_index"].min() < 0:
        raise ValueError("Predictions contain negative row_index values.")

    if predictions["row_index"].max() >= len(X):
        raise ValueError(
            "Predictions contain row_index values outside X row range. "
            f"Max row_index={predictions['row_index'].max()}, len(X)={len(X)}."
        )

    if has_ground_truth:
        if y is None:
            raise ValueError("Evaluation mode requires y data.")

        if len(X) != len(y):
            raise ValueError(
                f"X and y row counts do not match: {len(X)} != {len(y)}."
            )

        if "y_true" not in predictions.columns:
            raise ValueError("Evaluation mode requires y_true in predictions.")

        selected_y_ids = y.iloc[predictions["row_index"].to_numpy()][
            ID_COLUMN
        ].astype(int).to_numpy()

        prediction_ids = predictions[ID_COLUMN].astype(int).to_numpy()

        if not np.array_equal(selected_y_ids, prediction_ids):
            raise ValueError(
                "Prediction IDs do not align with y data by row_index."
            )

        selected_y_true = y.iloc[predictions["row_index"].to_numpy()][
            TARGET_COLUMN
        ].astype(int).to_numpy()

        prediction_y_true = predictions["y_true"].astype(int).to_numpy()

        if not np.array_equal(selected_y_true, prediction_y_true):
            raise ValueError(
                "Prediction y_true values do not align with y data by row_index."
            )

    else:
        if run_mode != RUN_MODE_INFERENCE:
            raise ValueError(
                "has_ground_truth=False is currently only valid for inference mode."
            )


def validate_loaded_inputs(inputs: XAIInputs) -> None:
    validate_run_mode(inputs.run_mode)

    validate_X_matches_model_features(
        X=inputs.X,
        model_bundle=inputs.model_bundle,
        tree_feature_columns=inputs.tree_feature_columns,
    )

    validate_predictions_alignment(
        X=inputs.X,
        y=inputs.y,
        predictions=inputs.predictions,
        run_mode=inputs.run_mode,
        has_ground_truth=inputs.has_ground_truth,
    )

    if len(inputs.feature_mapping) != inputs.model_bundle.feature_count:
        raise ValueError(
            "Feature mapping count does not match model feature count. "
            f"{len(inputs.feature_mapping)} != {inputs.model_bundle.feature_count}"
        )


def load_xai_inputs(
    run_mode: str | None = None,
) -> XAIInputs:
    run_mode = validate_run_mode(run_mode)
    has_ground_truth = mode_has_ground_truth(run_mode)

    validate_required_inputs_exist(run_mode)

    model_bundle = load_model_bundle(
        path=validate_required_inputs_exist.__globals__["BEST_MODEL_PATH"]
    )

    model_registry = load_model_registry()
    tree_feature_columns = load_tree_feature_columns()
    feature_mapping = load_feature_mapping()
    feature_registry = load_feature_registry()
    concept_registry = load_concept_registry()

    X = load_x_data(
        get_x_data_path_for_mode(run_mode)
    )

    y = load_y_data(
        get_y_data_path_for_mode(run_mode)
    )

    predictions = load_predictions(
        get_predictions_path_for_mode(run_mode),
        require_y_true=has_ground_truth,
    )

    inputs = XAIInputs(
        run_mode=run_mode,
        has_ground_truth=has_ground_truth,
        model_bundle=model_bundle,
        model_registry=model_registry,
        X=X,
        y=y,
        predictions=predictions,
        tree_feature_columns=tree_feature_columns,
        feature_mapping=feature_mapping,
        feature_registry=feature_registry,
        concept_registry=concept_registry,
    )

    validate_loaded_inputs(inputs)

    return inputs


def summarize_loaded_inputs(inputs: XAIInputs) -> dict[str, Any]:
    y_shape = None if inputs.y is None else list(inputs.y.shape)

    prediction_label_column = find_prediction_label_column(inputs.predictions)
    prediction_probability_column = find_prediction_probability_column(inputs.predictions)

    return {
        "run_mode": inputs.run_mode,
        "has_ground_truth": inputs.has_ground_truth,
        "model": {
            "model_name": inputs.model_bundle.model_name,
            "model_version": inputs.model_bundle.model_version,
            "model_family": inputs.model_bundle.model_family,
            "dataset_branch": inputs.model_bundle.dataset_branch,
            "estimator_type": type(inputs.model_bundle.estimator).__name__,
            "default_threshold": inputs.model_bundle.default_threshold,
            "feature_count": inputs.model_bundle.feature_count,
        },
        "data": {
            "X_shape": list(inputs.X.shape),
            "y_shape": y_shape,
            "predictions_shape": list(inputs.predictions.shape),
            "X_test_shape": list(inputs.X.shape),
            "y_test_shape": y_shape,
            "predictions_test_shape": list(inputs.predictions.shape),
            "tree_feature_columns_count": len(inputs.tree_feature_columns),
            "feature_mapping_count": len(inputs.feature_mapping),
            "feature_registry_shape": list(inputs.feature_registry.shape),
            "concept_registry_keys": list(inputs.concept_registry.keys()),
        },
        "predictions": {
            "prediction_label_column": prediction_label_column,
            "prediction_probability_column": prediction_probability_column,
            "y_proba_min": float(inputs.predictions["y_proba"].min()),
            "y_proba_max": float(inputs.predictions["y_proba"].max()),
            "y_proba_mean": float(inputs.predictions["y_proba"].mean()),
            "first_5_SK_ID_CURR": inputs.predictions[ID_COLUMN].head(5).tolist(),
            "has_y_true": "y_true" in inputs.predictions.columns,
        },
    }


__all__ = [
    "XAIModelBundle",
    "XAIInputs",
    "read_json",
    "read_yaml",
    "load_model_registry",
    "validate_model_bundle_dict",
    "load_model_bundle",
    "load_tree_feature_columns",
    "load_feature_mapping",
    "load_feature_registry",
    "load_concept_registry",
    "load_x_data",
    "load_y_data",
    "find_prediction_label_column",
    "find_prediction_probability_column",
    "normalize_predictions_columns",
    "load_predictions",
    "validate_X_matches_model_features",
    "validate_predictions_alignment",
    "validate_loaded_inputs",
    "load_xai_inputs",
    "summarize_loaded_inputs",
]