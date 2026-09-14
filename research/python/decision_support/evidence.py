"""Gắn paired statistical evidence vào primary recommendations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ALPHA


def option_id(model_id: object, evidence_level: object) -> str:
    """Tạo option ID theo cùng quy tắc với decision_options.csv."""

    return f"{model_id}__{evidence_level}"


def paired_test_lookup(paired_tests: pd.DataFrame) -> dict[frozenset[str], dict]:
    """Map một unordered option pair tới đúng một planned paired test."""

    lookup: dict[frozenset[str], dict] = {}
    for row in paired_tests.to_dict("records"):
        option_a = option_id(
            row["condition_a_model_id"],
            row["condition_a_evidence_level"],
        )
        option_b = option_id(
            row["condition_b_model_id"],
            row["condition_b_evidence_level"],
        )
        key = frozenset({option_a, option_b})
        if key in lookup:
            raise ValueError(f"Duplicate paired test for option pair: {key}")
        row["option_a"] = option_a
        row["option_b"] = option_b
        lookup[key] = row
    return lookup


def classify_evidence(
    adjusted_p_value: float,
    oriented_difference: float,
) -> str:
    """Phân loại test đã orient theo recommendation − comparator."""

    if adjusted_p_value < ALPHA and oriented_difference > 0:
        return "SIGNIFICANT_ADVANTAGE"
    if adjusted_p_value < ALPHA and oriented_difference < 0:
        return "SIGNIFICANT_DISADVANTAGE"
    return "NO_SIGNIFICANT_DIFFERENCE"


def build_recommendation_evidence(
    recommendations: pd.DataFrame,
    decision_options: pd.DataFrame,
    paired_tests: pd.DataFrame,
) -> pd.DataFrame:
    """Tạo 17 comparator rows cho primary recommendation của mỗi scenario."""

    primary = recommendations.loc[
        recommendations["recommendation_role"] == "PRIMARY"
    ]
    option_values = decision_options.set_index("option_id")
    lookup = paired_test_lookup(paired_tests)
    rows: list[dict[str, object]] = []

    for recommendation in primary.itertuples(index=False):
        recommended_id = str(recommendation.option_id)
        recommended_mean = float(
            option_values.loc[recommended_id, "mean_end_to_end_yield"]
        )

        for comparator_id in option_values.index:
            comparator_id = str(comparator_id)
            if comparator_id == recommended_id:
                continue

            comparator_mean = float(
                option_values.loc[comparator_id, "mean_end_to_end_yield"]
            )
            test = lookup.get(frozenset({recommended_id, comparator_id}))

            if test is None:
                rows.append(
                    {
                        "scenario_order": int(recommendation.scenario_order),
                        "scenario_id": recommendation.scenario_id,
                        "recommended_option_id": recommended_id,
                        "comparator_option_id": comparator_id,
                        "comparison_available": False,
                        "comparison_family": None,
                        "comparison_orientation": None,
                        "recommended_mean": recommended_mean,
                        "comparator_mean": comparator_mean,
                        "oriented_mean_difference": np.nan,
                        "adjusted_p_value": np.nan,
                        "oriented_rank_biserial_correlation": np.nan,
                        "evidence_status": "NOT_TESTED",
                    }
                )
                continue

            recommendation_is_a = test["option_a"] == recommended_id
            orientation = (
                "RECOMMENDATION_IS_A"
                if recommendation_is_a
                else "RECOMMENDATION_IS_B"
            )
            sign = 1.0 if recommendation_is_a else -1.0
            oriented_difference = sign * float(test["mean_difference"])
            oriented_rbc = sign * float(test["rank_biserial_correlation"])
            adjusted_p = float(test["adjusted_p_value"])

            rows.append(
                {
                    "scenario_order": int(recommendation.scenario_order),
                    "scenario_id": recommendation.scenario_id,
                    "recommended_option_id": recommended_id,
                    "comparator_option_id": comparator_id,
                    "comparison_available": True,
                    "comparison_family": test["contrast_family"],
                    "comparison_orientation": orientation,
                    "recommended_mean": recommended_mean,
                    "comparator_mean": comparator_mean,
                    "oriented_mean_difference": oriented_difference,
                    "adjusted_p_value": adjusted_p,
                    "oriented_rank_biserial_correlation": oriented_rbc,
                    "evidence_status": classify_evidence(
                        adjusted_p,
                        oriented_difference,
                    ),
                }
            )

    return pd.DataFrame(rows).sort_values(
        ["scenario_order", "comparator_option_id"],
        kind="stable",
    ).reset_index(drop=True)


def summarize_primary_evidence(
    evidence: pd.DataFrame,
) -> pd.DataFrame:
    """Đếm tested/untested và các hướng significant cho mỗi scenario."""

    rows: list[dict[str, object]] = []
    for scenario_id, group in evidence.groupby("scenario_id", sort=False):
        status_counts = group["evidence_status"].value_counts()
        rows.append(
            {
                "scenario_order": int(group["scenario_order"].iloc[0]),
                "scenario_id": scenario_id,
                "tested_comparator_count": int(
                    group["comparison_available"].astype(bool).sum()
                ),
                "significant_advantage_count": int(
                    status_counts.get("SIGNIFICANT_ADVANTAGE", 0)
                ),
                "significant_disadvantage_count": int(
                    status_counts.get("SIGNIFICANT_DISADVANTAGE", 0)
                ),
                "no_significant_difference_count": int(
                    status_counts.get("NO_SIGNIFICANT_DIFFERENCE", 0)
                ),
                "untested_comparator_count": int(
                    status_counts.get("NOT_TESTED", 0)
                ),
            }
        )
    return pd.DataFrame(rows)
