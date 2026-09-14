"""Tạo bảng 18 model × evidence options từ dữ liệu chi tiết."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import DECISION_VERSION, P10_QUANTILE


def divide_or_nan(numerator: float, denominator: float) -> float:
    """Không tạo infinity khi denominator bằng zero."""

    if denominator <= 0:
        return float("nan")
    return float(numerator / denominator)


def summarize_generation_group(group: pd.DataFrame) -> dict[str, object]:
    """Tóm tắt 36 planned generations của một option."""

    quality = pd.to_numeric(
        group["end_to_end_faithfulness_yield"],
        errors="coerce",
    ).astype(float)
    usable = group["usable"].astype(bool)

    return {
        "planned_generation_count": int(len(group)),
        "mean_end_to_end_yield": float(quality.mean()),
        "median_end_to_end_yield": float(quality.median()),
        "p10_end_to_end_yield": float(quality.quantile(P10_QUANTILE)),
        "standard_deviation_end_to_end_yield": float(quality.std(ddof=1)),
        "minimum_end_to_end_yield": float(quality.min()),
        "maximum_end_to_end_yield": float(quality.max()),
        "mean_pipeline_loss": float(group["pipeline_loss"].mean()),
        "mean_not_verifiable_loss": float(
            group["not_verifiable_loss"].mean()
        ),
        "mean_unsupported_loss": float(group["unsupported_loss"].mean()),
        "mean_contradiction_loss": float(
            group["contradiction_loss"].mean()
        ),
        "mean_resolved_error_loss": float(
            group["resolved_error_loss"].mean()
        ),
        "mean_claim_quality_loss": float(
            group["claim_quality_loss"].mean()
        ),
        "usable_generation_count": int(usable.sum()),
        "unusable_generation_count": int((~usable).sum()),
        "usability_rate": float(usable.mean()),
    }


def summarize_runtime_group(group: pd.DataFrame) -> dict[str, object]:
    """Tóm tắt runtime metrics theo planned và usable populations."""

    usable = group["usable"].astype(bool)
    latency = pd.to_numeric(group["latency_seconds"], errors="coerce")
    tokens = pd.to_numeric(group["total_token_count"], errors="coerce")
    efficiency = pd.to_numeric(
        group["supported_claims_per_1000_total_tokens"],
        errors="coerce",
    )

    usable_latency = latency.loc[usable].dropna()
    usable_tokens = tokens.loc[usable].dropna()

    return {
        "truncated_generation_count": int(
            group["is_truncated"].astype(bool).sum()
        ),
        "truncation_rate": float(group["is_truncated"].astype(bool).mean()),
        "parse_success_rate": float(
            group["is_parse_success"].astype(bool).mean()
        ),
        "schema_valid_rate": float(
            group["is_schema_valid"].astype(bool).mean()
        ),
        "latency_observed_count": int(latency.notna().sum()),
        "token_observed_count": int(tokens.notna().sum()),
        "mean_latency_seconds_planned": float(latency.mean()),
        "median_latency_seconds_planned": float(latency.median()),
        "mean_total_token_count_planned": float(tokens.mean()),
        "median_total_token_count_planned": float(tokens.median()),
        "mean_supported_claims_per_1000_tokens": float(efficiency.mean()),
        "mean_latency_seconds_usable": (
            float(usable_latency.mean())
            if not usable_latency.empty
            else float("nan")
        ),
        "mean_total_token_count_usable": (
            float(usable_tokens.mean())
            if not usable_tokens.empty
            else float("nan")
        ),
    }


def build_option_generation_metrics(
    generation_diagnostics: pd.DataFrame,
    generation_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Tính quality, loss, reliability và efficiency cho 18 options."""

    runtime_columns = generation_metrics[
        [
            "generation_id",
            "model_id",
            "evidence_level",
            "usable",
            "is_truncated",
            "is_parse_success",
            "is_schema_valid",
            "latency_seconds",
            "total_token_count",
            "supported_claims_per_1000_total_tokens",
        ]
    ].rename(
        columns={
            "model_id": "runtime_model_id",
            "evidence_level": "runtime_evidence_level",
            "usable": "runtime_usable",
        }
    )

    frame = generation_diagnostics.merge(
        runtime_columns,
        on="generation_id",
        how="left",
        validate="one_to_one",
    )

    mismatch = (
        (frame["model_id"] != frame["runtime_model_id"])
        | (frame["evidence_level"] != frame["runtime_evidence_level"])
        | (
            frame["usable"].astype(bool)
            != frame["runtime_usable"].astype(bool)
        )
    )
    if mismatch.any():
        raise ValueError(
            "generation_diagnostics.csv and generation_metrics.csv "
            f"disagree for {int(mismatch.sum())} generations."
        )

    rows: list[dict[str, object]] = []
    grouped = frame.groupby(["model_id", "evidence_level"], sort=False)
    for (model_id, evidence_level), group in grouped:
        rows.append(
            {
                "model_id": model_id,
                "evidence_level": evidence_level,
                **summarize_generation_group(group),
                **summarize_runtime_group(group),
            }
        )

    return pd.DataFrame(rows)


def build_option_claim_mechanisms(
    claim_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Lấy exclusive safe-phrase categories ở grain model × evidence."""

    rows = claim_summary.loc[
        claim_summary["group_type"] == "model_evidence",
        [
            "model_id",
            "evidence_level",
            "claim_count",
            "safe_phrase_exposed_claim_count",
            "safe_phrase_eligible_claim_count",
            "safe_phrase_best_exact_claim_count",
            "safe_phrase_best_contained_claim_count",
            "safe_phrase_best_high_overlap_claim_count",
            "safe_phrase_best_none_claim_count",
        ],
    ].copy()

    count_columns = [column for column in rows.columns if column.endswith("count")]
    rows[count_columns] = rows[count_columns].fillna(0).astype(int)

    rows["strong_safe_phrase_signal_count"] = (
        rows["safe_phrase_best_exact_claim_count"]
        + rows["safe_phrase_best_contained_claim_count"]
    )
    rows["weak_safe_phrase_signal_count"] = rows[
        "safe_phrase_best_high_overlap_claim_count"
    ]

    rows["safe_phrase_eligible_claim_share"] = rows.apply(
        lambda row: divide_or_nan(
            row["safe_phrase_eligible_claim_count"],
            row["claim_count"],
        ),
        axis=1,
    )
    rows["strong_safe_phrase_signal_share_all_claims"] = rows.apply(
        lambda row: divide_or_nan(
            row["strong_safe_phrase_signal_count"],
            row["claim_count"],
        ),
        axis=1,
    )
    rows["weak_safe_phrase_signal_share_all_claims"] = rows.apply(
        lambda row: divide_or_nan(
            row["weak_safe_phrase_signal_count"],
            row["claim_count"],
        ),
        axis=1,
    )
    rows["strong_safe_phrase_signal_rate_eligible"] = rows.apply(
        lambda row: divide_or_nan(
            row["strong_safe_phrase_signal_count"],
            row["safe_phrase_eligible_claim_count"],
        ),
        axis=1,
    )
    rows["weak_safe_phrase_signal_rate_eligible"] = rows.apply(
        lambda row: divide_or_nan(
            row["weak_safe_phrase_signal_count"],
            row["safe_phrase_eligible_claim_count"],
        ),
        axis=1,
    )
    rows["no_safe_phrase_match_rate_eligible"] = rows.apply(
        lambda row: divide_or_nan(
            row["safe_phrase_best_none_claim_count"],
            row["safe_phrase_eligible_claim_count"],
        ),
        axis=1,
    )

    return rows


def build_decision_options(input_data: dict[str, Any]) -> pd.DataFrame:
    """Tạo bảng 18 options, mỗi option đại diện một model × evidence cell."""

    generation_part = build_option_generation_metrics(
        input_data["generation_diagnostics"],
        input_data["generation_metrics"],
    )
    claim_part = build_option_claim_mechanisms(
        input_data["claim_mechanism_summary"]
    )

    options = generation_part.merge(
        claim_part,
        on=["model_id", "evidence_level"],
        how="left",
        validate="one_to_one",
    )
    options = options.merge(
        input_data["models"][["model_id", "model_order", "model_label"]],
        on="model_id",
        how="left",
        validate="many_to_one",
    )
    options = options.merge(
        input_data["evidence_levels"][
            [
                "evidence_level",
                "evidence_order",
                "evidence_label",
                "intended_role",
            ]
        ],
        on="evidence_level",
        how="left",
        validate="many_to_one",
    )

    required_dimension_values = options[
        ["model_label", "model_order", "evidence_label", "evidence_order"]
    ]
    if required_dimension_values.isna().any(axis=None):
        raise ValueError("Decision options contain orphan model/evidence keys.")

    options.insert(
        0,
        "option_id",
        options["model_id"].astype(str)
        + "__"
        + options["evidence_level"].astype(str),
    )
    options.insert(0, "decision_version", DECISION_VERSION)

    options = options.sort_values(
        ["model_order", "evidence_order"],
        kind="stable",
    ).reset_index(drop=True)

    preferred_columns = [
        "decision_version",
        "option_id",
        "model_id",
        "model_label",
        "model_order",
        "evidence_level",
        "evidence_label",
        "evidence_order",
        "intended_role",
    ]
    remaining_columns = [
        column for column in options.columns if column not in preferred_columns
    ]
    return options[preferred_columns + remaining_columns].copy()
