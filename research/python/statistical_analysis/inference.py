"""Run repeated-measures and paired inference at the case level."""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy.linalg import helmert
from scipy.stats import f as f_distribution
from scipy.stats import rankdata, wilcoxon

from .config import ALPHA, PRIMARY_METRIC, SECONDARY_METRICS


def ordered_levels(
    frame: pd.DataFrame,
    id_column: str,
    order_column: str,
) -> list[object]:
    """Return unique factor levels in their audited experiment order."""

    levels = (
        frame[[id_column, order_column]]
        .drop_duplicates()
        .sort_values(order_column, kind="stable")
    )
    return levels[id_column].tolist()


def build_balanced_array(
    analysis_frame: pd.DataFrame,
    metric_id: str,
) -> tuple[np.ndarray, list[object], list[object], list[object]]:
    """Build y[case, model, evidence] and reject incomplete cells."""

    case_ids = sorted(analysis_frame["case_id"].unique().tolist())
    model_ids = ordered_levels(
        analysis_frame,
        "model_id",
        "model_order",
    )
    evidence_levels = ordered_levels(
        analysis_frame,
        "evidence_level",
        "evidence_order",
    )

    duplicate_key_count = int(
        analysis_frame.duplicated(
            subset=["case_id", "model_id", "evidence_level"],
            keep=False,
        ).sum()
    )
    if duplicate_key_count > 0:
        raise ValueError(
            "Repeated-measures input contains duplicate "
            "case × model × evidence rows."
        )

    indexed = analysis_frame.set_index(
        ["case_id", "model_id", "evidence_level"]
    )
    expected_index = pd.MultiIndex.from_product(
        [case_ids, model_ids, evidence_levels],
        names=["case_id", "model_id", "evidence_level"],
    )
    metric_values = indexed[metric_id].reindex(expected_index)

    if metric_values.isna().any():
        missing_count = int(metric_values.isna().sum())
        raise ValueError(
            f"{metric_id} is missing {missing_count} repeated-measures "
            "cells. Primary omnibus analysis requires a balanced matrix."
        )

    values = metric_values.to_numpy(dtype=float).reshape(
        len(case_ids),
        len(model_ids),
        len(evidence_levels),
    )

    return values, case_ids, model_ids, evidence_levels


def greenhouse_geisser_epsilon(
    repeated_values: np.ndarray,
) -> float:
    """Calculate Greenhouse–Geisser epsilon for repeated conditions."""

    condition_count = repeated_values.shape[1]
    contrast_dimension = condition_count - 1

    if contrast_dimension <= 1:
        return 1.0

    covariance = np.cov(repeated_values, rowvar=False, ddof=1)
    centering = (
        np.eye(condition_count)
        - np.ones((condition_count, condition_count))
        / condition_count
    )
    centered_covariance = centering @ covariance @ centering

    numerator = float(np.trace(centered_covariance) ** 2)
    denominator = float(
        contrast_dimension
        * np.trace(centered_covariance @ centered_covariance)
    )

    if denominator <= 0:
        return 1.0

    epsilon = numerator / denominator
    lower_bound = 1.0 / contrast_dimension
    return float(np.clip(epsilon, lower_bound, 1.0))


def interaction_epsilon(values: np.ndarray) -> float:
    """Calculate epsilon from orthonormal model × evidence contrasts."""

    model_count = values.shape[1]
    evidence_count = values.shape[2]

    model_contrasts = helmert(model_count, full=False).T
    evidence_contrasts = helmert(evidence_count, full=False).T

    interaction_scores: list[np.ndarray] = []
    for subject_values in values:
        score_matrix = (
            model_contrasts.T
            @ subject_values
            @ evidence_contrasts
        )
        interaction_scores.append(score_matrix.reshape(-1))

    score_array = np.vstack(interaction_scores)
    contrast_dimension = score_array.shape[1]

    if contrast_dimension <= 1:
        return 1.0

    covariance = np.cov(score_array, rowvar=False, ddof=1)
    numerator = float(np.trace(covariance) ** 2)
    denominator = float(
        contrast_dimension * np.trace(covariance @ covariance)
    )

    if denominator <= 0:
        return 1.0

    epsilon = numerator / denominator
    lower_bound = 1.0 / contrast_dimension
    return float(np.clip(epsilon, lower_bound, 1.0))


def safe_f_test(
    effect_sum_squares: float,
    effect_degrees_freedom: float,
    error_sum_squares: float,
    error_degrees_freedom: float,
    epsilon: float,
) -> dict[str, float]:
    """Calculate F, uncorrected p, corrected p and effect size."""

    effect_mean_square = (
        effect_sum_squares / effect_degrees_freedom
    )
    error_mean_square = error_sum_squares / error_degrees_freedom

    if error_mean_square <= 0:
        f_statistic = (
            float(np.finfo(np.float64).max)
            if effect_mean_square > 0
            else 0.0
        )
    else:
        f_statistic = effect_mean_square / error_mean_square

    if np.isfinite(f_statistic):
        p_uncorrected = float(
            f_distribution.sf(
                f_statistic,
                effect_degrees_freedom,
                error_degrees_freedom,
            )
        )
        corrected_df_numerator = epsilon * effect_degrees_freedom
        corrected_df_denominator = epsilon * error_degrees_freedom
        p_corrected = float(
            f_distribution.sf(
                f_statistic,
                corrected_df_numerator,
                corrected_df_denominator,
            )
        )
    else:
        p_uncorrected = 0.0
        p_corrected = 0.0
        corrected_df_numerator = epsilon * effect_degrees_freedom
        corrected_df_denominator = epsilon * error_degrees_freedom

    eta_denominator = effect_sum_squares + error_sum_squares
    partial_eta_squared = (
        effect_sum_squares / eta_denominator
        if eta_denominator > 0
        else 0.0
    )

    return {
        "f_statistic": float(f_statistic),
        "p_value_uncorrected": p_uncorrected,
        "greenhouse_geisser_epsilon": float(epsilon),
        "df_numerator_corrected": float(corrected_df_numerator),
        "df_denominator_corrected": float(corrected_df_denominator),
        "p_value_greenhouse_geisser": p_corrected,
        "p_value_used": p_corrected,
        "partial_eta_squared": float(partial_eta_squared),
    }


def run_repeated_measures_anova(
    analysis_frame: pd.DataFrame,
    metric_id: str = PRIMARY_METRIC,
    analysis_role: str = "PRIMARY",
) -> pd.DataFrame:
    """Run a balanced two-factor within-subject repeated-measures ANOVA."""

    values, case_ids, model_ids, evidence_levels = (
        build_balanced_array(analysis_frame, metric_id)
    )

    subject_count, model_count, evidence_count = values.shape
    grand_mean = float(values.mean())
    subject_means = values.mean(axis=(1, 2))
    model_means = values.mean(axis=(0, 2))
    evidence_means = values.mean(axis=(0, 1))
    cell_means = values.mean(axis=0)
    subject_model_means = values.mean(axis=2)
    subject_evidence_means = values.mean(axis=1)

    total_ss = float(((values - grand_mean) ** 2).sum())
    subject_ss = float(
        model_count
        * evidence_count
        * ((subject_means - grand_mean) ** 2).sum()
    )
    model_ss = float(
        subject_count
        * evidence_count
        * ((model_means - grand_mean) ** 2).sum()
    )
    evidence_ss = float(
        subject_count
        * model_count
        * ((evidence_means - grand_mean) ** 2).sum()
    )

    interaction_component = (
        cell_means
        - model_means[:, None]
        - evidence_means[None, :]
        + grand_mean
    )
    interaction_ss = float(
        subject_count * (interaction_component ** 2).sum()
    )

    subject_model_component = (
        subject_model_means
        - subject_means[:, None]
        - model_means[None, :]
        + grand_mean
    )
    subject_model_ss = float(
        evidence_count * (subject_model_component ** 2).sum()
    )

    subject_evidence_component = (
        subject_evidence_means
        - subject_means[:, None]
        - evidence_means[None, :]
        + grand_mean
    )
    subject_evidence_ss = float(
        model_count * (subject_evidence_component ** 2).sum()
    )

    residual_ss = float(
        total_ss
        - subject_ss
        - model_ss
        - evidence_ss
        - interaction_ss
        - subject_model_ss
        - subject_evidence_ss
    )
    residual_ss = max(residual_ss, 0.0)

    model_df = model_count - 1
    evidence_df = evidence_count - 1
    interaction_df = model_df * evidence_df
    subject_model_df = (subject_count - 1) * model_df
    subject_evidence_df = (subject_count - 1) * evidence_df
    residual_df = (
        (subject_count - 1) * model_df * evidence_df
    )

    model_repeated = values.mean(axis=2)
    evidence_repeated = values.mean(axis=1)

    effect_inputs = [
        (
            "model",
            model_ss,
            model_df,
            subject_model_ss,
            subject_model_df,
            greenhouse_geisser_epsilon(model_repeated),
        ),
        (
            "evidence",
            evidence_ss,
            evidence_df,
            subject_evidence_ss,
            subject_evidence_df,
            greenhouse_geisser_epsilon(evidence_repeated),
        ),
        (
            "model:evidence",
            interaction_ss,
            interaction_df,
            residual_ss,
            residual_df,
            interaction_epsilon(values),
        ),
    ]

    rows: list[dict[str, object]] = []
    for effect, effect_ss, effect_df, error_ss, error_df, epsilon in effect_inputs:
        test_values = safe_f_test(
            effect_ss,
            effect_df,
            error_ss,
            error_df,
            epsilon,
        )
        rows.append(
            {
                "analysis_role": analysis_role,
                "metric_id": metric_id,
                "test_method": (
                    "two_way_repeated_measures_anova_"
                    "greenhouse_geisser"
                ),
                "effect": effect,
                "subject_count": len(case_ids),
                "observation_count": int(values.size),
                "model_level_count": len(model_ids),
                "evidence_level_count": len(evidence_levels),
                "sum_squares_effect": effect_ss,
                "sum_squares_error": error_ss,
                "df_numerator": float(effect_df),
                "df_denominator": float(error_df),
                **test_values,
                "alpha": ALPHA,
                "significant": (
                    test_values["p_value_used"] < ALPHA
                ),
            }
        )

    return pd.DataFrame(rows)


def rank_biserial_correlation(differences: np.ndarray) -> float:
    """Calculate signed-rank effect size for condition A minus B."""

    nonzero = differences[differences != 0]
    if len(nonzero) == 0:
        return 0.0

    ranks = rankdata(np.abs(nonzero), method="average")
    positive_rank_sum = float(ranks[nonzero > 0].sum())
    negative_rank_sum = float(ranks[nonzero < 0].sum())
    denominator = positive_rank_sum + negative_rank_sum

    if denominator == 0:
        return 0.0

    return (positive_rank_sum - negative_rank_sum) / denominator


def run_wilcoxon_pair(
    condition_a: pd.DataFrame,
    condition_b: pd.DataFrame,
    metric_id: str,
) -> dict[str, float | int]:
    """Pair two conditions by case_id and run a two-sided Wilcoxon test."""

    paired = condition_a[["case_id", metric_id]].merge(
        condition_b[["case_id", metric_id]],
        on="case_id",
        how="inner",
        validate="one_to_one",
        suffixes=("_a", "_b"),
    )
    paired = paired.dropna(
        subset=[f"{metric_id}_a", f"{metric_id}_b"]
    )

    values_a = paired[f"{metric_id}_a"].to_numpy(dtype=float)
    values_b = paired[f"{metric_id}_b"].to_numpy(dtype=float)
    differences = values_a - values_b

    if len(differences) == 0:
        raise ValueError(
            f"No complete case pairs are available for {metric_id}."
        )

    if np.allclose(differences, 0.0, rtol=0.0, atol=1e-15):
        test_statistic = 0.0
        p_value = 1.0
    else:
        test_result = wilcoxon(
            differences,
            zero_method="wilcox",
            correction=False,
            alternative="two-sided",
            method="auto",
        )
        test_statistic = float(test_result.statistic)
        p_value = float(test_result.pvalue)

    return {
        "observed_pair_count": int(len(paired)),
        "mean_a": float(values_a.mean()),
        "mean_b": float(values_b.mean()),
        "mean_difference": float(differences.mean()),
        "median_difference": float(np.median(differences)),
        "wilcoxon_statistic": test_statistic,
        "raw_p_value": p_value,
        "rank_biserial_correlation": float(
            rank_biserial_correlation(differences)
        ),
    }


def holm_adjust(p_values: pd.Series) -> pd.Series:
    """Apply Holm family-wise error correction in original row order."""

    values = p_values.to_numpy(dtype=float)
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    comparison_count = len(sorted_values)

    adjusted_sorted = np.empty(comparison_count, dtype=float)
    running_maximum = 0.0

    for index, p_value in enumerate(sorted_values):
        multiplier = comparison_count - index
        candidate = min(1.0, multiplier * p_value)
        running_maximum = max(running_maximum, candidate)
        adjusted_sorted[index] = running_maximum

    adjusted = np.empty(comparison_count, dtype=float)
    adjusted[order] = adjusted_sorted
    return pd.Series(adjusted, index=p_values.index, dtype="float64")


def select_condition(
    analysis_frame: pd.DataFrame,
    model_id: object,
    evidence_level: object,
) -> pd.DataFrame:
    """Select one model × evidence condition without relying on row order."""

    return analysis_frame.loc[
        (analysis_frame["model_id"] == model_id)
        & (analysis_frame["evidence_level"] == evidence_level)
    ]


def build_paired_tests(
    analysis_frame: pd.DataFrame,
    metric_id: str = PRIMARY_METRIC,
    analysis_role: str = "PRIMARY",
) -> pd.DataFrame:
    """Run 33 frozen planned primary paired comparisons."""

    model_ids = ordered_levels(
        analysis_frame,
        "model_id",
        "model_order",
    )
    evidence_levels = ordered_levels(
        analysis_frame,
        "evidence_level",
        "evidence_order",
    )

    if "S0" not in evidence_levels:
        raise ValueError(
            "Evidence-vs-baseline contrasts require S0."
        )

    rows: list[dict[str, object]] = []

    for evidence_level in evidence_levels:
        for model_a, model_b in combinations(model_ids, 2):
            result = run_wilcoxon_pair(
                select_condition(
                    analysis_frame,
                    model_a,
                    evidence_level,
                ),
                select_condition(
                    analysis_frame,
                    model_b,
                    evidence_level,
                ),
                metric_id,
            )
            rows.append(
                {
                    "analysis_role": analysis_role,
                    "metric_id": metric_id,
                    "contrast_family": "model_within_evidence",
                    "context_model_id": None,
                    "context_evidence_level": evidence_level,
                    "condition_a_model_id": model_a,
                    "condition_a_evidence_level": evidence_level,
                    "condition_b_model_id": model_b,
                    "condition_b_evidence_level": evidence_level,
                    "planned_pair_count": analysis_frame[
                        "case_id"
                    ].nunique(),
                    **result,
                }
            )

    for model_id in model_ids:
        baseline = select_condition(
            analysis_frame,
            model_id,
            "S0",
        )

        for evidence_level in evidence_levels:
            if evidence_level == "S0":
                continue

            result = run_wilcoxon_pair(
                select_condition(
                    analysis_frame,
                    model_id,
                    evidence_level,
                ),
                baseline,
                metric_id,
            )
            rows.append(
                {
                    "analysis_role": analysis_role,
                    "metric_id": metric_id,
                    "contrast_family": "evidence_vs_s0",
                    "context_model_id": model_id,
                    "context_evidence_level": None,
                    "condition_a_model_id": model_id,
                    "condition_a_evidence_level": evidence_level,
                    "condition_b_model_id": model_id,
                    "condition_b_evidence_level": "S0",
                    "planned_pair_count": analysis_frame[
                        "case_id"
                    ].nunique(),
                    **result,
                }
            )

    output = pd.DataFrame(rows)
    output["excluded_pair_count"] = (
        output["planned_pair_count"]
        - output["observed_pair_count"]
    )
    output["adjusted_p_value"] = output.groupby(
        ["metric_id", "contrast_family"],
        sort=False,
    )["raw_p_value"].transform(holm_adjust)
    output["adjustment_method"] = "holm"
    output["alpha"] = ALPHA
    output["significant_raw"] = output["raw_p_value"] < ALPHA
    output["significant_adjusted"] = (
        output["adjusted_p_value"] < ALPHA
    )

    model_order = {
        model_id: index
        for index, model_id in enumerate(model_ids)
    }
    evidence_order = {
        evidence_level: index
        for index, evidence_level in enumerate(evidence_levels)
    }
    family_order = {
        "model_within_evidence": 0,
        "evidence_vs_s0": 1,
    }

    output["_family_order"] = output["contrast_family"].map(
        family_order
    )
    output["_context_model_order"] = output[
        "context_model_id"
    ].map(model_order)
    output["_context_evidence_order"] = output[
        "context_evidence_level"
    ].map(evidence_order)
    output["_a_model_order"] = output[
        "condition_a_model_id"
    ].map(model_order)
    output["_a_evidence_order"] = output[
        "condition_a_evidence_level"
    ].map(evidence_order)
    output["_b_model_order"] = output[
        "condition_b_model_id"
    ].map(model_order)

    output = output.sort_values(
        [
            "_family_order",
            "_context_evidence_order",
            "_context_model_order",
            "_a_model_order",
            "_a_evidence_order",
            "_b_model_order",
        ],
        kind="stable",
        na_position="first",
    ).reset_index(drop=True)

    return output.drop(
        columns=[
            column
            for column in output.columns
            if column.startswith("_")
        ]
    )

def build_conditional_paired_tests(
    analysis_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Run frozen planned paired sensitivities for conditional metrics.

    Missing unusable cells are never imputed. Each contrast reports the
    observed and excluded case-pair counts explicitly.
    """

    outputs = [
        build_paired_tests(
            analysis_frame,
            metric_id=metric_id,
            analysis_role="SECONDARY_CONDITIONAL",
        )
        for metric_id in SECONDARY_METRICS
    ]
    return pd.concat(outputs, ignore_index=True)


def build_complete_case_omnibus_tests(
    analysis_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Run a balanced semantic sensitivity on cases with all 18 usable cells."""

    complete = analysis_frame.loc[
        analysis_frame["is_complete_case"].astype(bool)
    ].copy()
    if complete.empty:
        raise ValueError("No complete cases are available for sensitivity analysis.")

    return run_repeated_measures_anova(
        complete,
        metric_id="conservative_faithfulness",
        analysis_role="SENSITIVITY_COMPLETE_CASE",
    )
