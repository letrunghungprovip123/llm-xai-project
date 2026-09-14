from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..modeling.data_quality import DatasetBranch, ModelReadyDatasets
from ..modeling.evaluation import (
    ModelEvaluation,
    compute_binary_classification_metrics,
    get_feature_importance_for_model,
    select_best_model,
)
from ..modeling.training import TrainedModel
from .context import CommonMLRunContext
from .split import CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN


RANDOM_STATE = 42
DEFAULT_THRESHOLD = 0.5
MODEL_VERSION = "v1"
THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]


@dataclass(frozen=True)
class CommonModelingResult:
    manifest_path: Path
    best_model_path: Path
    best_model_name: str
    best_model_branch: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _load_branch(ctx: CommonMLRunContext, branch: str) -> DatasetBranch:
    directory = ctx.paths.processed_dir / "model_ready" / branch
    suffix = "tree" if branch == "tree" else "linear"
    X_train = pd.read_parquet(directory / f"X_train_{suffix}.parquet")
    X_valid = pd.read_parquet(directory / f"X_valid_{suffix}.parquet")
    X_test = pd.read_parquet(directory / f"X_test_{suffix}.parquet")
    y_train = pd.read_parquet(directory / "y_train.parquet")
    y_valid = pd.read_parquet(directory / "y_valid.parquet")
    y_test = pd.read_parquet(directory / "y_test.parquet")
    feature_columns = [
        str(item)
        for item in _read_json(ctx.paths.registry_dir / f"preprocessed_feature_columns_{branch}.json")
    ]
    return DatasetBranch(
        name=branch,
        X_train=X_train,
        X_valid=X_valid,
        X_test=X_test,
        y_train=y_train,
        y_valid=y_valid,
        y_test=y_test,
        feature_columns=feature_columns,
    )


def _validate_branch(branch: DatasetBranch, target_column: str) -> list[str]:
    errors: list[str] = []
    expected = branch.feature_columns
    for split, X, y in (
        ("train", branch.X_train, branch.y_train),
        ("valid", branch.X_valid, branch.y_valid),
        ("test", branch.X_test, branch.y_test),
    ):
        if list(X.columns) != expected:
            errors.append(f"{branch.name}/{split}: X columns do not match registry")
        if len(X) != len(y):
            errors.append(f"{branch.name}/{split}: X/y row mismatch")
        forbidden = [
            column
            for column in (CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN, target_column)
            if column in X.columns
        ]
        if forbidden:
            errors.append(f"{branch.name}/{split}: forbidden columns in X: {forbidden}")
        if int(X.isna().sum().sum()) != 0:
            errors.append(f"{branch.name}/{split}: missing values in X")
        numeric = X.select_dtypes(include=[np.number])
        if numeric.shape[1] != X.shape[1]:
            errors.append(f"{branch.name}/{split}: non-numeric model-ready columns remain")
        if np.isinf(numeric.to_numpy()).any():
            errors.append(f"{branch.name}/{split}: infinite values in X")
        if target_column not in y.columns:
            errors.append(f"{branch.name}/{split}: target column missing")
        elif sorted(y[target_column].dropna().unique().tolist()) != [0, 1]:
            errors.append(f"{branch.name}/{split}: canonical target is not [0, 1]")
        for identity in (CASE_ID_COLUMN, SOURCE_ENTITY_ID_COLUMN):
            if identity not in y.columns:
                errors.append(f"{branch.name}/{split}: y missing {identity}")
    return errors


def _target(branch: DatasetBranch, split: str, target_column: str) -> pd.Series:
    y = getattr(branch, f"y_{split}")
    return y[target_column].astype(int)


def _train_model(model_name: str, branch: DatasetBranch, target_column: str) -> TrainedModel:
    X_train = branch.X_train
    y_train = _target(branch, "train", target_column)

    if model_name == "logistic_regression":
        from sklearn.linear_model import LogisticRegression

        estimator = LogisticRegression(
            class_weight="balanced",
            max_iter=2000,
            solver="lbfgs",
            random_state=RANDOM_STATE,
        )
        family = "linear"
        metadata = {
            "algorithm": "LogisticRegression",
            "class_imbalance_strategy": "class_weight='balanced'",
            "solver": "lbfgs",
            "max_iter": 2000,
            "random_state": RANDOM_STATE,
        }
    elif model_name == "random_forest":
        from sklearn.ensemble import RandomForestClassifier

        estimator = RandomForestClassifier(
            n_estimators=300,
            max_depth=None,
            min_samples_leaf=20,
            class_weight="balanced_subsample",
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )
        family = "tree"
        metadata = {
            "algorithm": "RandomForestClassifier",
            "n_estimators": 300,
            "max_depth": None,
            "min_samples_leaf": 20,
            "class_imbalance_strategy": "class_weight='balanced_subsample'",
            "random_state": RANDOM_STATE,
        }
    elif model_name == "hist_gradient_boosting":
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.utils.class_weight import compute_sample_weight

        estimator = HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_iter=300,
            max_leaf_nodes=31,
            l2_regularization=0.1,
            random_state=RANDOM_STATE,
        )
        sample_weight = compute_sample_weight(class_weight="balanced", y=y_train)
        family = "tree_boosting"
        metadata = {
            "algorithm": "HistGradientBoostingClassifier",
            "learning_rate": 0.05,
            "max_iter": 300,
            "max_leaf_nodes": 31,
            "l2_regularization": 0.1,
            "class_imbalance_strategy": "sample_weight=balanced",
            "random_state": RANDOM_STATE,
        }
    else:
        raise ValueError(f"Unsupported common model: {model_name}")

    start = time.perf_counter()
    if model_name == "hist_gradient_boosting":
        estimator.fit(X_train, y_train, sample_weight=sample_weight)
    else:
        estimator.fit(X_train, y_train)
    elapsed = time.perf_counter() - start
    return TrainedModel(
        model_name=model_name,
        model_family=family,
        dataset_branch=branch.name,
        estimator=estimator,
        feature_columns=list(X_train.columns),
        training_seconds=elapsed,
        train_rows=len(X_train),
        feature_count=X_train.shape[1],
        metadata=metadata,
    )


def _predict_positive(model: TrainedModel, X: pd.DataFrame) -> np.ndarray:
    proba = model.estimator.predict_proba(X)
    if proba.ndim != 2 or proba.shape[1] < 2:
        raise ValueError(f"{model.model_name}: predict_proba does not expose positive class")
    return np.asarray(proba[:, 1], dtype=float)


def _prediction_frame(
    *,
    ctx: CommonMLRunContext,
    model: TrainedModel,
    branch: DatasetBranch,
    split: str,
    target_column: str,
    y_proba: np.ndarray,
) -> pd.DataFrame:
    y_df = getattr(branch, f"y_{split}").reset_index(drop=True)
    y_true = y_df[target_column].astype(int)
    y_pred = (y_proba >= DEFAULT_THRESHOLD).astype(int)
    return pd.DataFrame(
        {
            CASE_ID_COLUMN: y_df[CASE_ID_COLUMN].astype(str),
            SOURCE_ENTITY_ID_COLUMN: y_df[SOURCE_ENTITY_ID_COLUMN].astype(str),
            "row_index": np.arange(len(y_df)),
            "y_true": y_true,
            "y_proba": y_proba,
            "y_pred_default_threshold_0_5": y_pred,
            "split": split,
            "model_name": model.model_name,
            "model_version": MODEL_VERSION,
            "model_family": model.model_family,
            "dataset_branch": model.dataset_branch,
            "threshold": DEFAULT_THRESHOLD,
            "dataset_id": ctx.profile.dataset_id,
            "dataset_fingerprint": ctx.bundle.dataset_fingerprint,
        }
    )


def _evaluate(
    *,
    ctx: CommonMLRunContext,
    model: TrainedModel,
    branch: DatasetBranch,
    split: str,
    target_column: str,
) -> ModelEvaluation:
    X = getattr(branch, f"X_{split}")
    y_true = _target(branch, split, target_column)
    y_proba = _predict_positive(model, X)
    metrics = compute_binary_classification_metrics(
        y_true=y_true,
        y_proba=y_proba,
        threshold=DEFAULT_THRESHOLD,
    )
    predictions = _prediction_frame(
        ctx=ctx,
        model=model,
        branch=branch,
        split=split,
        target_column=target_column,
        y_proba=y_proba,
    )
    return ModelEvaluation(
        model_name=model.model_name,
        model_family=model.model_family,
        dataset_branch=model.dataset_branch,
        split=split,
        metrics=metrics,
        predictions=predictions,
    )


def _bundle_payload(ctx: CommonMLRunContext, model: TrainedModel, target_column: str) -> dict[str, Any]:
    return {
        "artifact_schema_version": "common_ml_model_bundle_v1",
        "artifact_type": "sklearn_model_bundle",
        "estimator": model.estimator,
        "feature_columns": model.feature_columns,
        "model_name": model.model_name,
        "model_version": MODEL_VERSION,
        "model_family": model.model_family,
        "dataset_branch": model.dataset_branch,
        "threshold": DEFAULT_THRESHOLD,
        "target_column": target_column,
        "id_column": CASE_ID_COLUMN,
        "source_entity_id_column": SOURCE_ENTITY_ID_COLUMN,
        "dataset_id": ctx.profile.dataset_id,
        "dataset_version": ctx.profile.dataset_version,
        "dataset_fingerprint": ctx.bundle.dataset_fingerprint,
        "experiment_id": ctx.experiment_id,
        "run_id": ctx.run_id,
        "training_metadata": model.metadata,
    }


def run_common_modeling(ctx: CommonMLRunContext) -> CommonModelingResult:
    ctx.create_workspace()
    preprocessing_manifest = ctx.paths.manifest_dir / "common_ml_preprocessing_manifest.json"
    if not preprocessing_manifest.is_file():
        raise FileNotFoundError("Run common preprocessing before common modeling")

    target_column = str(_read_json(ctx.paths.registry_dir / "target_column.json"))
    linear = _load_branch(ctx, "linear")
    tree = _load_branch(ctx, "tree")
    datasets = ModelReadyDatasets(linear=linear, tree=tree)

    quality_errors = _validate_branch(linear, target_column) + _validate_branch(tree, target_column)
    if quality_errors:
        raise RuntimeError(f"Common modeling quality gate failed: {quality_errors}")

    model_specs = [
        ("logistic_regression", datasets.linear),
        ("random_forest", datasets.tree),
        ("hist_gradient_boosting", datasets.tree),
    ]
    trained: list[TrainedModel] = []
    valid_evaluations: list[ModelEvaluation] = []
    for name, branch in model_specs:
        model = _train_model(name, branch, target_column)
        trained.append(model)
        valid_evaluations.append(
            _evaluate(ctx=ctx, model=model, branch=branch, split="valid", target_column=target_column)
        )

    best_model, best_valid = select_best_model(
        trained_models=trained,
        valid_evaluations=valid_evaluations,
    )
    best_branch = datasets.linear if best_model.dataset_branch == "linear" else datasets.tree
    best_test = _evaluate(
        ctx=ctx,
        model=best_model,
        branch=best_branch,
        split="test",
        target_column=target_column,
    )

    model_dir = ctx.paths.artifact_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    import joblib

    model_paths: dict[str, str] = {}
    for model in trained:
        path = model_dir / f"{model.model_name}.joblib"
        joblib.dump(_bundle_payload(ctx, model, target_column), path)
        model_paths[model.model_name] = str(path)
    best_model_path = model_dir / "best_model.joblib"
    joblib.dump(_bundle_payload(ctx, best_model, target_column), best_model_path)

    metric_rows: list[dict[str, Any]] = []
    for evaluation in [*valid_evaluations, best_test]:
        model = next(item for item in trained if item.model_name == evaluation.model_name)
        metric_rows.append(
            {
                "dataset_id": ctx.profile.dataset_id,
                "model_name": evaluation.model_name,
                "model_version": MODEL_VERSION,
                "model_family": evaluation.model_family,
                "dataset_branch": evaluation.dataset_branch,
                "split": evaluation.split,
                "train_rows": model.train_rows,
                "feature_count": model.feature_count,
                "training_seconds": model.training_seconds,
                **evaluation.metrics,
            }
        )
    metrics_df = pd.DataFrame(metric_rows)
    metrics_path = ctx.paths.report_dir / "model_metrics_summary.csv"
    metrics_df.to_csv(metrics_path, index=False)

    valid_predictions = pd.concat(
        [evaluation.predictions for evaluation in valid_evaluations], ignore_index=True
    )
    valid_predictions_path = ctx.paths.report_dir / "model_predictions_valid.csv"
    valid_predictions.to_csv(valid_predictions_path, index=False)
    test_predictions_path = ctx.paths.report_dir / "model_predictions_test.csv"
    best_test.predictions.to_csv(test_predictions_path, index=False)

    threshold_rows: list[dict[str, Any]] = []
    for model, evaluation in zip(trained, valid_evaluations):
        y_true = _target(
            datasets.linear if model.dataset_branch == "linear" else datasets.tree,
            "valid",
            target_column,
        )
        y_proba = evaluation.predictions["y_proba"].to_numpy()
        for threshold in THRESHOLDS:
            threshold_rows.append(
                {
                    "dataset_id": ctx.profile.dataset_id,
                    "model_name": model.model_name,
                    "model_version": MODEL_VERSION,
                    "model_family": model.model_family,
                    "dataset_branch": model.dataset_branch,
                    "split": "valid",
                    **compute_binary_classification_metrics(
                        y_true=y_true,
                        y_proba=y_proba,
                        threshold=threshold,
                    ),
                }
            )
    threshold_path = ctx.paths.report_dir / "model_threshold_analysis_valid.csv"
    pd.DataFrame(threshold_rows).to_csv(threshold_path, index=False)

    importance = get_feature_importance_for_model(best_model)
    importance_path = ctx.paths.report_dir / "model_feature_importance.csv"
    importance.to_csv(importance_path, index=False)

    registry_payload = {
        "schema_version": "common_ml_model_registry_v1",
        **ctx.common_provenance(),
        "target_column": target_column,
        "selection_policy": {
            "primary": "average_precision",
            "secondary": "roc_auc",
            "tiebreaker": "brier_score_lower_is_better",
        },
        "models": [
            {
                "model_name": model.model_name,
                "model_family": model.model_family,
                "dataset_branch": model.dataset_branch,
                "feature_count": model.feature_count,
                "artifact_path": model_paths[model.model_name],
            }
            for model in trained
        ],
        "best_model": {
            "model_name": best_model.model_name,
            "model_family": best_model.model_family,
            "dataset_branch": best_model.dataset_branch,
            "artifact_path": str(best_model_path),
            "valid_metrics": best_valid.metrics,
            "test_metrics": best_test.metrics,
        },
    }
    model_registry_path = ctx.paths.registry_dir / "model_registry.json"
    _write_json(model_registry_path, registry_payload)

    manifest = {
        "schema_version": "common_ml_model_training_manifest_v1",
        "created_at_utc": _utc_now(),
        **ctx.common_provenance(),
        "quality_gate": "passed",
        "target_column": target_column,
        "model_portfolio": ["logistic_regression", "random_forest", "hist_gradient_boosting"],
        "selection_policy": registry_payload["selection_policy"],
        "best_model": registry_payload["best_model"],
        "outputs": {
            "best_model": str(best_model_path),
            "model_registry": str(model_registry_path),
            "metrics": str(metrics_path),
            "valid_predictions": str(valid_predictions_path),
            "test_predictions": str(test_predictions_path),
            "threshold_analysis": str(threshold_path),
            "feature_importance": str(importance_path),
        },
        "status": "passed",
    }
    manifest_path = ctx.paths.manifest_dir / "common_ml_model_training_manifest.json"
    _write_json(manifest_path, manifest)
    return CommonModelingResult(
        manifest_path=manifest_path,
        best_model_path=best_model_path,
        best_model_name=best_model.model_name,
        best_model_branch=best_model.dataset_branch,
    )
