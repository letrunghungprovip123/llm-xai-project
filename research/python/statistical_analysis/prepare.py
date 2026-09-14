"""Create one clean generation-level frame for statistical analysis."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .config import (
    ANALYSIS_FRAME_COLUMNS,
    PRIMARY_METRIC,
    STATISTICAL_ANALYSIS_VERSION,
)


def build_analysis_frame(
    input_data: dict[str, Any],
) -> pd.DataFrame:
    """Join dimensions without changing the 648-generation grain."""

    metrics = input_data["generation_metrics"].copy()

    case_columns = input_data["cases"][
        [
            "case_id",
            "selection_stratum",
            "prediction_correct",
            "prediction_outcome",
            "distance_from_threshold",
        ]
    ].rename(
        columns={
            "selection_stratum": "case_selection_stratum",
        }
    )

    model_columns = input_data["models"][
        ["model_id", "model_label", "model_order"]
    ].rename(
        columns={"model_order": "dimension_model_order"}
    )

    evidence_columns = input_data["evidence_levels"][
        [
            "evidence_level",
            "evidence_label",
            "intended_role",
            "evidence_order",
        ]
    ].rename(
        columns={
            "evidence_order": "dimension_evidence_order",
        }
    )

    frame = metrics.merge(
        case_columns,
        on="case_id",
        how="left",
        validate="many_to_one",
    )
    frame = frame.merge(
        model_columns,
        on="model_id",
        how="left",
        validate="many_to_one",
    )
    frame = frame.merge(
        evidence_columns,
        on="evidence_level",
        how="left",
        validate="many_to_one",
    )

    missing_dimension_rows = frame[
        [
            "case_selection_stratum",
            "model_label",
            "evidence_label",
        ]
    ].isna().any(axis=1)

    if missing_dimension_rows.any():
        missing_ids = frame.loc[
            missing_dimension_rows,
            "generation_id",
        ].head(10).tolist()
        raise ValueError(
            "Analysis frame contains orphan dimension keys. "
            f"Example generation IDs: {missing_ids}"
        )

    stratum_mismatch = (
        frame["selection_stratum"]
        != frame["case_selection_stratum"]
    )
    if stratum_mismatch.any():
        raise ValueError(
            "selection_stratum does not match cases.csv for "
            f"{int(stratum_mismatch.sum())} generations."
        )

    model_order_mismatch = (
        frame["model_order"]
        != frame["dimension_model_order"]
    )
    evidence_order_mismatch = (
        frame["evidence_order"]
        != frame["dimension_evidence_order"]
    )
    if model_order_mismatch.any() or evidence_order_mismatch.any():
        raise ValueError(
            "Metric ordering metadata does not match dimension tables."
        )

    frame["is_primary_analysis_row"] = frame[
        PRIMARY_METRIC
    ].notna()
    frame["is_usable_analysis_row"] = frame["usable"].astype(bool)
    complete_case_ids = (
        frame.groupby("case_id", sort=False)["usable"]
        .all()
        .loc[lambda values: values]
        .index
    )
    frame["is_complete_case"] = frame["case_id"].isin(
        complete_case_ids
    )
    frame["has_resolved_metric"] = frame[
        "resolved_faithfulness"
    ].notna()
    frame["has_verifiability_metric"] = frame[
        "verifiability"
    ].notna()
    frame["has_conservative_metric"] = frame[
        "conservative_faithfulness"
    ].notna()

    frame.insert(
        0,
        "statistical_analysis_version",
        STATISTICAL_ANALYSIS_VERSION,
    )

    frame = frame.sort_values(
        [
            "model_order",
            "evidence_order",
            "case_order",
            "generation_id",
        ],
        kind="stable",
    ).reset_index(drop=True)

    return frame[ANALYSIS_FRAME_COLUMNS].copy()
