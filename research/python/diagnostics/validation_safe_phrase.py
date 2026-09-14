"""Fail-closed safe-phrase validation from raw source tables."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import (
    HIGH_OVERLAP_THRESHOLD,
    MIN_SAFE_PHRASE_TOKENS,
    NUMERIC_TOLERANCE,
)
from .text_normalization import normalize_text, token_coverage, tokenize_text
from .validation_common import ValidationChecks, add_check


SAFE_PAIR_KEYS = ["claim_id", "safe_phrase_item_id"]


def validation_cache(input_data: dict[str, Any]) -> dict[str, Any]:
    """Keep raw-input expectations so mutation tests stay fast."""

    cache = input_data.get("_diagnostic_validation_cache")
    if cache is None:
        cache = {}
        input_data["_diagnostic_validation_cache"] = cache
    return cache


def source_claims_with_packages(
    input_data: dict[str, Any],
) -> pd.DataFrame:
    """Return raw claims with the package used by their generation."""

    return input_data["claims"][
        [
            "claim_id",
            "generation_id",
            "model_id",
            "evidence_level",
            "source_text",
            "feature_id",
            "concept_id",
        ]
    ].merge(
        input_data["generations"][["generation_id", "package_id"]],
        on="generation_id",
        how="left",
        validate="many_to_one",
    )


def source_safe_phrases(input_data: dict[str, Any]) -> pd.DataFrame:
    """Return authored safe phrases with stable output column names."""

    cache = validation_cache(input_data)
    if "source_safe_phrases" in cache:
        return cache["source_safe_phrases"]

    items = input_data["evidence_items"]
    phrases = items.loc[
        items["safe_phrase"].notna()
        & (items["safe_phrase"].astype(str).str.strip() != ""),
        [
            "evidence_item_id",
            "package_id",
            "item_type",
            "item_order",
            "feature_id",
            "concept_id",
            "safe_phrase",
        ],
    ].copy()

    phrases = phrases.rename(
        columns={
            "evidence_item_id": "safe_phrase_item_id",
            "item_type": "safe_phrase_item_type",
            "item_order": "safe_phrase_item_order",
            "feature_id": "safe_phrase_feature_id",
            "concept_id": "safe_phrase_concept_id",
            "safe_phrase": "safe_phrase_text",
        }
    )
    cache["source_safe_phrases"] = phrases
    return phrases


def expected_safe_phrase_eligible_claim_ids(
    input_data: dict[str, Any],
) -> set[str]:
    """Rebuild claim eligibility from package and structured IDs."""

    cache = validation_cache(input_data)
    if "eligible_claim_ids" in cache:
        return cache["eligible_claim_ids"]

    claims = source_claims_with_packages(input_data)
    phrases = source_safe_phrases(input_data)

    feature_claims = claims.loc[
        claims["feature_id"].notna(),
        ["claim_id", "package_id", "feature_id"],
    ].merge(
        phrases.loc[
            phrases["safe_phrase_feature_id"].notna(),
            ["package_id", "safe_phrase_feature_id"],
        ].drop_duplicates(),
        left_on=["package_id", "feature_id"],
        right_on=["package_id", "safe_phrase_feature_id"],
        how="inner",
    )

    concept_claims = claims.loc[
        claims["concept_id"].notna(),
        ["claim_id", "package_id", "concept_id"],
    ].merge(
        phrases.loc[
            phrases["safe_phrase_concept_id"].notna(),
            ["package_id", "safe_phrase_concept_id"],
        ].drop_duplicates(),
        left_on=["package_id", "concept_id"],
        right_on=["package_id", "safe_phrase_concept_id"],
        how="inner",
    )

    eligible_ids = set(feature_claims["claim_id"].astype(str)) | set(
        concept_claims["claim_id"].astype(str)
    )
    cache["eligible_claim_ids"] = eligible_ids
    return eligible_ids


def independent_text_match(
    candidate_text: object,
    safe_phrase_text: object,
) -> dict[str, object]:
    """Recalculate lexical matching without calling the build function."""

    candidate_normalized = normalize_text(candidate_text)
    phrase_normalized = normalize_text(safe_phrase_text)
    phrase_token_count = len(tokenize_text(safe_phrase_text))

    exact = bool(
        candidate_normalized
        and candidate_normalized == phrase_normalized
    )
    contained = bool(
        exact
        or (
            phrase_token_count >= MIN_SAFE_PHRASE_TOKENS
            and phrase_normalized
            and phrase_normalized in candidate_normalized
        )
    )
    coverage = float(token_coverage(candidate_text, safe_phrase_text))
    high_overlap = bool(
        phrase_token_count >= MIN_SAFE_PHRASE_TOKENS
        and coverage >= HIGH_OVERLAP_THRESHOLD
    )

    if exact:
        match_type = "EXACT"
    elif contained:
        match_type = "CONTAINED"
    elif high_overlap:
        match_type = "HIGH_OVERLAP"
    else:
        match_type = "NONE"

    return {
        "match_type": match_type,
        "exact_match": exact,
        "contained_match": contained,
        "high_overlap_match": high_overlap,
        "token_coverage": coverage,
        "claim_token_count": len(tokenize_text(candidate_text)),
        "safe_phrase_token_count": phrase_token_count,
    }


def safe_phrase_candidates(input_data: dict[str, Any]) -> pd.DataFrame:
    """Build same-package candidates with feature identity precedence."""

    claims = source_claims_with_packages(input_data).rename(
        columns={
            "feature_id": "claim_feature_id",
            "concept_id": "claim_concept_id",
            "source_text": "claim_text",
        }
    )
    phrases = source_safe_phrases(input_data)

    feature_candidates = claims.loc[
        claims["claim_feature_id"].notna()
    ].merge(
        phrases.loc[phrases["safe_phrase_feature_id"].notna()],
        left_on=["package_id", "claim_feature_id"],
        right_on=["package_id", "safe_phrase_feature_id"],
        how="inner",
        validate="many_to_many",
    )
    feature_candidates["matched_identifier_type"] = "FEATURE_ID"
    feature_candidates["identifier_priority"] = 0

    concept_candidates = claims.loc[
        claims["claim_concept_id"].notna()
    ].merge(
        phrases.loc[phrases["safe_phrase_concept_id"].notna()],
        left_on=["package_id", "claim_concept_id"],
        right_on=["package_id", "safe_phrase_concept_id"],
        how="inner",
        validate="many_to_many",
    )
    concept_candidates["matched_identifier_type"] = "CONCEPT_ID"
    concept_candidates["identifier_priority"] = 1

    candidates = pd.concat(
        [feature_candidates, concept_candidates],
        ignore_index=True,
    )
    if candidates.empty:
        return candidates

    return candidates.sort_values(
        [
            "claim_id",
            "safe_phrase_item_id",
            "identifier_priority",
        ],
        kind="stable",
    ).drop_duplicates(
        subset=SAFE_PAIR_KEYS,
        keep="first",
    ).reset_index(drop=True)


def rebuild_expected_safe_phrase_matches(
    input_data: dict[str, Any],
) -> pd.DataFrame:
    """Rebuild every expected claim × safe-phrase match from raw inputs."""

    cache = validation_cache(input_data)
    if "expected_safe_phrase_matches" in cache:
        return cache["expected_safe_phrase_matches"]

    rows: list[dict[str, object]] = []
    for row in safe_phrase_candidates(input_data).itertuples(index=False):
        result = independent_text_match(
            row.claim_text,
            row.safe_phrase_text,
        )
        if result["match_type"] == "NONE":
            continue

        rows.append(
            {
                "claim_id": row.claim_id,
                "generation_id": row.generation_id,
                "package_id": row.package_id,
                "model_id": row.model_id,
                "evidence_level": row.evidence_level,
                "safe_phrase_item_id": row.safe_phrase_item_id,
                "safe_phrase_item_type": row.safe_phrase_item_type,
                "safe_phrase_item_order": row.safe_phrase_item_order,
                "safe_phrase_feature_id": row.safe_phrase_feature_id,
                "safe_phrase_concept_id": row.safe_phrase_concept_id,
                "matched_identifier_type": row.matched_identifier_type,
                "claim_text": row.claim_text,
                "safe_phrase_text": row.safe_phrase_text,
                **result,
            }
        )

    columns = [
        "claim_id",
        "generation_id",
        "package_id",
        "model_id",
        "evidence_level",
        "safe_phrase_item_id",
        "safe_phrase_item_type",
        "safe_phrase_item_order",
        "safe_phrase_feature_id",
        "safe_phrase_concept_id",
        "matched_identifier_type",
        "claim_text",
        "safe_phrase_text",
        "match_type",
        "exact_match",
        "contained_match",
        "high_overlap_match",
        "token_coverage",
        "claim_token_count",
        "safe_phrase_token_count",
    ]
    expected = pd.DataFrame(rows, columns=columns).sort_values(
        ["claim_id", "safe_phrase_item_order", "safe_phrase_item_id"],
        kind="stable",
    ).reset_index(drop=True)
    cache["expected_safe_phrase_matches"] = expected
    return expected


def expected_claim_match_state(
    claim_diagnostics: pd.DataFrame,
    expected_matches: pd.DataFrame,
    input_data: dict[str, Any],
) -> pd.DataFrame:
    """Build expected best-match and cumulative flags for every claim."""

    phrase_packages = set(source_safe_phrases(input_data)["package_id"])
    eligible_ids = expected_safe_phrase_eligible_claim_ids(input_data)

    state = claim_diagnostics[["claim_id", "package_id"]].copy()
    state["safe_phrase_exposed"] = state["package_id"].isin(
        phrase_packages
    )
    state["safe_phrase_match_eligible"] = state["claim_id"].astype(
        str
    ).isin(eligible_ids)
    state["best_safe_phrase_item_id"] = None
    state["best_safe_phrase_match_type"] = "NONE"
    state["best_safe_phrase_token_coverage"] = 0.0
    state["safe_phrase_exact_match"] = False
    state["safe_phrase_contained_match"] = False
    state["safe_phrase_high_overlap"] = False
    state["safe_phrase_any_match"] = False

    if expected_matches.empty:
        return state

    priority = {"EXACT": 0, "CONTAINED": 1, "HIGH_OVERLAP": 2}
    ordered = expected_matches.assign(
        match_priority=expected_matches["match_type"].map(priority)
    ).sort_values(
        [
            "claim_id",
            "match_priority",
            "token_coverage",
            "safe_phrase_item_order",
            "safe_phrase_item_id",
        ],
        ascending=[True, True, False, True, True],
        kind="stable",
    )
    best = ordered.drop_duplicates("claim_id", keep="first")

    grouped = expected_matches.groupby("claim_id", sort=False).agg(
        safe_phrase_exact_match=("exact_match", "any"),
        safe_phrase_contained_match=("contained_match", "any"),
        safe_phrase_high_overlap=("high_overlap_match", "any"),
    ).reset_index()
    grouped["safe_phrase_any_match"] = True

    best = best[
        [
            "claim_id",
            "safe_phrase_item_id",
            "match_type",
            "token_coverage",
        ]
    ].rename(
        columns={
            "safe_phrase_item_id": "best_safe_phrase_item_id",
            "match_type": "best_safe_phrase_match_type",
            "token_coverage": "best_safe_phrase_token_coverage",
        }
    )

    expected = state.drop(
        columns=[
            "best_safe_phrase_item_id",
            "best_safe_phrase_match_type",
            "best_safe_phrase_token_coverage",
            "safe_phrase_exact_match",
            "safe_phrase_contained_match",
            "safe_phrase_high_overlap",
            "safe_phrase_any_match",
        ]
    ).merge(best, on="claim_id", how="left", validate="one_to_one")
    expected = expected.merge(
        grouped,
        on="claim_id",
        how="left",
        validate="one_to_one",
    )

    expected["best_safe_phrase_match_type"] = expected[
        "best_safe_phrase_match_type"
    ].fillna("NONE")
    expected["best_safe_phrase_token_coverage"] = expected[
        "best_safe_phrase_token_coverage"
    ].fillna(0.0)
    for column in [
        "safe_phrase_exact_match",
        "safe_phrase_contained_match",
        "safe_phrase_high_overlap",
        "safe_phrase_any_match",
    ]:
        expected[column] = (
            expected[column]
            .astype("boolean")
            .fillna(False)
            .astype(bool)
        )

    return expected


def claim_match_state_mismatch_count(
    claim_diagnostics: pd.DataFrame,
    expected_state: pd.DataFrame,
) -> int:
    """Compare claim-level best-match fields with rebuilt expectations."""

    columns = [
        "safe_phrase_exposed",
        "safe_phrase_match_eligible",
        "best_safe_phrase_item_id",
        "best_safe_phrase_match_type",
        "best_safe_phrase_token_coverage",
        "safe_phrase_exact_match",
        "safe_phrase_contained_match",
        "safe_phrase_high_overlap",
        "safe_phrase_any_match",
    ]
    joined = expected_state[["claim_id", *columns]].merge(
        claim_diagnostics[["claim_id", *columns]],
        on="claim_id",
        how="outer",
        validate="one_to_one",
        suffixes=("_expected", "_observed"),
        indicator=True,
    )

    mismatch = joined["_merge"] != "both"
    for column in columns:
        expected = joined[f"{column}_expected"]
        observed = joined[f"{column}_observed"]
        if column == "best_safe_phrase_token_coverage":
            matches = np.isclose(
                expected,
                observed,
                rtol=0.0,
                atol=NUMERIC_TOLERANCE,
                equal_nan=True,
            )
        else:
            matches = (
                expected.fillna("<NULL>").astype(str)
                == observed.fillna("<NULL>").astype(str)
            )
        mismatch = mismatch | ~matches

    return int(mismatch.sum())


def safe_phrase_pair_comparison(
    expected: pd.DataFrame,
    observed: pd.DataFrame,
) -> dict[str, int]:
    """Compare expected and observed pair keys, metadata and rules."""

    metadata_columns = [
        "generation_id",
        "package_id",
        "model_id",
        "evidence_level",
        "safe_phrase_item_type",
        "safe_phrase_item_order",
        "safe_phrase_feature_id",
        "safe_phrase_concept_id",
        "matched_identifier_type",
    ]
    rule_columns = [
        "match_type",
        "exact_match",
        "contained_match",
        "high_overlap_match",
        "token_coverage",
        "claim_token_count",
        "safe_phrase_token_count",
    ]
    expected_unique = expected.drop_duplicates(
        subset=SAFE_PAIR_KEYS,
        keep="first",
    )
    observed_unique = observed.drop_duplicates(
        subset=SAFE_PAIR_KEYS,
        keep="first",
    )
    joined = expected_unique.merge(
        observed_unique,
        on=SAFE_PAIR_KEYS,
        how="outer",
        validate="one_to_one",
        suffixes=("_expected", "_observed"),
        indicator=True,
    )

    missing = int((joined["_merge"] == "left_only").sum())
    extra = int((joined["_merge"] == "right_only").sum())
    both = joined.loc[joined["_merge"] == "both"]

    source_mismatch = (
        both["claim_text_expected"].fillna("<NULL>").astype(str)
        != both["claim_text_observed"].fillna("<NULL>").astype(str)
    ) | (
        both["safe_phrase_text_expected"].fillna("<NULL>").astype(str)
        != both["safe_phrase_text_observed"].fillna("<NULL>").astype(str)
    )

    metadata_mismatch = pd.Series(False, index=both.index)
    for column in metadata_columns:
        metadata_mismatch = metadata_mismatch | (
            both[f"{column}_expected"].fillna("<NULL>").astype(str)
            != both[f"{column}_observed"].fillna("<NULL>").astype(str)
        )

    rule_mismatch = pd.Series(False, index=both.index)
    for column in rule_columns:
        expected_values = both[f"{column}_expected"]
        observed_values = both[f"{column}_observed"]
        if column == "token_coverage":
            matches = np.isclose(
                expected_values,
                observed_values,
                rtol=0.0,
                atol=NUMERIC_TOLERANCE,
                equal_nan=True,
            )
        else:
            matches = (
                expected_values.astype("string").fillna("<NULL>")
                == observed_values.astype("string").fillna("<NULL>")
            )
        rule_mismatch = rule_mismatch | ~matches

    return {
        "missing": missing,
        "extra": extra,
        "source_mismatch": int(source_mismatch.sum()),
        "metadata_mismatch": int(metadata_mismatch.sum()),
        "rule_mismatch": int(rule_mismatch.sum()),
    }


def validate_safe_phrase_matches(
    checks: ValidationChecks,
    matches: pd.DataFrame,
    claim_diagnostics: pd.DataFrame,
    input_data: dict[str, Any],
) -> None:
    """Rebuild and validate the complete safe-phrase mechanism."""

    duplicate_count = int(
        matches.duplicated(
            subset=SAFE_PAIR_KEYS,
            keep=False,
        ).sum()
    )
    add_check(
        checks,
        "duplicate_claim_safe_phrase_pair_count",
        0,
        duplicate_count,
        duplicate_count == 0,
    )

    expected_matches = rebuild_expected_safe_phrase_matches(input_data)
    comparison = safe_phrase_pair_comparison(expected_matches, matches)

    add_check(
        checks,
        "expected_safe_phrase_match_pair_count",
        len(expected_matches),
        len(matches),
        len(matches) == len(expected_matches),
    )
    for check_name, comparison_key in [
        ("missing_safe_phrase_match_pair_count", "missing"),
        ("extra_safe_phrase_match_pair_count", "extra"),
        ("safe_phrase_match_source_text_mismatch_count", "source_mismatch"),
        (
            "safe_phrase_match_item_metadata_mismatch_count",
            "metadata_mismatch",
        ),
        ("safe_phrase_rule_mismatch_count", "rule_mismatch"),
    ]:
        observed = comparison[comparison_key]
        add_check(checks, check_name, 0, observed, observed == 0)

    expected_state = expected_claim_match_state(
        claim_diagnostics,
        expected_matches,
        input_data,
    )
    state_mismatch = claim_match_state_mismatch_count(
        claim_diagnostics,
        expected_state,
    )
    add_check(
        checks,
        "claim_best_match_reconciliation_mismatch_count",
        0,
        state_mismatch,
        state_mismatch == 0,
    )

    exact_not_contained = int(
        (matches["exact_match"] & ~matches["contained_match"]).sum()
    )
    high_overlap_below_threshold = int(
        (
            matches["high_overlap_match"]
            & (
                matches["token_coverage"]
                + NUMERIC_TOLERANCE
                < HIGH_OVERLAP_THRESHOLD
            )
        ).sum()
    )
    add_check(
        checks,
        "exact_match_not_contained_count",
        0,
        exact_not_contained,
        exact_not_contained == 0,
    )
    add_check(
        checks,
        "high_overlap_below_threshold_count",
        0,
        high_overlap_below_threshold,
        high_overlap_below_threshold == 0,
    )
