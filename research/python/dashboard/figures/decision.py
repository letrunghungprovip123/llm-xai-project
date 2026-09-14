"""Pure Plotly factories for Page 4 — Decision Studio."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ..settings import (
    DECISION_CONTRIBUTION_LABELS,
    DECISION_X_AXIS_LABELS,
    VISUALIZATION_RELEASE_ID,
)
from ..theme import MODEL_COLORS
from .common import (
    GRID_COLOR,
    MUTED_TEXT_COLOR,
    apply_research_layout,
    figure_metadata,
)


FIG_DECISION_TRADEOFF_MAP = "FIG_DECISION_TRADEOFF_MAP"
FIG_DECISION_CRITERION_CONTRIBUTIONS = (
    "FIG_DECISION_CRITERION_CONTRIBUTIONS"
)
FIG_DECISION_WHAT_IF_CONTRIBUTION_COMPARISON = (
    "FIG_DECISION_WHAT_IF_CONTRIBUTION_COMPARISON"
)


def _x_axis_title(metric_id: str) -> str:
    label = DECISION_X_AXIS_LABELS[metric_id]
    direction = (
        "Lower is better"
        if metric_id in {
            "mean_latency_seconds_planned",
            "mean_total_token_count_planned",
        }
        else "Higher is better"
    )
    return f"{label} · {direction}"


def _format_optional_rank(value: object) -> str:
    """Format a frozen rank without converting missing values to integers."""

    return "N/A" if pd.isna(value) else str(int(value))


def _format_optional_score(value: object) -> str:
    """Format a frozen utility score while preserving structured missingness."""

    return "N/A" if pd.isna(value) else f"{float(value):.3f}"


def build_tradeoff_map(
    ranking: pd.DataFrame,
    *,
    x_metric: str,
    recommended_option_id: str | None,
    alternative_option_id: str | None = None,
    focused_option_id: str | None = None,
) -> go.Figure:
    """Build a restrained quality–efficiency map for 18 options."""

    if x_metric not in DECISION_X_AXIS_LABELS:
        raise ValueError(f"Unsupported decision X-axis: {x_metric}")
    required = {
        "option_id",
        "model_id",
        "model_label",
        "model_order",
        "evidence_level",
        "evidence_order",
        "mean_end_to_end_yield",
        "p10_end_to_end_yield",
        "usability_rate",
        "mean_latency_seconds_planned",
        "mean_total_token_count_planned",
        "mean_supported_claims_per_1000_tokens",
        "scenario_rank",
        "utility_rank",
        "utility_score",
        "is_pareto_optimal",
        "eligible",
    }
    missing = required - set(ranking.columns)
    if missing:
        raise ValueError(f"Trade-off map is missing columns: {sorted(missing)}")
    if len(ranking) != 18:
        raise ValueError("Trade-off map requires exactly 18 configurations")

    figure = go.Figure()
    ordered = ranking.sort_values(["model_order", "evidence_order"])
    for model_id, group in ordered.groupby("model_id", sort=False):
        for pareto, subset in group.groupby("is_pareto_optimal", sort=False):
            figure.add_trace(
                go.Scatter(
                    x=subset[x_metric],
                    y=subset["mean_end_to_end_yield"],
                    mode="markers",
                    name=(
                        str(subset.iloc[0]["model_label"])
                        if bool(pareto)
                        else f"{subset.iloc[0]['model_label']} · dominated"
                    ),
                    legendgroup=str(model_id),
                    showlegend=bool(pareto),
                    marker={
                        "size": 12 if bool(pareto) else 10,
                        "symbol": "circle" if bool(pareto) else "circle-open",
                        "color": MODEL_COLORS[str(model_id)],
                        "opacity": 0.9 if bool(pareto) else 0.55,
                        "line": {
                            "width": 1.5,
                            "color": MODEL_COLORS[str(model_id)],
                        },
                    },
                    customdata=np.stack(
                        [
                            subset["option_id"],
                            subset["model_label"],
                            subset["evidence_level"],
                            subset["p10_end_to_end_yield"],
                            subset["usability_rate"],
                            subset["mean_latency_seconds_planned"],
                            subset["mean_total_token_count_planned"],
                            subset[
                                "mean_supported_claims_per_1000_tokens"
                            ],
                            subset["scenario_rank"],
                            subset["utility_rank"],
                            subset["utility_score"],
                            subset["is_pareto_optimal"],
                            subset["eligible"],
                        ],
                        axis=-1,
                    ),
                    hovertext=[
                        (
                            f"<b>{row.model_label} · {row.evidence_level}</b><br>"
                            f"{DECISION_X_AXIS_LABELS[x_metric]}: "
                            f"{float(getattr(row, x_metric)):,.2f}<br>"
                            f"Mean E2E: {float(row.mean_end_to_end_yield):.1%}<br>"
                            f"P10 E2E: {float(row.p10_end_to_end_yield):.1%}<br>"
                            f"Usability: {float(row.usability_rate):.1%}<br>"
                            f"Latency: {float(row.mean_latency_seconds_planned):.1f} s<br>"
                            f"Total tokens: {float(row.mean_total_token_count_planned):,.0f}<br>"
                            "Supported claims / 1,000 tokens: "
                            f"{float(row.mean_supported_claims_per_1000_tokens):.2f}<br>"
                            f"Decision rank: {_format_optional_rank(row.scenario_rank)}<br>"
                            f"Utility rank: {_format_optional_rank(row.utility_rank)}<br>"
                            f"Utility: {_format_optional_score(row.utility_score)}<br>"
                            f"Pareto-efficient: {'Yes' if bool(row.is_pareto_optimal) else 'No'}<br>"
                            f"Eligible: {'Yes' if bool(row.eligible) else 'No'}"
                        )
                        for row in subset.itertuples()
                    ],
                    hovertemplate="%{hovertext}<extra></extra>",
                )
            )

    def overlay(
        option_id: str | None,
        *,
        label: str,
        line_width: float,
        color: str,
        showlegend: bool,
    ) -> None:
        if not option_id:
            return
        selected = ordered.loc[ordered["option_id"] == option_id]
        if selected.empty:
            return
        row = selected.iloc[0]
        figure.add_trace(
            go.Scatter(
                x=[row[x_metric]],
                y=[row["mean_end_to_end_yield"]],
                mode="markers",
                name=label,
                marker={
                    "size": 18 if line_width >= 3 else 15,
                    "symbol": "circle-open",
                    "color": color,
                    "line": {"width": line_width, "color": color},
                },
                hoverinfo="skip",
                showlegend=showlegend,
                legendgroup="decision-role",
                legendrank=90 if label == "Recommended" else 91,
            )
        )

    overlay(
        recommended_option_id,
        label="Recommended",
        line_width=3.0,
        color="#101828",
        showlegend=True,
    )
    overlay(
        alternative_option_id,
        label="Alternative",
        line_width=1.8,
        color="#667085",
        showlegend=True,
    )
    if focused_option_id not in {recommended_option_id, alternative_option_id}:
        overlay(
            focused_option_id,
            label="Focused",
            line_width=2.2,
            color="#344054",
            showlegend=False,
        )

    figure.update_xaxes(
        title=_x_axis_title(x_metric),
        gridcolor=GRID_COLOR,
        zeroline=False,
        automargin=True,
    )
    figure.update_yaxes(
        title="Mean E2E operational faithfulness",
        range=[0, 1],
        tickformat=".0%",
        dtick=0.2,
        gridcolor=GRID_COLOR,
        zeroline=False,
        fixedrange=True,
    )
    apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_DECISION_TRADEOFF_MAP,
            source="scenario_options.csv",
            metric=f"mean_end_to_end_yield × {x_metric}",
            denominator="18 certified LLM configurations",
            release=VISUALIZATION_RELEASE_ID,
            grain="scenario × model × evidence condition",
        ),
        height=455,
        margin={"l": 76, "r": 24, "t": 42, "b": 94},
        show_legend=True,
    )
    figure.update_layout(
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.08,
            "font": {"size": 10},
            "title": None,
        },
        hovermode="closest",
    )
    return figure


def build_criterion_contribution_profile(
    profile: pd.DataFrame,
) -> go.Figure:
    """Explain certified utility for one option under one scenario."""

    required = {
        "criterion_label",
        "criterion_order",
        "direction",
        "weight",
        "raw_value",
        "normalized_value",
        "weighted_contribution",
        "criterion_display_value",
    }
    missing = required - set(profile.columns)
    if missing:
        raise ValueError(
            f"Contribution profile is missing columns: {sorted(missing)}"
        )
    ordered = profile.sort_values("criterion_order", ascending=False).copy()
    ordered["display_label"] = ordered["criterion_id"].map(
        DECISION_CONTRIBUTION_LABELS
    ).fillna(ordered["criterion_label"])
    figure = go.Figure(
        go.Bar(
            x=ordered["weighted_contribution"],
            y=ordered["display_label"],
            orientation="h",
            marker={"color": "#0F766E"},
            text=ordered["weighted_contribution"].map(lambda value: f"{value:.3f}"),
            textposition="outside",
            cliponaxis=False,
            customdata=np.stack(
                [
                    ordered["criterion_display_value"],
                    ordered["normalized_value"],
                    ordered["weight"],
                    ordered["direction"],
                ],
                axis=-1,
            ),
            hovertext=[
                (
                    f"<b>{row.display_label}</b><br>"
                    f"Raw value: {row.criterion_display_value}<br>"
                    f"Normalized value: {float(row.normalized_value):.3f}<br>"
                    f"Scenario weight: {float(row.weight):.1%}<br>"
                    f"Contribution: {float(row.weighted_contribution):.3f}<br>"
                    f"Direction: {'Maximize' if str(row.direction) == 'MAX' else 'Minimize'}"
                )
                for row in ordered.itertuples()
            ],
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    figure.update_xaxes(
        title="Weighted contribution",
        rangemode="tozero",
        gridcolor=GRID_COLOR,
        zeroline=True,
        zerolinecolor="#98A2B3",
    )
    figure.update_yaxes(title=None, automargin=True)
    apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_DECISION_CRITERION_CONTRIBUTIONS,
            source="scenario_criterion_contributions.csv",
            metric="normalized criterion value × certified scenario weight",
            denominator="one certified option–scenario profile",
            release=VISUALIZATION_RELEASE_ID,
            grain="criterion",
        ),
        height=max(330, 52 * len(ordered)),
        margin={"l": 210, "r": 72, "t": 18, "b": 58},
        show_legend=False,
    )
    return figure


def build_certified_custom_contribution_comparison(
    certified_profile: pd.DataFrame,
    custom_profile: pd.DataFrame,
) -> go.Figure:
    """Compare certified and custom contributions for one option."""

    certified = certified_profile[
        ["criterion_id", "criterion_label", "criterion_order", "weighted_contribution"]
    ].rename(columns={"weighted_contribution": "certified_contribution"})
    certified["display_label"] = certified["criterion_id"].map(
        DECISION_CONTRIBUTION_LABELS
    ).fillna(certified["criterion_label"])
    custom = custom_profile[
        ["criterion_id", "custom_contribution", "custom_weight"]
    ]
    merged = certified.merge(custom, on="criterion_id", how="left")
    merged = merged.sort_values("criterion_order", ascending=False)

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=merged["certified_contribution"],
            y=merged["display_label"],
            orientation="h",
            name="Certified",
            marker={"color": "#98A2B3"},
            hovertemplate="<b>%{y}</b><br>Certified contribution: %{x:.3f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Bar(
            x=merged["custom_contribution"],
            y=merged["display_label"],
            orientation="h",
            name="Custom",
            marker={"color": "#0F766E"},
            customdata=merged["custom_weight"],
            hovertemplate=(
                "<b>%{y}</b><br>Custom contribution: %{x:.3f}<br>"
                "Custom weight: %{customdata:.1%}<extra></extra>"
            ),
        )
    )
    figure.update_layout(barmode="group")
    figure.update_xaxes(
        title="Weighted contribution",
        rangemode="tozero",
        gridcolor=GRID_COLOR,
        zeroline=False,
    )
    figure.update_yaxes(title=None, automargin=True)
    apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_DECISION_WHAT_IF_CONTRIBUTION_COMPARISON,
            source="scenario_criterion_contributions.csv + What-if weights",
            metric="certified versus user-specified contribution",
            denominator="one option under two weight vectors",
            release=VISUALIZATION_RELEASE_ID,
            grain="criterion",
        ),
        height=max(350, 54 * len(merged)),
        margin={"l": 210, "r": 32, "t": 24, "b": 58},
        show_legend=True,
    )
    figure.update_layout(
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.06,
            "font": {"size": 10},
        }
    )
    return figure
