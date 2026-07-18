from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.utils.class_weight import compute_sample_weight

from .config import (
    MODEL_CONFIGS,
    RANDOM_STATE,
)
from .data_quality import (
    DatasetBranch,
    ModelReadyDatasets,
    extract_target,
)



@dataclass(frozen=True)
class TrainedModel:
    model_name : str
    model_family : str
    dataset_branch : str
    estimator : str
    feature_columns : list[str]
    training_seconds : float
    train_rows : int
    feature_count : int
    metadata : dict[str, Any]

@dataclass(frozen=True)
class TrainingResult: 
    trained_models : list[TrainedModel]
    skipped_models : list[dict[str,Any]]
    errors : list[str]


def get_branch_for_model(*,datasets : ModelReadyDatasets, dataset_branch : str,) -> DatasetBranch : 
    if dataset_branch == "linear" :
        return datasets.linear

    if dataset_branch == "tree" :
        return datasets.tree 
    
    raise ValueError(f"ko biết dataset : {dataset_branch}")


def build_sample_weight_balanced(y : pd.Series) -> np.ndarray :
    return compute_sample_weight(class_weight="balanced",y=y)


def train_logistic_regression(branch : DatasetBranch) -> TrainedModel :
    X_train = branch.X_train
    y_train = extract_target(branch.y_train)


    estimator = LogisticRegression(
        class_weight="balanced",
        max_iter=2000,
        solver='lbfgs',
        random_state=RANDOM_STATE,
    )

    start_time = time.perf_counter()
    estimator.fit(X_train,y_train)
    training_seconds = time.perf_counter() - start_time

    return TrainedModel(
        model_name="logistic_regression",
        model_family="linear",
        dataset_branch=branch.name,
        estimator=estimator,
        feature_columns=branch.feature_columns,
        training_seconds=training_seconds,
        train_rows=len(X_train),
        feature_count=X_train.shape[1],
        metadata={
            "algorithm": "LogisticRegression",
            "class_imbalance_strategy": "class_weight='balanced'",
            "solver": "lbfgs",
            "max_iter": 2000,
            "random_state": RANDOM_STATE,
        },
    )



def train_random_forest(branch: DatasetBranch) -> TrainedModel:


    X_train = branch.X_train
    y_train = extract_target(branch.y_train)

    estimator = RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=20,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    start_time = time.perf_counter()
    estimator.fit(X_train, y_train)
    training_seconds = time.perf_counter() - start_time

    return TrainedModel(
        model_name="random_forest",
        model_family="tree",
        dataset_branch=branch.name,
        estimator=estimator,
        feature_columns=branch.feature_columns,
        training_seconds=training_seconds,
        train_rows=len(X_train),
        feature_count=X_train.shape[1],
        metadata={
            "algorithm": "RandomForestClassifier",
            "n_estimators": 300,
            "max_depth": None,
            "min_samples_leaf": 20,
            "class_imbalance_strategy": "class_weight='balanced_subsample'",
            "random_state": RANDOM_STATE,
        },
    )


def train_hist_gradient_boosting(branch: DatasetBranch) -> TrainedModel:


    X_train = branch.X_train
    y_train = extract_target(branch.y_train)

    sample_weight = build_sample_weight_balanced(y_train)

    estimator = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=300,
        max_leaf_nodes=31,
        l2_regularization=0.1,
        random_state=RANDOM_STATE,
    )

    start_time = time.perf_counter()
    estimator.fit(
        X_train,
        y_train,
        sample_weight=sample_weight,
    )
    training_seconds = time.perf_counter() - start_time

    return TrainedModel(
        model_name="hist_gradient_boosting",
        model_family="tree_boosting",
        dataset_branch=branch.name,
        estimator=estimator,
        feature_columns=branch.feature_columns,
        training_seconds=training_seconds,
        train_rows=len(X_train),
        feature_count=X_train.shape[1],
        metadata={
            "algorithm": "HistGradientBoostingClassifier",
            "learning_rate": 0.05,
            "max_iter": 300,
            "max_leaf_nodes": 31,
            "l2_regularization": 0.1,
            "class_imbalance_strategy": "sample_weight=balanced",
            "random_state": RANDOM_STATE,
        },
    )


def train_single_model(
    *,
    model_name: str,
    branch: DatasetBranch,
) -> TrainedModel:


    if model_name == "logistic_regression":
        return train_logistic_regression(branch)

    if model_name == "random_forest":
        return train_random_forest(branch)

    if model_name == "hist_gradient_boosting":
        return train_hist_gradient_boosting(branch)

    raise ValueError(f"Unsupported model_name: {model_name}")


def train_all_models(datasets: ModelReadyDatasets) -> TrainingResult:


    trained_models: list[TrainedModel] = []
    skipped_models: list[dict[str, Any]] = []
    errors: list[str] = []

    for model_config in MODEL_CONFIGS:
        if not model_config.enabled:
            skipped_models.append(
                {
                    "model_name": model_config.model_name,
                    "reason": "disabled_in_config",
                }
            )
            continue

        try:
            branch = get_branch_for_model(
                datasets=datasets,
                dataset_branch=model_config.dataset_branch,
            )

            trained_model = train_single_model(
                model_name=model_config.model_name,
                branch=branch,
            )

            trained_models.append(trained_model)

        except Exception as exc:
            errors.append(
                f"Failed to train {model_config.model_name}: {type(exc).__name__}: {exc}"
            )

    return TrainingResult(
        trained_models=trained_models,
        skipped_models=skipped_models,
        errors=errors,
    )

