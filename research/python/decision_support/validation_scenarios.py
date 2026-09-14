"""Validation cho scenario scores, Pareto, ranking và recommendations."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .build import (
    build_recommendations,
    build_scenario_rankings,
    enrich_recommendations_with_evidence,
)
from .config import EXPECTED_COUNTS, KNOWN_CRITERIA
from .evidence import (
    build_recommendation_evidence,
    summarize_primary_evidence,
)
from .pareto import build_pareto_frontier
from .scoring import build_scenario_definitions, build_scenario_scores
from .validation_common import (
    ValidationChecks,
    add_check,
    dataframe_key_set,
    dataframe_value_mismatch_count,
)


def validate_scenario_definitions(
    checks: ValidationChecks,
    observed: pd.DataFrame,
) -> None:
    """Kiểm năm scenarios, rule keys và weight sums."""

    expected = build_scenario_definitions()
    key_columns = ["scenario_id", "rule_type", "criterion_id"]

    scenario_count = int(observed["scenario_id"].nunique())
    add_check(
        checks,
        "scenario_count",
        EXPECTED_COUNTS["scenarios"],
        scenario_count,
        scenario_count == EXPECTED_COUNTS["scenarios"],
    )
    duplicate_count = int(
        observed.duplicated(subset=key_columns, keep=False).sum()
    )
    add_check(
        checks,
        "duplicate_scenario_rule_count",
        0,
        duplicate_count,
        duplicate_count == 0,
    )
    key_mismatch = len(
        dataframe_key_set(observed, key_columns)
        ^ dataframe_key_set(expected, key_columns)
    )
    add_check(
        checks,
        "scenario_definition_key_set_mismatch_count",
        0,
        key_mismatch,
        key_mismatch == 0,
    )
    value_mismatch = dataframe_value_mismatch_count(
        observed,
        expected,
        key_columns,
    )
    add_check(
        checks,
        "scenario_definition_value_mismatch_count",
        0,
        value_mismatch,
        value_mismatch == 0,
    )

    objectives = observed.loc[
        observed["rule_type"] == "WEIGHTED_OBJECTIVE"
    ]
    weight_sums = objectives.groupby("scenario_id")["weight"].sum()
    bad_weight_sum = int(
        (~np.isclose(weight_sums, 1.0, rtol=0.0, atol=1e-12)).sum()
    )
    add_check(
        checks,
        "scenario_weight_sum_mismatch_count",
        0,
        bad_weight_sum,
        bad_weight_sum == 0,
    )
    unknown_criteria = sorted(
        set(observed["criterion_id"].astype(str)) - KNOWN_CRITERIA
    )
    add_check(
        checks,
        "unknown_scenario_criteria",
        [],
        unknown_criteria,
        unknown_criteria == [],
    )
    invalid_directions = int(
        (~observed["direction"].isin(["MAX", "MIN", "RANGE"])).sum()
    )
    add_check(
        checks,
        "invalid_scenario_direction_count",
        0,
        invalid_directions,
        invalid_directions == 0,
    )


def rebuild_scenario_outputs(
    options: pd.DataFrame,
    definitions: pd.DataFrame,
    paired_tests: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Rebuild mọi downstream decision output từ options và definitions."""

    scores, ranking_base = build_scenario_scores(options, definitions)
    pareto = build_pareto_frontier(ranking_base, definitions)
    rankings = build_scenario_rankings(ranking_base, pareto)
    recommendations = build_recommendations(rankings)
    evidence = build_recommendation_evidence(
        recommendations,
        options,
        paired_tests,
    )
    recommendations = enrich_recommendations_with_evidence(
        recommendations,
        summarize_primary_evidence(evidence),
    )
    return {
        "scenario_criterion_scores": scores,
        "scenario_rankings": rankings,
        "pareto_frontier": pareto,
        "recommendations": recommendations,
        "recommendation_evidence": evidence,
    }


def compare_output(
    checks: ValidationChecks,
    check_prefix: str,
    observed: pd.DataFrame,
    expected: pd.DataFrame,
    key_columns: list[str],
) -> None:
    """So key set và toàn bộ values cho một output."""

    key_mismatch = len(
        dataframe_key_set(observed, key_columns)
        ^ dataframe_key_set(expected, key_columns)
    )
    add_check(
        checks,
        f"{check_prefix}_key_set_mismatch_count",
        0,
        key_mismatch,
        key_mismatch == 0,
    )
    value_mismatch = dataframe_value_mismatch_count(
        observed,
        expected,
        key_columns,
    )
    add_check(
        checks,
        f"{check_prefix}_value_mismatch_count",
        0,
        value_mismatch,
        value_mismatch == 0,
    )


def validate_scenario_outputs(
    checks: ValidationChecks,
    outputs: dict[str, pd.DataFrame],
    input_data: dict[str, Any],
) -> None:
    """Rebuild score, Pareto, ranking, recommendation và evidence outputs."""

    expected = rebuild_scenario_outputs(
        outputs["decision_options"],
        outputs["scenario_definitions"],
        input_data["paired_tests"],
    )

    compare_output(
        checks,
        "criterion_score",
        outputs["scenario_criterion_scores"],
        expected["scenario_criterion_scores"],
        ["scenario_id", "option_id", "criterion_id"],
    )
    compare_output(
        checks,
        "pareto",
        outputs["pareto_frontier"],
        expected["pareto_frontier"],
        ["scenario_id", "option_id"],
    )
    compare_output(
        checks,
        "ranking",
        outputs["scenario_rankings"],
        expected["scenario_rankings"],
        ["scenario_id", "option_id"],
    )
    compare_output(
        checks,
        "recommendation",
        outputs["recommendations"],
        expected["recommendations"],
        ["scenario_id", "recommendation_rank"],
    )
    compare_output(
        checks,
        "recommendation_evidence",
        outputs["recommendation_evidence"],
        expected["recommendation_evidence"],
        ["scenario_id", "comparator_option_id"],
    )

    ranking_count = len(outputs["scenario_rankings"])
    add_check(
        checks,
        "scenario_ranking_row_count",
        EXPECTED_COUNTS["ranking_rows"],
        ranking_count,
        ranking_count == EXPECTED_COUNTS["ranking_rows"],
    )

    rankings = outputs["scenario_rankings"]
    scored = rankings["eligible"].astype(bool) & rankings[
        "score_available"
    ].astype(bool)
    utility_rank_mismatches = int(
        rankings.loc[scored, "utility_rank"].isna().sum()
        + rankings.loc[~scored, "utility_rank"].notna().sum()
    )
    for _, group in rankings.loc[scored].groupby("scenario_id", sort=False):
        observed_ranks = sorted(group["utility_rank"].astype(int).tolist())
        expected_ranks = list(range(1, len(group) + 1))
        utility_rank_mismatches += sum(
            observed != expected
            for observed, expected in zip(observed_ranks, expected_ranks)
        )
    add_check(
        checks,
        "utility_rank_state_mismatch_count",
        0,
        utility_rank_mismatches,
        utility_rank_mismatches == 0,
    )

    reason_code_mismatches = 0
    for recommendation in outputs["recommendations"].itertuples(index=False):
        codes = json.loads(recommendation.reason_codes)
        if recommendation.recommendation_role == "PRIMARY":
            valid = (
                "TOP_SCENARIO_UTILITY" in codes
                and "TOP_PARETO_ALTERNATIVE" not in codes
                and "TOP_THREE_SCENARIO_UTILITY" not in codes
            )
        else:
            valid = (
                "TOP_PARETO_ALTERNATIVE" in codes
                and "TOP_SCENARIO_UTILITY" not in codes
                and "TOP_THREE_SCENARIO_UTILITY" not in codes
            )
        reason_code_mismatches += int(not valid)
    add_check(
        checks,
        "recommendation_reason_code_mismatch_count",
        0,
        reason_code_mismatches,
        reason_code_mismatches == 0,
    )
    primary_count = int(
        (
            outputs["recommendations"]["recommendation_role"]
            == "PRIMARY"
        ).sum()
    )
    add_check(
        checks,
        "primary_recommendation_count",
        EXPECTED_COUNTS["primary_recommendations"],
        primary_count,
        primary_count == EXPECTED_COUNTS["primary_recommendations"],
    )
    evidence_count = len(outputs["recommendation_evidence"])
    add_check(
        checks,
        "recommendation_evidence_row_count",
        EXPECTED_COUNTS["recommendation_evidence_rows"],
        evidence_count,
        evidence_count == EXPECTED_COUNTS["recommendation_evidence_rows"],
    )

    normalized = outputs["scenario_criterion_scores"]["normalized_value"]
    invalid_normalized = int(
        (
            normalized.notna()
            & ((normalized < 0.0) | (normalized > 1.0))
        ).sum()
    )
    add_check(
        checks,
        "normalized_value_out_of_bounds_count",
        0,
        invalid_normalized,
        invalid_normalized == 0,
    )

    ineligible_scored = int(
        (
            ~outputs["scenario_rankings"]["eligible"].astype(bool)
            & outputs["scenario_rankings"]["utility_score"].notna()
        ).sum()
    )
    add_check(
        checks,
        "ineligible_nonnull_utility_count",
        0,
        ineligible_scored,
        ineligible_scored == 0,
    )

    invalid_recommendation = int(
        (
            ~outputs["recommendations"]["is_pareto_optimal"].astype(bool)
        ).sum()
    )
    add_check(
        checks,
        "non_pareto_recommendation_count",
        0,
        invalid_recommendation,
        invalid_recommendation == 0,
    )
