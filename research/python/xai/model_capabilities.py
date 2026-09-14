"""Model-capability resolution for dataset-neutral XAI.

The resolver decides which SHAP strategy to try from estimator capability, not
from dataset identity. It is dependency-light and can be tested without SHAP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class XAIExplainerPlan:
    strategy: str
    prefer_tree_explainer: bool
    preferred_explainer: str
    fallback_explainer: str | None
    reason: str


def resolve_xai_explainer_plan(*, estimator: Any, model_family: str = "") -> XAIExplainerPlan:
    family = str(model_family).strip().lower()
    class_name = type(estimator).__name__.lower()
    module_name = type(estimator).__module__.lower()

    tree_markers = (
        "tree",
        "forest",
        "gradientboost",
        "histgradientboost",
        "xgb",
        "lightgbm",
        "catboost",
    )
    linear_markers = ("linear", "logistic", "ridge", "sgd")

    looks_tree = any(marker in family for marker in tree_markers) or any(
        marker in class_name or marker in module_name for marker in tree_markers
    )
    looks_linear = any(marker in family for marker in linear_markers) or any(
        marker in class_name for marker in linear_markers
    )

    if looks_tree:
        return XAIExplainerPlan(
            strategy="tree_first",
            prefer_tree_explainer=True,
            preferred_explainer="TreeExplainer",
            fallback_explainer="PermutationExplainer",
            reason="tree_capability_detected",
        )
    if looks_linear:
        return XAIExplainerPlan(
            strategy="permutation_safe",
            prefer_tree_explainer=False,
            preferred_explainer="PermutationExplainer",
            fallback_explainer=None,
            reason="linear_model_detected",
        )
    return XAIExplainerPlan(
        strategy="permutation_safe",
        prefer_tree_explainer=False,
        preferred_explainer="PermutationExplainer",
        fallback_explainer=None,
        reason="unknown_model_family_uses_model_agnostic_fallback",
    )
