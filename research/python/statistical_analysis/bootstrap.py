"""Deterministic case-resampled bootstrap for repeated-measures effects."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _percentile_bounds(values: np.ndarray, confidence: float) -> tuple[float, float]:
    alpha = 1.0 - confidence
    return (
        float(np.quantile(values, alpha / 2.0)),
        float(np.quantile(values, 1.0 - alpha / 2.0)),
    )


def _case_condition_values(
    frame: pd.DataFrame,
    case_ids: list[str],
    model_id: str,
    evidence_level: str,
    metric_id: str,
) -> np.ndarray:
    subset = frame.loc[
        (frame["model_id"].astype(str) == model_id)
        & (frame["evidence_level"].astype(str) == evidence_level),
        ["case_id", metric_id],
    ].copy()
    if subset["case_id"].astype(str).duplicated().any():
        raise ValueError(f"Duplicate case in condition {model_id}::{evidence_level}")
    series = subset.assign(case_id=subset["case_id"].astype(str)).set_index("case_id")[metric_id]
    values = series.reindex(case_ids)
    if values.isna().any():
        raise ValueError(
            f"Bootstrap primary metric missing for {model_id}::{evidence_level}."
        )
    return values.to_numpy(dtype=float)


def build_case_bootstrap(
    analysis_frame: pd.DataFrame,
    contrasts: list[dict[str, Any]],
    metric_id: str,
    *,
    iterations: int,
    confidence: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return option and planned-contrast percentile intervals.

    One common case-index resample is shared by every condition per iteration,
    preserving the repeated-measures dependence structure.
    """

    if iterations <= 0:
        raise ValueError("Bootstrap iterations must be positive.")
    if not 0.0 < confidence < 1.0:
        raise ValueError("Bootstrap confidence must be in (0,1).")
    case_ids = sorted(analysis_frame["case_id"].astype(str).unique().tolist())
    if not case_ids:
        raise ValueError("Bootstrap requires at least one case.")
    models = (
        analysis_frame[["model_id", "model_order"]]
        .drop_duplicates()
        .sort_values("model_order", kind="stable")["model_id"]
        .astype(str)
        .tolist()
    )
    levels = (
        analysis_frame[["evidence_level", "evidence_order"]]
        .drop_duplicates()
        .sort_values("evidence_order", kind="stable")["evidence_level"]
        .astype(str)
        .tolist()
    )
    condition_values: dict[tuple[str, str], np.ndarray] = {}
    for model in models:
        for level in levels:
            condition_values[(model, level)] = _case_condition_values(
                analysis_frame, case_ids, model, level, metric_id
            )

    rng = np.random.default_rng(seed)
    sample_indices = rng.integers(
        0, len(case_ids), size=(iterations, len(case_ids)), endpoint=False
    )

    option_rows: list[dict[str, Any]] = []
    for model in models:
        for level in levels:
            values = condition_values[(model, level)]
            bootstrap_means = values[sample_indices].mean(axis=1)
            lower, upper = _percentile_bounds(bootstrap_means, confidence)
            option_rows.append({
                "option_id": f"{model}::{level}",
                "model_id": model,
                "evidence_level": level,
                "metric_id": metric_id,
                "case_count": len(case_ids),
                "observed_mean": float(values.mean()),
                "bootstrap_mean": float(bootstrap_means.mean()),
                "ci_lower": lower,
                "ci_upper": upper,
                "confidence": confidence,
                "iterations": iterations,
                "seed": seed,
                "method": "case_resampled_percentile",
            })

    contrast_rows: list[dict[str, Any]] = []
    for contrast in contrasts:
        a = contrast["condition_a"]
        b = contrast["condition_b"]
        values_a = condition_values[(str(a["model_id"]), str(a["evidence_level"]))]
        values_b = condition_values[(str(b["model_id"]), str(b["evidence_level"]))]
        differences = values_a - values_b
        bootstrap_differences = differences[sample_indices].mean(axis=1)
        lower, upper = _percentile_bounds(bootstrap_differences, confidence)
        contrast_rows.append({
            "contrast_id": str(contrast["contrast_id"]),
            "contrast_family": str(contrast["contrast_family"]),
            "metric_id": metric_id,
            "case_count": len(case_ids),
            "observed_mean_difference": float(differences.mean()),
            "bootstrap_mean_difference": float(bootstrap_differences.mean()),
            "ci_lower": lower,
            "ci_upper": upper,
            "confidence": confidence,
            "iterations": iterations,
            "seed": seed,
            "method": "case_resampled_percentile",
        })

    return pd.DataFrame(option_rows), pd.DataFrame(contrast_rows)
