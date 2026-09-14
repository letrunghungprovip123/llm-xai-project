"""Pure Plotly factories for the Executive Overview page."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ..settings import (
    EXPECTED_EVIDENCE_ORDER,
    EXPECTED_MODEL_ORDER,
    VISUALIZATION_RELEASE_ID,
)
from ..theme import (
    E2E_BAND_LABELS,
    E2E_DISCRETE_COLORSCALE,
    MODEL_COLORS,
)
from .common import apply_research_layout, figure_metadata, format_percent


FIG_OVERVIEW_E2E_HEATMAP = "FIG_OVERVIEW_E2E_HEATMAP"
FIG_OVERVIEW_EVIDENCE_PROFILE = "FIG_OVERVIEW_EVIDENCE_PROFILE"


def _ordered_options(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a defensive, contract-ordered copy of option performance."""

    required = {
        "model_id",
        "model_label",
        "model_order",
        "evidence_level",
        "evidence_label",
        "evidence_order",
        "mean_end_to_end_yield",
        "median_end_to_end_yield",
        "p10_end_to_end_yield",
        "usability_rate",
        "planned_generation_count",
        "usable_generation_count",
        "unusable_generation_count",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Overview figure input is missing columns: {missing}")

    data = frame.copy(deep=True)
    if len(data) != 18:
        raise ValueError(f"Expected 18 LLM options, observed {len(data)}")
    if data["model_id"].astype(str).str.contains("template", case=False).any():
        raise ValueError("Template reference must not appear in LLM overview figures")

    observed_models = tuple(
        data.sort_values("model_order")["model_id"].drop_duplicates()
    )
    observed_evidence = tuple(
        data.sort_values("evidence_order")["evidence_level"].drop_duplicates()
    )
    if observed_models != EXPECTED_MODEL_ORDER:
        raise ValueError(f"Unexpected model order: {observed_models}")
    if observed_evidence != EXPECTED_EVIDENCE_ORDER:
        raise ValueError(f"Unexpected evidence order: {observed_evidence}")

    return data.sort_values(["model_order", "evidence_order"]).reset_index(drop=True)


def build_e2e_option_heatmap(option_performance: pd.DataFrame) -> go.Figure:
    """Build the certified 3 × 6 primary E2E option matrix."""

    data = _ordered_options(option_performance)
    model_rows = (
        data[["model_id", "model_label", "model_order"]]
        .drop_duplicates()
        .sort_values("model_order")
    )
    evidence_columns = (
        data[["evidence_level", "evidence_label", "evidence_order"]]
        .drop_duplicates()
        .sort_values("evidence_order")
    )

    model_ids = model_rows["model_id"].astype(str).tolist()
    model_labels = model_rows["model_label"].astype(str).tolist()
    evidence_levels = evidence_columns["evidence_level"].astype(str).tolist()

    z = np.zeros((len(model_ids), len(evidence_levels)), dtype=float)
    text = np.empty(z.shape, dtype=object)
    customdata = np.empty((*z.shape, 10), dtype=object)

    row_index = {model_id: index for index, model_id in enumerate(model_ids)}
    column_index = {
        evidence: index for index, evidence in enumerate(evidence_levels)
    }

    for row in data.itertuples(index=False):
        model_id = str(row.model_id)
        evidence_level = str(row.evidence_level)
        row_position = row_index[model_id]
        column_position = column_index[evidence_level]
        mean_e2e = float(row.mean_end_to_end_yield)
        unusable = int(row.unusable_generation_count)

        z[row_position, column_position] = mean_e2e
        text[row_position, column_position] = (
            f"{format_percent(mean_e2e)}{'  ⚠' if unusable else ''}"
        )
        customdata[row_position, column_position] = [
            model_id,
            str(row.model_label),
            evidence_level,
            str(row.evidence_label),
            float(row.median_end_to_end_yield),
            float(row.p10_end_to_end_yield),
            float(row.usability_rate),
            int(row.planned_generation_count),
            int(row.usable_generation_count),
            unusable,
        ]

    figure = go.Figure(
        data=[
            go.Heatmap(
                z=z,
                x=evidence_levels,
                y=model_labels,
                zmin=0,
                zmax=1,
                colorscale=E2E_DISCRETE_COLORSCALE,
                                showscale=False,
                xgap=5,
                ygap=5,
                text=text,
                texttemplate="%{text}",
                textfont={"color": "#FFFFFF", "size": 14},
                customdata=customdata,
                hovertemplate=(
                    "<b>%{customdata[1]}</b><br>"
                    "%{customdata[2]} · %{customdata[3]}<br><br>"
                    "Mean E2E: <b>%{z:.1%}</b><br>"
                    "Median E2E: %{customdata[4]:.1%}<br>"
                    "P10 E2E: %{customdata[5]:.1%}<br>"
                    "Usability: %{customdata[6]:.1%}<br>"
                    "Planned: %{customdata[7]} · Usable: %{customdata[8]}"
                    " · Unusable: %{customdata[9]}<br>"
                    "<extra>Certified option performance</extra>"
                ),
                hoverongaps=False,
            )
        ]
    )

    # Compact categorical legend. These annotations communicate bands without
    # introducing a continuous colorbar that implies false precision.
    legend_x = 0.0
    for label, color in E2E_BAND_LABELS:
        figure.add_annotation(
            xref="paper",
            yref="paper",
            x=legend_x,
            y=-0.23,
            text=f"<span style='color:{color}'>■</span> {label}",
            showarrow=False,
            xanchor="left",
            font={"size": 10, "color": "#667085"},
        )
        legend_x += 0.205

    figure.update_xaxes(
        title=None,
        side="top",
        categoryorder="array",
        categoryarray=evidence_levels,
        showgrid=False,
        ticks="",
        tickfont={"size": 12},
        fixedrange=True,
    )
    figure.update_yaxes(
        title=None,
        categoryorder="array",
        categoryarray=model_labels,
        autorange="reversed",
        showgrid=False,
        ticks="",
        tickfont={"size": 12},
        fixedrange=True,
    )

    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_OVERVIEW_E2E_HEATMAP,
            source="option_performance.csv",
            metric="mean_end_to_end_yield",
            denominator="36 canonical cases per model–evidence option",
            release=VISUALIZATION_RELEASE_ID,
            grain="model × evidence condition",
            extra={
                "interaction": "click cell to open Effectiveness page",
                "template_included": False,
            },
        ),
        height=348,
        margin={"l": 118, "r": 10, "t": 28, "b": 36},
        show_legend=False,
    )


def build_evidence_profile(option_performance: pd.DataFrame) -> go.Figure:
    """Build three model profiles across categorical S0–S5 conditions."""

    data = _ordered_options(option_performance)
    figure = go.Figure()

    for model_id in EXPECTED_MODEL_ORDER:
        subset = (
            data.loc[data["model_id"] == model_id]
            .sort_values("evidence_order")
            .reset_index(drop=True)
        )
        label = str(subset.iloc[0]["model_label"])
        customdata = np.column_stack(
            [
                subset["model_id"].astype(str),
                subset["evidence_level"].astype(str),
                subset["evidence_label"].astype(str),
                subset["p10_end_to_end_yield"].astype(float),
                subset["usability_rate"].astype(float),
                subset["planned_generation_count"].astype(int),
                subset["unusable_generation_count"].astype(int),
            ]
        )
        figure.add_trace(
            go.Scatter(
                x=subset["evidence_level"],
                y=subset["mean_end_to_end_yield"].astype(float),
                mode="lines+markers",
                name=label,
                line={"color": MODEL_COLORS[model_id], "width": 2.1},
                marker={
                    "color": MODEL_COLORS[model_id],
                    "size": 7,
                    "line": {"color": "#FFFFFF", "width": 1.0},
                },
                customdata=customdata,
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "%{customdata[1]} · %{customdata[2]}<br><br>"
                    "Mean E2E: <b>%{y:.1%}</b><br>"
                    "P10 E2E: %{customdata[3]:.1%}<br>"
                    "Usability: %{customdata[4]:.1%}<br>"
                    "Planned: %{customdata[5]} · Unusable: %{customdata[6]}<br>"
                    "<extra>Categorical experimental order</extra>"
                ),
            )
        )

    figure.update_xaxes(
        title=None,
        categoryorder="array",
        categoryarray=list(EXPECTED_EVIDENCE_ORDER),
        showgrid=False,
        tickfont={"size": 11},
        fixedrange=True,
    )
    figure.update_yaxes(
        title=None,
        range=[0, 1],
        tickmode="array",
        tickvals=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        ticktext=["0%", "20%", "40%", "60%", "80%", "100%"],
        gridcolor="rgba(102,112,133,0.16)",
        zeroline=False,
        fixedrange=True,
        automargin=True,
    )
    figure.update_layout(
        legend={
            "orientation": "h",
            "x": 0,
            "xanchor": "left",
            "y": 1.06,
            "yanchor": "bottom",
            "font": {"size": 10},
            "itemclick": False,
            "itemdoubleclick": False,
        },
        hovermode="closest",
    )

    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_OVERVIEW_EVIDENCE_PROFILE,
            source="option_performance.csv",
            metric="mean_end_to_end_yield",
            denominator="36 canonical cases per model–evidence option",
            release=VISUALIZATION_RELEASE_ID,
            grain="model × evidence condition",
            extra={
                "x_semantics": "categorical experimental order",
                "template_included": False,
            },
        ),
        height=340,
        margin={"l": 48, "r": 12, "t": 38, "b": 44},
        show_legend=True,
    )
