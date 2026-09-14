"""Case-level paired inference for LLM versus Template Baseline."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import rankdata, wilcoxon

from research.python.statistical_analysis.inference import holm_adjust

from .config import ALPHA, TEST_METRICS


def rank_biserial(differences: np.ndarray) -> float:
    nonzero = differences[np.abs(differences) > 1e-15]
    if len(nonzero) == 0:
        return 0.0
    ranks = rankdata(np.abs(nonzero), method="average")
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    denominator = positive + negative
    return 0.0 if denominator == 0 else (positive - negative) / denominator


def paired_test(
    frame: pd.DataFrame,
    llm_column: str,
    template_column: str,
) -> dict[str, float | int]:
    complete = frame[["case_id", llm_column, template_column]].dropna()
    if complete["case_id"].duplicated().any():
        raise ValueError("Paired baseline test must contain one row per case.")
    llm_values = complete[llm_column].to_numpy(dtype=float)
    template_values = complete[template_column].to_numpy(dtype=float)
    differences = llm_values - template_values
    if len(differences) == 0:
        raise ValueError("No complete pairs are available.")
    if np.allclose(differences, 0.0, rtol=0.0, atol=1e-15):
        statistic = 0.0
        p_value = 1.0
    else:
        result = wilcoxon(
            differences,
            zero_method="wilcox",
            correction=False,
            alternative="two-sided",
            method="auto",
        )
        statistic = float(result.statistic)
        p_value = float(result.pvalue)
    return {
        "paired_case_count": int(len(complete)),
        "llm_mean": float(llm_values.mean()),
        "template_mean": float(template_values.mean()),
        "mean_delta_llm_minus_template": float(differences.mean()),
        "median_delta_llm_minus_template": float(np.median(differences)),
        "wilcoxon_statistic": statistic,
        "raw_p_value": p_value,
        "rank_biserial_correlation": float(rank_biserial(differences)),
    }


def build_baseline_tests(pairs: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metric_id, (llm_column, template_column) in TEST_METRICS.items():
        for (model_id, evidence_level), group in pairs.groupby(
            ["model_id", "evidence_level"],
            sort=False,
        ):
            rows.append(
                {
                    "analysis_role": "RQ6_PER_EVIDENCE",
                    "contrast_family": "llm_vs_template_within_evidence",
                    "metric_id": metric_id,
                    "model_id": model_id,
                    "evidence_level": evidence_level,
                    "evidence_scope": evidence_level,
                    **paired_test(group, llm_column, template_column),
                }
            )

        pooled = pairs.loc[pairs["evidence_level"].isin(["S1", "S2", "S3", "S4"])].copy()
        for model_id, model_group in pooled.groupby("model_id", sort=False):
            case_aggregate = (
                model_group.groupby("case_id", as_index=False)[
                    [llm_column, template_column]
                ]
                .mean()
            )
            rows.append(
                {
                    "analysis_role": "RQ6_POOLED_S1_S4",
                    "contrast_family": "llm_vs_template_case_aggregated_s1_s4",
                    "metric_id": metric_id,
                    "model_id": model_id,
                    "evidence_level": None,
                    "evidence_scope": "S1-S4_CASE_MEAN",
                    **paired_test(
                        case_aggregate,
                        llm_column,
                        template_column,
                    ),
                }
            )

    output = pd.DataFrame(rows)
    output["planned_pair_count"] = 36
    output["excluded_pair_count"] = (
        output["planned_pair_count"] - output["paired_case_count"]
    )
    output["adjusted_p_value"] = output.groupby(
        ["metric_id", "contrast_family"],
        sort=False,
    )["raw_p_value"].transform(holm_adjust)
    output["adjustment_method"] = "holm_within_metric_and_family"
    output["alpha"] = ALPHA
    output["significant_adjusted"] = output["adjusted_p_value"] < ALPHA
    output["inference_unit"] = "paired_canonical_case"
    output["claims_used_as_independent_units"] = False
    return output.sort_values(
        ["metric_id", "contrast_family", "model_id", "evidence_scope"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
