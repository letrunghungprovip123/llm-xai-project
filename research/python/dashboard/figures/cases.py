"""Pure Plotly figure factories for Page 6 — Case Explorer."""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ..settings import (
    CASE_MATRIX_METRIC_LABELS,
    CASE_OUTCOME_LABELS,
    CASE_RATE_METRICS,
    CASE_STRATUM_LABELS,
    CASE_STRATUM_ORDER,
    CASE_VALIDATOR_METRICS,
    EXPECTED_EVIDENCE_ORDER,
    EXPECTED_MODEL_ORDER,
    ROBUSTNESS_METRIC_LABELS,
    ROBUSTNESS_MODEL_LABELS,
    VISUALIZATION_RELEASE_ID,
)
from ..theme import MODEL_COLORS, TEMPLATE_REFERENCE_COLOR
from .common import apply_research_layout, figure_metadata


FIG_CASES_COHORT = "FIG-CASES-01"
FIG_CASES_MATRIX = "FIG-CASES-02"
FIG_CASES_UTILIZATION = "FIG-CASES-03"
FIG_CASES_CLAIM_COMPOSITION = "FIG-CASES-04"
FIG_CASES_VALIDATOR_SENSITIVITY = "FIG-CASES-05"

_OUTCOME_COLORS = {
    "TP": "#0F766E",
    "TN": "#2563EB",
    "FP": "#B7791F",
    "FN": "#B42318",
}
_CLAIM_COLORS = {
    "Supported": "#0F766E",
    "Not verifiable": "#D97706",
    "Unsupported": "#EA580C",
    "Contradicted": "#B42318",
    "Not applicable": "#98A2B3",
}
_RATE_COLORSCALE = [
    [0.0, "#F2F4F7"],
    [0.45, "#99D5CF"],
    [1.0, "#0F766E"],
]
_COUNT_COLORSCALE = [
    [0.0, "#F2F4F7"],
    [0.5, "#B8C4D6"],
    [1.0, "#475467"],
]


def _optional_float(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(parsed) if pd.notna(parsed) else None


def _format_metric(value: float | None, metric_id: str) -> str:
    if value is None or not math.isfinite(value):
        return "N/A"
    if metric_id in CASE_RATE_METRICS:
        return f"{value:.1%}"
    if metric_id == "output_word_count":
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def build_cohort_landscape(
    catalog: pd.DataFrame,
    *,
    selected_case_id: int | None = None,
) -> go.Figure:
    """Plot the filtered canonical cohort without ranking cases by performance."""

    frame = catalog.copy()
    required = {
        "case_id", "selection_stratum", "prediction_outcome",
        "prediction_probability", "distance_from_threshold",
        "complete_llm_case", "unusable_slot_count", "selection_rank",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Cohort landscape missing columns: {missing}")

    stratum_position = {value: index for index, value in enumerate(CASE_STRATUM_ORDER)}
    frame["stratum_position"] = frame["selection_stratum"].map(stratum_position)
    frame["within_stratum_rank"] = frame.groupby("selection_stratum")["selection_rank"].rank(
        method="first"
    )
    frame["stratum_count"] = frame.groupby("selection_stratum")["case_id"].transform("count")
    frame["jitter"] = np.where(
        frame["stratum_count"] > 1,
        (frame["within_stratum_rank"] - 1) / (frame["stratum_count"] - 1) * 0.32 - 0.16,
        0.0,
    )
    frame["plot_y"] = frame["stratum_position"] + frame["jitter"]

    figure = go.Figure()
    for outcome in ("TP", "TN", "FP", "FN"):
        group = frame.loc[frame["prediction_outcome"] == outcome].copy()
        if group.empty:
            continue
        custom = np.column_stack(
            [
                group["case_id"].astype(int),
                group["selection_stratum"].astype(str),
                group["prediction_outcome"].astype(str),
                group["distance_from_threshold"].astype(float),
                group["complete_llm_case"].astype(bool),
                group["unusable_slot_count"].astype(int),
            ]
        )
        figure.add_trace(
            go.Scatter(
                x=group["prediction_probability"].astype(float),
                y=group["plot_y"].astype(float),
                mode="markers",
                name=CASE_OUTCOME_LABELS[outcome],
                marker={
                    "size": 11,
                    "color": _OUTCOME_COLORS[outcome],
                    "line": {
                        "color": [
                            "#7F1D1D" if count > 0 else "#FFFFFF"
                            for count in group["unusable_slot_count"]
                        ],
                        "width": [2.2 if count > 0 else 1.0 for count in group["unusable_slot_count"]],
                    },
                },
                customdata=custom,
                hovertext=[
                    (
                        f"Canonical case {int(row.case_id)}<br>"
                        f"Stratum: {CASE_STRATUM_LABELS[str(row.selection_stratum)]}<br>"
                        f"Outcome: {CASE_OUTCOME_LABELS[str(row.prediction_outcome)]}<br>"
                        f"Prediction probability: {float(row.prediction_probability):.2%}<br>"
                        f"Distance from threshold: {float(row.distance_from_threshold):.2%}<br>"
                        f"Complete 18-condition matrix: "
                        f"{'Yes' if bool(row.complete_llm_case) else 'No'}<br>"
                        f"Unusable LLM slots: {int(row.unusable_slot_count)}"
                    )
                    for row in group.itertuples()
                ],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )

    if selected_case_id is not None:
        selected = frame.loc[frame["case_id"] == int(selected_case_id)]
        if len(selected) == 1:
            row = selected.iloc[0]
            figure.add_trace(
                go.Scatter(
                    x=[float(row["prediction_probability"])],
                    y=[float(row["plot_y"])],
                    mode="markers",
                    name="Selected case",
                    marker={
                        "size": 18,
                        "color": "rgba(0,0,0,0)",
                        "line": {"color": "#101828", "width": 3},
                        "symbol": "circle-open",
                    },
                    customdata=[[int(row["case_id"])]],
                    hovertemplate="Selected canonical case %{customdata[0]}<extra></extra>",
                )
            )

    figure.add_vline(
        x=0.5,
        line_dash="dash",
        line_color="#667085",
        line_width=1.4,
        annotation_text="Decision threshold · 0.50",
        annotation_position="top",
        annotation_font={"size": 10, "color": "#475467"},
    )
    figure.update_xaxes(
        range=[0, 1],
        tickformat=".0%",
        title_text="Prediction probability",
        gridcolor="rgba(102,112,133,0.14)",
        fixedrange=True,
        automargin=True,
    )
    figure.update_yaxes(
        tickmode="array",
        tickvals=list(range(len(CASE_STRATUM_ORDER))),
        ticktext=[CASE_STRATUM_LABELS[value] for value in CASE_STRATUM_ORDER],
        range=[len(CASE_STRATUM_ORDER) - 0.55, -0.55],
        title_text="Selection stratum",
        fixedrange=True,
        automargin=True,
        gridcolor="rgba(102,112,133,0.10)",
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_CASES_COHORT,
            source="case_heterogeneity_summary.csv",
            metric="prediction probability and frozen selection stratum",
            denominator=f"{len(frame)} filtered canonical cases",
            release=VISUALIZATION_RELEASE_ID,
            grain="canonical case",
            extra={"selection_rule": "stable cohort order, not performance extremity"},
        ),
        height=430,
        margin={"l": 142, "r": 24, "t": 48, "b": 62},
        show_legend=True,
    )


def build_case_performance_matrix(
    matrix: pd.DataFrame,
    *,
    metric_id: str,
    focused_model_id: str,
    focused_evidence_level: str,
) -> go.Figure:
    """Render all 18 LLM and six Template slots for one canonical case."""

    if metric_id not in CASE_MATRIX_METRIC_LABELS:
        raise ValueError(f"Unsupported matrix metric: {metric_id}")
    frame = matrix.copy()
    row_ids = [*EXPECTED_MODEL_ORDER, "template_baseline"]
    row_labels = [
        *[ROBUSTNESS_MODEL_LABELS[value] for value in EXPECTED_MODEL_ORDER],
        "Deterministic Template",
    ]
    x_positions = list(range(len(EXPECTED_EVIDENCE_ORDER)))
    y_positions = list(range(len(row_ids)))

    z = np.full((len(row_ids), len(EXPECTED_EVIDENCE_ORDER)), np.nan, dtype=float)
    text = np.full(z.shape, "", dtype=object)
    hover = np.full(z.shape, "", dtype=object)
    custom = np.empty(z.shape + (7,), dtype=object)
    for y, generator_id in enumerate(row_ids):
        for x, evidence_level in enumerate(EXPECTED_EVIDENCE_ORDER):
            selected = frame.loc[
                (frame["generator_id"] == generator_id)
                & (frame["evidence_level"] == evidence_level)
            ]
            if len(selected) != 1:
                raise ValueError(
                    f"Matrix cell is not unique: {generator_id} × {evidence_level}"
                )
            row = selected.iloc[0]
            value = _optional_float(row["metric_value"])
            z[y, x] = np.nan if value is None else value
            label = _format_metric(value, metric_id)
            if bool(row["is_unusable"]) and metric_id == "end_to_end_faithfulness_yield":
                label = "0%<br>failure"
            text[y, x] = label
            family_label = (
                "Deterministic reference"
                if str(row["generator_family"]) == "TEMPLATE"
                else "LLM"
            )
            runtime_label = (
                "Success" if str(row["runtime_status"]) == "SUCCESS"
                else str(row["runtime_status"])
            )
            hover[y, x] = (
                f"{row['generator_label']} · {evidence_level}<br>"
                f"Generator family: {family_label}<br>"
                f"{CASE_MATRIX_METRIC_LABELS[metric_id]}: {label}<br>"
                f"Usable: {'Yes' if bool(row['usable']) else 'No'}<br>"
                f"Runtime status: {runtime_label}"
            )
            custom[y, x] = [
                str(row["generator_label"]),
                str(row["generator_family"]),
                str(row["generator_id"]),
                str(evidence_level),
                bool(row["usable"]),
                str(row["runtime_status"]),
                None if value is None else float(value),
            ]

    finite = z[np.isfinite(z)]
    if metric_id in CASE_RATE_METRICS:
        zmin, zmax, colorscale = 0.0, 1.0, _RATE_COLORSCALE
    else:
        zmin = 0.0
        zmax = float(finite.max()) if finite.size else 1.0
        if zmax <= 0:
            zmax = 1.0
        colorscale = _COUNT_COLORSCALE

    figure = go.Figure(
        go.Heatmap(
            x=x_positions,
            y=y_positions,
            z=z,
            zmin=zmin,
            zmax=zmax,
            colorscale=colorscale,
            showscale=False,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 11},
            customdata=custom,
            hovertext=hover,
            hovertemplate="%{hovertext}<extra></extra>",
            xgap=4,
            ygap=4,
        )
    )
    figure.add_hline(y=2.5, line_color="#98A2B3", line_width=1.4)
    if focused_model_id in EXPECTED_MODEL_ORDER:
        focus_y = row_ids.index(focused_model_id)
        focus_x = EXPECTED_EVIDENCE_ORDER.index(focused_evidence_level)
        figure.add_shape(
            type="rect",
            x0=focus_x - 0.48,
            x1=focus_x + 0.48,
            y0=focus_y - 0.48,
            y1=focus_y + 0.48,
            line={"color": "#101828", "width": 3},
            fillcolor="rgba(0,0,0,0)",
            layer="above",
        )
    figure.update_xaxes(
        tickmode="array",
        tickvals=x_positions,
        ticktext=EXPECTED_EVIDENCE_ORDER,
        side="top",
        title_text="Categorical evidence condition",
        fixedrange=True,
        automargin=True,
    )
    figure.update_yaxes(
        tickmode="array",
        tickvals=y_positions,
        ticktext=row_labels,
        range=[3.55, -0.55],
        fixedrange=True,
        automargin=True,
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_CASES_MATRIX,
            source="case_heterogeneity_summary.csv",
            metric=CASE_MATRIX_METRIC_LABELS[metric_id],
            denominator="18 LLM plus six deterministic Template slots for one case",
            release=VISUALIZATION_RELEASE_ID,
            grain="generator × evidence condition",
            extra={"template_is_fourth_llm": False, "evidence_is_ordinal": False},
        ),
        height=390,
        margin={"l": 185, "r": 24, "t": 78, "b": 34},
        show_legend=False,
    )


def build_evidence_utilization_profile(
    utilization: pd.Series,
    *,
    model_id: str,
    model_label: str,
    evidence_level: str,
) -> go.Figure:
    """Render defined utilization rates while preserving not-applicable values."""

    metrics = [
        ("Selected features mentioned", "selected_feature_mention_rate"),
        ("Concept evidence mentioned", "concept_mention_rate"),
        ("Top-1 evidence mentioned", "top1_mention_rate"),
        ("Top-3 evidence mentioned", "top3_mention_rate"),
        ("Top-5 evidence mentioned", "top5_mention_rate"),
        ("Supported claims / all claims", "conservative_faithfulness"),
    ]
    labels = [item[0] for item in metrics]
    values = [_optional_float(utilization.get(item[1])) for item in metrics]
    plot_values = [0.0 if value is None else value for value in values]
    defined = [value is not None for value in values]
    text = [f"{value:.0%}" if value is not None else "N/A" for value in values]

    figure = go.Figure(
        go.Bar(
            x=plot_values,
            y=labels,
            orientation="h",
            marker={
                "color": [
                    MODEL_COLORS[model_id] if is_defined else "rgba(152,162,179,0.18)"
                    for is_defined in defined
                ],
                "line": {"color": "rgba(0,0,0,0)", "width": 0},
            },
            text=text,
            textposition="outside",
            cliponaxis=False,
            customdata=np.column_stack(
                [defined, [np.nan if value is None else value for value in values]]
            ),
            hovertext=[
                (
                    f"{label}<br>Observed rate: "
                    f"{value:.0%}<br>Focused LLM: {model_label}<br>"
                    f"Evidence condition: {evidence_level}"
                    if value is not None
                    else (
                        f"{label}<br>Observed rate: N/A<br>"
                        f"Focused LLM: {model_label}<br>"
                        f"Evidence condition: {evidence_level}"
                    )
                )
                for label, value in zip(labels, values)
            ],
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    figure.update_xaxes(
        range=[0, 1.10],
        tickvals=[0, 0.25, 0.5, 0.75, 1.0],
        ticktext=["0%", "25%", "50%", "75%", "100%"],
        gridcolor="rgba(102,112,133,0.14)",
        fixedrange=True,
        automargin=True,
    )
    figure.update_yaxes(autorange="reversed", fixedrange=True, automargin=True)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_CASES_UTILIZATION,
            source="evidence_utilization_summary.csv",
            metric="evidence-utilization rates",
            denominator="one focused LLM generation",
            release=VISUALIZATION_RELEASE_ID,
            grain="generation",
            extra={"interpretation": "descriptive association, not causal mediation"},
        ),
        height=390,
        margin={"l": 200, "r": 52, "t": 24, "b": 48},
        show_legend=False,
    )


def build_claim_composition(validator_pair: pd.Series) -> go.Figure:
    """Render Candidate claim outcomes for one focused generation."""

    labels = [
        "Supported",
        "Not verifiable",
        "Unsupported",
        "Contradicted",
        "Not applicable",
    ]
    columns = [
        "candidate_supported_count",
        "candidate_not_verifiable_count",
        "candidate_unsupported_count",
        "candidate_contradicted_count",
        "candidate_not_applicable_count",
    ]
    counts = [int(validator_pair.get(column, 0) or 0) for column in columns]
    total = int(sum(counts))
    figure = go.Figure()
    if total == 0:
        figure.add_annotation(
            x=0.5,
            y=0.56,
            xref="paper",
            yref="paper",
            text="No conditional claim composition is reported for this unusable generation.",
            showarrow=False,
            align="center",
            font={"size": 13, "color": "#475467"},
        )
        figure.add_annotation(
            x=0.5,
            y=0.40,
            xref="paper",
            yref="paper",
            text="Operational end-to-end yield remains 0 under the frozen policy.",
            showarrow=False,
            align="center",
            font={"size": 11, "color": "#667085"},
        )
    else:
        for label, count in zip(labels, counts):
            if count == 0:
                continue
            share = count / total
            figure.add_trace(
                go.Bar(
                    x=[share],
                    y=["Candidate claim outcomes"],
                    orientation="h",
                    name=label,
                    marker_color=_CLAIM_COLORS[label],
                    text=[f"{label}<br>{count}" if share >= 0.12 else str(count)],
                    textposition="inside",
                    insidetextanchor="middle",
                    customdata=[[count, total]],
                    hovertemplate=(
                        f"{label}: %{{customdata[0]}} / %{{customdata[1]}}"
                        "<extra></extra>"
                    ),
                )
            )
        figure.update_layout(barmode="stack")
    figure.update_xaxes(
        range=[0, 1],
        tickformat=".0%",
        title_text="Share of Candidate claims",
        fixedrange=True,
        gridcolor="rgba(102,112,133,0.12)",
    )
    figure.update_yaxes(fixedrange=True)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_CASES_CLAIM_COMPOSITION,
            source="validator_generation_pairs.csv",
            metric="Candidate claim-status composition",
            denominator=f"{total} Candidate claims for one focused generation",
            release=VISUALIZATION_RELEASE_ID,
            grain="focused generation",
            extra={"measurement_role": "Candidate primary artifact"},
        ),
        height=270,
        margin={"l": 42, "r": 24, "t": 28, "b": 62},
        show_legend=total > 0,
    )


def build_candidate_v4_case_dumbbell(
    validator_pair: pd.Series,
    *,
    model_label: str,
    evidence_level: str,
) -> go.Figure:
    """Compare Candidate and V4 for one focused generation."""

    metric_labels = [ROBUSTNESS_METRIC_LABELS[item] for item in CASE_VALIDATOR_METRICS]
    candidate_values = [
        _optional_float(validator_pair.get(f"candidate_{metric_id}"))
        for metric_id in CASE_VALIDATOR_METRICS
    ]
    v4_values = [
        _optional_float(validator_pair.get(f"v4_{metric_id}"))
        for metric_id in CASE_VALIDATOR_METRICS
    ]
    y = list(range(len(metric_labels)))
    figure = go.Figure()
    for index, (candidate, v4) in enumerate(zip(candidate_values, v4_values)):
        if candidate is None or v4 is None:
            figure.add_annotation(
                x=0.03,
                y=index,
                text="N/A",
                showarrow=False,
                xanchor="left",
                font={"size": 11, "color": "#667085"},
            )
            continue
        figure.add_trace(
            go.Scatter(
                x=[candidate, v4],
                y=[index, index],
                mode="lines",
                line={"color": "#98A2B3", "width": 2},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    figure.add_trace(
        go.Scatter(
            x=[np.nan if value is None else value for value in candidate_values],
            y=y,
            mode="markers",
            name="Candidate · primary",
            marker={"size": 11, "color": "#0F766E", "symbol": "circle"},
            customdata=np.column_stack([CASE_VALIDATOR_METRICS, candidate_values]),
            hovertext=[
                f"{label}<br>Candidate: {value:.1%}" if value is not None else f"{label}<br>Candidate: N/A"
                for label, value in zip(metric_labels, candidate_values)
            ],
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[np.nan if value is None else value for value in v4_values],
            y=y,
            mode="markers",
            name="V4 · sensitivity only",
            marker={
                "size": 12,
                "color": "#FFFFFF",
                "line": {"color": "#0F766E", "width": 2.2},
                "symbol": "circle-open",
            },
            customdata=np.column_stack([CASE_VALIDATOR_METRICS, v4_values]),
            hovertext=[
                f"{label}<br>V4: {value:.1%}" if value is not None else f"{label}<br>V4: N/A"
                for label, value in zip(metric_labels, v4_values)
            ],
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    figure.update_xaxes(
        range=[0, 1.035],
        tickformat=".0%",
        gridcolor="rgba(102,112,133,0.14)",
        title_text="Measured rate",
        fixedrange=True,
    )
    figure.update_yaxes(
        tickmode="array",
        tickvals=y,
        ticktext=metric_labels,
        range=[len(metric_labels) - 0.55, -0.55],
        fixedrange=True,
        automargin=True,
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_CASES_VALIDATOR_SENSITIVITY,
            source="validator_generation_pairs.csv",
            metric="Candidate–V4 generation-level measurement shift",
            denominator="one paired generation",
            release=VISUALIZATION_RELEASE_ID,
            grain="focused generation",
            extra={
                "model": model_label,
                "evidence": evidence_level,
                "candidate_role": "primary",
                "v4_role": "sensitivity_only",
            },
        ),
        height=330,
        margin={"l": 185, "r": 24, "t": 36, "b": 54},
        show_legend=True,
    )
