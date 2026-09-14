"""Pure Plotly figure factories for Page 2 — Effectiveness & Reliability."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ..theme import E2E_DISCRETE_COLORSCALE, MODEL_COLORS
from .common import apply_research_layout, figure_metadata, format_percent


FIG_EFFECTIVENESS_RELIABILITY_MAP = "FIG_EFFECTIVENESS_RELIABILITY_MAP"
FIG_EFFECTIVENESS_LOSS_DECOMPOSITION = (
    "FIG_EFFECTIVENESS_LOSS_DECOMPOSITION"
)
FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP = (
    "FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP"
)
FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP = (
    "FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP"
)
FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES = (
    "FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES"
)


EFFECT_LABELS: Mapping[str, str] = {
    "model": "Model",
    "evidence": "Evidence condition",
    "model:evidence": "Model × evidence",
}

LOSS_COMPONENTS: tuple[tuple[str, str, str], ...] = (
    ("mean_end_to_end_yield", "E2E success", "#26734D"),
    ("mean_pipeline_loss", "Pipeline loss", "#667085"),
    ("mean_not_verifiable_loss", "Not verifiable", "#D68A16"),
    ("mean_unsupported_loss", "Unsupported", "#C55A2A"),
    ("mean_contradiction_loss", "Contradicted", "#A6382E"),
)


def _ordered_options(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["model_order", "evidence_order"]).reset_index(
        drop=True
    )


def _option_axis_label(row: pd.Series) -> str:
    return f"{row['model_label']} · {row['evidence_level']}"


def _format_p_value(value: float) -> str:
    number = float(value)
    if number < 0.0001:
        return "<0.0001"
    return f"{number:.4f}"


def build_reliability_map(
    option_performance: pd.DataFrame,
    *,
    focused_option_id: str | None = None,
) -> go.Figure:
    """Compare average E2E with P10 lower-tail E2E for all 18 options."""

    ordered = _ordered_options(option_performance)
    figure = go.Figure()

    for model_id, group in ordered.groupby("model_id", sort=False):
        group = group.sort_values("evidence_order")
        symbols = [
            "triangle-up" if int(value) > 0 else "circle"
            for value in group["unusable_generation_count"]
        ]
        customdata = np.column_stack(
            [
                group["option_id"],
                group["model_id"],
                group["model_label"],
                group["evidence_level"],
                group["median_end_to_end_yield"],
                group["usability_rate"],
                group["planned_generation_count"],
                group["usable_generation_count"],
                group["unusable_generation_count"],
                group["mean_pipeline_loss"],
            ]
        )
        figure.add_trace(
            go.Scatter(
                x=group["mean_end_to_end_yield"],
                y=group["p10_end_to_end_yield"],
                mode="markers+text",
                name=str(group.iloc[0]["model_label"]),
                text=group["evidence_level"],
                textposition="top center",
                textfont={"size": 10, "color": MODEL_COLORS[str(model_id)]},
                marker={
                    "size": 11,
                    "symbol": symbols,
                    "color": MODEL_COLORS[str(model_id)],
                    "line": {"color": "#FFFFFF", "width": 1.2},
                },
                customdata=customdata,
                hovertemplate=(
                    "<b>%{customdata[2]} · %{customdata[3]}</b><br>"
                    "Mean E2E: %{x:.1%}<br>"
                    "P10 E2E: %{y:.1%}<br>"
                    "Median E2E: %{customdata[4]:.1%}<br>"
                    "Usability: %{customdata[5]:.1%}<br>"
                    "Planned / usable: %{customdata[6]} / %{customdata[7]}<br>"
                    "Unusable: %{customdata[8]}<br>"
                    "Pipeline loss: %{customdata[9]:.1%}"
                    "<extra></extra>"
                ),
            )
        )

    if focused_option_id:
        focus = ordered.loc[ordered["option_id"] == focused_option_id]
        if len(focus) == 1:
            row = focus.iloc[0]
            figure.add_trace(
                go.Scatter(
                    x=[row["mean_end_to_end_yield"]],
                    y=[row["p10_end_to_end_yield"]],
                    mode="markers",
                    marker={
                        "size": 20,
                        "symbol": "circle-open",
                        "color": MODEL_COLORS[str(row["model_id"])],
                        "line": {
                            "color": MODEL_COLORS[str(row["model_id"])],
                            "width": 3,
                        },
                    },
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

    figure.add_vline(x=0.90, line_width=1, line_dash="dot", line_color="#98A2B3")
    figure.add_hline(y=0.90, line_width=1, line_dash="dot", line_color="#98A2B3")
    figure.add_annotation(
        x=0.985,
        y=0.985,
        text="High average · strong lower tail",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        font={"size": 10, "color": "#667085"},
    )

    figure.update_xaxes(
        title="Mean E2E operational faithfulness",
        range=[0, 1.02],
        tickmode="array",
        tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
        ticktext=["0%", "20%", "40%", "60%", "80%", "100%"],
        gridcolor="rgba(102,112,133,0.16)",
        zeroline=False,
        fixedrange=True,
    )
    figure.update_yaxes(
        title="P10 E2E operational faithfulness",
        range=[0, 1.02],
        tickmode="array",
        tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
        ticktext=["0%", "20%", "40%", "60%", "80%", "100%"],
        gridcolor="rgba(102,112,133,0.16)",
        zeroline=False,
        fixedrange=True,
    )
    figure.update_layout(
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.08,
            "xanchor": "left",
            "yanchor": "bottom",
            "font": {"size": 10},
        }
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_EFFECTIVENESS_RELIABILITY_MAP,
            source="option_performance.csv",
            metric="mean_end_to_end_yield × p10_end_to_end_yield",
            denominator="36 canonical cases per model–evidence option",
            release="visualization-data-v2",
            grain="model × evidence condition",
        ),
        height=420,
        margin={"l": 70, "r": 18, "t": 44, "b": 64},
        show_legend=True,
    )


def build_operational_loss_decomposition(
    option_performance: pd.DataFrame,
) -> go.Figure:
    """Render mutually exclusive operational E2E success/loss components."""

    ordered = _ordered_options(option_performance).copy()
    ordered["axis_label"] = ordered.apply(_option_axis_label, axis=1)
    axis_labels = ordered["axis_label"].tolist()[::-1]
    figure = go.Figure()

    for column, label, color in LOSS_COMPONENTS:
        values = ordered[column].astype(float).tolist()[::-1]
        custom = np.column_stack(
            [
                ordered["model_label"].tolist()[::-1],
                ordered["evidence_level"].tolist()[::-1],
                ordered["planned_generation_count"].tolist()[::-1],
            ]
        )
        figure.add_trace(
            go.Bar(
                x=values,
                y=axis_labels,
                orientation="h",
                name=label,
                marker={"color": color},
                customdata=custom,
                hovertemplate=(
                    "<b>%{customdata[0]} · %{customdata[1]}</b><br>"
                    + label
                    + ": %{x:.1%}<br>Planned: %{customdata[2]}"
                    "<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        barmode="stack",
        bargap=0.30,
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.035,
            "xanchor": "left",
            "yanchor": "bottom",
            "font": {"size": 10},
        },
    )
    figure.update_xaxes(
        title=None,
        range=[0, 1],
        tickmode="array",
        tickvals=[0, 0.25, 0.5, 0.75, 1.0],
        ticktext=["0%", "25%", "50%", "75%", "100%"],
        gridcolor="rgba(102,112,133,0.14)",
        fixedrange=True,
    )
    figure.update_yaxes(title=None, fixedrange=True, automargin=True)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_EFFECTIVENESS_LOSS_DECOMPOSITION,
            source="option_performance.csv",
            metric="mutually exclusive operational success/loss components",
            denominator="all planned generations per option",
            release="visualization-data-v2",
            grain="model × evidence condition",
        ),
        height=560,
        margin={"l": 170, "r": 18, "t": 46, "b": 46},
        show_legend=True,
    )


def build_conditional_quality_heatmap(
    conditional_summary: pd.DataFrame,
    *,
    metric_id: str,
    metric_label: str,
) -> go.Figure:
    """Show conditional quality while preserving observed/missing counts."""

    ordered = conditional_summary.sort_values(["model_order", "evidence_order"])
    models = (
        ordered[["model_id", "model_label", "model_order"]]
        .drop_duplicates()
        .sort_values("model_order")
    )
    evidence = (
        ordered[["evidence_level", "evidence_order"]]
        .drop_duplicates()
        .sort_values("evidence_order")
    )
    model_ids = models["model_id"].tolist()
    model_labels = models["model_label"].tolist()
    evidence_levels = evidence["evidence_level"].tolist()

    values: list[list[float]] = []
    annotations: list[list[str]] = []
    custom_rows: list[list[list[object]]] = []
    for model_id in model_ids:
        group = ordered.loc[ordered["model_id"] == model_id].set_index(
            "evidence_level"
        )
        row_values: list[float] = []
        row_text: list[str] = []
        row_custom: list[list[object]] = []
        for level in evidence_levels:
            item = group.loc[level]
            mean = float(item["mean"])
            observed = int(item["observed_count"])
            missing = int(item["missing_count"])
            row_values.append(mean)
            row_text.append(
                f"{format_percent(mean)}<br>n={observed}"
                + (f" · {missing} missing" if missing else "")
            )
            row_custom.append(
                [
                    str(item["model_label"]),
                    level,
                    metric_label,
                    float(item["median"]),
                    observed,
                    missing,
                    int(item["planned_count"]),
                ]
            )
        values.append(row_values)
        annotations.append(row_text)
        custom_rows.append(row_custom)

    figure = go.Figure(
        go.Heatmap(
            z=values,
            x=evidence_levels,
            y=model_labels,
            zmin=0,
            zmax=1,
            colorscale=E2E_DISCRETE_COLORSCALE,
            showscale=False,
            xgap=4,
            ygap=4,
            text=annotations,
            texttemplate="%{text}",
            textfont={"size": 11, "color": "#FFFFFF"},
            customdata=custom_rows,
            hovertemplate=(
                "<b>%{customdata[0]} · %{customdata[1]}</b><br>"
                "%{customdata[2]}: %{z:.1%}<br>"
                "Median: %{customdata[3]:.1%}<br>"
                "Observed / planned: %{customdata[4]} / %{customdata[6]}<br>"
                "Missing: %{customdata[5]}<extra></extra>"
            ),
        )
    )
    figure.update_xaxes(side="top", title=None, fixedrange=True)
    figure.update_yaxes(title=None, autorange="reversed", fixedrange=True)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP,
            source="descriptive_statistics.csv",
            metric=metric_id,
            denominator="usable generations with defined conditional metric",
            release="visualization-data-v2",
            grain="model × evidence condition",
        ),
        height=390,
        margin={"l": 150, "r": 12, "t": 38, "b": 26},
        show_legend=False,
    )


def build_operational_conditional_gap(
    conditional_summary: pd.DataFrame,
    *,
    metric_id: str,
    metric_label: str,
) -> go.Figure:
    """Show the gap between operational E2E and conditional quality."""

    ordered = conditional_summary.sort_values(
        ["model_order", "evidence_order"]
    ).copy()
    ordered["axis_label"] = ordered.apply(_option_axis_label, axis=1)
    ordered = ordered.iloc[::-1].reset_index(drop=True)

    line_x: list[float | None] = []
    line_y: list[str | None] = []
    for _, row in ordered.iterrows():
        line_x.extend(
            [float(row["mean_end_to_end_yield"]), float(row["mean"]), None]
        )
        line_y.extend([row["axis_label"], row["axis_label"], None])

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=line_x,
            y=line_y,
            mode="lines",
            line={"color": "#D0D5DD", "width": 2},
            showlegend=False,
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=ordered["mean_end_to_end_yield"],
            y=ordered["axis_label"],
            mode="markers",
            name="Operational E2E",
            marker={"size": 8, "color": "#475467"},
            customdata=np.column_stack(
                [
                    ordered["model_label"],
                    ordered["evidence_level"],
                    ordered["planned_count"],
                ]
            ),
            hovertemplate=(
                "<b>%{customdata[0]} · %{customdata[1]}</b><br>"
                "Operational E2E: %{x:.1%}<br>"
                "Planned: %{customdata[2]}<extra></extra>"
            ),
        )
    )
    for model_id, group in ordered.groupby("model_id", sort=False):
        figure.add_trace(
            go.Scatter(
                x=group["mean"],
                y=group["axis_label"],
                mode="markers",
                name=f"{group.iloc[0]['model_label']} conditional",
                marker={"size": 9, "color": MODEL_COLORS[str(model_id)]},
                customdata=np.column_stack(
                    [
                        group["model_label"],
                        group["evidence_level"],
                        group["mean_end_to_end_yield"],
                        group["operational_gap"],
                        group["observed_count"],
                        group["missing_count"],
                    ]
                ),
                hovertemplate=(
                    "<b>%{customdata[0]} · %{customdata[1]}</b><br>"
                    + metric_label
                    + ": %{x:.1%}<br>Operational E2E: %{customdata[2]:.1%}<br>"
                    "Gap: %{customdata[3]:+.1%}<br>"
                    "Observed / missing: %{customdata[4]} / %{customdata[5]}"
                    "<extra></extra>"
                ),
            )
        )

    figure.update_xaxes(
        title=None,
        range=[0, 1.02],
        tickmode="array",
        tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
        ticktext=["0%", "20%", "40%", "60%", "80%", "100%"],
        gridcolor="rgba(102,112,133,0.14)",
        fixedrange=True,
    )
    figure.update_yaxes(title=None, fixedrange=True, automargin=True)
    figure.update_layout(
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.035,
            "xanchor": "left",
            "yanchor": "bottom",
            "font": {"size": 9},
        }
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP,
            source="descriptive_statistics.csv + option_performance.csv",
            metric=f"{metric_id} minus operational E2E",
            denominator="planned operational and observed conditional populations",
            release="visualization-data-v2",
            grain="model × evidence condition",
        ),
        height=560,
        margin={"l": 170, "r": 16, "t": 44, "b": 46},
        show_legend=True,
    )


def build_effect_size_chart(omnibus_tests: pd.DataFrame) -> go.Figure:
    """Compare practical magnitude of the three primary effects."""

    ordered_effects = ["model", "evidence", "model:evidence"]
    frame = omnibus_tests.set_index("effect").loc[ordered_effects].reset_index()
    labels = [EFFECT_LABELS[value] for value in frame["effect"]]
    p_labels = [_format_p_value(value) for value in frame["p_value_used"]]
    text = [
        f"ηp²={effect:.3f} · p={p_value}"
        for effect, p_value in zip(frame["partial_eta_squared"], p_labels)
    ]

    figure = go.Figure(
        go.Bar(
            x=frame["partial_eta_squared"],
            y=labels,
            orientation="h",
            marker={"color": "#256B5C"},
            text=text,
            textposition="outside",
            cliponaxis=False,
            customdata=np.column_stack(
                [
                    frame["f_statistic"],
                    frame["p_value_used"],
                    frame["subject_count"],
                    frame["observation_count"],
                ]
            ),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Partial η²: %{x:.3f}<br>"
                "F: %{customdata[0]:.3f}<br>"
                "Corrected p: %{customdata[1]:.4g}<br>"
                "Subjects / observations: %{customdata[2]} / %{customdata[3]}"
                "<extra></extra>"
            ),
        )
    )
    figure.update_xaxes(
        title="Partial eta squared",
        range=[0, 1],
        tickmode="array",
        tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
        gridcolor="rgba(102,112,133,0.14)",
        fixedrange=True,
    )
    figure.update_yaxes(title=None, autorange="reversed", fixedrange=True)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES,
            source="omnibus_tests.csv",
            metric="partial_eta_squared",
            denominator="36 canonical cases; 648 planned observations",
            release="visualization-data-v2",
            grain="primary omnibus effect",
        ),
        height=330,
        margin={"l": 126, "r": 130, "t": 18, "b": 54},
        show_legend=False,
    )
