"""Calculate transparent generation reliability flags."""

from __future__ import annotations

import pandas as pd


def add_reliability_metrics(
    generations: pd.DataFrame,
) -> pd.DataFrame:
    """Add component reliability flags instead of one weighted score."""

    metrics = generations.copy()

    usable = metrics["usable"].astype(bool)
    truncated = metrics["truncated_response"].astype(bool)
    raw_parse_success = metrics[
        "raw_json_parse_success"
    ].astype(bool)
    cleaned_parse_success = metrics[
        "json_parse_success"
    ].astype(bool)
    schema_valid = metrics["schema_valid"].astype(bool)
    retry_count = metrics["retry_count"]

    metrics["is_unusable"] = ~usable
    metrics["is_truncated"] = truncated
    metrics["is_parse_success"] = (
        raw_parse_success & cleaned_parse_success
    )
    metrics["is_schema_valid"] = schema_valid
    metrics["is_first_attempt_success"] = (
        usable & (retry_count == 0)
    )
    metrics["was_retried"] = retry_count > 0

    metrics["is_strict_pipeline_success"] = (
        usable
        & (metrics["runtime_status"] == "SUCCESS")
        & ~truncated
        & metrics["is_parse_success"]
        & schema_valid
        & (metrics["claim_count"] > 0)
    )

    return metrics
