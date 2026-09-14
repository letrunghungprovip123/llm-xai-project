"""Pure Plotly figure factories for Page 5 — Robustness & Template Baseline."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ..settings import (
    BASELINE_OPTION_METRIC_COLUMNS,
    DEFAULT_TEMPLATE_SCOPE,
    EXPECTED_EVIDENCE_ORDER,
    EXPECTED_MODEL_ORDER,
    LLM_OPTION_METRIC_COLUMNS,
    ROBUSTNESS_METRIC_LABELS,
    TEMPLATE_METRIC_LABELS,
    VALIDATOR_METRIC_COLUMNS,
    VISUALIZATION_RELEASE_ID,
)
from ..theme import MODEL_COLORS, TEMPLATE_REFERENCE_COLOR
from .common import (
    GRID_COLOR,
    MUTED_TEXT_COLOR,
    apply_research_layout,
    figure_metadata,
)


FIG_ROBUSTNESS_MEASUREMENT_SHIFT = "FIG_ROBUSTNESS_MEASUREMENT_SHIFT"
FIG_ROBUSTNESS_MEASUREMENT_DELTA = "FIG_ROBUSTNESS_MEASUREMENT_DELTA"
FIG_ROBUSTNESS_TEMPLATE_PROGRESSION = "FIG_ROBUSTNESS_TEMPLATE_PROGRESSION"
FIG_ROBUSTNESS_TEMPLATE_UPLIFT = "FIG_ROBUSTNESS_TEMPLATE_UPLIFT"
FIG_ROBUSTNESS_TEMPLATE_DELTA = "FIG_ROBUSTNESS_TEMPLATE_DELTA"
FIG_ROBUSTNESS_TEMPLATE_COVERAGE = "FIG_ROBUSTNESS_TEMPLATE_COVERAGE"


_RATE_METRICS = {
    "end_to_end_faithfulness_yield",
    "conservative_faithfulness",
    "verifiability",
    "resolved_faithfulness",
}


def _metric_tickformat(metric_id: str) -> str | None:
    return ".0%" if metric_id in _RATE_METRICS else None


def _metric_value(value: object, metric_id: str) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    number = float(value)
    if metric_id in _RATE_METRICS:
        return f"{number:.1%}"
    if metric_id == "output_word_count":
        return f"{number:,.0f}"
    return f"{number:.2f}"


def _delta_value(value: object, metric_id: str) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    number = float(value)
    sign = "+" if number >= 0 else "−"
    magnitude = abs(number)
    if metric_id in _RATE_METRICS:
        return f"{sign}{magnitude * 100:.1f} pp"
    if metric_id == "output_word_count":
        return f"{sign}{magnitude:,.0f} words"
    return f"{sign}{magnitude:.2f}"


def build_candidate_v4_dumbbell(
    summary: pd.DataFrame,
    *,
    metric_id: str,
    focused_option_id: str | None = None,
) -> go.Figure:
    """Compare Candidate and V4 values without implying either is ground truth."""

    if metric_id not in ROBUSTNESS_METRIC_LABELS:
        raise ValueError(f"Unsupported measurement metric: {metric_id}")
    required = {
        "model_id",
        "model_label",
        "model_order",
        "evidence_level",
        "evidence_order",
        "generation_count",
        "candidate_mean",
        "v4_mean",
        "mean_delta_v4_minus_candidate",
    }
    missing = required - set(summary.columns)
    if missing:
        raise ValueError(f"Measurement shift summary missing columns: {sorted(missing)}")

    frame = summary.sort_values(
        ["model_order", "evidence_order"], ascending=[False, False]
    ).copy()
    frame["option_id"] = frame["model_id"] + "__" + frame["evidence_level"]
    frame["row_label"] = frame["model_label"] + " · " + frame["evidence_level"]
    frame["absolute_delta"] = frame["mean_delta_v4_minus_candidate"].abs()
    annotated = set(frame.nlargest(min(3, len(frame)), "absolute_delta")["option_id"])
    if focused_option_id:
        annotated.add(focused_option_id)

    line_x: list[float | None] = []
    line_y: list[str | None] = []
    for row in frame.itertuples(index=False):
        line_x.extend([float(row.candidate_mean), float(row.v4_mean), None])
        line_y.extend([row.row_label, row.row_label, None])

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=line_x,
            y=line_y,
            mode="lines",
            line={"color": "rgba(102,112,133,0.42)", "width": 2},
            hoverinfo="skip",
            showlegend=False,
        )
    )

    visible_models = [
        model_id
        for model_id in EXPECTED_MODEL_ORDER
        if (frame["model_id"] == model_id).any()
    ]
    if not visible_models:
        raise ValueError("Measurement shift summary has no visible models")

    for model_id in visible_models:
        group = frame.loc[frame["model_id"] == model_id].copy()
        custom = np.column_stack(
            [
                group["model_id"],
                group["model_label"],
                group["evidence_level"],
                group["candidate_mean"],
                group["v4_mean"],
                group["mean_delta_v4_minus_candidate"],
                group["generation_count"],
            ]
        )
        figure.add_trace(
            go.Scatter(
                x=group["candidate_mean"],
                y=group["row_label"],
                mode="markers",
                name=f"{group.iloc[0]['model_label']} · Candidate",
                legendgroup=model_id,
                marker={
                    "symbol": "circle",
                    "size": 10,
                    "color": MODEL_COLORS[model_id],
                    "line": {"color": "#FFFFFF", "width": 1},
                },
                customdata=custom,
                hovertemplate=(
                    "<b>%{customdata[1]} · %{customdata[2]}</b><br>"
                    "Candidate: %{customdata[3]:.1%}<br>"
                    "V4 sensitivity: %{customdata[4]:.1%}<br>"
                    "V4 − Candidate: %{customdata[5]:+.1%}<br>"
                    "Paired generations: %{customdata[6]:.0f}<extra></extra>"
                ),
            )
        )
        text = [
            _delta_value(delta, metric_id) if option_id in annotated else ""
            for delta, option_id in zip(
                group["mean_delta_v4_minus_candidate"],
                group["option_id"],
                strict=False,
            )
        ]
        figure.add_trace(
            go.Scatter(
                x=group["v4_mean"],
                y=group["row_label"],
                mode="markers+text",
                name=f"{group.iloc[0]['model_label']} · V4",
                legendgroup=model_id,
                showlegend=False,
                text=text,
                textposition="middle right",
                textfont={"size": 10, "color": MUTED_TEXT_COLOR},
                cliponaxis=False,
                marker={
                    "symbol": "circle-open",
                    "size": 12,
                    "color": MODEL_COLORS[model_id],
                    "line": {"color": MODEL_COLORS[model_id], "width": 2},
                },
                customdata=custom,
                hovertemplate=(
                    "<b>%{customdata[1]} · %{customdata[2]}</b><br>"
                    "Candidate: %{customdata[3]:.1%}<br>"
                    "V4 sensitivity: %{customdata[4]:.1%}<br>"
                    "V4 − Candidate: %{customdata[5]:+.1%}<br>"
                    "Paired generations: %{customdata[6]:.0f}<extra></extra>"
                ),
            )
        )

    figure.update_xaxes(
        title=ROBUSTNESS_METRIC_LABELS[metric_id],
        range=[0, 1.035],
        tickformat=_metric_tickformat(metric_id),
        gridcolor=GRID_COLOR,
        zeroline=False,
    )
    figure.update_yaxes(title=None, gridcolor="rgba(0,0,0,0)", automargin=True)
    figure.update_layout(
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.01,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 10},
        }
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_ROBUSTNESS_MEASUREMENT_SHIFT,
            source="validator_metric_summary.csv",
            metric=metric_id,
            denominator="36 paired generations per model–evidence option",
            release=VISUALIZATION_RELEASE_ID,
            grain="model × evidence condition",
            extra={
                "candidate_role": "primary",
                "v4_role": "sensitivity_only",
            },
        ),
        height=max(390, 34 * len(frame) + 110),
        margin={"l": 218, "r": 74, "t": 48, "b": 62},
        show_legend=True,
    )


def _delta_distribution(
    cases: pd.DataFrame,
    *,
    metric_id: str,
    figure_id: str,
    source: str,
    axis_title: str,
    point_label: str,
    marker_color: str,
    reference_a_label: str,
    reference_b_label: str,
    delta_label: str,
) -> go.Figure:
    required = {"case_id", "delta_value"}
    missing = required - set(cases.columns)
    if missing:
        raise ValueError(f"Paired delta data missing columns: {sorted(missing)}")
    planned_count = len(cases)
    frame = cases.dropna(subset=["delta_value"]).copy()
    observed_count = len(frame)
    if frame.empty:
        raise ValueError("Paired delta distribution has no observed values")
    reference_a = frame.get("candidate_value", frame.get("llm_value"))
    reference_b = frame.get("sensitivity_value", frame.get("template_value"))
    hover = np.column_stack(
        [
            frame["case_id"],
            [_metric_value(value, metric_id) for value in reference_a],
            [_metric_value(value, metric_id) for value in reference_b],
            [_delta_value(value, metric_id) for value in frame["delta_value"]],
        ]
    )
    figure = go.Figure(
        go.Box(
            x=frame["delta_value"],
            y=[point_label] * len(frame),
            orientation="h",
            boxpoints="all",
            jitter=0.42,
            pointpos=0,
            marker={"size": 7, "color": marker_color, "opacity": 0.72},
            line={"color": marker_color, "width": 1.6},
            fillcolor="rgba(255,255,255,0)",
            customdata=hover,
            hovertemplate=(
                "<b>Case %{customdata[0]}</b><br>"
                f"{reference_a_label}: %{{customdata[1]}}<br>"
                f"{reference_b_label}: %{{customdata[2]}}<br>"
                f"{delta_label}: %{{customdata[3]}}<extra></extra>"
            ),
            showlegend=False,
        )
    )
    max_abs = max(float(frame["delta_value"].abs().max()), 0.02)
    if metric_id in _RATE_METRICS:
        max_abs = min(max(max_abs * 1.18, 0.08), 1.0)
        axis_range = [-max_abs, max_abs]
    else:
        axis_range = [-max_abs * 1.18, max_abs * 1.18]
    figure.add_vline(x=0, line={"color": "#667085", "dash": "dash", "width": 1.4})
    if observed_count < planned_count:
        figure.add_annotation(
            x=1,
            y=1.12,
            xref="paper",
            yref="paper",
            xanchor="right",
            showarrow=False,
            text=(
                f"{observed_count}/{planned_count} observed paired cases · "
                "missing conditional values preserved"
            ),
            font={"size": 10, "color": MUTED_TEXT_COLOR},
        )
    figure.update_xaxes(
        title=axis_title,
        range=axis_range,
        tickformat=_metric_tickformat(metric_id),
        gridcolor=GRID_COLOR,
        zeroline=False,
    )
    figure.update_yaxes(title=None, showgrid=False)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=figure_id,
            source=source,
            metric=metric_id,
            denominator=(
                f"{observed_count} observed of {planned_count} planned paired canonical cases"
            ),
            release=VISUALIZATION_RELEASE_ID,
            grain="paired canonical case",
        ),
        height=330,
        margin={"l": 42, "r": 28, "t": 22, "b": 66},
        show_legend=False,
    )


def build_candidate_v4_delta_distribution(
    cases: pd.DataFrame,
    *,
    metric_id: str,
    focus_label: str,
) -> go.Figure:
    """Show case-level V4-minus-Candidate variation for one configuration."""

    return _delta_distribution(
        cases,
        metric_id=metric_id,
        figure_id=FIG_ROBUSTNESS_MEASUREMENT_DELTA,
        source="validator_generation_pairs.csv",
        axis_title="V4 minus Candidate",
        point_label=focus_label,
        marker_color="#0F766E",
        reference_a_label="Candidate primary",
        reference_b_label="V4 sensitivity",
        delta_label="V4 − Candidate",
    )


def build_template_evidence_progression(
    llm_options: pd.DataFrame,
    baseline_options: pd.DataFrame,
    *,
    metric_id: str,
) -> go.Figure:
    """Compare three LLM profiles with the deterministic Template reference."""

    if metric_id not in TEMPLATE_METRIC_LABELS:
        raise ValueError(f"Unsupported Template metric: {metric_id}")
    llm_column = LLM_OPTION_METRIC_COLUMNS[metric_id]
    template_column = BASELINE_OPTION_METRIC_COLUMNS[metric_id]
    required_llm = {
        "group_type", "model_id", "evidence_level", "evidence_scope", llm_column,
    }
    required_template = {
        "generator_label", "evidence_level", "evidence_order", template_column,
    }
    if missing := required_llm - set(llm_options.columns):
        raise ValueError(f"LLM option profile missing columns: {sorted(missing)}")
    if missing := required_template - set(baseline_options.columns):
        raise ValueError(f"Template option profile missing columns: {sorted(missing)}")

    llm_frame = llm_options.loc[llm_options["group_type"] == "model_evidence"].copy()
    llm_frame["model_label"] = llm_frame["model_id"].map(
        {
            "qwen3_8b": "Qwen3 8B",
            "deepseek_v4_flash": "DeepSeek V4 Flash",
            "phi4_mini_instruct": "Phi-4 Mini Instruct",
        }
    )
    llm_frame["evidence_order"] = llm_frame["evidence_level"].map(
        {level: index for index, level in enumerate(EXPECTED_EVIDENCE_ORDER)}
    )
    figure = go.Figure()
    for model_id in EXPECTED_MODEL_ORDER:
        group = llm_frame.loc[llm_frame["model_id"] == model_id].sort_values("evidence_order")
        figure.add_trace(
            go.Scatter(
                x=group["evidence_level"],
                y=group[llm_column],
                mode="lines+markers",
                name=str(group.iloc[0]["model_label"]),
                line={"color": MODEL_COLORS[model_id], "width": 2.4},
                marker={"symbol": "circle", "size": 8},
                customdata=np.column_stack(
                    [
                        group["model_label"],
                        group["evidence_level"],
                        [_metric_value(value, metric_id) for value in group[llm_column]],
                    ]
                ),
                hovertemplate=(
                    "<b>%{customdata[0]} · %{customdata[1]}</b><br>"
                    f"{TEMPLATE_METRIC_LABELS[metric_id]}: %{{customdata[2]}}<extra></extra>"
                ),
            )
        )
    template = baseline_options.sort_values("evidence_order")
    figure.add_trace(
        go.Scatter(
            x=template["evidence_level"],
            y=template[template_column],
            mode="lines+markers",
            name="Deterministic Template Baseline",
            line={"color": TEMPLATE_REFERENCE_COLOR, "width": 2.4, "dash": "dash"},
            marker={"symbol": "diamond", "size": 9, "color": TEMPLATE_REFERENCE_COLOR},
            customdata=np.column_stack(
                [
                    ["template_baseline"] * len(template),
                    template["evidence_level"],
                    [_metric_value(value, metric_id) for value in template[template_column]],
                ]
            ),
            hovertext=[
                (
                    f"<b>Deterministic Template Baseline · {evidence}</b><br>"
                    f"{TEMPLATE_METRIC_LABELS[metric_id]}: {value}<br>"
                    "Decision-ranking eligible: No"
                )
                for evidence, value in zip(
                    template["evidence_level"],
                    [_metric_value(item, metric_id) for item in template[template_column]],
                    strict=False,
                )
            ],
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    figure.update_xaxes(
        title="Categorical evidence condition",
        categoryorder="array",
        categoryarray=list(EXPECTED_EVIDENCE_ORDER),
        gridcolor=GRID_COLOR,
    )
    y_kwargs: dict[str, object] = {
        "title": TEMPLATE_METRIC_LABELS[metric_id],
        "gridcolor": GRID_COLOR,
        "zeroline": False,
    }
    if metric_id in _RATE_METRICS:
        y_kwargs.update({"range": [0, 1.02], "tickformat": ".0%"})
    figure.update_yaxes(**y_kwargs)
    figure.update_layout(
        legend={"orientation": "h", "y": 1.08, "x": 0, "font": {"size": 10}}
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_ROBUSTNESS_TEMPLATE_PROGRESSION,
            source="option_performance.csv + baseline_option_performance.csv",
            metric=metric_id,
            denominator="36 generations per generator–condition profile",
            release=VISUALIZATION_RELEASE_ID,
            grain="generator × evidence condition",
            extra={"template_is_fourth_llm": False},
        ),
        height=455,
        margin={"l": 64, "r": 26, "t": 54, "b": 66},
        show_legend=True,
    )


def build_template_uplift_matrix(
    tests: pd.DataFrame,
    *,
    evidence_scope: str = DEFAULT_TEMPLATE_SCOPE,
) -> go.Figure:
    """Show direction-aware paired deltas across the five planned RQ6 metrics."""

    required = {
        "metric_id", "model_id", "model_label", "model_order",
        "evidence_scope", "mean_delta_llm_minus_template",
        "paired_case_count",
    }
    if missing := required - set(tests.columns):
        raise ValueError(f"Template uplift matrix missing columns: {sorted(missing)}")
    frame = tests.loc[tests["evidence_scope"] == evidence_scope].copy()
    if frame.empty:
        raise ValueError(f"Template uplift matrix has no rows for scope: {evidence_scope}")

    metrics = list(TEMPLATE_METRIC_LABELS)
    matrix = frame.pivot(
        index="model_label",
        columns="metric_id",
        values="mean_delta_llm_minus_template",
    )
    paired_counts = frame.pivot(
        index="model_label",
        columns="metric_id",
        values="paired_case_count",
    )
    ordered_labels = [
        frame.loc[frame["model_id"] == model_id, "model_label"].iloc[0]
        for model_id in EXPECTED_MODEL_ORDER
    ]
    matrix = matrix.reindex(index=ordered_labels, columns=metrics)
    paired_counts = paired_counts.reindex(index=ordered_labels, columns=metrics)
    raw = matrix.to_numpy(dtype=float)
    normalized = np.zeros_like(raw)
    for index, metric_id in enumerate(metrics):
        if metric_id == "output_word_count":
            normalized[:, index] = 0.0
            continue
        column = raw[:, index]
        max_abs = np.nanmax(np.abs(column))
        normalized[:, index] = column / max_abs if max_abs > 0 else 0.0

    text = [
        [_delta_value(raw[row, column], metrics[column]) for column in range(len(metrics))]
        for row in range(len(ordered_labels))
    ]
    customdata = np.empty((len(ordered_labels), len(metrics), 3), dtype=object)
    customdata[:, :, 0] = raw
    customdata[:, :, 1] = paired_counts.to_numpy(dtype=float)
    customdata[:, :, 2] = np.array(
        [metrics] * len(ordered_labels),
        dtype=object,
    )
    hovertext = np.empty((len(ordered_labels), len(metrics)), dtype=object)
    for row_index, model_label in enumerate(ordered_labels):
        for column_index, metric_id in enumerate(metrics):
            hovertext[row_index, column_index] = (
                f"<b>{model_label}</b><br>"
                f"{TEMPLATE_METRIC_LABELS[metric_id]}<br>"
                f"LLM − Template: {raw[row_index, column_index]:+.4f}<br>"
                f"Paired cases: {paired_counts.iloc[row_index, column_index]:.0f}"
            )

    short_tick_labels = {
        "end_to_end_faithfulness_yield": "E2E<br>yield",
        "conservative_faithfulness": "Conservative<br>faithfulness",
        "supported_claim_count": "Supported<br>claims",
        "supported_claims_per_100_words": "Claims /<br>100 words",
        "output_word_count": "Output<br>words",
    }
    figure = go.Figure(
        go.Heatmap(
            z=normalized,
            x=metrics,
            y=ordered_labels,
            zmin=-1,
            zmax=1,
            zmid=0,
            colorscale=[
                [0.0, "#F59E0B"],
                [0.5, "#F2F4F7"],
                [1.0, "#0F766E"],
            ],
            showscale=False,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 10},
            customdata=customdata,
            hovertext=hovertext,
            hovertemplate="%{hovertext}<extra></extra>",
            xgap=3,
            ygap=3,
        )
    )
    figure.update_xaxes(
        side="top",
        tickmode="array",
        tickvals=metrics,
        ticktext=[short_tick_labels[item] for item in metrics],
        tickangle=0,
        tickfont={"size": 10},
        automargin=True,
    )
    figure.update_yaxes(autorange="reversed", automargin=True)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_ROBUSTNESS_TEMPLATE_UPLIFT,
            source="llm_vs_template_tests.csv",
            metric="five planned RQ6 paired metrics",
            denominator="36 paired canonical cases per model and scope",
            release=VISUALIZATION_RELEASE_ID,
            grain="model × metric",
            extra={
                "evidence_scope": evidence_scope,
                "output_word_count_direction": "descriptive_only",
            },
        ),
        height=340,
        margin={"l": 170, "r": 18, "t": 82, "b": 22},
        show_legend=False,
    )


def build_template_delta_distribution(
    cases: pd.DataFrame,
    *,
    metric_id: str,
    focus_label: str,
) -> go.Figure:
    """Show one case-paired LLM-minus-Template distribution."""

    return _delta_distribution(
        cases,
        metric_id=metric_id,
        figure_id=FIG_ROBUSTNESS_TEMPLATE_DELTA,
        source="llm_vs_template_case_pairs.csv",
        axis_title="LLM minus Template",
        point_label=focus_label,
        marker_color="#2563EB",
        reference_a_label="LLM narrative",
        reference_b_label="Deterministic Template",
        delta_label="LLM − Template",
    )


def build_template_coverage_scatter(
    llm_options: pd.DataFrame,
    baseline_options: pd.DataFrame,
) -> go.Figure:
    """Compare supported informational coverage with operational faithfulness."""

    required_llm = {
        "group_type", "model_id", "evidence_level",
        "llm_mean_end_to_end_yield", "llm_mean_supported_count",
    }
    required_template = {
        "generator_label", "evidence_level", "mean_end_to_end_yield",
        "mean_supported_claim_count",
    }
    if missing := required_llm - set(llm_options.columns):
        raise ValueError(f"LLM coverage data missing columns: {sorted(missing)}")
    if missing := required_template - set(baseline_options.columns):
        raise ValueError(f"Template coverage data missing columns: {sorted(missing)}")
    llm_frame = llm_options.loc[llm_options["group_type"] == "model_evidence"].copy()
    llm_frame["model_label"] = llm_frame["model_id"].map(
        {
            "qwen3_8b": "Qwen3 8B",
            "deepseek_v4_flash": "DeepSeek V4 Flash",
            "phi4_mini_instruct": "Phi-4 Mini Instruct",
        }
    )
    figure = go.Figure()
    for model_id in EXPECTED_MODEL_ORDER:
        group = llm_frame.loc[llm_frame["model_id"] == model_id]
        figure.add_trace(
            go.Scatter(
                x=group["llm_mean_end_to_end_yield"],
                y=group["llm_mean_supported_count"],
                mode="markers",
                name=str(group.iloc[0]["model_label"]),
                marker={"size": 10, "color": MODEL_COLORS[model_id], "symbol": "circle"},
                customdata=np.column_stack([group["model_label"], group["evidence_level"]]),
                hovertemplate=(
                    "<b>%{customdata[0]} · %{customdata[1]}</b><br>"
                    "Mean E2E: %{x:.1%}<br>"
                    "Supported claims / generation: %{y:.2f}<extra></extra>"
                ),
            )
        )
    template = baseline_options.copy()
    figure.add_trace(
        go.Scatter(
            x=template["mean_end_to_end_yield"],
            y=template["mean_supported_claim_count"],
            mode="markers",
            name="Deterministic Template Baseline",
            marker={"size": 11, "color": TEMPLATE_REFERENCE_COLOR, "symbol": "diamond"},
            customdata=np.column_stack(
                [["template_baseline"] * len(template), template["evidence_level"]]
            ),
            hovertext=[
                (
                    f"<b>Deterministic Template Baseline · {row.evidence_level}</b><br>"
                    f"Mean E2E: {float(row.mean_end_to_end_yield):.1%}<br>"
                    "Supported claims / generation: "
                    f"{float(row.mean_supported_claim_count):.2f}"
                )
                for row in template.itertuples()
            ],
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    figure.update_xaxes(
        title="Mean end-to-end yield",
        range=[0, 1.02],
        tickformat=".0%",
        gridcolor=GRID_COLOR,
        zeroline=False,
    )
    figure.update_yaxes(
        title="Supported claims per generation",
        rangemode="tozero",
        gridcolor=GRID_COLOR,
        zeroline=False,
    )
    figure.update_layout(legend={"orientation": "h", "y": 1.08, "x": 0, "font": {"size": 10}})
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_ROBUSTNESS_TEMPLATE_COVERAGE,
            source="option_performance.csv + baseline_option_performance.csv",
            metric="mean E2E × mean supported claim count",
            denominator="18 LLM options + 6 Template conditions",
            release=VISUALIZATION_RELEASE_ID,
            grain="generator × evidence condition",
        ),
        height=420,
        margin={"l": 72, "r": 24, "t": 54, "b": 66},
        show_legend=True,
    )
