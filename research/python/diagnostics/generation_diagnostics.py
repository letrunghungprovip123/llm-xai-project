"""Build generation-level loss and mechanism diagnostics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import (
    CLAIM_TYPE_COUNT_COLUMNS,
    DIAGNOSTIC_VERSION,
    GENERATION_DIAGNOSTIC_BASE_COLUMNS,
)


def aggregate_claim_diagnostics(
    claim_diagnostics: pd.DataFrame,
    *,
    claim_type_count_columns: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Aggregate audited claim flags to one row per generation.

    The optional mapping lets a dataset opt into additional registered claim
    types without changing the historical Home Credit output schema.
    """

    type_columns = claim_type_count_columns or CLAIM_TYPE_COUNT_COLUMNS

    grouped = claim_diagnostics.groupby("generation_id", sort=False)

    aggregates = grouped.agg(
        claim_count=("claim_id", "size"),
        supported_count=("is_supported", "sum"),
        unsupported_count=("is_unsupported", "sum"),
        contradicted_count=("is_contradicted", "sum"),
        not_verifiable_count=("is_not_verifiable", "sum"),
        not_applicable_count=("is_not_applicable", "sum"),
        resolved_count=("is_resolved", "sum"),
        applicable_count=("is_applicable", "sum"),
        claim_type_count=("claim_type", "nunique"),
        safe_phrase_exposed_claim_count=(
            "safe_phrase_exposed",
            "sum",
        ),
        safe_phrase_eligible_claim_count=(
            "safe_phrase_match_eligible",
            "sum",
        ),
        safe_phrase_matched_claim_count=(
            "safe_phrase_any_match",
            "sum",
        ),
        safe_phrase_exact_claim_count=(
            "safe_phrase_exact_match",
            "sum",
        ),
        safe_phrase_contained_claim_count=(
            "safe_phrase_contained_match",
            "sum",
        ),
        safe_phrase_high_overlap_claim_count=(
            "safe_phrase_high_overlap",
            "sum",
        ),
    ).reset_index()

    type_counts = pd.crosstab(
        claim_diagnostics["generation_id"],
        claim_diagnostics["claim_type"],
    )

    unknown_types = sorted(
        set(type_counts.columns) - set(type_columns)
    )
    if unknown_types:
        raise ValueError(
            f"Unknown claim types require an explicit output column: "
            f"{unknown_types}"
        )

    type_counts = type_counts.rename(
        columns=type_columns
    )
    for output_column in type_columns.values():
        if output_column not in type_counts.columns:
            type_counts[output_column] = 0

    type_counts = type_counts[
        list(type_columns.values())
    ].reset_index()

    return aggregates.merge(
        type_counts,
        on="generation_id",
        how="left",
        validate="one_to_one",
    )


def calculate_loss_components(frame: pd.DataFrame) -> pd.DataFrame:
    """Create an exact planned-generation end-to-end decomposition."""

    output = frame.copy()
    usable = output["usable"].astype(bool)
    applicable = output["applicable_count"].astype(float)

    invalid_usable = usable & (applicable <= 0)
    if invalid_usable.any():
        raise ValueError(
            "Usable generations must contain at least one applicable claim "
            "for exact loss decomposition."
        )

    output["supported_yield_component"] = 0.0
    output["pipeline_loss"] = (~usable).astype(float)
    output["not_verifiable_loss"] = 0.0
    output["unsupported_loss"] = 0.0
    output["contradiction_loss"] = 0.0

    output.loc[usable, "supported_yield_component"] = (
        output.loc[usable, "supported_count"].astype(float)
        / applicable.loc[usable]
    )
    output.loc[usable, "not_verifiable_loss"] = (
        output.loc[usable, "not_verifiable_count"].astype(float)
        / applicable.loc[usable]
    )
    output.loc[usable, "unsupported_loss"] = (
        output.loc[usable, "unsupported_count"].astype(float)
        / applicable.loc[usable]
    )
    output.loc[usable, "contradiction_loss"] = (
        output.loc[usable, "contradicted_count"].astype(float)
        / applicable.loc[usable]
    )

    output["resolved_error_loss"] = (
        output["unsupported_loss"]
        + output["contradiction_loss"]
    )
    output["claim_quality_loss"] = (
        output["not_verifiable_loss"]
        + output["unsupported_loss"]
        + output["contradiction_loss"]
    )
    output["total_loss"] = 1.0 - output[
        "supported_yield_component"
    ]

    return output


def build_generation_diagnostics(
    input_data: dict[str, Any],
    claim_diagnostics: pd.DataFrame,
    narrative_matches: pd.DataFrame,
    *,
    claim_type_count_columns: dict[str, str] | None = None,
    diagnostic_version: str = DIAGNOSTIC_VERSION,
) -> pd.DataFrame:
    """Build one diagnostic row for every planned generation."""

    type_columns = claim_type_count_columns or CLAIM_TYPE_COUNT_COLUMNS

    metrics = input_data["generation_metrics"].copy()
    generations = input_data["generations"]
    packages = input_data["evidence_packages"]

    runtime_columns = generations[
        [
            "generation_id",
            "case_id",
            "model_id",
            "evidence_level",
            "package_id",
            "selection_stratum",
            "usable",
            "runtime_status",
        ]
    ].rename(
        columns={
            "case_id": "runtime_case_id",
            "model_id": "runtime_model_id",
            "evidence_level": "runtime_evidence_level",
            "package_id": "runtime_package_id",
            "selection_stratum": "runtime_selection_stratum",
            "usable": "runtime_usable",
            "runtime_status": "source_runtime_status",
        }
    )

    frame = metrics.merge(
        runtime_columns,
        on="generation_id",
        how="left",
        validate="one_to_one",
    )

    identity_mismatch = (
        (frame["case_id"] != frame["runtime_case_id"])
        | (frame["model_id"] != frame["runtime_model_id"])
        | (
            frame["evidence_level"]
            != frame["runtime_evidence_level"]
        )
        | (frame["package_id"] != frame["runtime_package_id"])
        | (
            frame["selection_stratum"]
            != frame["runtime_selection_stratum"]
        )
        | (
            frame["usable"].astype(bool)
            != frame["runtime_usable"].astype(bool)
        )
        | (frame["runtime_status"] != frame["source_runtime_status"])
    )
    if identity_mismatch.any():
        raise ValueError(
            "generation_metrics.csv does not match generations.csv for "
            f"{int(identity_mismatch.sum())} rows."
        )

    package_counts = packages[
        ["package_id", "safe_phrase_count"]
    ].rename(columns={"safe_phrase_count": "safe_phrase_item_count"})
    frame = frame.merge(
        package_counts,
        on="package_id",
        how="left",
        validate="many_to_one",
    )

    claim_aggregates = aggregate_claim_diagnostics(
        claim_diagnostics,
        claim_type_count_columns=type_columns,
    )
    frame = frame.merge(
        claim_aggregates,
        on="generation_id",
        how="left",
        validate="one_to_one",
        suffixes=("_metric", "_claims"),
    )

    count_columns = [
        "claim_count",
        "supported_count",
        "unsupported_count",
        "contradicted_count",
        "not_verifiable_count",
        "not_applicable_count",
        "resolved_count",
        "applicable_count",
    ]

    usable = frame["usable"].astype(bool)
    for column in count_columns:
        metric_column = f"{column}_metric"
        claim_column = f"{column}_claims"
        frame[claim_column] = frame[claim_column].fillna(0).astype(int)

        mismatch = frame[metric_column].astype(int) != frame[
            claim_column
        ]
        if mismatch.any():
            raise ValueError(
                f"Claim aggregation does not match {metric_column} for "
                f"{int(mismatch.sum())} generations."
            )

        frame[column] = frame[metric_column].astype(int)

    missing_claims_on_usable = usable & frame[
        "claim_type_count"
    ].isna()
    if missing_claims_on_usable.any():
        raise ValueError("Usable generations are missing claim aggregates.")

    aggregate_fill_columns = [
        "claim_type_count",
        "safe_phrase_exposed_claim_count",
        "safe_phrase_eligible_claim_count",
        "safe_phrase_matched_claim_count",
        "safe_phrase_exact_claim_count",
        "safe_phrase_contained_claim_count",
        "safe_phrase_high_overlap_claim_count",
        *type_columns.values(),
    ]
    for column in aggregate_fill_columns:
        frame[column] = frame[column].fillna(0).astype(int)

    frame["safe_phrase_exposed"] = frame[
        "safe_phrase_item_count"
    ].fillna(0).astype(int) > 0

    frame["safe_phrase_match_eligible"] = (
        frame["safe_phrase_eligible_claim_count"] > 0
    )
    frame["safe_phrase_matched_claim_rate"] = np.nan
    eligible_claims = frame["safe_phrase_eligible_claim_count"] > 0
    frame.loc[
        eligible_claims,
        "safe_phrase_matched_claim_rate",
    ] = (
        frame.loc[
            eligible_claims,
            "safe_phrase_matched_claim_count",
        ].astype(float)
        / frame.loc[
            eligible_claims,
            "safe_phrase_eligible_claim_count",
        ].astype(float)
    )
    frame["has_safe_phrase_claim_match"] = (
        frame["safe_phrase_matched_claim_count"] > 0
    )

    frame = frame.merge(
        narrative_matches,
        on="generation_id",
        how="left",
        validate="one_to_one",
    )

    narrative_boolean_columns = [
        "narrative_exact_safe_phrase_match",
        "narrative_contained_safe_phrase_match",
        "narrative_high_overlap_safe_phrase_match",
        "narrative_any_safe_phrase_match",
    ]
    for column in narrative_boolean_columns:
        frame[column] = frame[column].fillna(False).astype(bool)
    frame["narrative_max_safe_phrase_token_coverage"] = frame[
        "narrative_max_safe_phrase_token_coverage"
    ].fillna(0.0)

    frame["has_any_safe_phrase_match"] = (
        frame["has_safe_phrase_claim_match"]
        | frame["narrative_any_safe_phrase_match"]
    )

    frame = calculate_loss_components(frame)
    frame.insert(0, "diagnostic_version", diagnostic_version)

    frame = frame.sort_values(
        [
            "generation_id",
        ],
        kind="stable",
    ).reset_index(drop=True)

    return frame[[*GENERATION_DIAGNOSTIC_BASE_COLUMNS, *type_columns.values()]].copy()
