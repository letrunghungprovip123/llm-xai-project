"""Build và ghi toàn bộ Decision Support Core outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import (
    DECISION_OPTIONS_PATH,
    MAX_RECOMMENDATIONS_PER_SCENARIO,
    PARETO_FRONTIER_PATH,
    RECOMMENDATIONS_PATH,
    RECOMMENDATION_EVIDENCE_PATH,
    SCENARIO_CRITERION_SCORES_PATH,
    SCENARIO_DEFINITIONS_PATH,
    SCENARIO_RANKINGS_PATH,
)
from .evidence import (
    build_recommendation_evidence,
    summarize_primary_evidence,
)
from .pareto import build_pareto_frontier
from .prepare import build_decision_options
from .scoring import build_scenario_definitions, build_scenario_scores


def add_utility_ranks(ranking: pd.DataFrame) -> pd.DataFrame:
    """Xếp utility trực tiếp, không ưu tiên Pareto trước.

    ``scenario_rank`` dùng Pareto-first để trình bày recommendation.
    ``utility_rank`` chỉ phản ánh thứ tự utility trong các option đủ điều kiện.
    Hai cột phải được giữ riêng để dashboard không diễn giải nhầm.
    """

    scored = ranking.loc[
        ranking["eligible"].astype(bool)
        & ranking["score_available"].astype(bool)
    ].copy()
    scored = scored.sort_values(
        [
            "scenario_order",
            "utility_score",
            "mean_end_to_end_yield",
            "usability_rate",
            "mean_latency_seconds_planned",
            "model_order",
            "evidence_order",
        ],
        ascending=[True, False, False, False, True, True, True],
        kind="stable",
    )
    scored["utility_rank"] = (
        scored.groupby("scenario_id", sort=False).cumcount() + 1
    ).astype("Int64")

    return ranking.merge(
        scored[["scenario_id", "option_id", "utility_rank"]],
        on=["scenario_id", "option_id"],
        how="left",
        validate="one_to_one",
    )


def build_scenario_rankings(
    ranking_base: pd.DataFrame,
    pareto_frontier: pd.DataFrame,
) -> pd.DataFrame:
    """Xếp hạng ổn định nhưng vẫn giữ đủ ineligible options."""

    ranking = ranking_base.merge(
        pareto_frontier[
            ["scenario_order", "scenario_id", "option_id", "is_pareto_optimal"]
        ],
        on=["scenario_order", "scenario_id", "option_id"],
        how="left",
        validate="one_to_one",
    )
    ranking["is_pareto_optimal"] = ranking[
        "is_pareto_optimal"
    ].fillna(False).astype(bool)
    ranking = add_utility_ranks(ranking)

    ranking["_eligible_sort"] = ~ranking["eligible"].astype(bool)
    ranking["_score_sort"] = ~ranking["score_available"].astype(bool)
    ranking["_pareto_sort"] = ~ranking["is_pareto_optimal"].astype(bool)
    ranking["_utility_sort"] = ranking["utility_score"].fillna(-np.inf)

    ranking = ranking.sort_values(
        [
            "scenario_order",
            "_eligible_sort",
            "_score_sort",
            "_pareto_sort",
            "_utility_sort",
            "mean_end_to_end_yield",
            "usability_rate",
            "mean_latency_seconds_planned",
            "model_order",
            "evidence_order",
        ],
        ascending=[
            True,
            True,
            True,
            True,
            False,
            False,
            False,
            True,
            True,
            True,
        ],
        kind="stable",
    ).reset_index(drop=True)

    ranking["scenario_rank"] = ranking.groupby(
        "scenario_id",
        sort=False,
    ).cumcount() + 1
    ranking["eligible_rank"] = pd.Series(pd.NA, index=ranking.index, dtype="Int64")
    eligible_mask = ranking["eligible"].astype(bool)
    ranking.loc[eligible_mask, "eligible_rank"] = (
        ranking.loc[eligible_mask]
        .groupby("scenario_id", sort=False)
        .cumcount()
        + 1
    )
    ranking["pareto_rank"] = pd.Series(pd.NA, index=ranking.index, dtype="Int64")
    pareto_mask = ranking["is_pareto_optimal"].astype(bool)
    ranking.loc[pareto_mask, "pareto_rank"] = (
        ranking.loc[pareto_mask]
        .groupby("scenario_id", sort=False)
        .cumcount()
        + 1
    )

    ranking = ranking.rename(columns={"is_pareto_optimal": "pareto_optimal"})
    drop_columns = [
        "_eligible_sort",
        "_score_sort",
        "_pareto_sort",
        "_utility_sort",
    ]
    return ranking.drop(columns=drop_columns)


def median_of_eligible(group: pd.DataFrame, column: str) -> float:
    """Median dùng để tạo reason/caution codes có thể giải thích."""

    eligible = group.loc[group["eligible"].astype(bool), column].dropna()
    return float(eligible.median()) if not eligible.empty else float("nan")


def build_reason_codes(
    row: pd.Series,
    scenario_group: pd.DataFrame,
    recommendation_rank: int,
) -> list[str]:
    """Tạo reason codes hoàn toàn deterministic."""

    codes = ["MEETS_ALL_CONSTRAINTS", "PARETO_OPTIMAL"]
    codes.append(
        "TOP_SCENARIO_UTILITY"
        if recommendation_rank == 1
        else "TOP_PARETO_ALTERNATIVE"
    )

    if row["usability_rate"] >= 1.0:
        codes.append("FULL_USABILITY")
    if row["mean_end_to_end_yield"] >= median_of_eligible(
        scenario_group,
        "mean_end_to_end_yield",
    ):
        codes.append("HIGH_MEAN_QUALITY")
    if row["p10_end_to_end_yield"] >= median_of_eligible(
        scenario_group,
        "p10_end_to_end_yield",
    ):
        codes.append("HIGH_CASE_ROBUSTNESS")
    if row["mean_supported_claims_per_1000_tokens"] >= median_of_eligible(
        scenario_group,
        "mean_supported_claims_per_1000_tokens",
    ):
        codes.append("TOKEN_EFFICIENT")
    if row["strong_safe_phrase_signal_share_all_claims"] <= median_of_eligible(
        scenario_group,
        "strong_safe_phrase_signal_share_all_claims",
    ):
        codes.append("LOW_STRONG_OVERLAP_SIGNAL")
    return codes


def build_caution_codes(
    row: pd.Series,
    scenario_group: pd.DataFrame,
    primary_quality: float,
) -> list[str]:
    """Ghi rõ trade-off thay vì che mất nhược điểm của option."""

    codes: list[str] = []
    if row["unusable_generation_count"] > 0:
        codes.append("PIPELINE_FAILURE_PRESENT")
    if row["mean_end_to_end_yield"] < primary_quality:
        codes.append("QUALITY_BELOW_SCENARIO_LEADER")
    if row["strong_safe_phrase_signal_share_all_claims"] > median_of_eligible(
        scenario_group,
        "strong_safe_phrase_signal_share_all_claims",
    ):
        codes.append("HIGH_STRONG_OVERLAP_SIGNAL")
    if row["weak_safe_phrase_signal_share_all_claims"] > median_of_eligible(
        scenario_group,
        "weak_safe_phrase_signal_share_all_claims",
    ):
        codes.append("HIGH_WEAK_OVERLAP_SIGNAL")
    if row["mean_total_token_count_planned"] > median_of_eligible(
        scenario_group,
        "mean_total_token_count_planned",
    ):
        codes.append("HIGH_TOKEN_USAGE")
    if row["mean_latency_seconds_planned"] > median_of_eligible(
        scenario_group,
        "mean_latency_seconds_planned",
    ):
        codes.append("HIGH_LATENCY")
    return codes


def build_recommendations(rankings: pd.DataFrame) -> pd.DataFrame:
    """Chọn tối đa ba Pareto-optimal recommendations cho mỗi scenario."""

    rows: list[dict[str, object]] = []
    for scenario_id, group in rankings.groupby("scenario_id", sort=False):
        candidates = group.loc[
            group["eligible"].astype(bool)
            & group["score_available"].astype(bool)
            & group["pareto_optimal"].astype(bool)
        ].head(MAX_RECOMMENDATIONS_PER_SCENARIO)

        if candidates.empty:
            raise ValueError(f"Scenario {scenario_id} has no valid recommendation.")

        primary_quality = float(candidates.iloc[0]["mean_end_to_end_yield"])
        for recommendation_rank, (_, row) in enumerate(
            candidates.iterrows(),
            start=1,
        ):
            reason_codes = build_reason_codes(
                row,
                group,
                recommendation_rank,
            )
            caution_codes = build_caution_codes(
                row,
                group,
                primary_quality,
            )
            rows.append(
                {
                    "scenario_order": int(row["scenario_order"]),
                    "scenario_id": scenario_id,
                    "recommendation_rank": recommendation_rank,
                    "recommendation_role": (
                        "PRIMARY" if recommendation_rank == 1 else "ALTERNATIVE"
                    ),
                    "option_id": row["option_id"],
                    "model_id": row["model_id"],
                    "evidence_level": row["evidence_level"],
                    "utility_score": row["utility_score"],
                    "is_pareto_optimal": bool(row["pareto_optimal"]),
                    "mean_end_to_end_yield": row["mean_end_to_end_yield"],
                    "p10_end_to_end_yield": row["p10_end_to_end_yield"],
                    "usability_rate": row["usability_rate"],
                    "mean_pipeline_loss": row["mean_pipeline_loss"],
                    "mean_resolved_error_loss": row[
                        "mean_resolved_error_loss"
                    ],
                    "mean_latency_seconds_planned": row[
                        "mean_latency_seconds_planned"
                    ],
                    "mean_total_token_count_planned": row[
                        "mean_total_token_count_planned"
                    ],
                    "mean_supported_claims_per_1000_tokens": row[
                        "mean_supported_claims_per_1000_tokens"
                    ],
                    "strong_safe_phrase_signal_share_all_claims": row[
                        "strong_safe_phrase_signal_share_all_claims"
                    ],
                    "weak_safe_phrase_signal_share_all_claims": row[
                        "weak_safe_phrase_signal_share_all_claims"
                    ],
                    "reason_codes": json.dumps(
                        reason_codes,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "caution_codes": json.dumps(
                        caution_codes,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )

    return pd.DataFrame(rows)


def enrich_recommendations_with_evidence(
    recommendations: pd.DataFrame,
    evidence_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Chỉ primary recommendation nhận statistical evidence summary."""

    output = recommendations.merge(
        evidence_summary,
        on=["scenario_order", "scenario_id"],
        how="left",
        validate="many_to_one",
    )
    primary = output["recommendation_role"] == "PRIMARY"
    evidence_columns = [
        "tested_comparator_count",
        "significant_advantage_count",
        "significant_disadvantage_count",
        "no_significant_difference_count",
        "untested_comparator_count",
    ]
    output.loc[~primary, evidence_columns] = np.nan

    for index in output.index[primary]:
        cautions = json.loads(output.at[index, "caution_codes"])
        if output.at[index, "untested_comparator_count"] > 0:
            cautions.append("STATISTICAL_ADVANTAGE_NOT_TESTED")
        if output.at[index, "significant_disadvantage_count"] > 0:
            cautions.append("SIGNIFICANT_QUALITY_DISADVANTAGE_EXISTS")
        output.at[index, "caution_codes"] = json.dumps(
            cautions,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    return output


def build_decision_outputs(
    input_data: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    """Chạy Decision Support theo thứ tự dễ kiểm tra."""

    options = build_decision_options(input_data)
    definitions = build_scenario_definitions()
    criterion_scores, ranking_base = build_scenario_scores(
        options,
        definitions,
    )
    pareto = build_pareto_frontier(ranking_base, definitions)
    rankings = build_scenario_rankings(ranking_base, pareto)
    recommendations = build_recommendations(rankings)
    recommendation_evidence = build_recommendation_evidence(
        recommendations,
        options,
        input_data["paired_tests"],
    )
    evidence_summary = summarize_primary_evidence(recommendation_evidence)
    recommendations = enrich_recommendations_with_evidence(
        recommendations,
        evidence_summary,
    )

    return {
        "decision_options": options,
        "scenario_definitions": definitions,
        "scenario_criterion_scores": criterion_scores,
        "scenario_rankings": rankings,
        "pareto_frontier": pareto,
        "recommendations": recommendations,
        "recommendation_evidence": recommendation_evidence,
    }


def write_decision_outputs(outputs: dict[str, pd.DataFrame]) -> None:
    """Ghi bảy CSV outputs theo path cố định."""

    path_map: dict[str, Path] = {
        "decision_options": DECISION_OPTIONS_PATH,
        "scenario_definitions": SCENARIO_DEFINITIONS_PATH,
        "scenario_criterion_scores": SCENARIO_CRITERION_SCORES_PATH,
        "scenario_rankings": SCENARIO_RANKINGS_PATH,
        "pareto_frontier": PARETO_FRONTIER_PATH,
        "recommendations": RECOMMENDATIONS_PATH,
        "recommendation_evidence": RECOMMENDATION_EVIDENCE_PATH,
    }
    for name, file_path in path_map.items():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        outputs[name].to_csv(file_path, index=False)
