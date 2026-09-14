"""Build claim, generation and pipeline-failure summaries."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from .config import (
    CLAIM_GROUP_TYPES,
    GENERATION_GROUP_TYPES,
)


CLAIM_GROUP_COLUMNS = {
    "overall": [],
    "model": ["model_id"],
    "evidence": ["evidence_level"],
    "model_evidence": ["model_id", "evidence_level"],
    "claim_type": ["claim_type"],
    "model_evidence_claim_type": [
        "model_id",
        "evidence_level",
        "claim_type",
    ],
    "stratum": ["selection_stratum"],
}

GENERATION_GROUP_COLUMNS = {
    "overall": [],
    "model": ["model_id"],
    "evidence": ["evidence_level"],
    "model_evidence": ["model_id", "evidence_level"],
    "stratum": ["selection_stratum"],
}


def divide_or_nan(numerator: float, denominator: float) -> float:
    """Divide only when the denominator is positive."""

    if denominator <= 0:
        return float("nan")
    return float(numerator / denominator)


def group_iterator(
    frame: pd.DataFrame,
    group_columns: list[str],
) -> Iterable[tuple[tuple[object, ...], pd.DataFrame]]:
    """Yield tuple keys for grouped and ungrouped data."""

    if not group_columns:
        yield tuple(), frame
        return

    grouped = frame.groupby(
        group_columns,
        sort=False,
        dropna=False,
    )

    for key, group in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        yield key, group


def summarize_claim_group(group: pd.DataFrame) -> dict[str, object]:
    """Calculate count-based claim diagnostics for one group."""

    claim_count = int(len(group))
    applicable_count = int(group["is_applicable"].sum())
    resolved_count = int(group["is_resolved"].sum())
    supported_count = int(group["is_supported"].sum())
    not_verifiable_count = int(group["is_not_verifiable"].sum())
    unsupported_count = int(group["is_unsupported"].sum())
    contradicted_count = int(group["is_contradicted"].sum())
    not_applicable_count = int(group["is_not_applicable"].sum())

    exposed_count = int(group["safe_phrase_exposed"].sum())
    eligible_count = int(group["safe_phrase_match_eligible"].sum())
    matched_count = int(group["safe_phrase_any_match"].sum())
    exact_count = int(group["safe_phrase_exact_match"].sum())
    contained_count = int(
        group["safe_phrase_contained_match"].sum()
    )
    high_overlap_count = int(
        group["safe_phrase_high_overlap"].sum()
    )

    eligible = group["safe_phrase_match_eligible"].astype(bool)
    best_match_type = group["best_safe_phrase_match_type"].astype(str)
    best_exact_count = int((eligible & (best_match_type == "EXACT")).sum())
    best_contained_count = int(
        (eligible & (best_match_type == "CONTAINED")).sum()
    )
    best_high_overlap_count = int(
        (eligible & (best_match_type == "HIGH_OVERLAP")).sum()
    )
    best_none_count = int((eligible & (best_match_type == "NONE")).sum())

    return {
        "claim_count": claim_count,
        "applicable_count": applicable_count,
        "resolved_count": resolved_count,
        "supported_count": supported_count,
        "not_verifiable_count": not_verifiable_count,
        "unsupported_count": unsupported_count,
        "contradicted_count": contradicted_count,
        "not_applicable_count": not_applicable_count,
        "resolved_faithfulness": divide_or_nan(
            supported_count,
            resolved_count,
        ),
        "verifiability": divide_or_nan(
            resolved_count,
            applicable_count,
        ),
        "conservative_faithfulness": divide_or_nan(
            supported_count,
            applicable_count,
        ),
        "not_verifiable_rate": divide_or_nan(
            not_verifiable_count,
            applicable_count,
        ),
        "unsupported_rate": divide_or_nan(
            unsupported_count,
            applicable_count,
        ),
        "contradiction_rate": divide_or_nan(
            contradicted_count,
            applicable_count,
        ),
        "resolved_error_rate": divide_or_nan(
            unsupported_count + contradicted_count,
            resolved_count,
        ),
        "safe_phrase_exposed_claim_count": exposed_count,
        "safe_phrase_eligible_claim_count": eligible_count,
        "safe_phrase_matched_claim_count": matched_count,
        "safe_phrase_exact_claim_count": exact_count,
        "safe_phrase_contained_claim_count": contained_count,
        "safe_phrase_high_overlap_claim_count": high_overlap_count,
        "safe_phrase_matched_claim_rate": divide_or_nan(
            matched_count,
            eligible_count,
        ),
        "safe_phrase_exact_claim_rate": divide_or_nan(
            exact_count,
            eligible_count,
        ),
        "safe_phrase_contained_claim_rate": divide_or_nan(
            contained_count,
            eligible_count,
        ),
        "safe_phrase_high_overlap_claim_rate": divide_or_nan(
            high_overlap_count,
            eligible_count,
        ),
        "safe_phrase_best_exact_claim_count": best_exact_count,
        "safe_phrase_best_contained_claim_count": best_contained_count,
        "safe_phrase_best_high_overlap_claim_count": (
            best_high_overlap_count
        ),
        "safe_phrase_best_none_claim_count": best_none_count,
        "safe_phrase_best_exact_claim_rate": divide_or_nan(
            best_exact_count,
            eligible_count,
        ),
        "safe_phrase_best_contained_claim_rate": divide_or_nan(
            best_contained_count,
            eligible_count,
        ),
        "safe_phrase_best_high_overlap_claim_rate": divide_or_nan(
            best_high_overlap_count,
            eligible_count,
        ),
        "safe_phrase_best_none_claim_rate": divide_or_nan(
            best_none_count,
            eligible_count,
        ),
    }


def build_claim_mechanism_summary(
    claim_diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    """Create tidy claim-mechanism summaries."""

    rows: list[dict[str, object]] = []

    for group_order, group_type in enumerate(CLAIM_GROUP_TYPES):
        columns = CLAIM_GROUP_COLUMNS[group_type]

        for key, group in group_iterator(claim_diagnostics, columns):
            identity = dict(zip(columns, key))
            rows.append(
                {
                    "group_order": group_order,
                    "group_type": group_type,
                    "model_id": identity.get("model_id"),
                    "evidence_level": identity.get("evidence_level"),
                    "claim_type": identity.get("claim_type"),
                    "selection_stratum": identity.get(
                        "selection_stratum"
                    ),
                    **summarize_claim_group(group),
                }
            )

    output = pd.DataFrame(rows)
    output = output.sort_values(
        [
            "group_order",
            "model_id",
            "evidence_level",
            "claim_type",
            "selection_stratum",
        ],
        kind="stable",
        na_position="first",
    ).reset_index(drop=True)

    return output.drop(columns=["group_order"])


def summarize_generation_group(group: pd.DataFrame) -> dict[str, object]:
    """Calculate planned-generation mechanism diagnostics."""

    planned_count = int(len(group))
    usable_count = int(group["usable"].astype(bool).sum())
    unusable_count = planned_count - usable_count

    exposed_count = int(group["safe_phrase_exposed"].sum())
    claim_match_count = int(
        group["has_safe_phrase_claim_match"].sum()
    )
    narrative_match_count = int(
        group["narrative_any_safe_phrase_match"].sum()
    )
    any_match_count = int(group["has_any_safe_phrase_match"].sum())

    return {
        "planned_generation_count": planned_count,
        "usable_generation_count": usable_count,
        "unusable_generation_count": unusable_count,
        "usability_rate": divide_or_nan(usable_count, planned_count),
        "mean_end_to_end_yield": float(
            group["supported_yield_component"].mean()
        ),
        "mean_pipeline_loss": float(group["pipeline_loss"].mean()),
        "mean_not_verifiable_loss": float(
            group["not_verifiable_loss"].mean()
        ),
        "mean_unsupported_loss": float(
            group["unsupported_loss"].mean()
        ),
        "mean_contradiction_loss": float(
            group["contradiction_loss"].mean()
        ),
        "mean_resolved_error_loss": float(
            group["resolved_error_loss"].mean()
        ),
        "mean_claim_quality_loss": float(
            group["claim_quality_loss"].mean()
        ),
        "mean_total_loss": float(group["total_loss"].mean()),
        "safe_phrase_exposed_generation_count": exposed_count,
        "safe_phrase_claim_matched_generation_count": (
            claim_match_count
        ),
        "safe_phrase_narrative_matched_generation_count": (
            narrative_match_count
        ),
        "safe_phrase_matched_generation_count": any_match_count,
        "safe_phrase_claim_matched_generation_rate": divide_or_nan(
            claim_match_count,
            exposed_count,
        ),
        "safe_phrase_narrative_matched_generation_rate": (
            divide_or_nan(narrative_match_count, exposed_count)
        ),
        "safe_phrase_matched_generation_rate": divide_or_nan(
            any_match_count,
            exposed_count,
        ),
        "mean_claim_count": float(group["claim_count"].mean()),
        "mean_applicable_count": float(
            group["applicable_count"].mean()
        ),
        "mean_supported_count": float(
            group["supported_count"].mean()
        ),
    }


def build_generation_mechanism_summary(
    generation_diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    """Create tidy planned-generation mechanism summaries."""

    rows: list[dict[str, object]] = []

    for group_order, group_type in enumerate(GENERATION_GROUP_TYPES):
        columns = GENERATION_GROUP_COLUMNS[group_type]

        for key, group in group_iterator(generation_diagnostics, columns):
            identity = dict(zip(columns, key))
            rows.append(
                {
                    "group_order": group_order,
                    "group_type": group_type,
                    "model_id": identity.get("model_id"),
                    "evidence_level": identity.get("evidence_level"),
                    "selection_stratum": identity.get(
                        "selection_stratum"
                    ),
                    **summarize_generation_group(group),
                }
            )

    output = pd.DataFrame(rows)
    output = output.sort_values(
        [
            "group_order",
            "model_id",
            "evidence_level",
            "selection_stratum",
        ],
        kind="stable",
        na_position="first",
    ).reset_index(drop=True)

    return output.drop(columns=["group_order"])


def classify_failure(row: pd.Series) -> str:
    """Classify one unusable generation with explicit precedence."""

    if bool(row["truncated_response"]):
        return "TRUNCATED"
    if not bool(row["raw_json_parse_success"]) or not bool(
        row["json_parse_success"]
    ):
        return "PARSE_FAILURE"
    if not bool(row["schema_valid"]):
        return "SCHEMA_FAILURE"
    if str(row["runtime_status"]) != "SUCCESS":
        return "OTHER_RUNTIME_FAILURE"
    return "VALIDATION_FAILURE"


def build_pipeline_failures(
    input_data: dict[str, Any],
) -> pd.DataFrame:
    """Return one structured row for every unusable generation."""

    generations = input_data["generations"].copy()
    failures = generations.loc[
        ~generations["usable"].astype(bool),
        [
            "generation_id",
            "case_id",
            "model_id",
            "evidence_level",
            "selection_stratum",
            "runtime_status",
            "finish_reason",
            "truncated_response",
            "raw_json_parse_success",
            "json_parse_success",
            "schema_valid",
            "retry_count",
            "latency_ms",
            "input_token_count",
            "output_token_count",
            "total_token_count",
            "runtime_error_type",
            "runtime_error_message",
            "empty_response",
            "cleanup_type",
            "usability_reason_codes_json",
        ],
    ].copy()

    failures.insert(
        5,
        "failure_category",
        failures.apply(classify_failure, axis=1),
    )

    return failures.sort_values(
        ["model_id", "evidence_level", "case_id", "generation_id"],
        kind="stable",
    ).reset_index(drop=True)
