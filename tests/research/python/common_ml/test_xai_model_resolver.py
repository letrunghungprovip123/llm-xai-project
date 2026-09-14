from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from research.python.xai.loaders import load_model_bundle
from research.python.xai.model_capabilities import resolve_xai_explainer_plan


def _fit(estimator):
    X = np.array([[0.0], [1.0], [2.0], [3.0]])
    y = np.array([0, 0, 1, 1])
    estimator.fit(X, y)
    return estimator


def _bundle(estimator, model_name: str, family: str, branch: str) -> dict:
    return {
        "estimator": estimator,
        "feature_columns": ["feature_alpha"],
        "model_name": model_name,
        "model_version": "v1",
        "model_family": family,
        "dataset_branch": branch,
        "threshold": 0.5,
    }


def test_capability_resolver_uses_tree_for_rf_and_permutation_for_lr() -> None:
    rf = _fit(RandomForestClassifier(n_estimators=2, random_state=1))
    lr = _fit(LogisticRegression())
    rf_plan = resolve_xai_explainer_plan(estimator=rf, model_family="tree")
    lr_plan = resolve_xai_explainer_plan(estimator=lr, model_family="linear")
    assert rf_plan.prefer_tree_explainer is True
    assert rf_plan.preferred_explainer == "TreeExplainer"
    assert lr_plan.prefer_tree_explainer is False
    assert lr_plan.preferred_explainer == "PermutationExplainer"


def test_generic_loader_accepts_non_hgb_selected_model_only_when_opted_in(tmp_path: Path) -> None:
    lr = _fit(LogisticRegression())
    path = tmp_path / "best_model.joblib"
    joblib.dump(_bundle(lr, "logistic_regression", "linear", "linear"), path)

    try:
        load_model_bundle(path)
    except ValueError as exc:
        assert "legacy best model" in str(exc)
    else:
        raise AssertionError("legacy loader must still enforce historical HGB expectation")

    loaded = load_model_bundle(path, enforce_legacy_expectations=False)
    assert loaded.model_name == "logistic_regression"
    assert loaded.dataset_branch == "linear"
