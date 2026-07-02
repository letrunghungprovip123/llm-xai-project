from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from ml.scripts.xai_layer.config import (
    POSITIVE_CLASS,
    XAI_CONFIG,
)
from ml.scripts.xai_layer.loaders import XAIInputs


@dataclass(frozen=True)
class LocalShapResult:
    selected_cases: pd.DataFrame
    X_cases: pd.DataFrame
    shap_values: np.ndarray
    base_values: np.ndarray
    model_outputs: np.ndarray
    feature_names: list[str]
    explainer_type: str
    output_space: str
    additivity_errors: np.ndarray
    passed_additivity_check: np.ndarray
    warnings: list[str]


def require_shap() -> Any:
    try:
        import shap
    except ImportError as exc:
        raise ImportError(
            "Package 'shap' is required for Batch G. "
            "Install it with: pip install shap"
        ) from exc

    return shap


def make_predict_positive_proba(
    *,
    estimator: Any,
    feature_columns: list[str],
) -> Callable[[Any], np.ndarray]:
    def predict_positive_proba(X: Any) -> np.ndarray:
        if isinstance(X, pd.DataFrame):
            X_df = X.loc[:, feature_columns].copy()
        else:
            X_df = pd.DataFrame(X, columns=feature_columns)

        proba = estimator.predict_proba(X_df)

        if proba.ndim != 2:
            raise ValueError(
                f"predict_proba must return 2D array, got shape={proba.shape}"
            )

        if proba.shape[1] <= POSITIVE_CLASS:
            raise ValueError(
                f"predict_proba output does not contain class index {POSITIVE_CLASS}. "
                f"Output shape={proba.shape}"
            )

        return proba[:, POSITIVE_CLASS]

    return predict_positive_proba


def build_background_data(
    inputs: XAIInputs,
    background_sample_size: int | None = None,
) -> pd.DataFrame:
    if background_sample_size is None:
        background_sample_size = XAI_CONFIG.shap_background_sample_size

    if background_sample_size <= 0:
        raise ValueError("background_sample_size must be greater than 0.")

    sample_size = min(background_sample_size, len(inputs.X_test))

    background = inputs.X_test.sample(
        n=sample_size,
        random_state=XAI_CONFIG.random_state,
    )

    background = background.loc[:, inputs.model_bundle.feature_columns].copy()

    return background


def get_X_cases_from_selected_cases(
    *,
    inputs: XAIInputs,
    selected_cases: pd.DataFrame,
) -> pd.DataFrame:
    if selected_cases.empty:
        raise ValueError("selected_cases is empty.")

    if "row_index" not in selected_cases.columns:
        raise ValueError("selected_cases must contain row_index column.")

    row_indices = selected_cases["row_index"].astype(int).to_numpy()

    if row_indices.min() < 0:
        raise ValueError("selected_cases contains negative row_index.")

    if row_indices.max() >= len(inputs.X_test):
        raise ValueError("selected_cases contains row_index outside X_test range.")

    X_cases = inputs.X_test.iloc[row_indices].copy()
    X_cases = X_cases.loc[:, inputs.model_bundle.feature_columns].copy()

    return X_cases


def normalize_shap_values(
    *,
    raw_values: Any,
    positive_class: int = POSITIVE_CLASS,
) -> np.ndarray:
    values = raw_values

    if isinstance(values, list):
        if len(values) <= positive_class:
            raise ValueError(
                f"SHAP values list does not contain class index {positive_class}."
            )
        values = values[positive_class]

    values_array = np.asarray(values)

    if values_array.ndim == 3:
        if values_array.shape[2] <= positive_class:
            raise ValueError(
                "3D SHAP values do not contain requested positive class index. "
                f"Shape={values_array.shape}, positive_class={positive_class}"
            )
        values_array = values_array[:, :, positive_class]

    if values_array.ndim != 2:
        raise ValueError(
            f"Normalized SHAP values must be 2D, got shape={values_array.shape}"
        )

    return values_array.astype(float)


def normalize_base_values(
    *,
    raw_base_values: Any,
    n_cases: int,
    positive_class: int = POSITIVE_CLASS,
) -> np.ndarray:
    base_values = raw_base_values

    if isinstance(base_values, list):
        if len(base_values) <= positive_class:
            raise ValueError(
                f"Base values list does not contain class index {positive_class}."
            )
        base_values = base_values[positive_class]

    base_array = np.asarray(base_values)

    if base_array.ndim == 0:
        base_array = np.repeat(float(base_array), n_cases)

    elif base_array.ndim == 1:
        if len(base_array) == 1:
            base_array = np.repeat(float(base_array[0]), n_cases)
        elif len(base_array) != n_cases:
            raise ValueError(
                f"Base values length mismatch. Expected {n_cases}, got {len(base_array)}"
            )

    elif base_array.ndim == 2:
        if base_array.shape[0] != n_cases:
            raise ValueError(
                "Base values row count mismatch. "
                f"Expected {n_cases}, got {base_array.shape[0]}"
            )

        if base_array.shape[1] <= positive_class:
            raise ValueError(
                "Base values do not contain requested positive class index. "
                f"Shape={base_array.shape}, positive_class={positive_class}"
            )

        base_array = base_array[:, positive_class]

    else:
        raise ValueError(f"Unsupported base values shape: {base_array.shape}")

    return base_array.astype(float)


def validate_shap_matrix(
    *,
    shap_values: np.ndarray,
    X_cases: pd.DataFrame,
) -> None:
    expected_shape = X_cases.shape

    if shap_values.shape != expected_shape:
        raise ValueError(
            f"SHAP values shape mismatch. "
            f"Expected {expected_shape}, got {shap_values.shape}"
        )

    if np.isnan(shap_values).any():
        raise ValueError("SHAP values contain NaN.")

    if np.isinf(shap_values).any():
        raise ValueError("SHAP values contain inf or -inf.")


def compute_additivity_check(
    *,
    base_values: np.ndarray,
    shap_values: np.ndarray,
    model_outputs: np.ndarray,
    tolerance: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if tolerance is None:
        tolerance = XAI_CONFIG.additivity_tolerance

    reconstructed_outputs = base_values + shap_values.sum(axis=1)
    additivity_errors = np.abs(reconstructed_outputs - model_outputs)
    passed = additivity_errors <= tolerance

    return additivity_errors, passed


def try_tree_explainer(
    *,
    inputs: XAIInputs,
    X_cases: pd.DataFrame,
    background: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, str, str]:
    shap = require_shap()

    estimator = inputs.model_bundle.estimator

    explainer = shap.TreeExplainer(
        estimator,
        data=background,
        model_output="probability",
    )

    explanation = explainer(X_cases)

    shap_values = normalize_shap_values(
        raw_values=explanation.values,
        positive_class=POSITIVE_CLASS,
    )

    base_values = normalize_base_values(
        raw_base_values=explanation.base_values,
        n_cases=len(X_cases),
        positive_class=POSITIVE_CLASS,
    )

    return (
        shap_values,
        base_values,
        "TreeExplainer",
        "probability",
    )


def run_permutation_explainer(
    *,
    inputs: XAIInputs,
    X_cases: pd.DataFrame,
    background: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, str, str]:
    shap = require_shap()

    predict_positive_proba = make_predict_positive_proba(
        estimator=inputs.model_bundle.estimator,
        feature_columns=inputs.model_bundle.feature_columns,
    )

    explainer = shap.Explainer(
        predict_positive_proba,
        background,
        algorithm="permutation",
    )

    max_evals = max(2 * X_cases.shape[1] + 1, 500)

    explanation = explainer(
        X_cases,
        max_evals=max_evals,
    )

    shap_values = normalize_shap_values(
        raw_values=explanation.values,
        positive_class=POSITIVE_CLASS,
    )

    base_values = normalize_base_values(
        raw_base_values=explanation.base_values,
        n_cases=len(X_cases),
        positive_class=POSITIVE_CLASS,
    )

    return (
        shap_values,
        base_values,
        "PermutationExplainer",
        "probability",
    )


def compute_local_shap_values(
    *,
    inputs: XAIInputs,
    selected_cases: pd.DataFrame,
    background_sample_size: int | None = None,
    prefer_tree_explainer: bool = True,
) -> LocalShapResult:
    warnings: list[str] = []

    X_cases = get_X_cases_from_selected_cases(
        inputs=inputs,
        selected_cases=selected_cases,
    )

    background = build_background_data(
        inputs=inputs,
        background_sample_size=background_sample_size,
    )

    predict_positive_proba = make_predict_positive_proba(
        estimator=inputs.model_bundle.estimator,
        feature_columns=inputs.model_bundle.feature_columns,
    )

    model_outputs = predict_positive_proba(X_cases).astype(float)

    if prefer_tree_explainer:
        try:
            shap_values, base_values, explainer_type, output_space = try_tree_explainer(
                inputs=inputs,
                X_cases=X_cases,
                background=background,
            )
        except Exception as exc:
            warnings.append(
                "TreeExplainer failed. Falling back to PermutationExplainer. "
                f"Reason: {type(exc).__name__}: {exc}"
            )

            shap_values, base_values, explainer_type, output_space = run_permutation_explainer(
                inputs=inputs,
                X_cases=X_cases,
                background=background,
            )
    else:
        shap_values, base_values, explainer_type, output_space = run_permutation_explainer(
            inputs=inputs,
            X_cases=X_cases,
            background=background,
        )

    validate_shap_matrix(
        shap_values=shap_values,
        X_cases=X_cases,
    )

    additivity_errors, passed_additivity_check = compute_additivity_check(
        base_values=base_values,
        shap_values=shap_values,
        model_outputs=model_outputs,
    )

    if not bool(passed_additivity_check.all()):
        failed_count = int((~passed_additivity_check).sum())
        max_error = float(additivity_errors.max())
        warnings.append(
            f"Additivity check failed for {failed_count} cases. "
            f"Max error={max_error:.8f}"
        )

    return LocalShapResult(
        selected_cases=selected_cases.reset_index(drop=True).copy(),
        X_cases=X_cases.reset_index(drop=True).copy(),
        shap_values=shap_values,
        base_values=base_values,
        model_outputs=model_outputs,
        feature_names=inputs.model_bundle.feature_columns,
        explainer_type=explainer_type,
        output_space=output_space,
        additivity_errors=additivity_errors,
        passed_additivity_check=passed_additivity_check,
        warnings=warnings,
    )


def summarize_local_shap_result(result: LocalShapResult) -> dict[str, Any]:
    abs_values = np.abs(result.shap_values)

    return {
        "case_count": int(len(result.selected_cases)),
        "feature_count": int(len(result.feature_names)),
        "shap_values_shape": list(result.shap_values.shape),
        "explainer_type": result.explainer_type,
        "output_space": result.output_space,
        "model_output_min": float(result.model_outputs.min()),
        "model_output_max": float(result.model_outputs.max()),
        "model_output_mean": float(result.model_outputs.mean()),
        "base_value_min": float(result.base_values.min()),
        "base_value_max": float(result.base_values.max()),
        "base_value_mean": float(result.base_values.mean()),
        "mean_abs_shap": float(abs_values.mean()),
        "max_abs_shap": float(abs_values.max()),
        "additivity_error_max": float(result.additivity_errors.max()),
        "additivity_error_mean": float(result.additivity_errors.mean()),
        "passed_additivity_count": int(result.passed_additivity_check.sum()),
        "failed_additivity_count": int((~result.passed_additivity_check).sum()),
        "warnings": result.warnings,
    }


__all__ = [
    "LocalShapResult",
    "require_shap",
    "make_predict_positive_proba",
    "build_background_data",
    "get_X_cases_from_selected_cases",
    "normalize_shap_values",
    "normalize_base_values",
    "validate_shap_matrix",
    "compute_additivity_check",
    "try_tree_explainer",
    "run_permutation_explainer",
    "compute_local_shap_values",
    "summarize_local_shap_result",
]