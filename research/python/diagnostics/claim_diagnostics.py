"""Build the claim-level mechanism frame."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .config import (
    CLAIM_DIAGNOSTIC_COLUMNS,
    DIAGNOSTIC_VERSION,
    RESOLVED_ERROR_STATUSES,
    RESOLVED_STATUSES,
    VALIDATION_STATUSES,
)


def require_known_statuses(claims: pd.DataFrame) -> None:
    """Reject validation statuses not covered by the diagnostic rules."""

    observed = set(
        claims["validation_status"].dropna().astype(str).unique()
    )
    unknown = sorted(observed - VALIDATION_STATUSES)

    if unknown:
        raise ValueError(
            f"claims.csv contains unknown validation statuses: {unknown}"
        )


def build_claim_base_frame(
    input_data: dict[str, Any],
    *,
    diagnostic_version: str = DIAGNOSTIC_VERSION,
) -> pd.DataFrame:
    """Join generation identity and create structured claim flags."""

    claims = input_data["claims"].copy()
    generations = input_data["generations"]
    packages = input_data["evidence_packages"]

    require_known_statuses(claims)

    generation_identity = generations[
        [
            "generation_id",
            "case_id",
            "model_id",
            "evidence_level",
            "package_id",
            "selection_stratum",
        ]
    ].rename(
        columns={
            "case_id": "generation_case_id",
            "model_id": "generation_model_id",
            "evidence_level": "generation_evidence_level",
        }
    )

    frame = claims.merge(
        generation_identity,
        on="generation_id",
        how="left",
        validate="many_to_one",
    )

    missing_generation = frame["package_id"].isna()
    if missing_generation.any():
        examples = frame.loc[
            missing_generation,
            "claim_id",
        ].head(10).tolist()
        raise ValueError(
            "Claim diagnostics found claims without generations. "
            f"Example claim IDs: {examples}"
        )

    identity_mismatch = (
        (frame["case_id"] != frame["generation_case_id"])
        | (frame["model_id"] != frame["generation_model_id"])
        | (
            frame["evidence_level"]
            != frame["generation_evidence_level"]
        )
    )

    if identity_mismatch.any():
        raise ValueError(
            "Claim identity does not match generations.csv for "
            f"{int(identity_mismatch.sum())} claims."
        )

    safe_phrase_counts = packages[
        ["package_id", "safe_phrase_count"]
    ].copy()
    frame = frame.merge(
        safe_phrase_counts,
        on="package_id",
        how="left",
        validate="many_to_one",
    )

    if frame["safe_phrase_count"].isna().any():
        raise ValueError(
            "Claim diagnostics found package IDs missing from "
            "evidence_packages.csv."
        )

    status = frame["validation_status"]
    frame["is_applicable"] = status != "NOT_APPLICABLE"
    frame["is_resolved"] = status.isin(RESOLVED_STATUSES)
    frame["is_supported"] = status == "SUPPORTED"
    frame["is_not_verifiable"] = status == "NOT_VERIFIABLE"
    frame["is_unsupported"] = status == "UNSUPPORTED"
    frame["is_contradicted"] = status == "CONTRADICTED"
    frame["is_not_applicable"] = status == "NOT_APPLICABLE"
    frame["is_resolved_error"] = status.isin(
        RESOLVED_ERROR_STATUSES
    )

    frame["has_feature_reference"] = frame["feature_id"].notna()
    frame["has_concept_reference"] = frame["concept_id"].notna()
    frame["has_source_anchor"] = (
        frame["source_start"].notna()
        & frame["source_end"].notna()
        & frame["source_text"].notna()
    )
    frame["has_numeric_value"] = frame["numeric_value"].notna()
    frame["safe_phrase_exposed"] = frame["safe_phrase_count"] > 0
    frame["safe_phrase_item_count"] = frame[
        "safe_phrase_count"
    ].astype(int)
    frame["safe_phrase_match_eligible"] = False

    frame["best_safe_phrase_item_id"] = pd.NA
    frame["best_safe_phrase_match_type"] = "NONE"
    frame["best_safe_phrase_token_coverage"] = 0.0
    frame["safe_phrase_exact_match"] = False
    frame["safe_phrase_contained_match"] = False
    frame["safe_phrase_high_overlap"] = False
    frame["safe_phrase_any_match"] = False

    frame.insert(0, "diagnostic_version", diagnostic_version)

    frame = frame.sort_values(
        ["generation_id", "local_claim_index", "claim_id"],
        kind="stable",
    ).reset_index(drop=True)

    return frame[CLAIM_DIAGNOSTIC_COLUMNS].copy()
