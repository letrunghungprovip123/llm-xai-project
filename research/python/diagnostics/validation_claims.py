"""Claim-grain validation rules."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .config import DIAGNOSTIC_VERSION, EXPECTED_COUNTS, VALIDATION_STATUSES
from .validation_common import ValidationChecks, add_check
from .validation_safe_phrase import (
    expected_safe_phrase_eligible_claim_ids,
    source_safe_phrases,
)


def claim_source_mismatch_count(
    claim_diagnostics: pd.DataFrame,
    input_data: dict[str, Any],
) -> int:
    """Compare claim identity and status with source tables."""

    claims = input_data["claims"]
    generations = input_data["generations"]

    source = claims[
        [
            "claim_id",
            "generation_id",
            "case_id",
            "model_id",
            "evidence_level",
            "validation_status",
            "claim_type",
            "source_section",
            "source_text",
        ]
    ].merge(
        generations[["generation_id", "package_id"]],
        on="generation_id",
        how="left",
        validate="many_to_one",
    )

    columns = [
        "claim_id",
        "generation_id",
        "case_id",
        "model_id",
        "evidence_level",
        "package_id",
        "validation_status",
        "claim_type",
        "source_section",
        "source_text",
    ]

    joined = claim_diagnostics[columns].merge(
        source[columns],
        on="claim_id",
        how="outer",
        validate="one_to_one",
        suffixes=("_diagnostic", "_source"),
        indicator=True,
    )

    mismatch = joined["_merge"] != "both"
    for column in columns[1:]:
        left = joined[f"{column}_diagnostic"].fillna("<NULL>")
        right = joined[f"{column}_source"].fillna("<NULL>")
        mismatch = mismatch | (left != right)

    return int(mismatch.sum())


def validate_claim_diagnostics(
    checks: ValidationChecks,
    claim_diagnostics: pd.DataFrame,
    input_data: dict[str, Any],
) -> None:
    """Validate claim grain, flags, identity and phrase eligibility."""

    add_check(
        checks,
        "claim_diagnostic_row_count",
        EXPECTED_COUNTS["claims"],
        len(claim_diagnostics),
        len(claim_diagnostics) == EXPECTED_COUNTS["claims"],
    )

    duplicate_count = int(
        claim_diagnostics["claim_id"].duplicated(keep=False).sum()
    )
    add_check(
        checks,
        "duplicate_claim_diagnostic_id_count",
        0,
        duplicate_count,
        duplicate_count == 0,
    )

    source_mismatch = claim_source_mismatch_count(
        claim_diagnostics,
        input_data,
    )
    add_check(
        checks,
        "claim_source_identity_mismatch_count",
        0,
        source_mismatch,
        source_mismatch == 0,
    )

    unknown_statuses = sorted(
        set(claim_diagnostics["validation_status"].unique())
        - VALIDATION_STATUSES
    )
    add_check(
        checks,
        "unknown_validation_statuses",
        [],
        unknown_statuses,
        unknown_statuses == [],
    )

    status = claim_diagnostics["validation_status"]
    expected_flags = {
        "is_applicable": status != "NOT_APPLICABLE",
        "is_resolved": status.isin(
            ["SUPPORTED", "UNSUPPORTED", "CONTRADICTED"]
        ),
        "is_supported": status == "SUPPORTED",
        "is_not_verifiable": status == "NOT_VERIFIABLE",
        "is_unsupported": status == "UNSUPPORTED",
        "is_contradicted": status == "CONTRADICTED",
        "is_not_applicable": status == "NOT_APPLICABLE",
        "is_resolved_error": status.isin(
            ["UNSUPPORTED", "CONTRADICTED"]
        ),
    }

    flag_mismatches = 0
    for column, expected in expected_flags.items():
        observed = claim_diagnostics[column].astype(bool)
        flag_mismatches += int((observed != expected).sum())

    add_check(
        checks,
        "claim_status_flag_mismatch_count",
        0,
        flag_mismatches,
        flag_mismatches == 0,
    )

    partition_count = (
        claim_diagnostics[
            [
                "is_supported",
                "is_not_verifiable",
                "is_unsupported",
                "is_contradicted",
                "is_not_applicable",
            ]
        ]
        .astype(int)
        .sum(axis=1)
    )
    partition_mismatch = int((partition_count != 1).sum())
    add_check(
        checks,
        "claim_status_partition_mismatch_count",
        0,
        partition_mismatch,
        partition_mismatch == 0,
    )

    expected_eligible_ids = expected_safe_phrase_eligible_claim_ids(
        input_data
    )
    observed_eligible = claim_diagnostics["claim_id"].astype(str).isin(
        expected_eligible_ids
    )
    eligibility_mismatch = int(
        (
            claim_diagnostics["safe_phrase_match_eligible"].astype(bool)
            != observed_eligible
        ).sum()
    )
    add_check(
        checks,
        "safe_phrase_eligibility_mismatch_count",
        0,
        eligibility_mismatch,
        eligibility_mismatch == 0,
    )

    phrase_packages = set(source_safe_phrases(input_data)["package_id"])
    expected_exposure = claim_diagnostics["package_id"].isin(
        phrase_packages
    )
    exposure_mismatch = int(
        (
            claim_diagnostics["safe_phrase_exposed"].astype(bool)
            != expected_exposure
        ).sum()
    )
    add_check(
        checks,
        "safe_phrase_exposure_mismatch_count",
        0,
        exposure_mismatch,
        exposure_mismatch == 0,
    )

    match_without_exposure = int(
        (
            claim_diagnostics["safe_phrase_any_match"]
            & ~claim_diagnostics["safe_phrase_exposed"]
        ).sum()
    )
    match_without_eligibility = int(
        (
            claim_diagnostics["safe_phrase_any_match"]
            & ~claim_diagnostics["safe_phrase_match_eligible"]
        ).sum()
    )
    add_check(
        checks,
        "safe_phrase_match_without_exposure_count",
        0,
        match_without_exposure,
        match_without_exposure == 0,
    )
    add_check(
        checks,
        "safe_phrase_match_without_eligibility_count",
        0,
        match_without_eligibility,
        match_without_eligibility == 0,
    )

    version_values = sorted(
        claim_diagnostics["diagnostic_version"]
        .astype(str)
        .unique()
        .tolist()
    )
    add_check(
        checks,
        "claim_diagnostic_version_set",
        [DIAGNOSTIC_VERSION],
        version_values,
        version_values == [DIAGNOSTIC_VERSION],
    )
