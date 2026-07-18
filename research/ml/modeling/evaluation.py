from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from .config import (
    DEFAULT_THRESHOLD,
    MODEL_VERSION,
    SELECTION_PRIMARY_METRIC,
    SELECTION_SECONDARY_METRIC,
    SELECTION_TIEBREAKER_METRIC,
    THRESHOLDS_FOR_ANALYSIS,
)
from .data_quality import (
    DatasetBranch,
    ModelReadyDatasets,
    extract_ids_or_row_index,
    extract_target,
)
from .training import TrainedModel


# ============================================================
# Evaluation Result Containers
# ============================================================

@dataclass(frozen=True)
class ModelEvaluation:
    """
    Kết quả đánh giá một model trên một split cụ thể.

    Ví dụ:
        logistic_regression trên valid
        random_forest trên valid
        best_model trên test

    metrics:
        Dict chứa ROC-AUC, Average Precision, Precision, Recall, F1,
        Brier Score, Confusion Matrix.

    predictions:
        DataFrame chứa y_true, y_proba, y_pred và metadata.
    """

    model_name: str
    model_family: str
    dataset_branch: str
    split: str
    metrics: dict[str, Any]
    predictions: pd.DataFrame


@dataclass(frozen=True)
class EvaluationResult:
    """
    Kết quả đánh giá toàn bộ models.

    valid_evaluations:
        Evaluation của tất cả model trên validation set.

    best_model:
        Model được chọn theo validation metrics.

    best_valid_evaluation:
        Kết quả validation của best model.

    best_test_evaluation:
        Kết quả test của best model.

    metrics_df:
        Bảng metrics chuẩn để lưu CSV/report.

    valid_predictions_df:
        Prediction của tất cả model trên valid.

    test_predictions_df:
        Prediction của best model trên test.

    threshold_analysis_df:
        Phân tích nhiều threshold trên validation set.

    feature_importance_df:
        Global feature importance nếu model hỗ trợ.
    """

    valid_evaluations: list[ModelEvaluation]
    best_model: TrainedModel
    best_valid_evaluation: ModelEvaluation
    best_test_evaluation: ModelEvaluation
    metrics_df: pd.DataFrame
    valid_predictions_df: pd.DataFrame
    test_predictions_df: pd.DataFrame
    threshold_analysis_df: pd.DataFrame
    feature_importance_df: pd.DataFrame


# ============================================================
# Dataset Branch Helpers
# ============================================================

def get_branch_for_trained_model(
    *,
    datasets: ModelReadyDatasets,
    trained_model: TrainedModel,
) -> DatasetBranch:
    """
    Lấy đúng data branch cho model đã train.

    Nếu model được train bằng linear branch:
        dùng X_valid_linear / X_test_linear

    Nếu model được train bằng tree branch:
        dùng X_valid_tree / X_test_tree
    """

    if trained_model.dataset_branch == "linear":
        return datasets.linear

    if trained_model.dataset_branch == "tree":
        return datasets.tree

    raise ValueError(
        f"Unknown dataset_branch for model {trained_model.model_name}: "
        f"{trained_model.dataset_branch}"
    )


def get_split_data(
    *,
    branch: DatasetBranch,
    split: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Lấy X/y dataframe theo split.

    split:
        - train
        - valid
        - test
    """

    if split == "train":
        return branch.X_train, branch.y_train

    if split == "valid":
        return branch.X_valid, branch.y_valid

    if split == "test":
        return branch.X_test, branch.y_test

    raise ValueError(f"Unknown split: {split}")


# ============================================================
# Prediction Helpers
# ============================================================

def predict_positive_class_proba(
    *,
    trained_model: TrainedModel,
    X: pd.DataFrame,
) -> np.ndarray:
    """
    Lấy xác suất thuộc class 1.

    Hầu hết sklearn classifier có:
        predict_proba(X)[:, 1]

    Nếu model không có predict_proba, ta báo lỗi rõ ràng.
    """

    estimator = trained_model.estimator

    if not hasattr(estimator, "predict_proba"):
        raise TypeError(
            f"Model {trained_model.model_name} does not support predict_proba"
        )

    proba = estimator.predict_proba(X)

    if proba.ndim != 2 or proba.shape[1] < 2:
        raise ValueError(
            f"Invalid predict_proba output for {trained_model.model_name}: "
            f"shape={proba.shape}"
        )

    return proba[:, 1]


def proba_to_pred(
    *,
    y_proba: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
) -> np.ndarray:
    """
    Convert xác suất thành nhãn 0/1 theo threshold.

    Nếu y_proba >= threshold:
        predict 1

    Ngược lại:
        predict 0
    """

    return (y_proba >= threshold).astype(int)


# ============================================================
# Metrics
# ============================================================

def compute_binary_classification_metrics(
    *,
    y_true: pd.Series | np.ndarray,
    y_proba: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """
    Tính bộ metrics chuẩn cho bài toán binary classification.

    Vì target bị imbalance, ta không dùng accuracy làm metric chính.

    Metrics chính:
        - ROC-AUC
        - Average Precision / PR-AUC
        - Precision
        - Recall
        - F1
        - Brier Score
        - Confusion Matrix
    """

    y_true_array = np.asarray(y_true).astype(int)
    y_pred = proba_to_pred(y_proba=y_proba, threshold=threshold)

    roc_auc = roc_auc_score(y_true_array, y_proba)
    average_precision = average_precision_score(y_true_array, y_proba)

    precision = precision_score(
        y_true_array,
        y_pred,
        zero_division=0,
    )
    recall = recall_score(
        y_true_array,
        y_pred,
        zero_division=0,
    )
    f1 = f1_score(
        y_true_array,
        y_pred,
        zero_division=0,
    )

    brier_score = brier_score_loss(y_true_array, y_proba)

    tn, fp, fn, tp = confusion_matrix(
        y_true_array,
        y_pred,
        labels=[0, 1],
    ).ravel()

    positive_prediction_rate = float(np.mean(y_pred == 1))

    return {
        "threshold": float(threshold),
        "roc_auc": float(roc_auc),
        "average_precision": float(average_precision),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "brier_score": float(brier_score),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "positive_prediction_rate": positive_prediction_rate,
    }


def build_metrics_row(
    *,
    trained_model: TrainedModel,
    split: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """
    Chuyển metrics dict thành một row chuẩn để đưa vào metrics_df.
    """

    return {
        "model_name": trained_model.model_name,
        "model_version": MODEL_VERSION,
        "model_family": trained_model.model_family,
        "dataset_branch": trained_model.dataset_branch,
        "split": split,
        "train_rows": trained_model.train_rows,
        "feature_count": trained_model.feature_count,
        "training_seconds": trained_model.training_seconds,
        **metrics,
    }


# ============================================================
# Prediction DataFrame
# ============================================================

def build_prediction_dataframe(
    *,
    trained_model: TrainedModel,
    y_df: pd.DataFrame,
    y_proba: np.ndarray,
    split: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> pd.DataFrame:
    """
    Tạo prediction dataframe chuẩn hóa.

    Đây là output quan trọng cho XAI Layer sau này.

    Nếu y_df có SK_ID_CURR:
        lưu SK_ID_CURR

    Nếu không có:
        dùng row_index
    """

    y_true = extract_target(y_df).reset_index(drop=True)
    ids_or_index = extract_ids_or_row_index(y_df).reset_index(drop=True)
    y_pred = proba_to_pred(y_proba=y_proba, threshold=threshold)

    prediction_df = pd.DataFrame(
        {
            "row_index": np.arange(len(y_true)),
            "y_true": y_true.astype(int),
            "y_proba": y_proba,
            "y_pred_default_threshold_0_5": y_pred.astype(int),
            "split": split,
            "model_name": trained_model.model_name,
            "model_version": MODEL_VERSION,
            "model_family": trained_model.model_family,
            "dataset_branch": trained_model.dataset_branch,
            "threshold": threshold,
        }
    )

    if ids_or_index.name == "SK_ID_CURR":
        prediction_df.insert(0, "SK_ID_CURR", ids_or_index)

    return prediction_df


# ============================================================
# Evaluate One Model
# ============================================================

def evaluate_model_on_split(
    *,
    trained_model: TrainedModel,
    branch: DatasetBranch,
    split: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> ModelEvaluation:
    """
    Đánh giá một model trên một split.

    Luồng:
        1. Lấy X/y của split
        2. Predict probability
        3. Tính metrics
        4. Tạo prediction dataframe
    """

    X, y_df = get_split_data(branch=branch, split=split)
    y_true = extract_target(y_df)

    y_proba = predict_positive_class_proba(
        trained_model=trained_model,
        X=X,
    )

    metrics = compute_binary_classification_metrics(
        y_true=y_true,
        y_proba=y_proba,
        threshold=threshold,
    )

    predictions = build_prediction_dataframe(
        trained_model=trained_model,
        y_df=y_df,
        y_proba=y_proba,
        split=split,
        threshold=threshold,
    )

    return ModelEvaluation(
        model_name=trained_model.model_name,
        model_family=trained_model.model_family,
        dataset_branch=trained_model.dataset_branch,
        split=split,
        metrics=metrics,
        predictions=predictions,
    )


# ============================================================
# Threshold Analysis
# ============================================================

def compute_threshold_analysis_for_model(
    *,
    trained_model: TrainedModel,
    y_true: pd.Series,
    y_proba: np.ndarray,
    split: str,
    thresholds: list[float] = THRESHOLDS_FOR_ANALYSIS,
) -> pd.DataFrame:
    """
    Tính precision/recall/f1/confusion matrix ở nhiều threshold.

    Mục đích:
        Credit risk thường không dùng threshold 0.5 cố định.
        Doanh nghiệp có thể chọn ngưỡng thấp hơn để bắt nhiều rủi ro hơn.
    """

    rows: list[dict[str, Any]] = []

    for threshold in thresholds:
        metrics = compute_binary_classification_metrics(
            y_true=y_true,
            y_proba=y_proba,
            threshold=threshold,
        )

        rows.append(
            {
                "model_name": trained_model.model_name,
                "model_version": MODEL_VERSION,
                "model_family": trained_model.model_family,
                "dataset_branch": trained_model.dataset_branch,
                "split": split,
                **metrics,
            }
        )

    return pd.DataFrame(rows)


def build_validation_threshold_analysis(
    *,
    trained_models: list[TrainedModel],
    datasets: ModelReadyDatasets,
) -> pd.DataFrame:
    """
    Tạo threshold analysis cho tất cả model trên validation set.
    """

    frames: list[pd.DataFrame] = []

    for trained_model in trained_models:
        branch = get_branch_for_trained_model(
            datasets=datasets,
            trained_model=trained_model,
        )

        X_valid, y_valid_df = get_split_data(branch=branch, split="valid")
        y_valid = extract_target(y_valid_df)

        y_valid_proba = predict_positive_class_proba(
            trained_model=trained_model,
            X=X_valid,
        )

        model_threshold_df = compute_threshold_analysis_for_model(
            trained_model=trained_model,
            y_true=y_valid,
            y_proba=y_valid_proba,
            split="valid",
        )

        frames.append(model_threshold_df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# ============================================================
# Best Model Selection
# ============================================================

def select_best_model(
    *,
    trained_models: list[TrainedModel],
    valid_evaluations: list[ModelEvaluation],
) -> tuple[TrainedModel, ModelEvaluation]:
    """
    Chọn best model dựa trên validation metrics.

    Quy tắc:
        1. Average Precision cao hơn tốt hơn
        2. Nếu hòa, ROC-AUC cao hơn tốt hơn
        3. Nếu vẫn hòa, Brier Score thấp hơn tốt hơn
    """

    if not trained_models:
        raise ValueError("No trained models available for selection")

    evaluation_by_name = {
        evaluation.model_name: evaluation
        for evaluation in valid_evaluations
    }

    def selection_key(model: TrainedModel) -> tuple[float, float, float]:
        evaluation = evaluation_by_name[model.model_name]
        metrics = evaluation.metrics

        primary = float(metrics[SELECTION_PRIMARY_METRIC])
        secondary = float(metrics[SELECTION_SECONDARY_METRIC])
        tiebreaker = float(metrics[SELECTION_TIEBREAKER_METRIC])

        # Brier score càng thấp càng tốt,
        # nên dùng negative brier để max() chọn được model tốt hơn.
        return (
            primary,
            secondary,
            -tiebreaker,
        )

    best_model = max(trained_models, key=selection_key)
    best_evaluation = evaluation_by_name[best_model.model_name]

    return best_model, best_evaluation


# ============================================================
# Feature Importance
# ============================================================

def get_feature_importance_for_model(
    trained_model: TrainedModel,
) -> pd.DataFrame:
    """
    Lấy global feature importance nếu model hỗ trợ.

    Logistic Regression:
        dùng coefficient

    Random Forest:
        dùng feature_importances_

    HistGradientBoosting:
        sklearn HistGradientBoostingClassifier không có built-in
        feature_importances_ ổn định, nên skip ở bước này.

    SHAP sau này mới là XAI chính.
    """

    estimator = trained_model.estimator
    feature_columns = trained_model.feature_columns

    rows: list[dict[str, Any]] = []

    if trained_model.model_name == "logistic_regression":
        if not hasattr(estimator, "coef_"):
            return pd.DataFrame()

        coefficients = estimator.coef_[0]

        for feature_name, coefficient in zip(feature_columns, coefficients):
            rows.append(
                {
                    "model_name": trained_model.model_name,
                    "model_version": MODEL_VERSION,
                    "model_family": trained_model.model_family,
                    "dataset_branch": trained_model.dataset_branch,
                    "feature_name": feature_name,
                    "importance_type": "coefficient",
                    "importance_value": float(coefficient),
                    "absolute_importance_value": float(abs(coefficient)),
                }
            )

    elif hasattr(estimator, "feature_importances_"):
        importances = estimator.feature_importances_

        for feature_name, importance in zip(feature_columns, importances):
            rows.append(
                {
                    "model_name": trained_model.model_name,
                    "model_version": MODEL_VERSION,
                    "model_family": trained_model.model_family,
                    "dataset_branch": trained_model.dataset_branch,
                    "feature_name": feature_name,
                    "importance_type": "feature_importances_",
                    "importance_value": float(importance),
                    "absolute_importance_value": float(abs(importance)),
                }
            )

    else:
        return pd.DataFrame(
            [
                {
                    "model_name": trained_model.model_name,
                    "model_version": MODEL_VERSION,
                    "model_family": trained_model.model_family,
                    "dataset_branch": trained_model.dataset_branch,
                    "feature_name": None,
                    "importance_type": "not_available",
                    "importance_value": None,
                    "absolute_importance_value": None,
                }
            ]
        )

    importance_df = pd.DataFrame(rows)

    if importance_df.empty:
        return importance_df

    importance_df = importance_df.sort_values(
        by="absolute_importance_value",
        ascending=False,
    ).reset_index(drop=True)

    importance_df["rank"] = np.arange(1, len(importance_df) + 1)

    return importance_df


def build_feature_importance_dataframe(
    trained_models: list[TrainedModel],
) -> pd.DataFrame:
    """
    Gom feature importance của tất cả model thành một dataframe.
    """

    frames = [
        get_feature_importance_for_model(trained_model)
        for trained_model in trained_models
    ]

    frames = [frame for frame in frames if not frame.empty]

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# ============================================================
# Full Evaluation Orchestration
# ============================================================

def evaluate_trained_models(
    *,
    trained_models: list[TrainedModel],
    datasets: ModelReadyDatasets,
) -> EvaluationResult:
    """
    Đánh giá toàn bộ trained models.

    Luồng:
        1. Evaluate tất cả model trên validation
        2. Chọn best model bằng validation metrics
        3. Evaluate best model trên test
        4. Tạo metrics_df
        5. Tạo prediction dataframes
        6. Tạo threshold analysis
        7. Tạo feature importance
    """

    if not trained_models:
        raise ValueError("No trained models to evaluate")

    valid_evaluations: list[ModelEvaluation] = []

    for trained_model in trained_models:
        branch = get_branch_for_trained_model(
            datasets=datasets,
            trained_model=trained_model,
        )

        valid_evaluation = evaluate_model_on_split(
            trained_model=trained_model,
            branch=branch,
            split="valid",
            threshold=DEFAULT_THRESHOLD,
        )

        valid_evaluations.append(valid_evaluation)

    best_model, best_valid_evaluation = select_best_model(
        trained_models=trained_models,
        valid_evaluations=valid_evaluations,
    )

    best_branch = get_branch_for_trained_model(
        datasets=datasets,
        trained_model=best_model,
    )

    best_test_evaluation = evaluate_model_on_split(
        trained_model=best_model,
        branch=best_branch,
        split="test",
        threshold=DEFAULT_THRESHOLD,
    )

    metrics_rows: list[dict[str, Any]] = []

    for trained_model, valid_evaluation in zip(trained_models, valid_evaluations):
        metrics_rows.append(
            build_metrics_row(
                trained_model=trained_model,
                split="valid",
                metrics=valid_evaluation.metrics,
            )
        )

    metrics_rows.append(
        build_metrics_row(
            trained_model=best_model,
            split="test",
            metrics=best_test_evaluation.metrics,
        )
    )

    metrics_df = pd.DataFrame(metrics_rows)

    valid_predictions_df = pd.concat(
        [evaluation.predictions for evaluation in valid_evaluations],
        ignore_index=True,
    )

    test_predictions_df = best_test_evaluation.predictions.copy()

    threshold_analysis_df = build_validation_threshold_analysis(
        trained_models=trained_models,
        datasets=datasets,
    )

    feature_importance_df = build_feature_importance_dataframe(trained_models)

    return EvaluationResult(
        valid_evaluations=valid_evaluations,
        best_model=best_model,
        best_valid_evaluation=best_valid_evaluation,
        best_test_evaluation=best_test_evaluation,
        metrics_df=metrics_df,
        valid_predictions_df=valid_predictions_df,
        test_predictions_df=test_predictions_df,
        threshold_analysis_df=threshold_analysis_df,
        feature_importance_df=feature_importance_df,
    )

