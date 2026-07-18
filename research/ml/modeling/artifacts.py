
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .config import (
    BATCH_NAME,
    BEST_MODEL_PATH,
    CONCEPT_REGISTRY_PATH,
    DEFAULT_THRESHOLD,
    LINEAR_FEATURE_COLUMNS_PATH,
    LINEAR_FEATURE_MAPPING_PATH,
    MODEL_FEATURE_IMPORTANCE_PATH,
    MODEL_METRICS_SUMMARY_PATH,
    MODEL_PREDICTIONS_TEST_PATH,
    MODEL_PREDICTIONS_VALID_PATH,
    MODEL_REGISTRY_PATH,
    MODEL_THRESHOLD_ANALYSIS_VALID_PATH,
    MODEL_TRAINING_MANIFEST_PATH,
    MODEL_VERSION,
    RAW_FEATURE_REGISTRY_CSV_PATH,
    RANDOM_STATE,
    SELECTION_PRIMARY_METRIC,
    SELECTION_SECONDARY_METRIC,
    SELECTION_TIEBREAKER_METRIC,
    TARGET_COLUMN,
    TREE_FEATURE_COLUMNS_PATH,
    TREE_FEATURE_MAPPING_PATH,
    ensure_output_dirs,
    get_output_paths,
    get_required_input_paths,
)
from .data_quality import QualityGateResult
from .evaluation import EvaluationResult
from .training import TrainingResult, TrainedModel


ARTIFACT_SCHEMA_VERSION = "1.0.0"
MODEL_ARTIFACT_TYPE = "sklearn_model_bundle"


# ============================================================
# Generic Helpers
# ============================================================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_jsonable(value: Any) -> Any:
    """
    Convert Python / numpy / pandas / Path objects to JSON-safe values.
    """

    if value is None:
        return None

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): to_jsonable(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [to_jsonable(item) for item in value]

    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]

    if isinstance(value, set):
        return sorted(to_jsonable(item) for item in value)

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, pd.Series):
        return value.tolist()

    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            to_jsonable(payload),
            file,
            indent=2,
            ensure_ascii=False,
        )


def write_dataframe(path: Path, df: pd.DataFrame) -> None:
    """
    Save dataframe by file extension.

    Supported:
        .csv
        .parquet
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    suffix = path.suffix.lower()

    if suffix == ".csv":
        df.to_csv(path, index=False)
        return

    if suffix == ".parquet":
        df.to_parquet(path, index=False)
        return

    raise ValueError(
        f"Unsupported dataframe output format: {path}. "
        f"Expected .csv or .parquet"
    )


# ============================================================
# Validation Helpers
# ============================================================

def infer_run_status(
    *,
    training_result: TrainingResult,
    quality_result: QualityGateResult | None,
) -> str:
    if quality_result is not None and quality_result.status != "passed":
        return "failed_quality_gate"

    if training_result.errors:
        return "failed_training"

    if not training_result.trained_models:
        return "failed_no_trained_models"

    return "passed"


def validate_artifact_inputs(
    *,
    training_result: TrainingResult,
    evaluation_result: EvaluationResult,
) -> None:
    if not training_result.trained_models:
        raise ValueError("No trained models available to save")

    trained_model_names = {
        trained_model.model_name
        for trained_model in training_result.trained_models
    }

    best_model_name = evaluation_result.best_model.model_name

    if best_model_name not in trained_model_names:
        raise ValueError(
            f"Best model {best_model_name} is not present in training_result"
        )

    if evaluation_result.metrics_df.empty:
        raise ValueError("evaluation_result.metrics_df is empty")

    if evaluation_result.valid_predictions_df.empty:
        raise ValueError("evaluation_result.valid_predictions_df is empty")

    if evaluation_result.test_predictions_df.empty:
        raise ValueError("evaluation_result.test_predictions_df is empty")


# ============================================================
# Branch Registry Helpers
# ============================================================

def get_feature_columns_path_for_branch(dataset_branch: str) -> str:
    if dataset_branch == "linear":
        return str(LINEAR_FEATURE_COLUMNS_PATH)

    if dataset_branch == "tree":
        return str(TREE_FEATURE_COLUMNS_PATH)

    raise ValueError(f"Unknown dataset_branch: {dataset_branch}")


def get_feature_mapping_path_for_branch(dataset_branch: str) -> str:
    if dataset_branch == "linear":
        return str(LINEAR_FEATURE_MAPPING_PATH)

    if dataset_branch == "tree":
        return str(TREE_FEATURE_MAPPING_PATH)

    raise ValueError(f"Unknown dataset_branch: {dataset_branch}")


# ============================================================
# Model Artifact Helpers
# ============================================================

def get_artifact_path_for_model(trained_model: TrainedModel) -> Path:
    """
    Resolve artifact path for one model from config.get_output_paths().
    """

    output_paths = get_output_paths()

    if trained_model.model_name == "logistic_regression":
        return output_paths["logistic_regression_model"]

    if trained_model.model_name == "random_forest":
        return output_paths["random_forest_model"]

    if trained_model.model_name == "hist_gradient_boosting":
        return output_paths["hist_gradient_boosting_model"]

    raise ValueError(
        f"Unknown model_name for artifact path: {trained_model.model_name}"
    )


def build_model_artifact_bundle(
    *,
    trained_model: TrainedModel,
    created_at: str,
    selected_as_best: bool,
) -> dict[str, Any]:
    """
    Build a complete model artifact bundle.

    Important:
        We do not save estimator only.
        We save estimator + metadata + feature schema.

    This makes inference safer.
    """

    return {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": MODEL_ARTIFACT_TYPE,
        "created_at": created_at,
        "batch_name": BATCH_NAME,
        "task_type": "binary_classification",
        "target_column": TARGET_COLUMN,
        "positive_class": 1,
        "negative_class": 0,
        "model_name": trained_model.model_name,
        "model_version": MODEL_VERSION,
        "model_family": trained_model.model_family,
        "dataset_branch": trained_model.dataset_branch,
        "selected_as_best": selected_as_best,
        "default_threshold": DEFAULT_THRESHOLD,
        "random_state": RANDOM_STATE,
        "feature_columns": list(trained_model.feature_columns),
        "feature_count": trained_model.feature_count,
        "train_rows": trained_model.train_rows,
        "training_seconds": trained_model.training_seconds,
        "metadata": to_jsonable(trained_model.metadata),
        "estimator": trained_model.estimator,
    }


def save_model_bundle(
    *,
    trained_model: TrainedModel,
    artifact_path: Path,
    created_at: str,
    selected_as_best: bool,
) -> str:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    bundle = build_model_artifact_bundle(
        trained_model=trained_model,
        created_at=created_at,
        selected_as_best=selected_as_best,
    )

    joblib.dump(bundle, artifact_path)

    return str(artifact_path)


def save_trained_model_artifacts(
    *,
    training_result: TrainingResult,
    evaluation_result: EvaluationResult,
    created_at: str,
) -> dict[str, str]:
    """
    Save every trained model as .joblib bundle.

    Returns:
        model_name -> artifact_path
    """

    saved_model_paths: dict[str, str] = {}

    best_model_name = evaluation_result.best_model.model_name

    for trained_model in training_result.trained_models:
        artifact_path = get_artifact_path_for_model(trained_model)

        saved_path = save_model_bundle(
            trained_model=trained_model,
            artifact_path=artifact_path,
            created_at=created_at,
            selected_as_best=trained_model.model_name == best_model_name,
        )

        saved_model_paths[trained_model.model_name] = saved_path

    return saved_model_paths


def save_best_model_artifact(
    *,
    best_model: TrainedModel,
    saved_model_paths: dict[str, str],
    created_at: str,
) -> str:
    """
    Save best_model.joblib.

    Prefer copying already saved bundle.
    If source does not exist, dump a fresh bundle.
    """

    BEST_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    source_path_str = saved_model_paths.get(best_model.model_name)

    if source_path_str:
        source_path = Path(source_path_str)

        if source_path.exists():
            shutil.copy2(source_path, BEST_MODEL_PATH)
            return str(BEST_MODEL_PATH)

    return save_model_bundle(
        trained_model=best_model,
        artifact_path=BEST_MODEL_PATH,
        created_at=created_at,
        selected_as_best=True,
    )


def load_model_artifact(path: Path) -> dict[str, Any]:
    """
    Load model artifact bundle.

    Future inference layer can use this helper.
    """

    artifact = joblib.load(path)

    if not isinstance(artifact, dict):
        raise TypeError(
            f"Invalid model artifact at {path}. "
            f"Expected dict bundle, got {type(artifact).__name__}"
        )

    required_keys = [
        "artifact_schema_version",
        "artifact_type",
        "model_name",
        "model_version",
        "dataset_branch",
        "feature_columns",
        "estimator",
    ]

    missing_keys = [
        key
        for key in required_keys
        if key not in artifact
    ]

    if missing_keys:
        raise ValueError(
            f"Invalid model artifact at {path}. "
            f"Missing keys: {missing_keys}"
        )

    if artifact["artifact_type"] != MODEL_ARTIFACT_TYPE:
        raise ValueError(
            f"Invalid artifact_type at {path}: {artifact['artifact_type']}"
        )

    return artifact


# ============================================================
# DataFrame Artifact Saving
# ============================================================

def save_dataframe_artifacts(
    *,
    evaluation_result: EvaluationResult,
) -> dict[str, str]:
    """
    Save evaluation dataframes.

    These files replace the Markdown report.
    They are machine-readable and safer for pipeline usage.
    """

    write_dataframe(
        MODEL_METRICS_SUMMARY_PATH,
        evaluation_result.metrics_df,
    )

    write_dataframe(
        MODEL_PREDICTIONS_VALID_PATH,
        evaluation_result.valid_predictions_df,
    )

    write_dataframe(
        MODEL_PREDICTIONS_TEST_PATH,
        evaluation_result.test_predictions_df,
    )

    write_dataframe(
        MODEL_THRESHOLD_ANALYSIS_VALID_PATH,
        evaluation_result.threshold_analysis_df,
    )

    write_dataframe(
        MODEL_FEATURE_IMPORTANCE_PATH,
        evaluation_result.feature_importance_df,
    )

    return {
        "model_metrics_summary": str(MODEL_METRICS_SUMMARY_PATH),
        "model_predictions_valid": str(MODEL_PREDICTIONS_VALID_PATH),
        "model_predictions_test": str(MODEL_PREDICTIONS_TEST_PATH),
        "model_threshold_analysis_valid": str(MODEL_THRESHOLD_ANALYSIS_VALID_PATH),
        "model_feature_importance": str(MODEL_FEATURE_IMPORTANCE_PATH),
    }


# ============================================================
# Model Registry
# ============================================================

def build_model_registry_payload(
    *,
    training_result: TrainingResult,
    evaluation_result: EvaluationResult,
    saved_model_paths: dict[str, str],
    best_model_path: str,
    dataframe_paths: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    valid_metrics_by_model = {
        evaluation.model_name: evaluation.metrics
        for evaluation in evaluation_result.valid_evaluations
    }

    test_metrics_by_model = {
        evaluation_result.best_model.model_name:
        evaluation_result.best_test_evaluation.metrics
    }

    models_payload: list[dict[str, Any]] = []

    for trained_model in training_result.trained_models:
        selected_as_best = (
            trained_model.model_name == evaluation_result.best_model.model_name
        )

        models_payload.append(
            {
                "model_name": trained_model.model_name,
                "model_version": MODEL_VERSION,
                "model_family": trained_model.model_family,
                "dataset_branch": trained_model.dataset_branch,
                "artifact_path": saved_model_paths.get(trained_model.model_name),
                "best_model_artifact_path": (
                    best_model_path if selected_as_best else None
                ),
                "feature_columns_path": get_feature_columns_path_for_branch(
                    trained_model.dataset_branch
                ),
                "feature_mapping_path": get_feature_mapping_path_for_branch(
                    trained_model.dataset_branch
                ),
                "train_rows": trained_model.train_rows,
                "feature_count": trained_model.feature_count,
                "training_seconds": trained_model.training_seconds,
                "metadata": to_jsonable(trained_model.metadata),
                "valid_metrics": to_jsonable(
                    valid_metrics_by_model.get(trained_model.model_name)
                ),
                "test_metrics": to_jsonable(
                    test_metrics_by_model.get(trained_model.model_name)
                ),
                "selected_as_best": selected_as_best,
            }
        )

    return {
        "created_at": created_at,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "batch_name": BATCH_NAME,
        "task_type": "binary_classification",
        "target_column": TARGET_COLUMN,
        "positive_class": 1,
        "negative_class": 0,
        "model_version": MODEL_VERSION,
        "random_state": RANDOM_STATE,
        "default_threshold": DEFAULT_THRESHOLD,
        "selection_policy": {
            "primary_metric": SELECTION_PRIMARY_METRIC,
            "secondary_metric": SELECTION_SECONDARY_METRIC,
            "tiebreaker_metric": SELECTION_TIEBREAKER_METRIC,
            "tiebreaker_direction": "lower_is_better",
            "selection_split": "valid",
        },
        "best_model": {
            "model_name": evaluation_result.best_model.model_name,
            "model_family": evaluation_result.best_model.model_family,
            "dataset_branch": evaluation_result.best_model.dataset_branch,
            "artifact_path": best_model_path,
            "valid_metrics": to_jsonable(
                evaluation_result.best_valid_evaluation.metrics
            ),
            "test_metrics": to_jsonable(
                evaluation_result.best_test_evaluation.metrics
            ),
        },
        "models": models_payload,
        "evaluation_outputs": dataframe_paths,
        "upstream_registries": {
            "raw_feature_registry_csv": str(RAW_FEATURE_REGISTRY_CSV_PATH),
            "concept_registry": str(CONCEPT_REGISTRY_PATH),
        },
    }


def save_model_registry(
    *,
    training_result: TrainingResult,
    evaluation_result: EvaluationResult,
    saved_model_paths: dict[str, str],
    best_model_path: str,
    dataframe_paths: dict[str, str],
    created_at: str,
) -> str:
    payload = build_model_registry_payload(
        training_result=training_result,
        evaluation_result=evaluation_result,
        saved_model_paths=saved_model_paths,
        best_model_path=best_model_path,
        dataframe_paths=dataframe_paths,
        created_at=created_at,
    )

    write_json(MODEL_REGISTRY_PATH, payload)

    return str(MODEL_REGISTRY_PATH)


# ============================================================
# Manifest
# ============================================================

def build_manifest_payload(
    *,
    training_result: TrainingResult,
    evaluation_result: EvaluationResult,
    quality_result: QualityGateResult | None,
    saved_model_paths: dict[str, str],
    best_model_path: str,
    dataframe_paths: dict[str, str],
    model_registry_path: str,
    created_at: str,
) -> dict[str, Any]:
    output_paths = get_output_paths()
    input_paths = get_required_input_paths()

    run_status = infer_run_status(
        training_result=training_result,
        quality_result=quality_result,
    )

    quality_gate_payload = None

    if quality_result is not None:
        quality_gate_payload = {
            "status": quality_result.status,
            "check_count": len(quality_result.checks),
            "error_count": len(quality_result.errors),
            "warning_count": len(quality_result.warnings),
            "errors": quality_result.errors,
            "warnings": quality_result.warnings,
        }

    return {
        "created_at": created_at,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "batch_name": BATCH_NAME,
        "status": run_status,
        "script": "ml/scripts/model_layer/run_f_model_training_layer.py",
        "random_state": RANDOM_STATE,
        "model_version": MODEL_VERSION,
        "target_column": TARGET_COLUMN,
        "quality_gate": quality_gate_payload,
        "models_trained": [
            trained_model.model_name
            for trained_model in training_result.trained_models
        ],
        "models_skipped": training_result.skipped_models,
        "training_errors": training_result.errors,
        "best_model": {
            "model_name": evaluation_result.best_model.model_name,
            "model_family": evaluation_result.best_model.model_family,
            "dataset_branch": evaluation_result.best_model.dataset_branch,
            "artifact_path": best_model_path,
            "valid_metrics": to_jsonable(
                evaluation_result.best_valid_evaluation.metrics
            ),
            "test_metrics": to_jsonable(
                evaluation_result.best_test_evaluation.metrics
            ),
        },
        "selection_policy": {
            "primary_metric": SELECTION_PRIMARY_METRIC,
            "secondary_metric": SELECTION_SECONDARY_METRIC,
            "tiebreaker_metric": SELECTION_TIEBREAKER_METRIC,
            "tiebreaker_direction": "lower_is_better",
            "selection_split": "valid",
        },
        "input_files": {
            name: str(path)
            for name, path in input_paths.items()
        },
        "configured_output_files": {
            name: str(path)
            for name, path in output_paths.items()
        },
        "saved_model_paths": saved_model_paths,
        "best_model_path": best_model_path,
        "dataframe_paths": dataframe_paths,
        "model_registry_path": model_registry_path,
    }


def save_manifest(
    *,
    training_result: TrainingResult,
    evaluation_result: EvaluationResult,
    quality_result: QualityGateResult | None,
    saved_model_paths: dict[str, str],
    best_model_path: str,
    dataframe_paths: dict[str, str],
    model_registry_path: str,
    created_at: str,
) -> str:
    payload = build_manifest_payload(
        training_result=training_result,
        evaluation_result=evaluation_result,
        quality_result=quality_result,
        saved_model_paths=saved_model_paths,
        best_model_path=best_model_path,
        dataframe_paths=dataframe_paths,
        model_registry_path=model_registry_path,
        created_at=created_at,
    )

    write_json(MODEL_TRAINING_MANIFEST_PATH, payload)

    return str(MODEL_TRAINING_MANIFEST_PATH)


# ============================================================
# Main Artifact Orchestration
# ============================================================

def save_all_model_artifacts(
    *,
    training_result: TrainingResult,
    evaluation_result: EvaluationResult,
    quality_result: QualityGateResult | None = None,
) -> dict[str, Any]:
    """
    Main artifact saving function.

    This should be called by the final model-layer pipeline.

    Saves:
        1. All model .joblib bundles
        2. Best model .joblib bundle
        3. Metrics dataframe
        4. Valid predictions dataframe
        5. Test predictions dataframe
        6. Threshold analysis dataframe
        7. Feature importance dataframe
        8. model_registry.json
        9. model_training_manifest.json

    No Markdown report is generated.
    """

    validate_artifact_inputs(
        training_result=training_result,
        evaluation_result=evaluation_result,
    )

    created_at = utc_now_iso()

    ensure_output_dirs()

    saved_model_paths = save_trained_model_artifacts(
        training_result=training_result,
        evaluation_result=evaluation_result,
        created_at=created_at,
    )

    best_model_path = save_best_model_artifact(
        best_model=evaluation_result.best_model,
        saved_model_paths=saved_model_paths,
        created_at=created_at,
    )

    dataframe_paths = save_dataframe_artifacts(
        evaluation_result=evaluation_result,
    )

    model_registry_path = save_model_registry(
        training_result=training_result,
        evaluation_result=evaluation_result,
        saved_model_paths=saved_model_paths,
        best_model_path=best_model_path,
        dataframe_paths=dataframe_paths,
        created_at=created_at,
    )

    manifest_path = save_manifest(
        training_result=training_result,
        evaluation_result=evaluation_result,
        quality_result=quality_result,
        saved_model_paths=saved_model_paths,
        best_model_path=best_model_path,
        dataframe_paths=dataframe_paths,
        model_registry_path=model_registry_path,
        created_at=created_at,
    )

    return {
        "created_at": created_at,
        "status": infer_run_status(
            training_result=training_result,
            quality_result=quality_result,
        ),
        "saved_model_paths": saved_model_paths,
        "best_model_path": best_model_path,
        "dataframe_paths": dataframe_paths,
        "model_registry_path": model_registry_path,
        "manifest_path": manifest_path,
    }


