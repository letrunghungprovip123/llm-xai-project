"""Generation-grain and pipeline-failure validation rules."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import CLAIM_TYPE_COUNT_COLUMNS, EXPECTED_COUNTS, NUMERIC_TOLERANCE
from .safe_phrase import extract_safe_phrase_items, match_generation_narratives
from .summarize import classify_failure
from .validation_common import (
    ValidationChecks,
    add_check,
    dataframe_value_mismatch_count,
)
from .validation_safe_phrase import validation_cache


def generation_count_mismatch_count(
    generation_diagnostics: pd.DataFrame,
    claim_diagnostics: pd.DataFrame,
) -> int:
    """Recalculate generation claim counts from claim diagnostics."""

    grouped = claim_diagnostics.groupby("generation_id").agg(
        claim_count=("claim_id", "size"),
        supported_count=("is_supported", "sum"),
        unsupported_count=("is_unsupported", "sum"),
        contradicted_count=("is_contradicted", "sum"),
        not_verifiable_count=("is_not_verifiable", "sum"),
        not_applicable_count=("is_not_applicable", "sum"),
        resolved_count=("is_resolved", "sum"),
        applicable_count=("is_applicable", "sum"),
    ).reset_index()

    joined = generation_diagnostics.merge(
        grouped,
        on="generation_id",
        how="left",
        validate="one_to_one",
        suffixes=("_diagnostic", "_claims"),
    )

    mismatch_count = 0
    columns = [
        "claim_count",
        "supported_count",
        "unsupported_count",
        "contradicted_count",
        "not_verifiable_count",
        "not_applicable_count",
        "resolved_count",
        "applicable_count",
    ]
    for column in columns:
        source = joined[f"{column}_claims"].fillna(0).astype(int)
        observed = joined[f"{column}_diagnostic"].astype(int)
        mismatch_count += int((source != observed).sum())

    return mismatch_count


def expected_loss_components(
    generation_diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    """Recalculate every loss component from audited status counts."""

    expected = generation_diagnostics[["generation_id"]].copy()
    usable = generation_diagnostics["usable"].astype(bool)
    applicable = generation_diagnostics["applicable_count"].astype(float)

    expected["supported_yield_component"] = 0.0
    expected["pipeline_loss"] = (~usable).astype(float)
    expected["not_verifiable_loss"] = 0.0
    expected["unsupported_loss"] = 0.0
    expected["contradiction_loss"] = 0.0

    expected.loc[usable, "supported_yield_component"] = (
        generation_diagnostics.loc[usable, "supported_count"].astype(float)
        / applicable.loc[usable]
    )
    expected.loc[usable, "not_verifiable_loss"] = (
        generation_diagnostics.loc[
            usable,
            "not_verifiable_count",
        ].astype(float)
        / applicable.loc[usable]
    )
    expected.loc[usable, "unsupported_loss"] = (
        generation_diagnostics.loc[usable, "unsupported_count"].astype(float)
        / applicable.loc[usable]
    )
    expected.loc[usable, "contradiction_loss"] = (
        generation_diagnostics.loc[
            usable,
            "contradicted_count",
        ].astype(float)
        / applicable.loc[usable]
    )

    expected["resolved_error_loss"] = (
        expected["unsupported_loss"] + expected["contradiction_loss"]
    )
    expected["claim_quality_loss"] = (
        expected["not_verifiable_loss"]
        + expected["unsupported_loss"]
        + expected["contradiction_loss"]
    )
    expected["total_loss"] = 1.0 - expected["supported_yield_component"]
    return expected


def loss_formula_mismatch_counts(
    generation_diagnostics: pd.DataFrame,
) -> dict[str, int]:
    """Count mismatches for each named loss component."""

    expected = expected_loss_components(generation_diagnostics)
    joined = generation_diagnostics.merge(
        expected,
        on="generation_id",
        how="outer",
        validate="one_to_one",
        suffixes=("_observed", "_expected"),
        indicator=True,
    )

    counts: dict[str, int] = {}
    for column in [
        "supported_yield_component",
        "pipeline_loss",
        "not_verifiable_loss",
        "unsupported_loss",
        "contradiction_loss",
        "resolved_error_loss",
        "claim_quality_loss",
        "total_loss",
    ]:
        matches = np.isclose(
            joined[f"{column}_observed"],
            joined[f"{column}_expected"],
            rtol=0.0,
            atol=NUMERIC_TOLERANCE,
            equal_nan=True,
        )
        counts[column] = int((~matches).sum())

    return counts


def expected_generation_safe_phrase_state(
    claim_diagnostics: pd.DataFrame,
    input_data: dict[str, Any],
) -> pd.DataFrame:
    """Rebuild generation-level claim and narrative phrase state."""

    claim_state = claim_diagnostics.groupby(
        "generation_id",
        sort=False,
    ).agg(
        safe_phrase_exposed_claim_count=("safe_phrase_exposed", "sum"),
        safe_phrase_eligible_claim_count=(
            "safe_phrase_match_eligible",
            "sum",
        ),
        safe_phrase_matched_claim_count=("safe_phrase_any_match", "sum"),
        safe_phrase_exact_claim_count=("safe_phrase_exact_match", "sum"),
        safe_phrase_contained_claim_count=(
            "safe_phrase_contained_match",
            "sum",
        ),
        safe_phrase_high_overlap_claim_count=(
            "safe_phrase_high_overlap",
            "sum",
        ),
    ).reset_index()

    packages = input_data["evidence_packages"][
        ["package_id", "safe_phrase_count"]
    ].rename(columns={"safe_phrase_count": "safe_phrase_item_count"})
    state = input_data["generations"][["generation_id", "package_id"]].merge(
        packages,
        on="package_id",
        how="left",
        validate="many_to_one",
    ).merge(
        claim_state,
        on="generation_id",
        how="left",
        validate="one_to_one",
    )

    count_columns = [
        "safe_phrase_exposed_claim_count",
        "safe_phrase_eligible_claim_count",
        "safe_phrase_matched_claim_count",
        "safe_phrase_exact_claim_count",
        "safe_phrase_contained_claim_count",
        "safe_phrase_high_overlap_claim_count",
    ]
    for column in count_columns:
        state[column] = state[column].fillna(0).astype(int)

    state["safe_phrase_item_count"] = state[
        "safe_phrase_item_count"
    ].fillna(0).astype(int)
    state["safe_phrase_exposed"] = state["safe_phrase_item_count"] > 0
    state["safe_phrase_match_eligible"] = (
        state["safe_phrase_eligible_claim_count"] > 0
    )
    state["safe_phrase_matched_claim_rate"] = (
        state["safe_phrase_matched_claim_count"]
        / state["safe_phrase_eligible_claim_count"].replace(0, np.nan)
    )
    state["has_safe_phrase_claim_match"] = (
        state["safe_phrase_matched_claim_count"] > 0
    )

    cache = validation_cache(input_data)
    narrative = cache.get("expected_narrative_matches")
    if narrative is None:
        phrases = extract_safe_phrase_items(input_data)
        narrative = match_generation_narratives(
            input_data["generations"],
            phrases,
        )
        cache["expected_narrative_matches"] = narrative
    state = state.merge(
        narrative,
        on="generation_id",
        how="left",
        validate="one_to_one",
    )
    state["has_any_safe_phrase_match"] = (
        state["has_safe_phrase_claim_match"]
        | state["narrative_any_safe_phrase_match"]
    )

    return state


def generation_safe_phrase_state_mismatch_count(
    generation_diagnostics: pd.DataFrame,
    claim_diagnostics: pd.DataFrame,
    input_data: dict[str, Any],
) -> int:
    """Compare generation safe-phrase fields with rebuilt expectations."""

    expected = expected_generation_safe_phrase_state(
        claim_diagnostics,
        input_data,
    )
    columns = [
        "safe_phrase_item_count",
        "safe_phrase_exposed",
        "safe_phrase_match_eligible",
        "safe_phrase_exposed_claim_count",
        "safe_phrase_eligible_claim_count",
        "safe_phrase_matched_claim_count",
        "safe_phrase_exact_claim_count",
        "safe_phrase_contained_claim_count",
        "safe_phrase_high_overlap_claim_count",
        "safe_phrase_matched_claim_rate",
        "has_safe_phrase_claim_match",
        "narrative_exact_safe_phrase_match",
        "narrative_contained_safe_phrase_match",
        "narrative_high_overlap_safe_phrase_match",
        "narrative_any_safe_phrase_match",
        "narrative_max_safe_phrase_token_coverage",
        "has_any_safe_phrase_match",
    ]
    _, _, changed = dataframe_value_mismatch_count(
        expected,
        generation_diagnostics,
        ["generation_id"],
        columns,
        tolerance=NUMERIC_TOLERANCE,
    )
    return changed


def validate_generation_diagnostics(
    checks: ValidationChecks,
    generation_diagnostics: pd.DataFrame,
    claim_diagnostics: pd.DataFrame,
    input_data: dict[str, Any],
) -> None:
    """Validate generation grain, formulas and mechanism reconciliation."""

    add_check(
        checks,
        "generation_diagnostic_row_count",
        EXPECTED_COUNTS["generations"],
        len(generation_diagnostics),
        len(generation_diagnostics) == EXPECTED_COUNTS["generations"],
    )

    duplicate_count = int(
        generation_diagnostics["generation_id"]
        .duplicated(keep=False)
        .sum()
    )
    add_check(
        checks,
        "duplicate_generation_diagnostic_id_count",
        0,
        duplicate_count,
        duplicate_count == 0,
    )

    source = input_data["generation_metrics"][[
        "generation_id",
        "case_id",
        "model_id",
        "evidence_level",
        "package_id",
        "end_to_end_faithfulness_yield",
    ]]
    joined = generation_diagnostics[[
        "generation_id",
        "case_id",
        "model_id",
        "evidence_level",
        "package_id",
        "end_to_end_faithfulness_yield",
    ]].merge(
        source,
        on="generation_id",
        how="outer",
        validate="one_to_one",
        suffixes=("_diagnostic", "_source"),
        indicator=True,
    )

    identity_mismatch = joined["_merge"] != "both"
    for column in ["case_id", "model_id", "evidence_level", "package_id"]:
        identity_mismatch = identity_mismatch | (
            joined[f"{column}_diagnostic"]
            != joined[f"{column}_source"]
        )
    identity_mismatch = identity_mismatch | ~np.isclose(
        joined["end_to_end_faithfulness_yield_diagnostic"],
        joined["end_to_end_faithfulness_yield_source"],
        rtol=0.0,
        atol=NUMERIC_TOLERANCE,
        equal_nan=True,
    )
    identity_mismatch_count = int(identity_mismatch.sum())
    add_check(
        checks,
        "generation_source_identity_mismatch_count",
        0,
        identity_mismatch_count,
        identity_mismatch_count == 0,
    )

    count_mismatch = generation_count_mismatch_count(
        generation_diagnostics,
        claim_diagnostics,
    )
    add_check(
        checks,
        "generation_claim_count_mismatch_count",
        0,
        count_mismatch,
        count_mismatch == 0,
    )

    formula_counts = loss_formula_mismatch_counts(generation_diagnostics)
    check_names = {
        "supported_yield_component": "supported_yield_formula_mismatch_count",
        "pipeline_loss": "pipeline_loss_formula_mismatch_count",
        "not_verifiable_loss": "not_verifiable_loss_formula_mismatch_count",
        "unsupported_loss": "unsupported_loss_formula_mismatch_count",
        "contradiction_loss": "contradiction_loss_formula_mismatch_count",
        "resolved_error_loss": "resolved_error_loss_formula_mismatch_count",
        "claim_quality_loss": "claim_quality_loss_formula_mismatch_count",
        "total_loss": "total_loss_formula_mismatch_count",
    }
    for column, check_name in check_names.items():
        observed = formula_counts[column]
        add_check(checks, check_name, 0, observed, observed == 0)

    component_sum = generation_diagnostics[
        [
            "supported_yield_component",
            "pipeline_loss",
            "not_verifiable_loss",
            "unsupported_loss",
            "contradiction_loss",
        ]
    ].sum(axis=1)
    decomposition_mismatch = int(
        (~np.isclose(
            component_sum,
            1.0,
            rtol=0.0,
            atol=NUMERIC_TOLERANCE,
        )).sum()
    )
    add_check(
        checks,
        "generation_loss_decomposition_mismatch_count",
        0,
        decomposition_mismatch,
        decomposition_mismatch == 0,
    )

    yield_mismatch = int(
        (~np.isclose(
            generation_diagnostics["supported_yield_component"],
            generation_diagnostics["end_to_end_faithfulness_yield"],
            rtol=0.0,
            atol=NUMERIC_TOLERANCE,
        )).sum()
    )
    add_check(
        checks,
        "supported_yield_metric_mismatch_count",
        0,
        yield_mismatch,
        yield_mismatch == 0,
    )

    unusable = ~generation_diagnostics["usable"].astype(bool)
    unusable_rule_mismatch = int(
        (
            (generation_diagnostics.loc[unusable, "pipeline_loss"] != 1)
            | (
                generation_diagnostics.loc[
                    unusable,
                    [
                        "supported_yield_component",
                        "not_verifiable_loss",
                        "unsupported_loss",
                        "contradiction_loss",
                    ],
                ].sum(axis=1)
                != 0
            )
        ).sum()
    )
    add_check(
        checks,
        "unusable_loss_rule_mismatch_count",
        0,
        unusable_rule_mismatch,
        unusable_rule_mismatch == 0,
    )

    type_total = generation_diagnostics[
        list(CLAIM_TYPE_COUNT_COLUMNS.values())
    ].sum(axis=1)
    type_count_mismatch = int(
        (type_total != generation_diagnostics["claim_count"]).sum()
    )
    add_check(
        checks,
        "generation_claim_type_partition_mismatch_count",
        0,
        type_count_mismatch,
        type_count_mismatch == 0,
    )

    safe_phrase_state_mismatch = generation_safe_phrase_state_mismatch_count(
        generation_diagnostics,
        claim_diagnostics,
        input_data,
    )
    add_check(
        checks,
        "generation_safe_phrase_state_mismatch_count",
        0,
        safe_phrase_state_mismatch,
        safe_phrase_state_mismatch == 0,
    )

    usable_count = int(generation_diagnostics["usable"].sum())
    unusable_count = len(generation_diagnostics) - usable_count
    add_check(
        checks,
        "usable_generation_count",
        EXPECTED_COUNTS["usable_generations"],
        usable_count,
        usable_count == EXPECTED_COUNTS["usable_generations"],
    )
    add_check(
        checks,
        "unusable_generation_count",
        EXPECTED_COUNTS["unusable_generations"],
        unusable_count,
        unusable_count == EXPECTED_COUNTS["unusable_generations"],
    )


def validate_pipeline_failures(
    checks: ValidationChecks,
    failures: pd.DataFrame,
    input_data: dict[str, Any],
) -> None:
    """Validate the exact unusable-generation failure table."""

    add_check(
        checks,
        "pipeline_failure_row_count",
        EXPECTED_COUNTS["unusable_generations"],
        len(failures),
        len(failures) == EXPECTED_COUNTS["unusable_generations"],
    )

    duplicate_count = int(
        failures["generation_id"].duplicated(keep=False).sum()
    )
    add_check(
        checks,
        "duplicate_pipeline_failure_generation_count",
        0,
        duplicate_count,
        duplicate_count == 0,
    )

    expected_ids = set(
        input_data["generations"].loc[
            ~input_data["generations"]["usable"].astype(bool),
            "generation_id",
        ]
    )
    observed_ids = set(failures["generation_id"])
    add_check(
        checks,
        "pipeline_failure_generation_set",
        sorted(expected_ids),
        sorted(observed_ids),
        observed_ids == expected_ids,
    )

    category_mismatch = 0
    for _, row in failures.iterrows():
        if row["failure_category"] != classify_failure(row):
            category_mismatch += 1
    add_check(
        checks,
        "pipeline_failure_category_mismatch_count",
        0,
        category_mismatch,
        category_mismatch == 0,
    )

    non_s4_count = int((failures["evidence_level"] != "S4").sum())
    add_check(
        checks,
        "pipeline_failure_non_s4_count",
        0,
        non_s4_count,
        non_s4_count == 0,
    )

    expected_model_counts = {
        "deepseek_v4_flash": 3,
        "phi4_mini_instruct": 7,
        "qwen3_8b": 0,
    }
    observed_model_counts = {
        model_id: int((failures["model_id"] == model_id).sum())
        for model_id in expected_model_counts
    }
    add_check(
        checks,
        "pipeline_failure_model_counts",
        expected_model_counts,
        observed_model_counts,
        observed_model_counts == expected_model_counts,
    )
