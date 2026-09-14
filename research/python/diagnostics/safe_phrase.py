"""Deterministic same-package safe-phrase matching."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .config import (
    CLAIM_DIAGNOSTIC_COLUMNS,
    GENERATION_TEXT_COLUMNS,
    HIGH_OVERLAP_THRESHOLD,
    MIN_SAFE_PHRASE_TOKENS,
)
from .text_normalization import (
    normalize_text,
    token_coverage,
    tokenize_text,
)


SAFE_MATCH_COLUMNS = [
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


def extract_safe_phrase_items(
    input_data: dict[str, Any],
) -> pd.DataFrame:
    """Select evidence items that contain an authored safe phrase."""

    items = input_data["evidence_items"].copy()
    packages = input_data["evidence_packages"]

    safe_phrases = items.loc[
        items["safe_phrase"].notna()
        & (items["safe_phrase"].astype(str).str.strip() != ""),
        [
            "evidence_item_id",
            "package_id",
            "case_id",
            "evidence_level",
            "item_type",
            "item_order",
            "feature_id",
            "concept_id",
            "safe_phrase",
        ],
    ].copy()

    observed_counts = (
        safe_phrases.groupby("package_id").size().rename("observed")
    )
    count_check = packages[
        ["package_id", "safe_phrase_count"]
    ].merge(
        observed_counts,
        on="package_id",
        how="left",
        validate="one_to_one",
    )
    count_check["observed"] = count_check["observed"].fillna(0)

    mismatch = (
        count_check["safe_phrase_count"].astype(int)
        != count_check["observed"].astype(int)
    )
    if mismatch.any():
        raise ValueError(
            "safe_phrase_count does not match evidence_items.csv for "
            f"{int(mismatch.sum())} packages."
        )

    safe_phrases["normalized_safe_phrase"] = safe_phrases[
        "safe_phrase"
    ].map(normalize_text)
    safe_phrases["safe_phrase_token_count"] = safe_phrases[
        "safe_phrase"
    ].map(lambda value: len(tokenize_text(value)))

    if (safe_phrases["normalized_safe_phrase"] == "").any():
        raise ValueError(
            "Evidence items contain safe phrases that normalize to empty."
        )

    return safe_phrases.sort_values(
        ["package_id", "item_order", "evidence_item_id"],
        kind="stable",
    ).reset_index(drop=True)


def evaluate_text_pair(
    candidate_text: object,
    safe_phrase_text: object,
    *,
    allow_high_overlap: bool = True,
) -> dict[str, object]:
    """Evaluate exact, contained and token-overlap rules."""

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
    coverage = token_coverage(candidate_text, safe_phrase_text)
    high_overlap = bool(
        allow_high_overlap
        and phrase_token_count >= MIN_SAFE_PHRASE_TOKENS
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
        "token_coverage": float(coverage),
        "candidate_token_count": len(tokenize_text(candidate_text)),
        "safe_phrase_token_count": phrase_token_count,
    }


def phrases_by_package(
    safe_phrases: pd.DataFrame,
) -> dict[str, list[dict[str, object]]]:
    """Create a small in-memory lookup keyed by package ID."""

    lookup: dict[str, list[dict[str, object]]] = {}

    for package_id, group in safe_phrases.groupby(
        "package_id",
        sort=False,
    ):
        lookup[str(package_id)] = group.to_dict("records")

    return lookup


def same_value(left: object, right: object) -> bool:
    """Compare optional structured identifiers without matching nulls."""

    if left is None or right is None:
        return False
    if pd.isna(left) or pd.isna(right):
        return False
    return str(left) == str(right)


def eligible_phrases_for_claim(
    claim: object,
    package_phrases: list[dict[str, object]],
) -> list[tuple[dict[str, object], str]]:
    """Use feature/concept identity to prevent boilerplate false matches."""

    candidates: dict[str, tuple[dict[str, object], str]] = {}

    for phrase in package_phrases:
        if same_value(claim.feature_id, phrase.get("feature_id")):
            candidates[str(phrase["evidence_item_id"])] = (
                phrase,
                "FEATURE_ID",
            )
        elif same_value(claim.concept_id, phrase.get("concept_id")):
            candidates[str(phrase["evidence_item_id"])] = (
                phrase,
                "CONCEPT_ID",
            )

    return list(candidates.values())


def best_match_sort_key(match: dict[str, object]) -> tuple[object, ...]:
    """Order matches by explicit precedence and stable evidence order."""

    priority = {
        "EXACT": 0,
        "CONTAINED": 1,
        "HIGH_OVERLAP": 2,
    }

    return (
        priority[str(match["match_type"])],
        -float(match["token_coverage"]),
        int(match["safe_phrase_item_order"]),
        str(match["safe_phrase_item_id"]),
    )


def match_claims_to_safe_phrases(
    claim_diagnostics: pd.DataFrame,
    safe_phrases: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match structured claims to same-identifier, same-package phrases."""

    lookup = phrases_by_package(safe_phrases)
    match_rows: list[dict[str, object]] = []
    eligible_claim_ids: set[str] = set()

    for claim in claim_diagnostics.itertuples(index=False):
        package_phrases = lookup.get(str(claim.package_id), [])
        candidates = eligible_phrases_for_claim(claim, package_phrases)

        if candidates:
            eligible_claim_ids.add(str(claim.claim_id))

        for phrase, identifier_type in candidates:
            result = evaluate_text_pair(
                claim.source_text,
                phrase["safe_phrase"],
            )

            if result["match_type"] == "NONE":
                continue

            match_rows.append(
                {
                    "claim_id": claim.claim_id,
                    "generation_id": claim.generation_id,
                    "package_id": claim.package_id,
                    "model_id": claim.model_id,
                    "evidence_level": claim.evidence_level,
                    "safe_phrase_item_id": phrase[
                        "evidence_item_id"
                    ],
                    "safe_phrase_item_type": phrase["item_type"],
                    "safe_phrase_item_order": phrase["item_order"],
                    "safe_phrase_feature_id": phrase["feature_id"],
                    "safe_phrase_concept_id": phrase["concept_id"],
                    "matched_identifier_type": identifier_type,
                    "claim_text": claim.source_text,
                    "safe_phrase_text": phrase["safe_phrase"],
                    "match_type": result["match_type"],
                    "exact_match": result["exact_match"],
                    "contained_match": result["contained_match"],
                    "high_overlap_match": result[
                        "high_overlap_match"
                    ],
                    "token_coverage": result["token_coverage"],
                    "claim_token_count": result[
                        "candidate_token_count"
                    ],
                    "safe_phrase_token_count": result[
                        "safe_phrase_token_count"
                    ],
                }
            )

    output = claim_diagnostics.copy()
    output["safe_phrase_match_eligible"] = output["claim_id"].astype(
        str
    ).isin(eligible_claim_ids)

    matches = pd.DataFrame(match_rows, columns=SAFE_MATCH_COLUMNS)
    if matches.empty:
        return output[CLAIM_DIAGNOSTIC_COLUMNS].copy(), matches

    matches = matches.sort_values(
        [
            "claim_id",
            "safe_phrase_item_order",
            "safe_phrase_item_id",
        ],
        kind="stable",
    ).reset_index(drop=True)

    best_rows = []
    for claim_id, group in matches.groupby("claim_id", sort=False):
        records = group.to_dict("records")
        best = min(records, key=best_match_sort_key)
        best_rows.append(
            {
                "claim_id": claim_id,
                "best_safe_phrase_item_id": best[
                    "safe_phrase_item_id"
                ],
                "best_safe_phrase_match_type": best["match_type"],
                "best_safe_phrase_token_coverage": best[
                    "token_coverage"
                ],
                "safe_phrase_exact_match": bool(
                    group["exact_match"].any()
                ),
                "safe_phrase_contained_match": bool(
                    group["contained_match"].any()
                ),
                "safe_phrase_high_overlap": bool(
                    group["high_overlap_match"].any()
                ),
                "safe_phrase_any_match": True,
            }
        )

    best_matches = pd.DataFrame(best_rows)
    output = output.drop(
        columns=[
            "best_safe_phrase_item_id",
            "best_safe_phrase_match_type",
            "best_safe_phrase_token_coverage",
            "safe_phrase_exact_match",
            "safe_phrase_contained_match",
            "safe_phrase_high_overlap",
            "safe_phrase_any_match",
        ]
    ).merge(
        best_matches,
        on="claim_id",
        how="left",
        validate="one_to_one",
    )

    output["best_safe_phrase_match_type"] = output[
        "best_safe_phrase_match_type"
    ].fillna("NONE")
    output["best_safe_phrase_token_coverage"] = output[
        "best_safe_phrase_token_coverage"
    ].fillna(0.0)

    boolean_columns = [
        "safe_phrase_exact_match",
        "safe_phrase_contained_match",
        "safe_phrase_high_overlap",
        "safe_phrase_any_match",
    ]
    for column in boolean_columns:
        output[column] = (
            output[column].astype("boolean").fillna(False).astype(bool)
        )

    return output[CLAIM_DIAGNOSTIC_COLUMNS].copy(), matches


def parse_factor_components(value: object) -> list[dict[str, object]]:
    """Extract factor text together with declared structured IDs."""

    if value is None or pd.isna(value):
        return []

    try:
        factors = json.loads(str(value))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid factors_json: {error}") from error

    if not isinstance(factors, list):
        raise ValueError("factors_json must contain a JSON array.")

    components: list[dict[str, object]] = []
    for factor in factors:
        if not isinstance(factor, dict):
            raise ValueError("Each factors_json item must be an object.")

        feature_ids = factor.get("declared_feature_ids", [])
        concept_ids = factor.get("declared_concept_ids", [])
        if not isinstance(feature_ids, list) or not isinstance(
            concept_ids,
            list,
        ):
            raise ValueError(
                "declared feature/concept IDs must be JSON arrays."
            )

        for key in ["factor_name", "explanation"]:
            text = factor.get(key)
            if text is not None and str(text).strip():
                components.append(
                    {
                        "text": str(text),
                        "feature_ids": [str(item) for item in feature_ids],
                        "concept_ids": [str(item) for item in concept_ids],
                        "allow_high_overlap": True,
                    }
                )

    return components


def generation_text_components(row: pd.Series) -> list[dict[str, object]]:
    """Collect narrative sections and structured factor components."""

    components: list[dict[str, object]] = []

    for column in GENERATION_TEXT_COLUMNS:
        value = row[column]
        if value is not None and not pd.isna(value):
            text = str(value).strip()
            if text:
                components.append(
                    {
                        "text": text,
                        "feature_ids": [],
                        "concept_ids": [],
                        "allow_high_overlap": False,
                    }
                )

    components.extend(parse_factor_components(row["factors_json"]))
    return components


def eligible_phrases_for_component(
    component: dict[str, object],
    package_phrases: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Restrict factor overlap to matching declared identifiers."""

    feature_ids = set(component["feature_ids"])
    concept_ids = set(component["concept_ids"])

    if not feature_ids and not concept_ids:
        return package_phrases

    candidates = []
    for phrase in package_phrases:
        phrase_feature = phrase.get("feature_id")
        phrase_concept = phrase.get("concept_id")

        if (
            phrase_feature is not None
            and not pd.isna(phrase_feature)
            and str(phrase_feature) in feature_ids
        ) or (
            phrase_concept is not None
            and not pd.isna(phrase_concept)
            and str(phrase_concept) in concept_ids
        ):
            candidates.append(phrase)

    return candidates


def match_generation_narratives(
    generations: pd.DataFrame,
    safe_phrases: pd.DataFrame,
) -> pd.DataFrame:
    """Measure safe-phrase overlap across structured narrative sections."""

    lookup = phrases_by_package(safe_phrases)
    rows: list[dict[str, object]] = []

    for _, generation in generations.iterrows():
        package_phrases = lookup.get(
            str(generation["package_id"]),
            [],
        )
        components = generation_text_components(generation)

        exact = False
        contained = False
        high_overlap = False
        maximum_coverage = 0.0

        for component in components:
            candidates = eligible_phrases_for_component(
                component,
                package_phrases,
            )

            for phrase in candidates:
                result = evaluate_text_pair(
                    component["text"],
                    phrase["safe_phrase"],
                    allow_high_overlap=bool(
                        component["allow_high_overlap"]
                    ),
                )
                exact = exact or bool(result["exact_match"])
                contained = contained or bool(
                    result["contained_match"]
                )
                high_overlap = high_overlap or bool(
                    result["high_overlap_match"]
                )
                maximum_coverage = max(
                    maximum_coverage,
                    float(result["token_coverage"]),
                )

        rows.append(
            {
                "generation_id": generation["generation_id"],
                "narrative_exact_safe_phrase_match": exact,
                "narrative_contained_safe_phrase_match": contained,
                "narrative_high_overlap_safe_phrase_match": (
                    high_overlap
                ),
                "narrative_any_safe_phrase_match": (
                    exact or contained or high_overlap
                ),
                "narrative_max_safe_phrase_token_coverage": (
                    maximum_coverage
                ),
            }
        )

    return pd.DataFrame(rows)
