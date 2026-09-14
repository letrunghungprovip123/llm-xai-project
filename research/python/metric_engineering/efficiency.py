"""Calculate observed speed and token-efficiency metrics."""

from __future__ import annotations

import pandas as pd

from .quality import divide_when_positive


def add_efficiency_metrics(
    generations: pd.DataFrame,
) -> pd.DataFrame:
    """Add observed resource metrics without estimating monetary cost."""

    metrics = generations.copy()

    metrics["latency_seconds"] = (
        metrics["latency_ms"].astype(float) / 1000.0
    )

    latency_seconds = metrics["latency_seconds"]
    total_tokens = metrics["total_token_count"]
    output_tokens = metrics["output_token_count"]
    claim_count = metrics["claim_count"]
    supported_count = metrics["supported_count"]

    metrics["output_tokens_per_second"] = divide_when_positive(
        output_tokens,
        latency_seconds,
    )
    metrics["claims_per_second"] = divide_when_positive(
        claim_count,
        latency_seconds,
    )
    metrics["supported_claims_per_second"] = divide_when_positive(
        supported_count,
        latency_seconds,
    )
    metrics[
        "latency_per_supported_claim_seconds"
    ] = divide_when_positive(
        latency_seconds,
        supported_count,
    )

    metrics["claims_per_1000_total_tokens"] = (
        divide_when_positive(
            claim_count,
            total_tokens,
        )
        * 1000.0
    )
    metrics["supported_claims_per_1000_total_tokens"] = (
        divide_when_positive(
            supported_count,
            total_tokens,
        )
        * 1000.0
    )
    metrics["output_tokens_per_supported_claim"] = (
        divide_when_positive(
            output_tokens,
            supported_count,
        )
    )

    return metrics
