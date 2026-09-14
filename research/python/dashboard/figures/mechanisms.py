"""Pure Plotly figure factories for Page 3 — RQ3 mechanisms."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..settings import EXPECTED_EVIDENCE_ORDER, EXPECTED_MODEL_ORDER, VISUALIZATION_RELEASE_ID
from ..theme import MODEL_COLORS
from .common import apply_research_layout, figure_metadata


FIG_MECHANISMS_EVIDENCE_COMPOSITION = "FIG_MECHANISMS_EVIDENCE_COMPOSITION"
FIG_MECHANISMS_COVERAGE_DIVERSITY = "FIG_MECHANISMS_COVERAGE_DIVERSITY"
FIG_MECHANISMS_UTILIZATION_MATRIX = "FIG_MECHANISMS_UTILIZATION_MATRIX"
FIG_MECHANISMS_UTILIZATION_PROFILE = "FIG_MECHANISMS_UTILIZATION_PROFILE"
FIG_MECHANISMS_UTILIZATION_QUALITY = "FIG_MECHANISMS_UTILIZATION_QUALITY"
FIG_MECHANISMS_CLAIM_STATUS = "FIG_MECHANISMS_CLAIM_STATUS"
FIG_MECHANISMS_CLAIM_DIFFICULTY = "FIG_MECHANISMS_CLAIM_DIFFICULTY"
FIG_MECHANISMS_PIPELINE_COMPLETION = "FIG_MECHANISMS_PIPELINE_COMPLETION"
FIG_MECHANISMS_FAILURE_MATRIX = "FIG_MECHANISMS_FAILURE_MATRIX"
FIG_MECHANISMS_NARRATIVE_STRUCTURE = "FIG_MECHANISMS_NARRATIVE_STRUCTURE"
FIG_MECHANISMS_POLICY_COMPLIANCE = "FIG_MECHANISMS_POLICY_COMPLIANCE"

CONDITION_COLORS = {
    "S0": "#98A2B3",
    "S1": "#99D5CF",
    "S2": "#5CB8AD",
    "S3": "#23877D",
    "S4": "#D97706",
    "S5": "#155E75",
}
CLAIM_STATUS_COLORS = {
    "Supported": "#237A57",
    "Not verifiable": "#D18A11",
    "Unsupported": "#C45A2A",
    "Contradicted": "#A83732",
    "Not applicable": "#98A2B3",
}
UTILIZATION_BANDS = (
    (0.50, "#B42318"),
    (0.80, "#D18A11"),
    (0.95, "#0F766E"),
    (1.01, "#237A57"),
)


def _band_color(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "#D0D5DD"
    for threshold, color in UTILIZATION_BANDS:
        if float(value) < threshold:
            return color
    return "#237A57"


def _humanize(value: object) -> str:
    return str(value).replace("_", " ").strip().title()


def build_evidence_composition_chart(evidence_design: pd.DataFrame) -> go.Figure:
    grouped = (
        evidence_design.groupby(["evidence_order", "evidence_level"], as_index=False)
        .agg(
            feature_items=("feature_item_count", "median"),
            concept_items=("concept_item_count", "median"),
        )
        .sort_values("evidence_order")
    )
    grouped[["feature_items", "concept_items"]] = grouped[
        ["feature_items", "concept_items"]
    ].fillna(0)

    figure = go.Figure()
    figure.add_bar(
        x=grouped["evidence_level"],
        y=grouped["feature_items"],
        name="Feature evidence",
        marker_color="#0F766E",
        hovertemplate="<b>%{x}</b><br>Feature evidence: %{y:.0f}<extra></extra>",
    )
    figure.add_bar(
        x=grouped["evidence_level"],
        y=grouped["concept_items"],
        name="Concept evidence",
        marker_color="#7C6F64",
        hovertemplate="<b>%{x}</b><br>Concept evidence: %{y:.0f}<extra></extra>",
    )
    figure.update_layout(
        barmode="stack",
        legend={
            "orientation": "h",
            "y": 1.06,
            "x": 0,
            "traceorder": "normal",
        },
        bargap=0.22,
    )
    figure.update_xaxes(
        categoryorder="array",
        categoryarray=list(EXPECTED_EVIDENCE_ORDER),
        fixedrange=True,
    )
    figure.update_yaxes(
        title="Median evidence items",
        rangemode="tozero",
        gridcolor="rgba(102,112,133,0.14)",
        fixedrange=True,
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_EVIDENCE_COMPOSITION,
            source="evidence_design_summary.csv",
            metric="median feature and concept evidence items",
            denominator="36 canonical cases per evidence condition",
            release=VISUALIZATION_RELEASE_ID,
            grain="evidence condition",
        ),
        height=340,
        margin={"l": 62, "r": 22, "t": 52, "b": 50},
    )

def build_coverage_diversity_scatter(evidence_design: pd.DataFrame) -> go.Figure:
    data = evidence_design.dropna(
        subset=["coverage", "normalized_entropy"]
    ).copy()

    figure = go.Figure()
    for level in EXPECTED_EVIDENCE_ORDER:
        subset = data.loc[data["evidence_level"] == level]
        if subset.empty:
            continue
        figure.add_scatter(
            x=subset["coverage"],
            y=subset["normalized_entropy"],
            mode="markers",
            name=level,
            marker={
                "size": 7,
                "color": CONDITION_COLORS[level],
                "opacity": 0.54,
                "line": {"width": 0.6, "color": "#FFFFFF"},
            },
            customdata=np.column_stack(
                [
                    subset["case_id"],
                    subset["evidence_label"],
                    subset["evidence_item_count"],
                    subset["feature_item_count"],
                    subset["concept_item_count"],
                ]
            ),
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>"
                "Case %{customdata[0]}<br>"
                "Coverage: %{x:.1%}<br>"
                "Diversity: %{y:.3f}<br>"
                "Evidence items: %{customdata[2]:.0f}<br>"
                "Features: %{customdata[3]:.0f} · "
                "Concepts: %{customdata[4]:.0f}<extra></extra>"
            ),
        )

    def padded_range(series: pd.Series, floor: float, ceiling: float) -> list[float]:
        minimum = float(series.min())
        maximum = float(series.max())
        span = max(maximum - minimum, 0.08)
        padding = max(span * 0.18, 0.035)
        return [max(floor, minimum - padding), min(ceiling, maximum + padding)]

    x_range = padded_range(data["coverage"], 0.0, 1.0)
    y_range = padded_range(data["normalized_entropy"], 0.0, 1.0)

    figure.update_layout(
        legend={"orientation": "h", "y": 1.05, "x": 0}
    )
    figure.update_xaxes(
        title="Evidence coverage",
        range=x_range,
        tickformat=".0%",
        gridcolor="rgba(102,112,133,0.14)",
        fixedrange=True,
        automargin=True,
    )
    figure.update_yaxes(
        title="Normalized diversity",
        range=y_range,
        gridcolor="rgba(102,112,133,0.14)",
        fixedrange=True,
        automargin=True,
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_COVERAGE_DIVERSITY,
            source="evidence_design_summary.csv",
            metric="coverage × normalized evidence diversity",
            denominator=(
                "Case × evidence packages with defined coverage and diversity"
            ),
            release=VISUALIZATION_RELEASE_ID,
            grain="case × evidence condition",
            extra={"interpretation": "descriptive, not causal"},
        ),
        height=350,
        margin={"l": 68, "r": 22, "t": 50, "b": 58},
    )

def build_utilization_matrix(
    summary: pd.DataFrame,
    *,
    metric_label: str,
    metric_id: str | None = None,
    focused_model_id: str | None = None,
    focused_evidence_level: str | None = None,
) -> go.Figure:
    ordered = summary.sort_values(["generator_order", "evidence_order"]).copy()
    values = ordered["mean_value"].astype(float)
    colors = [_band_color(value) for value in values]
    sizes = [18 if pd.isna(value) else 18 + 18 * max(0.0, min(1.0, float(value))) for value in values]
    text = ["N/A" if pd.isna(value) else f"{value:.0%}" for value in values]
    customdata = np.column_stack([
        ordered["generator_id"], ordered["generator_label"], ordered["evidence_level"], ordered["evidence_label"], ordered["observed_count"], ordered["missing_count"], ordered["mean_e2e"], ordered["mean_selected_evidence"], ordered["mean_feature_mentions"], ordered["mean_concept_mentions"],
    ])
    focus_mask = (
        (ordered["generator_id"] == focused_model_id)
        & (ordered["evidence_level"] == focused_evidence_level)
    )
    line_widths = [3.2 if selected else 1.2 for selected in focus_mask]
    line_colors = ["#101828" if selected else "#FFFFFF" for selected in focus_mask]
    figure = go.Figure(go.Scatter(
        x=ordered["evidence_level"],
        y=ordered["generator_label"],
        mode="markers+text",
        text=text,
        textposition="middle center",
        textfont={"color": "#FFFFFF", "size": 10},
        marker={"size": sizes, "color": colors, "line": {"color": line_colors, "width": line_widths}},
        customdata=customdata,
        hovertemplate=("<b>%{customdata[1]} · %{customdata[2]}</b><br>%{customdata[3]}<br>" + metric_label + ": <b>%{text}</b><br>Observed: %{customdata[4]} · Missing/N/A: %{customdata[5]}<br>Mean E2E: %{customdata[6]:.1%}<br>Selected evidence: %{customdata[7]:.1f}<br>Feature mentions: %{customdata[8]:.1f}<br>Concept mentions: %{customdata[9]:.1f}<extra></extra>"),
    ))
    figure.update_xaxes(side="top", categoryorder="array", categoryarray=list(EXPECTED_EVIDENCE_ORDER), showgrid=True, gridcolor="rgba(102,112,133,0.12)", fixedrange=True)
    model_labels = ordered.sort_values("generator_order")["generator_label"].drop_duplicates().tolist()
    figure.update_yaxes(categoryorder="array", categoryarray=model_labels, autorange="reversed", showgrid=True, gridcolor="rgba(102,112,133,0.12)", fixedrange=True)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_UTILIZATION_MATRIX,
            source="evidence_utilization_summary.csv",
            metric=metric_id or metric_label,
            denominator="36 canonical cases per model–evidence configuration when defined",
            release=VISUALIZATION_RELEASE_ID,
            grain="model × evidence condition",
        ),
        height=350,
        margin={"l": 150, "r": 20, "t": 42, "b": 26},
        show_legend=False,
    )


def build_utilization_stage_profile(
    profile: pd.DataFrame,
    *,
    model_id: str,
    model_label: str,
    evidence_level: str,
    defined_label: str = "Defined",
    not_applicable_label: str = "Not applicable",
) -> go.Figure:
    data = profile.copy()
    data["rate"] = pd.to_numeric(data["rate"], errors="coerce")
    defined = data["rate"].notna()
    plot_values = data["rate"].fillna(0.0)

    figure = go.Figure(
        go.Bar(
            x=plot_values,
            y=data["stage"],
            orientation="h",
            width=0.58,
            marker_color=[
                MODEL_COLORS[model_id]
                if is_defined
                else "rgba(152,162,179,0.16)"
                for is_defined in defined
            ],
            text=[
                f"{value:.0%}" if is_defined else ""
                for value, is_defined in zip(plot_values, defined)
            ],
            textposition="inside",
            insidetextanchor="end",
            textfont={"color": "#FFFFFF", "size": 11},
            customdata=np.column_stack(
                [
                    [
                        defined_label if value else not_applicable_label
                        for value in defined
                    ]
                ]
            ),
            hovertemplate=(
                "%{y}: "
                "%{customdata[0]}"
                "<extra></extra>"
            ),
        )
    )

    for row in data.loc[~defined].itertuples():
        figure.add_annotation(
            x=0.025,
            y=row.stage,
            text="N/A",
            showarrow=False,
            xanchor="left",
            font={"size": 11, "color": "#667085"},
        )

    figure.update_layout(bargap=0.38)
    figure.update_xaxes(
        range=[0, 1],
        tickmode="array",
        tickvals=[0, 0.25, 0.5, 0.75, 1.0],
        ticktext=["0%", "25%", "50%", "75%", "100%"],
        gridcolor="rgba(102,112,133,0.14)",
        fixedrange=True,
        automargin=True,
    )
    figure.update_yaxes(
        autorange="reversed",
        fixedrange=True,
        automargin=True,
        tickfont={"size": 12},
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_UTILIZATION_PROFILE,
            source="evidence_utilization_summary.csv",
            metric="selected utilization stages",
            denominator="36 canonical cases for the selected configuration",
            release=VISUALIZATION_RELEASE_ID,
            grain="selected model × evidence configuration",
            extra={"model": model_label, "evidence": evidence_level},
        ),
        height=380,
        margin={"l": 178, "r": 30, "t": 28, "b": 64},
        show_legend=False,
    )

def build_utilization_quality_scatter(utilization: pd.DataFrame, *, metric_id: str, metric_label: str) -> go.Figure:
    data = utilization.copy()
    if metric_id == "feature_use":
        data["metric_value"] = pd.to_numeric(data["selected_feature_mention_rate"], errors="coerce")
    elif metric_id == "concept_use":
        data["metric_value"] = pd.to_numeric(data["concept_mention_rate"], errors="coerce")
    else:
        claims = pd.to_numeric(data["claim_count"], errors="coerce")
        supported = pd.to_numeric(data["supported_count"], errors="coerce")
        data["metric_value"] = np.where(claims > 0, supported / claims, np.nan)
    figure = go.Figure()
    for model_id in EXPECTED_MODEL_ORDER:
        subset = data.loc[(data["generator_id"] == model_id) & data["metric_value"].notna()]
        figure.add_scatter(
            x=subset["metric_value"], y=subset["end_to_end_faithfulness_yield"],
            mode="markers", name=str(subset.iloc[0]["generator_label"]),
            marker={"size": 7, "color": MODEL_COLORS[model_id], "opacity": 0.38},
            customdata=np.column_stack([subset["case_id"], subset["evidence_level"], subset["evidence_label"]]),
            hovertemplate=("<b>" + str(subset.iloc[0]["generator_label"]) + " · %{customdata[1]}</b><br>Case %{customdata[0]}<br>" + metric_label + ": %{x:.1%}<br>E2E: %{y:.1%}<extra></extra>"),
        )
    figure.update_layout(legend={"orientation": "h", "y": 1.08, "x": 0})
    figure.update_xaxes(title=metric_label, range=[0, 1], tickformat=".0%", gridcolor="rgba(102,112,133,0.16)", fixedrange=True)
    figure.update_yaxes(title="E2E operational faithfulness", range=[0, 1], tickformat=".0%", gridcolor="rgba(102,112,133,0.16)", fixedrange=True)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_UTILIZATION_QUALITY,
            source="evidence_utilization_summary.csv",
            metric=f"{metric_id} × end_to_end_faithfulness_yield",
            denominator="Planned LLM generations with a defined utilization denominator",
            release=VISUALIZATION_RELEASE_ID,
            grain="generation",
            extra={"interpretation": "descriptive association, not causal"},
        ),
        height=360,
        margin={"l": 70, "r": 20, "t": 46, "b": 58},
    )


def build_claim_status_small_multiples(status: pd.DataFrame) -> go.Figure:
    model_rows = status.sort_values(["model_order", "evidence_order"])
    labels = model_rows.sort_values("model_order")["model_label"].drop_duplicates().tolist()
    figure = make_subplots(rows=1, cols=3, subplot_titles=labels, horizontal_spacing=0.06)
    status_specs = [
        ("supported_share", "Supported"), ("not_verifiable_share", "Not verifiable"),
        ("unsupported_share", "Unsupported"), ("contradicted_share", "Contradicted"),
        ("not_applicable_share", "Not applicable"),
    ]
    for col, model_id in enumerate(EXPECTED_MODEL_ORDER, start=1):
        subset = model_rows.loc[model_rows["model_id"] == model_id].sort_values("evidence_order")
        for field, label in status_specs:
            figure.add_trace(go.Bar(
                x=subset[field], y=subset["evidence_level"], orientation="h", name=label,
                marker_color=CLAIM_STATUS_COLORS[label], legendgroup=label, showlegend=col == 1,
                customdata=np.column_stack([subset["claim_count"], subset[field.replace("_share", "_count")]]),
                hovertemplate=f"<b>{label}</b><br>%{{y}}: %{{x:.1%}}<br>Claims: %{{customdata[1]:.0f}} / %{{customdata[0]:.0f}}<extra></extra>",
            ), row=1, col=col)
        figure.update_xaxes(range=[0, 1], tickformat=".0%", fixedrange=True, row=1, col=col)
        figure.update_yaxes(categoryorder="array", categoryarray=list(EXPECTED_EVIDENCE_ORDER), autorange="reversed", fixedrange=True, row=1, col=col)
    figure.update_layout(barmode="stack", legend={"orientation": "h", "y": 1.12, "x": 0})
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_CLAIM_STATUS,
            source="mechanism_breakdowns.csv",
            metric="claim-status composition",
            denominator="All finalized claims within each model–evidence configuration",
            release=VISUALIZATION_RELEASE_ID,
            grain="model × evidence condition",
        ),
        height=420,
        margin={"l": 50, "r": 20, "t": 72, "b": 42},
    )


def build_claim_difficulty_matrix(difficulty: pd.DataFrame, *, measure: str = "rate") -> go.Figure:
    fields = ["not_verifiable", "unsupported", "contradicted"]
    labels = ["Not verifiable", "Unsupported", "Contradicted"]
    suffix = "_share" if measure == "rate" else "_count"
    ordered = difficulty.sort_values("claim_count", ascending=True)
    z = np.column_stack([ordered[f + suffix] for f in fields])
    text = [[f"{value:.1%}" if measure == "rate" else f"{int(value):,}" for value in row] for row in z]
    figure = go.Figure(go.Heatmap(
        z=z, x=labels, y=[_humanize(value) for value in ordered["claim_type"]],
        zmin=0, zmax=float(np.nanmax(z)) if np.nanmax(z) > 0 else 1,
        colorscale=[[0, "#F8FAFC"], [0.45, "#F4C97A"], [1, "#B42318"]],
        showscale=False, text=text, texttemplate="%{text}",
        customdata=np.column_stack([ordered["claim_count"]]),
        hovertemplate="<b>%{y} · %{x}</b><br>Value: %{text}<br>Total claims in type: %{customdata[0]:,.0f}<extra></extra>",
        xgap=3, ygap=2,
    ))
    figure.update_xaxes(side="top", fixedrange=True)
    figure.update_yaxes(fixedrange=True)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_CLAIM_DIFFICULTY,
            source="mechanism_breakdowns.csv",
            metric=f"claim difficulty {measure}",
            denominator="Claims within each certified claim type",
            release=VISUALIZATION_RELEASE_ID,
            grain="claim type × validation difficulty",
        ),
        height=430,
        margin={"l": 170, "r": 18, "t": 50, "b": 24},
        show_legend=False,
    )


def build_pipeline_completion_chart(stages: pd.DataFrame) -> go.Figure:
    labels = (
        stages.sort_values("model_order")["model_label"]
        .drop_duplicates()
        .tolist()
    )
    figure = make_subplots(
        rows=1,
        cols=3,
        subplot_titles=labels,
        horizontal_spacing=0.105,
        shared_yaxes=True,
    )

    for col, model_id in enumerate(EXPECTED_MODEL_ORDER, start=1):
        subset = (
            stages.loc[stages["model_id"] == model_id]
            .sort_values("stage_order")
            .copy()
        )
        figure.add_trace(
            go.Bar(
                x=subset["count"],
                y=subset["stage"],
                orientation="h",
                width=0.68,
                marker_color=MODEL_COLORS[model_id],
                showlegend=False,
                text=[f"{int(value)}" for value in subset["count"]],
                textposition="inside",
                insidetextanchor="end",
                textfont={"color": "#FFFFFF", "size": 11},
                hovertemplate="%{y}: %{x:.0f} / 216<extra></extra>",
            ),
            row=1,
            col=col,
        )
        figure.update_xaxes(
            range=[0, 225],
            tickmode="array",
            tickvals=[0, 50, 100, 150, 200],
            gridcolor="rgba(102,112,133,0.13)",
            fixedrange=True,
            row=1,
            col=col,
        )
        figure.update_yaxes(
            autorange="reversed",
            fixedrange=True,
            showticklabels=col == 1,
            automargin=col == 1,
            tickfont={"size": 11},
            row=1,
            col=col,
        )

    figure.update_layout(
        bargap=0.30,
        uniformtext_minsize=10,
        uniformtext_mode="hide",
    )
    figure.update_annotations(font={"size": 15, "color": "#344054"})

    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_PIPELINE_COMPLETION,
            source="narrative_structure_summary.csv + pipeline_failures.csv",
            metric="pipeline completion stages",
            denominator="216 planned generations per model",
            release=VISUALIZATION_RELEASE_ID,
            grain="model × pipeline stage",
        ),
        height=390,
        margin={"l": 130, "r": 24, "t": 70, "b": 54},
        show_legend=False,
    )

def build_failure_matrix(matrix: pd.DataFrame) -> go.Figure:
    ordered = matrix.sort_values(["model_order", "evidence_order"])
    pivot = ordered.pivot(
        index="model_label",
        columns="evidence_level",
        values="failure_count",
    )
    model_labels = (
        ordered.sort_values("model_order")["model_label"]
        .drop_duplicates()
        .tolist()
    )
    pivot = pivot.reindex(
        index=model_labels,
        columns=list(EXPECTED_EVIDENCE_ORDER),
    ).fillna(0)

    z = pivot.to_numpy()
    figure = go.Figure(
        go.Heatmap(
            z=z,
            x=pivot.columns,
            y=pivot.index,
            zmin=0,
            zmax=7,
            colorscale=[
                [0.0, "#FFFFFF"],
                [0.01, "#FEF3C7"],
                [0.43, "#D97706"],
                [1.0, "#B42318"],
            ],
            showscale=False,
            xgap=4,
            ygap=4,
            hovertemplate=(
                "<b>%{y} · %{x}</b><br>"
                "Unusable generations: %{z:.0f}<extra></extra>"
            ),
        )
    )

    for row_index, model_label in enumerate(pivot.index):
        for col_index, evidence_level in enumerate(pivot.columns):
            value = int(z[row_index, col_index])
            figure.add_annotation(
                x=evidence_level,
                y=model_label,
                text=str(value),
                showarrow=False,
                font={
                    "size": 14 if value else 12,
                    "color": (
                        "#FFFFFF"
                        if value >= 5
                        else "#344054"
                        if value > 0
                        else "#98A2B3"
                    ),
                    "weight": 700 if value else 400,
                },
            )

    figure.update_xaxes(side="top", fixedrange=True)
    figure.update_yaxes(
        autorange="reversed",
        fixedrange=True,
        automargin=True,
    )
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_FAILURE_MATRIX,
            source="pipeline_failures.csv",
            metric="unusable generation count",
            denominator="36 planned generations per model–evidence cell",
            release=VISUALIZATION_RELEASE_ID,
            grain="model × evidence condition",
        ),
        height=275,
        margin={"l": 158, "r": 20, "t": 44, "b": 24},
        show_legend=False,
    )

def build_narrative_structure_chart(summary: pd.DataFrame) -> go.Figure:
    specs = [
        ("median_words", "Words"),
        ("median_sentences", "Sentences"),
        ("median_factors", "Factors"),
    ]
    values = summary.sort_values("generator_order").copy()
    short_labels = {
        "qwen3_8b": "Qwen",
        "deepseek_v4_flash": "DeepSeek",
        "phi4_mini_instruct": "Phi",
    }
    x_labels = [
        short_labels.get(str(model_id), str(label))
        for model_id, label in zip(
            values["generator_id"], values["generator_label"]
        )
    ]

    figure = make_subplots(
        rows=1,
        cols=3,
        subplot_titles=[label for _, label in specs],
        horizontal_spacing=0.12,
    )
    for col, (field, _) in enumerate(specs, start=1):
        figure.add_trace(
            go.Bar(
                x=x_labels,
                y=values[field],
                marker_color=[
                    MODEL_COLORS[item] for item in values["generator_id"]
                ],
                showlegend=False,
                text=[f"{value:.1f}" for value in values[field]],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{x}: %{y:.1f}<extra></extra>",
            ),
            row=1,
            col=col,
        )
        figure.update_xaxes(
            showticklabels=True,
            tickfont={"size": 10},
            fixedrange=True,
            row=1,
            col=col,
        )
        figure.update_yaxes(
            rangemode="tozero",
            gridcolor="rgba(102,112,133,0.13)",
            fixedrange=True,
            row=1,
            col=col,
        )

    density_summary = " · ".join(
        f"{label} {value:.1%}"
        for label, value in zip(
            x_labels,
            values["median_technical_term_ratio"],
        )
    )
    figure.add_annotation(
        x=0.5,
        y=-0.24,
        xref="paper",
        yref="paper",
        text=f"Median technical-term density · {density_summary}",
        showarrow=False,
        font={"size": 10, "color": "#667085"},
    )

    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_NARRATIVE_STRUCTURE,
            source="narrative_structure_summary.csv",
            metric="narrative structure summaries",
            denominator="216 planned generations per LLM",
            release=VISUALIZATION_RELEASE_ID,
            grain="model",
            extra={"restriction": "not a human naturalness measure"},
        ),
        height=350,
        margin={"l": 50, "r": 22, "t": 58, "b": 82},
        show_legend=False,
    )

def build_policy_compliance_chart(summary: pd.DataFrame) -> go.Figure:
    fields = [("uncertainty_compliance", "Uncertainty"), ("distributed_compliance", "Distributed note"), ("partial_evidence_compliance", "Partial evidence"), ("overall_policy_compliance", "Overall")]
    figure = go.Figure()
    for row in summary.sort_values("generator_order").itertuples():
        figure.add_bar(
            x=[label for _, label in fields], y=[getattr(row, field) for field, _ in fields],
            name=row.generator_label, marker_color=MODEL_COLORS[row.generator_id],
            hovertemplate=f"<b>{row.generator_label}</b><br>%{{x}}: %{{y:.1%}}<extra></extra>",
        )
    figure.update_layout(barmode="group", legend={"orientation": "h", "y": 1.08, "x": 0})
    figure.update_yaxes(range=[0, 1], tickformat=".0%", gridcolor="rgba(102,112,133,0.16)", fixedrange=True)
    figure.update_xaxes(fixedrange=True)
    return apply_research_layout(
        figure,
        metadata=figure_metadata(
            figure_id=FIG_MECHANISMS_POLICY_COMPLIANCE,
            source="narrative_structure_summary.csv",
            metric="policy compliance rates",
            denominator="Planned LLM generations within each model",
            release=VISUALIZATION_RELEASE_ID,
            grain="model × policy rule",
        ),
        height=320,
        margin={"l": 58, "r": 20, "t": 48, "b": 54},
    )
