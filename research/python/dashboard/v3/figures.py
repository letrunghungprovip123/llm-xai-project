from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


_MODEL_ORDER = ("qwen3_8b", "deepseek_v4_flash", "phi4_mini_instruct")
_MODEL_LABELS = {
    "qwen3_8b": "Qwen3 8B",
    "deepseek_v4_flash": "DeepSeek V4 Flash",
    "phi4_mini_instruct": "Phi-4 Mini Instruct",
}
_EVIDENCE_ORDER = tuple(f"S{i}" for i in range(6))
_DATASET_COLORS = {"HOME_CREDIT": "#4F46E5", "FREDDIE": "#0F766E"}
_VALIDATION_COLORS = {
    "SUPPORTED": "#0F766E",
    "NOT_VERIFIABLE": "#D69E2E",
    "UNSUPPORTED": "#C2410C",
    "CONTRADICTED": "#B42318",
    "NOT_APPLICABLE": "#98A2B3",
}
# Color-blind-friendlier dark sequential scale. All cells retain exact labels, so
# interpretation never depends on hue alone. The scale remains fixed at 0–100%.
_E2E_COLORSCALE = [
    [0.00, "#4C1D95"],
    [0.40, "#3730A3"],
    [0.62, "#1D4ED8"],
    [0.80, "#0369A1"],
    [0.90, "#0F766E"],
    [1.00, "#065F46"],
]
_EFFECT_LABELS = {
    "model": "Model",
    "evidence": "Evidence",
    "model_x_evidence": "Model × Evidence",
    "model:evidence": "Model × Evidence",
    "interaction": "Model × Evidence",
}
_EFFECT_ORDER = ("Model", "Evidence", "Model × Evidence")


def _base_layout(figure: go.Figure, *, height: int, margin: dict[str, int] | None = None) -> go.Figure:
    figure.update_layout(
        template="plotly_white",
        height=height,
        margin=margin or {"l": 60, "r": 24, "t": 42, "b": 48},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", "color": "#344054"},
        hoverlabel={"bgcolor": "#101828", "font": {"color": "#FFFFFF", "size": 12}, "bordercolor": "#101828"},
    )
    return figure


def _evidence_matrix(frame: pd.DataFrame, value_column: str) -> tuple[list[list[float]], list[list[list[object]]]]:
    z: list[list[float]] = []
    custom: list[list[list[object]]] = []
    for model_id in _MODEL_ORDER:
        values: list[float] = []
        metadata: list[list[object]] = []
        subset = frame.loc[frame["model_id"].astype(str).eq(model_id)].set_index("evidence_level")
        for evidence in _EVIDENCE_ORDER:
            row = subset.loc[evidence]
            values.append(float(row[value_column]))
            metadata.append([
                model_id,
                str(row.get("model_label") or _MODEL_LABELS[model_id]),
                evidence,
                row.get("p10_e2e_display", row.get("p10_e2e", "—")),
                row.get("usability_display", row.get("usability_rate", "—")),
                int(row.get("planned_generation_count", 36)),
                int(row.get("usable_generation_count", 0)),
                str(row.get("mean_e2e_report_number_id", "")),
            ])
        z.append(values)
        custom.append(metadata)
    return z, custom


def _style_heatmap_axes(figure: go.Figure) -> None:
    figure.update_xaxes(
        side="top",
        title=None,
        fixedrange=True,
        tickfont={"size": 11, "color": "#475467"},
        showgrid=False,
        zeroline=False,
    )
    figure.update_yaxes(
        title=None,
        autorange="reversed",
        fixedrange=True,
        tickfont={"size": 11, "color": "#475467"},
        showgrid=False,
        zeroline=False,
    )


def overview_option_landscape(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()

    if not cross_dataset:
        z, custom = _evidence_matrix(frame, "mean_e2e")
        figure = go.Figure(
            go.Heatmap(
                z=z,
                x=list(_EVIDENCE_ORDER),
                y=[_MODEL_LABELS[m] for m in _MODEL_ORDER],
                customdata=custom,
                zmin=0,
                zmax=1,
                colorscale=_E2E_COLORSCALE,
                colorbar={"title": "E2E", "tickformat": ".0%", "thickness": 10, "len": 0.78, "outlinewidth": 0},
                text=[[f"{value:.0%}" for value in row] for row in z],
                texttemplate="%{text}",
                textfont={"size": 12, "color": "white"},
                xgap=5,
                ygap=5,
                hovertemplate=(
                    "<b>%{customdata[1]} · %{customdata[2]}</b><br>"
                    "End-to-End Faithfulness: <b>%{z:.2%}</b><br>"
                    "P10 E2E: %{customdata[3]}<br>"
                    "Usability: %{customdata[4]}<br>"
                    "Planned: %{customdata[5]} · Usable: %{customdata[6]}<br>"
                    "<extra>Click để xem chi tiết</extra>"
                ),
            )
        )
        _style_heatmap_axes(figure)
        return _base_layout(figure, height=338, margin={"l": 150, "r": 48, "t": 46, "b": 24})

    # Cross-dataset comparison keeps the studies separate and synchronizes one
    # fixed 0–1 scale. Dataset labels are annotations above the top-axis ticks so
    # they never compete with S0–S5 labels for the same vertical space.
    figure = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.055)
    mappings = (
        (1, "HOME_CREDIT", "home_credit_mean_end_to_end_faithfulness_yield", "Home Credit"),
        (2, "FREDDIE", "freddie_mean_end_to_end_faithfulness_yield", "Freddie Mac"),
    )
    for col, scope, value_col, dataset_label in mappings:
        local = frame.copy()
        prefix = "home_credit" if scope == "HOME_CREDIT" else "freddie"
        local["p10_e2e_display"] = local[f"{prefix}_p10_e2e_display"]
        local["usability_display"] = local[f"{prefix}_usability_display"]
        local["planned_generation_count"] = 36
        local["usable_generation_count"] = 0
        local["mean_e2e_report_number_id"] = ""
        z, custom = _evidence_matrix(local, value_col)
        custom_with_scope = [[[scope, *cell] for cell in row] for row in custom]
        figure.add_trace(
            go.Heatmap(
                z=z,
                x=list(_EVIDENCE_ORDER),
                y=[_MODEL_LABELS[m] for m in _MODEL_ORDER],
                customdata=custom_with_scope,
                zmin=0,
                zmax=1,
                colorscale=_E2E_COLORSCALE,
                showscale=col == 2,
                colorbar={
                    "title": "E2E",
                    "tickformat": ".0%",
                    "thickness": 10,
                    "len": 0.74,
                    "x": 1.025,
                    "outlinewidth": 0,
                },
                text=[[f"{value:.0%}" for value in row] for row in z],
                texttemplate="%{text}",
                textfont={"size": 11, "color": "white"},
                xgap=5,
                ygap=5,
                hovertemplate=(
                    f"<b>{dataset_label}</b><br>"
                    "<b>%{customdata[2]} · %{customdata[3]}</b><br>"
                    "End-to-End Faithfulness: <b>%{z:.2%}</b><br>"
                    "P10 E2E: %{customdata[4]}<br>"
                    "Usability: %{customdata[5]}<br>"
                    "<extra>Click để xem chi tiết</extra>"
                ),
            ),
            row=1,
            col=col,
        )

    # Titles live in paper coordinates with dedicated top margin.
    figure.add_annotation(x=0.235, y=1.17, xref="paper", yref="paper", text="<b>Home Credit</b>", showarrow=False, font={"size": 12, "color": "#344054"})
    figure.add_annotation(x=0.765, y=1.17, xref="paper", yref="paper", text="<b>Freddie Mac</b>", showarrow=False, font={"size": 12, "color": "#344054"})
    _style_heatmap_axes(figure)
    return _base_layout(figure, height=366, margin={"l": 136, "r": 50, "t": 72, "b": 22})


def _effect_label(value: object) -> str:
    key = str(value).strip().lower().replace(" ", "_")
    return _EFFECT_LABELS.get(key, str(value).replace("_", " ").title())


def _ordered_effects(frame: pd.DataFrame) -> pd.DataFrame:
    local = frame.copy()
    local["effect_label"] = local["effect"].map(_effect_label)
    local["_order"] = local["effect_label"].map({label: idx for idx, label in enumerate(_EFFECT_ORDER)}).fillna(99)
    return local.sort_values(["_order", "effect_label"], kind="stable").drop(columns="_order")


def overview_major_effects(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()
    frame = _ordered_effects(frame)
    order = list(_EFFECT_ORDER)

    if not cross_dataset:
        x = frame["partial_eta_squared"].astype(float)
        custom = list(zip(frame["f_statistic"], frame["p_value_display"], frame["effect_label"]))
        figure = go.Figure(
            go.Scatter(
                x=x,
                y=frame["effect_label"],
                mode="markers+text",
                text=[f"{value:.3f}" for value in x],
                textposition="middle right",
                textfont={"size": 10, "color": "#475467"},
                cliponaxis=False,
                marker={"size": 12, "color": "#0F766E", "line": {"color": "#FFFFFF", "width": 1.5}},
                customdata=custom,
                hovertemplate=(
                    "<b>%{customdata[2]}</b><br>"
                    "Partial η²: <b>%{x:.3f}</b><br>"
                    "F: %{customdata[0]:.3f}<br>"
                    "p: %{customdata[1]}<extra></extra>"
                ),
            )
        )
        for _, row in frame.iterrows():
            figure.add_shape(type="line", x0=0, x1=float(row["partial_eta_squared"]), y0=row["effect_label"], y1=row["effect_label"], line={"color": "#D0D5DD", "width": 2}, layer="below")
        figure.update_xaxes(title="Partial η²", range=[0, 1], fixedrange=True, gridcolor="#EAECF0", dtick=0.25)
        figure.update_yaxes(title=None, categoryorder="array", categoryarray=order, autorange="reversed", fixedrange=True)
        return _base_layout(figure, height=262, margin={"l": 122, "r": 42, "t": 16, "b": 48})

    hc = frame["home_credit_partial_eta_squared"].astype(float)
    fr = frame["freddie_partial_eta_squared"].astype(float)
    figure = go.Figure()
    for _, row in frame.iterrows():
        figure.add_shape(
            type="line",
            x0=float(row["home_credit_partial_eta_squared"]),
            x1=float(row["freddie_partial_eta_squared"]),
            y0=row["effect_label"],
            y1=row["effect_label"],
            line={"color": "#D0D5DD", "width": 3},
            layer="below",
        )
    figure.add_trace(
        go.Scatter(
            x=hc,
            y=frame["effect_label"],
            mode="markers",
            name="Home Credit",
            marker={"size": 11, "color": _DATASET_COLORS["HOME_CREDIT"], "line": {"color": "white", "width": 1.3}},
            customdata=list(zip(frame["home_credit_f_statistic"], frame["home_credit_p_value_display"])),
            hovertemplate="<b>Home Credit · %{y}</b><br>Partial η²: <b>%{x:.3f}</b><br>F: %{customdata[0]:.3f}<br>p: %{customdata[1]}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=fr,
            y=frame["effect_label"],
            mode="markers",
            name="Freddie Mac",
            marker={"size": 11, "color": _DATASET_COLORS["FREDDIE"], "line": {"color": "white", "width": 1.3}},
            customdata=list(zip(frame["freddie_f_statistic"], frame["freddie_p_value_display"])),
            hovertemplate="<b>Freddie Mac · %{y}</b><br>Partial η²: <b>%{x:.3f}</b><br>F: %{customdata[0]:.3f}<br>p: %{customdata[1]}<extra></extra>",
        )
    )
    figure.update_xaxes(title="Partial η²", range=[0, 1], fixedrange=True, gridcolor="#EAECF0", dtick=0.25)
    figure.update_yaxes(title=None, categoryorder="array", categoryarray=order, autorange="reversed", fixedrange=True)
    figure.update_layout(legend={"orientation": "h", "y": 1.16, "x": 0, "xanchor": "left", "font": {"size": 10}})
    return _base_layout(figure, height=278, margin={"l": 122, "r": 22, "t": 48, "b": 48})


def overview_validation_composition(rows: Iterable[Mapping[str, object]]) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    figure = go.Figure()
    if frame.empty:
        return figure
    statuses = ("SUPPORTED", "NOT_VERIFIABLE", "UNSUPPORTED", "CONTRADICTED", "NOT_APPLICABLE")
    for status in statuses:
        shares: list[float] = []
        counts: list[int] = []
        report_ids: list[str] = []
        for row in frame.to_dict(orient="records"):
            count = int(row["counts"][status])
            total = int(row["total_claims"])
            shares.append((count / total * 100.0) if total else 0.0)
            counts.append(count)
            report_ids.append(str(row["report_number_ids"][status]))
        figure.add_trace(
            go.Bar(
                name=status,
                orientation="h",
                y=frame["dataset_label"],
                x=shares,
                customdata=list(zip(counts, report_ids)),
                marker={"color": _VALIDATION_COLORS[status]},
                hovertemplate=(
                    f"<b>{status}</b><br>"
                    "%{y}<br>Tỷ trọng trình bày: <b>%{x:.2f}%</b><br>"
                    "Atomic claims: %{customdata[0]:,}<extra>Click để mở Mechanisms</extra>"
                ),
            )
        )
    figure.update_layout(
        barmode="stack",
        legend={"orientation": "h", "y": 1.18, "x": 0, "xanchor": "left", "font": {"size": 9}, "itemclick": False, "itemdoubleclick": False},
    )
    figure.update_xaxes(title=None, range=[0, 100], ticksuffix="%", fixedrange=True, gridcolor="#EAECF0", dtick=20)
    figure.update_yaxes(title=None, autorange="reversed", fixedrange=True)
    height = 250 if len(frame) > 1 else 220
    top = 54 if len(frame) > 1 else 52
    return _base_layout(figure, height=height, margin={"l": 92, "r": 18, "t": top, "b": 42})


# Existing page figures retained for non-Overview pages.
def effectiveness_heatmap(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool = False) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()
    figure = go.Figure()
    if not cross_dataset:
        pivot = frame.pivot(index="model_id", columns="evidence_level", values="mean_e2e").reindex(index=_MODEL_ORDER, columns=_EVIDENCE_ORDER)
        figure.add_trace(go.Heatmap(z=pivot.to_numpy(), x=list(pivot.columns), y=list(pivot.index), zmin=0, zmax=1, colorscale="Viridis", colorbar={"title": "Mean E2E"}, hovertemplate="Model: %{y}<br>Evidence: %{x}<br>Mean E2E: %{z:.2%}<extra></extra>"))
    else:
        for label, column in (("Home Credit", "home_credit_mean_end_to_end_faithfulness_yield"), ("Freddie", "freddie_mean_end_to_end_faithfulness_yield")):
            figure.add_trace(go.Bar(name=label, x=frame["option_id"], y=frame[column], hovertemplate=f"{label}<br>%{{x}}<br>Mean E2E: %{{y:.2%}}<extra></extra>"))
        figure.update_layout(barmode="group")
    figure.update_layout(template="plotly_white", height=440, margin={"l": 60, "r": 24, "t": 36, "b": 110}, yaxis={"tickformat": ".0%"} if cross_dataset else None)
    return figure


def mechanism_loss_figure(rows: Iterable[Mapping[str, object]]) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    figure = go.Figure()
    if frame.empty:
        return figure
    components = (
        ("pipeline_loss", "Pipeline loss"),
        ("not_verifiable_loss", "Not verifiable"),
        ("unsupported_loss", "Unsupported"),
        ("contradiction_loss", "Contradicted"),
    )
    for column, label in components:
        figure.add_trace(go.Bar(name=label, x=frame["dataset_scope"], y=frame[column]))
    figure.update_layout(template="plotly_white", barmode="stack", height=390, margin={"l": 60, "r": 24, "t": 36, "b": 50}, yaxis={"tickformat": ".0%", "title": "Loss share"})
    return figure

# ============================================================================
# Page 2 — Effectiveness analytical redesign
# ============================================================================

_MODEL_COLORS = {
    "qwen3_8b": "#4F46E5",
    "deepseek_v4_flash": "#0F766E",
    "phi4_mini_instruct": "#C2410C",
}
_METRIC_LABELS = {
    "end_to_end_faithfulness_yield": "E2E",
    "resolved_faithfulness": "Resolved",
    "verifiability": "Verifiability",
    "conservative_faithfulness": "Conservative",
}
_CLAIM_STATUS_ORDER = ("SUPPORTED", "NOT_VERIFIABLE", "UNSUPPORTED", "CONTRADICTED", "NOT_APPLICABLE")


def effectiveness_reliability_map(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    """Mean E2E × P10 E2E. Cross-dataset mode keeps studies in synchronized facets."""
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()

    datasets = [(None, None)] if not cross_dataset else [("HOME_CREDIT", "Home Credit"), ("FREDDIE", "Freddie Mac")]
    figure = go.Figure() if not cross_dataset else make_subplots(rows=1, cols=2, horizontal_spacing=0.075)

    for dataset_index, (scope, dataset_label) in enumerate(datasets, start=1):
        local = frame if scope is None else frame.loc[frame["dataset_scope"].astype(str).eq(scope)]
        for model_id in _MODEL_ORDER:
            subset = local.loc[local["model_id"].astype(str).eq(model_id)].sort_values("evidence_order", kind="stable")
            if subset.empty:
                continue
            custom = list(
                zip(
                    subset["dataset_scope"],
                    subset["model_id"],
                    subset["model_label"],
                    subset["evidence_level"],
                    subset["median_e2e"],
                    subset["bootstrap_ci_lower"],
                    subset["bootstrap_ci_upper"],
                    subset["usability_rate"],
                    subset["quality_rank"],
                    subset["option_role"],
                    subset["planned_generation_count"],
                    subset["usable_generation_count"],
                    subset["mean_e2e_report_number_id"],
                )
            )
            trace = go.Scatter(
                x=subset["mean_e2e"],
                y=subset["p10_e2e"],
                mode="markers+text",
                text=subset["evidence_level"],
                textposition="top center",
                textfont={"size": 9, "color": "#475467"},
                name=_MODEL_LABELS[model_id],
                legendgroup=model_id,
                showlegend=(not cross_dataset) or dataset_index == 1,
                marker={
                    "size": 12,
                    "color": _MODEL_COLORS[model_id],
                    "line": {"color": "#FFFFFF", "width": 1.5},
                },
                error_x={
                    "type": "data",
                    "symmetric": False,
                    "array": (subset["bootstrap_ci_upper"] - subset["mean_e2e"]).clip(lower=0),
                    "arrayminus": (subset["mean_e2e"] - subset["bootstrap_ci_lower"]).clip(lower=0),
                    "thickness": 1,
                    "width": 2,
                    "color": "#98A2B3",
                },
                customdata=custom,
                hovertemplate=(
                    "<b>%{customdata[2]} × %{customdata[3]}</b><br>"
                    + ((f"{dataset_label}<br>") if dataset_label else "")
                    + "Mean End-to-End Faithfulness: <b>%{x:.2%}</b><br>"
                    "P10 End-to-End Faithfulness: <b>%{y:.2%}</b><br>"
                    "Median: %{customdata[4]:.2%}<br>"
                    "Bootstrap 95% CI: [%{customdata[5]:.2%}, %{customdata[6]:.2%}]<br>"
                    "Usability: %{customdata[7]:.2%}<br>"
                    "Quality rank: %{customdata[8]} · Role: %{customdata[9]}<br>"
                    "Usable: %{customdata[11]}/%{customdata[10]}"
                    "<extra>Click để xem option</extra>"
                ),
            )
            if cross_dataset:
                figure.add_trace(trace, row=1, col=dataset_index)
            else:
                figure.add_trace(trace)

    figure.update_xaxes(title="Mean End-to-End Faithfulness", range=[0, 1.02], tickformat=".0%", dtick=0.2, fixedrange=True, gridcolor="#EAECF0")
    figure.update_yaxes(title="P10 End-to-End Faithfulness", range=[0, 1.02], tickformat=".0%", dtick=0.2, fixedrange=True, gridcolor="#EAECF0")
    if cross_dataset:
        figure.add_annotation(x=0.235, y=1.14, xref="paper", yref="paper", text="<b>Home Credit</b>", showarrow=False, font={"size": 12})
        figure.add_annotation(x=0.765, y=1.14, xref="paper", yref="paper", text="<b>Freddie Mac</b>", showarrow=False, font={"size": 12})
    figure.update_layout(legend={"orientation": "h", "y": 1.16 if not cross_dataset else 1.24, "x": 0, "font": {"size": 10}})
    return _base_layout(figure, height=420 if not cross_dataset else 438, margin={"l": 72, "r": 26, "t": 72 if cross_dataset else 54, "b": 62})


def effectiveness_evidence_profiles(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    """Three model small-multiples over categorical S0–S5 with certified bootstrap CI."""
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()
    figure = make_subplots(rows=1, cols=3, subplot_titles=[_MODEL_LABELS[m] for m in _MODEL_ORDER], horizontal_spacing=0.055)
    for col, model_id in enumerate(_MODEL_ORDER, start=1):
        model_frame = frame.loc[frame["model_id"].astype(str).eq(model_id)]
        datasets = (("HOME_CREDIT", "Home Credit"), ("FREDDIE", "Freddie Mac")) if cross_dataset else ((None, "Mean E2E"),)
        for scope, label in datasets:
            local = model_frame if scope is None else model_frame.loc[model_frame["dataset_scope"].astype(str).eq(scope)]
            local = local.sort_values("evidence_order", kind="stable")
            if local.empty:
                continue
            color = _DATASET_COLORS.get(scope, _MODEL_COLORS[model_id])
            figure.add_trace(
                go.Scatter(
                    x=local["evidence_level"],
                    y=local["mean_e2e"],
                    mode="lines+markers",
                    name=label,
                    legendgroup=label,
                    showlegend=(col == 1),
                    line={"color": color, "width": 2},
                    marker={"size": 8, "color": color, "line": {"color": "white", "width": 1}},
                    error_y={
                        "type": "data",
                        "symmetric": False,
                        "array": (local["bootstrap_ci_upper"] - local["mean_e2e"]).clip(lower=0),
                        "arrayminus": (local["mean_e2e"] - local["bootstrap_ci_lower"]).clip(lower=0),
                        "thickness": 1,
                        "width": 2,
                        "color": "#98A2B3",
                    },
                    customdata=list(zip(local["dataset_scope"], local["model_id"], local["evidence_level"], local["p10_e2e"], local["usability_rate"])),
                    hovertemplate=(
                        "<b>%{x}</b><br>Mean E2E: <b>%{y:.2%}</b><br>"
                        "P10: %{customdata[3]:.2%}<br>Usability: %{customdata[4]:.2%}<extra></extra>"
                    ),
                ),
                row=1,
                col=col,
            )
    figure.update_xaxes(categoryorder="array", categoryarray=list(_EVIDENCE_ORDER), fixedrange=True, title=None)
    figure.update_yaxes(range=[0, 1.02], tickformat=".0%", dtick=0.2, fixedrange=True, gridcolor="#EAECF0")
    figure.update_yaxes(title="Mean E2E", row=1, col=1)
    figure.update_layout(legend={"orientation": "h", "y": 1.18, "x": 0})
    return _base_layout(figure, height=326, margin={"l": 62, "r": 20, "t": 58, "b": 48})


def effectiveness_metric_matrix(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()
    metric_order = list(_METRIC_LABELS)

    def matrix_for(local: pd.DataFrame):
        local = local.copy()
        local["row_label"] = local["model_label"].astype(str) + " · " + local["evidence_level"].astype(str)
        option_order = [f"{_MODEL_LABELS[m]} · {e}" for m in _MODEL_ORDER for e in _EVIDENCE_ORDER]
        pivot = local.pivot(index="row_label", columns="metric_id", values="metric_mean").reindex(index=option_order, columns=metric_order)
        return pivot

    if not cross_dataset:
        pivot = matrix_for(frame)
        figure = go.Figure(go.Heatmap(
            z=pivot.to_numpy(), x=[_METRIC_LABELS[m] for m in metric_order], y=list(pivot.index),
            zmin=0, zmax=1, colorscale=_E2E_COLORSCALE, colorbar={"title": "Mean", "tickformat": ".0%", "thickness": 10},
            text=[[f"{v:.0%}" if pd.notna(v) else "N/A" for v in row] for row in pivot.to_numpy()], texttemplate="%{text}",
            hovertemplate="<b>%{y}</b><br>%{x}: <b>%{z:.2%}</b><extra></extra>", xgap=3, ygap=2,
        ))
        figure.update_yaxes(autorange="reversed", fixedrange=True, tickfont={"size": 9})
        figure.update_xaxes(side="top", fixedrange=True)
        return _base_layout(figure, height=480, margin={"l": 170, "r": 52, "t": 54, "b": 26})

    figure = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.065)
    for col, (scope, label) in enumerate((("HOME_CREDIT", "Home Credit"), ("FREDDIE", "Freddie Mac")), start=1):
        pivot = matrix_for(frame.loc[frame["dataset_scope"].astype(str).eq(scope)])
        figure.add_trace(go.Heatmap(
            z=pivot.to_numpy(), x=[_METRIC_LABELS[m] for m in metric_order], y=list(pivot.index),
            zmin=0, zmax=1, colorscale=_E2E_COLORSCALE, showscale=(col == 2),
            colorbar={"title": "Mean", "tickformat": ".0%", "thickness": 10, "x": 1.025},
            text=[[f"{v:.0%}" if pd.notna(v) else "N/A" for v in row] for row in pivot.to_numpy()], texttemplate="%{text}",
            hovertemplate=f"<b>{label}</b><br><b>%{{y}}</b><br>%{{x}}: <b>%{{z:.2%}}</b><extra></extra>", xgap=3, ygap=2,
        ), row=1, col=col)
    figure.update_yaxes(autorange="reversed", fixedrange=True, tickfont={"size": 8})
    figure.update_xaxes(side="top", fixedrange=True, tickfont={"size": 9})
    figure.add_annotation(x=0.235, y=1.105, xref="paper", yref="paper", text="<b>Home Credit</b>", showarrow=False)
    figure.add_annotation(x=0.765, y=1.105, xref="paper", yref="paper", text="<b>Freddie Mac</b>", showarrow=False)
    return _base_layout(figure, height=500, margin={"l": 162, "r": 52, "t": 70, "b": 24})


def effectiveness_effect_size_plot(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()
    if not cross_dataset:
        return overview_major_effects(frame.to_dict(orient="records"), cross_dataset=False)

    hc = _ordered_effects(frame.loc[frame["dataset_scope"].astype(str).eq("HOME_CREDIT")])
    fr = _ordered_effects(frame.loc[frame["dataset_scope"].astype(str).eq("FREDDIE")])
    merged = hc[["effect_label", "partial_eta_squared", "f_statistic", "p_value_display"]].merge(
        fr[["effect_label", "partial_eta_squared", "f_statistic", "p_value_display"]],
        on="effect_label", suffixes=("_hc", "_fr"), validate="one_to_one"
    )
    rows_for_overview = []
    for row in merged.to_dict(orient="records"):
        rows_for_overview.append({
            "effect": row["effect_label"],
            "home_credit_partial_eta_squared": row["partial_eta_squared_hc"],
            "home_credit_f_statistic": row["f_statistic_hc"],
            "home_credit_p_value_display": row["p_value_display_hc"],
            "freddie_partial_eta_squared": row["partial_eta_squared_fr"],
            "freddie_f_statistic": row["f_statistic_fr"],
            "freddie_p_value_display": row["p_value_display_fr"],
        })
    return overview_major_effects(rows_for_overview, cross_dataset=True)


def effectiveness_contrast_plot(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool, family: str = "evidence_vs_s0") -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()
    if family != "all":
        frame = frame.loc[frame["contrast_family"].astype(str).eq(family)]
    frame = frame.copy()
    labels = list(dict.fromkeys(frame["contrast_label"].astype(str)))
    height = min(620, max(350, 150 + 18 * len(labels)))

    def add_dataset(figure: go.Figure, local: pd.DataFrame, *, col: int | None = None, show_y: bool = True):
        local = local.set_index("contrast_label").reindex(labels).reset_index()
        symbols = ["circle" if bool(v) else "circle-open" for v in local["significant_adjusted"]]
        trace = go.Scatter(
            x=local["mean_difference"], y=local["contrast_label"], mode="markers",
            marker={"size": 9, "symbol": symbols, "color": "#0F766E" if col in (None, 2) else "#4F46E5", "line": {"width": 1.4}},
            customdata=list(zip(local["adjusted_p_display"], local["rank_biserial_correlation"], local["planned_pair_count"], local["observed_pair_count"], local["excluded_pair_count"], local["significant_adjusted"])),
            hovertemplate=("<b>%{y}</b><br>Mean Δ: <b>%{x:.4f}</b><br>Holm-adjusted p: %{customdata[0]}<br>"
                           "Rank-biserial: %{customdata[1]:.3f}<br>Pairs: %{customdata[3]}/%{customdata[2]} · Excluded: %{customdata[4]}<br>"
                           "Adjusted significant: %{customdata[5]}<extra></extra>"),
            showlegend=False,
        )
        if col is None:
            figure.add_trace(trace)
        else:
            figure.add_trace(trace, row=1, col=col)
        return figure

    if not cross_dataset:
        figure = go.Figure()
        add_dataset(figure, frame)
        figure.add_vline(x=0, line={"color": "#98A2B3", "width": 1.2, "dash": "dot"})
        figure.update_yaxes(categoryorder="array", categoryarray=labels, autorange="reversed", fixedrange=True, tickfont={"size": 9})
        figure.update_xaxes(title="Mean Δ", zeroline=False, fixedrange=True, gridcolor="#EAECF0")
        return _base_layout(figure, height=height, margin={"l": 245, "r": 28, "t": 24, "b": 48})

    figure = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.08)
    add_dataset(figure, frame.loc[frame["dataset_scope"].astype(str).eq("HOME_CREDIT")], col=1)
    add_dataset(figure, frame.loc[frame["dataset_scope"].astype(str).eq("FREDDIE")], col=2)
    figure.add_vline(x=0, line={"color": "#98A2B3", "width": 1.2, "dash": "dot"}, row=1, col=1)
    figure.add_vline(x=0, line={"color": "#98A2B3", "width": 1.2, "dash": "dot"}, row=1, col=2)
    figure.update_yaxes(categoryorder="array", categoryarray=labels, autorange="reversed", fixedrange=True, tickfont={"size": 8})
    figure.update_xaxes(title="Mean Δ", zeroline=False, fixedrange=True, gridcolor="#EAECF0")
    figure.add_annotation(x=0.235, y=1.055, xref="paper", yref="paper", text="<b>Home Credit</b>", showarrow=False)
    figure.add_annotation(x=0.765, y=1.055, xref="paper", yref="paper", text="<b>Freddie Mac</b>", showarrow=False)
    return _base_layout(figure, height=height, margin={"l": 240, "r": 26, "t": 48, "b": 48})


# ============================================================================
# Page 3 — Mechanisms diagnostic redesign
# ============================================================================


def mechanism_faithfulness_accounting(rows: Iterable[Mapping[str, object]]) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    figure = go.Figure()
    if frame.empty:
        return figure
    components = (
        ("primary_e2e", "End-to-End Faithfulness", "#0F766E"),
        ("pipeline_loss", "Pipeline loss", "#98A2B3"),
        ("not_verifiable_loss", "NOT_VERIFIABLE loss", "#D69E2E"),
        ("unsupported_loss", "UNSUPPORTED loss", "#C2410C"),
        ("contradiction_loss", "CONTRADICTED loss", "#B42318"),
    )
    for column, label, color in components:
        figure.add_trace(go.Bar(
            name=label, orientation="h", y=frame["dataset_label"], x=frame[column], marker={"color": color},
            customdata=list(zip(frame["dataset_scope"], frame[f"{column}_display"] if f"{column}_display" in frame else frame[column])),
            hovertemplate=f"<b>{label}</b><br>%{{y}}: <b>%{{x:.2%}}</b><extra></extra>",
        ))
    figure.update_layout(barmode="stack", legend={"orientation": "h", "y": 1.23, "x": 0, "font": {"size": 9}})
    figure.update_xaxes(range=[0, 1], tickformat=".0%", dtick=0.2, fixedrange=True, title=None, gridcolor="#EAECF0")
    figure.update_yaxes(autorange="reversed", fixedrange=True, title=None)
    return _base_layout(figure, height=305 if len(frame) > 1 else 275, margin={"l": 100, "r": 18, "t": 62, "b": 38})


def mechanism_lexical_signal(rows: Iterable[Mapping[str, object]]) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()
    figure = go.Figure()
    if len(frame) == 1:
        row = frame.iloc[0]
        figure.add_shape(type="line", x0=0, x1=float(row["safe_phrase_matched_claim_rate"]), y0=0, y1=0, line={"color": "#D0D5DD", "width": 3})
        figure.add_trace(go.Scatter(x=[float(row["safe_phrase_matched_claim_rate"])], y=[0], mode="markers+text", text=[row["safe_phrase_matched_claim_rate_display"]], textposition="middle right", marker={"size": 12, "color": "#4F46E5"}, hovertemplate="Lexical-overlap signal: <b>%{x:.2%}</b><extra></extra>"))
    else:
        ordered = frame.set_index("dataset_scope")
        hc = float(ordered.loc["HOME_CREDIT", "safe_phrase_matched_claim_rate"])
        fr = float(ordered.loc["FREDDIE", "safe_phrase_matched_claim_rate"])
        figure.add_shape(type="line", x0=min(hc, fr), x1=max(hc, fr), y0=0, y1=0, line={"color": "#D0D5DD", "width": 4})
        figure.add_trace(go.Scatter(x=[hc], y=[0], mode="markers", name="Home Credit", marker={"size": 12, "color": _DATASET_COLORS["HOME_CREDIT"]}, hovertemplate="Home Credit: <b>%{x:.2%}</b><extra></extra>"))
        figure.add_trace(go.Scatter(x=[fr], y=[0], mode="markers", name="Freddie Mac", marker={"size": 12, "color": _DATASET_COLORS["FREDDIE"]}, hovertemplate="Freddie Mac: <b>%{x:.2%}</b><extra></extra>"))
        figure.update_layout(legend={"orientation": "h", "y": 1.18, "x": 0, "font": {"size": 9}})
    figure.update_xaxes(range=[0, 1], tickformat=".0%", dtick=0.2, title=None, fixedrange=True, gridcolor="#EAECF0")
    figure.update_yaxes(visible=False, fixedrange=True, range=[-0.6, 0.6])
    return _base_layout(figure, height=195, margin={"l": 24, "r": 34, "t": 42, "b": 36})


def mechanism_claim_matrix(
    rows: Iterable[Mapping[str, object]], *, cross_dataset: bool, measure: str = "share",
    claim_type: str | None = None, validation_status: str | None = None,
) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()
    if claim_type and claim_type != "ALL":
        frame = frame.loc[frame["claim_type"].astype(str).eq(claim_type)]
    statuses = [validation_status] if validation_status and validation_status != "ALL" else list(_CLAIM_STATUS_ORDER)
    all_types = sorted(set(frame["claim_type"].astype(str)))
    datasets = [str(frame.iloc[0]["dataset_scope"])] if not cross_dataset else ["HOME_CREDIT", "FREDDIE"]

    def matrix(scope: str):
        source_all = pd.DataFrame(list(rows))
        source_scope = source_all.loc[source_all["dataset_scope"].astype(str).eq(scope)]
        present_types = set(source_scope["claim_type"].astype(str))
        local = frame.loc[frame["dataset_scope"].astype(str).eq(scope)]
        z, text, custom = [], [], []
        for claim in all_types:
            row_values, row_text, row_custom = [], [], []
            claim_source = source_scope.loc[source_scope["claim_type"].astype(str).eq(claim)]
            total = int(claim_source["claim_count"].sum())
            local_type = local.loc[local["claim_type"].astype(str).eq(claim)]
            for status in statuses:
                if claim not in present_types:
                    value = None
                    count = None
                    share = None
                    label = "N/A"
                else:
                    matched = local_type.loc[local_type["validation_status"].astype(str).eq(status)]
                    count = int(matched["claim_count"].sum()) if not matched.empty else 0
                    share = (count / total) if total else 0.0
                    value = share if measure == "share" else count
                    label = f"{share:.0%}" if measure == "share" else f"{count:,}"
                row_values.append(value)
                row_text.append(label)
                row_custom.append([scope, claim, status, count, total, share])
            z.append(row_values); text.append(row_text); custom.append(row_custom)
        return z, text, custom

    matrices = {scope: matrix(scope) for scope in datasets}
    if measure == "share":
        zmax = 1.0
        colorscale = _E2E_COLORSCALE
        colorbar = {"title": "Share", "tickformat": ".0%", "thickness": 10}
    else:
        numeric = [v for scope in datasets for row in matrices[scope][0] for v in row if v is not None]
        zmax = max(numeric) if numeric else 1
        colorscale = "Blues"
        colorbar = {"title": "Claims", "thickness": 10}

    def trace_for(scope: str, label: str, showscale: bool):
        z, text, custom = matrices[scope]
        return go.Heatmap(
            z=z, x=statuses, y=all_types, zmin=0, zmax=zmax, colorscale=colorscale, showscale=showscale,
            colorbar=colorbar if showscale else None, text=text, texttemplate="%{text}", xgap=3, ygap=3,
            customdata=custom,
            hovertemplate=(f"<b>{label}</b><br>Claim type: %{{customdata[1]}}<br>Status: %{{customdata[2]}}<br>"
                           "Claims: %{customdata[3]}<br>Total type claims: %{customdata[4]}<br>Share within claim type: %{customdata[5]:.2%}<extra>Click để audit</extra>"),
        )

    if not cross_dataset:
        scope = datasets[0]
        figure = go.Figure(trace_for(scope, "Home Credit" if scope == "HOME_CREDIT" else "Freddie Mac", True))
        figure.update_yaxes(autorange="reversed", fixedrange=True, tickfont={"size": 9})
        figure.update_xaxes(side="top", fixedrange=True, tickfont={"size": 9})
        return _base_layout(figure, height=max(330, min(455, 165 + 23 * len(all_types))), margin={"l": 170, "r": 54, "t": 48, "b": 24})

    figure = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.06)
    figure.add_trace(trace_for("HOME_CREDIT", "Home Credit", False), row=1, col=1)
    fr_trace = trace_for("FREDDIE", "Freddie Mac", True)
    fr_trace.colorbar.x = 1.025
    figure.add_trace(fr_trace, row=1, col=2)
    figure.update_yaxes(autorange="reversed", fixedrange=True, tickfont={"size": 8})
    figure.update_xaxes(side="top", fixedrange=True, tickfont={"size": 8}, tickangle=-18)
    figure.add_annotation(x=0.235, y=1.115, xref="paper", yref="paper", text="<b>Home Credit</b>", showarrow=False)
    figure.add_annotation(x=0.765, y=1.115, xref="paper", yref="paper", text="<b>Freddie Mac</b>", showarrow=False)
    return _base_layout(figure, height=max(350, min(475, 185 + 23 * len(all_types))), margin={"l": 165, "r": 54, "t": 72, "b": 28})


def mechanism_quality_map(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return go.Figure()
    datasets = [(None, None)] if not cross_dataset else [("HOME_CREDIT", "Home Credit"), ("FREDDIE", "Freddie Mac")]
    figure = go.Figure() if not cross_dataset else make_subplots(rows=1, cols=2, horizontal_spacing=0.075)
    for dataset_index, (scope, label) in enumerate(datasets, start=1):
        local = frame if scope is None else frame.loc[frame["dataset_scope"].astype(str).eq(scope)]
        for model_id in _MODEL_ORDER:
            subset = local.loc[local["model_id"].astype(str).eq(model_id)].sort_values("evidence_level", kind="stable")
            if subset.empty:
                continue
            trace = go.Scatter(
                x=subset["verifiability"], y=subset["resolved_faithfulness"], mode="markers+text",
                text=subset["evidence_level"], textposition="top center", textfont={"size": 9, "color": "#475467"},
                name=_MODEL_LABELS[model_id], legendgroup=model_id, showlegend=(not cross_dataset) or dataset_index == 1,
                marker={"size": 12, "color": _MODEL_COLORS[model_id], "line": {"color": "white", "width": 1.4}},
                customdata=list(zip(subset["dataset_scope"], subset["model_id"], subset["model_label"], subset["evidence_level"], subset["conservative_faithfulness"], subset["end_to_end_faithfulness_yield"])),
                hovertemplate=("<b>%{customdata[2]} × %{customdata[3]}</b><br>" + ((f"{label}<br>") if label else "") +
                               "Verifiability: <b>%{x:.2%}</b><br>Resolved Faithfulness: <b>%{y:.2%}</b><br>"
                               "Conservative Faithfulness: %{customdata[4]:.2%}<br>End-to-End Faithfulness: %{customdata[5]:.2%}<extra>Click để xem option</extra>"),
            )
            if cross_dataset:
                figure.add_trace(trace, row=1, col=dataset_index)
            else:
                figure.add_trace(trace)
    figure.update_xaxes(title="Verifiability", range=[0, 1.02], tickformat=".0%", dtick=0.2, fixedrange=True, gridcolor="#EAECF0")
    figure.update_yaxes(title="Resolved Faithfulness", range=[0, 1.02], tickformat=".0%", dtick=0.2, fixedrange=True, gridcolor="#EAECF0")
    if cross_dataset:
        figure.add_annotation(x=0.235, y=1.14, xref="paper", yref="paper", text="<b>Home Credit</b>", showarrow=False)
        figure.add_annotation(x=0.765, y=1.14, xref="paper", yref="paper", text="<b>Freddie Mac</b>", showarrow=False)
    figure.update_layout(legend={"orientation": "h", "y": 1.18 if not cross_dataset else 1.24, "x": 0, "font": {"size": 10}})
    return _base_layout(figure, height=420 if not cross_dataset else 438, margin={"l": 72, "r": 24, "t": 72 if cross_dataset else 54, "b": 62})

# ---------------------------------------------------------------------------
# Page 4 — Decision Studio redesign (0052)
# ---------------------------------------------------------------------------

_DECISION_MODEL_COLORS = {
    "qwen3_8b": "#0F766E",
    "deepseek_v4_flash": "#4F46E5",
    "phi4_mini_instruct": "#B54708",
}


def decision_noninferiority_plot(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return _base_layout(go.Figure(), height=360)
    frame = frame.copy()
    frame["candidate_label"] = frame.apply(
        lambda r: f"{r.get('candidate_model_label', r.get('candidate_model_id'))} · {r.get('candidate_evidence_level', '')}",
        axis=1,
    )
    frame["sort_key"] = frame.apply(
        lambda r: (
            0 if str(r.get("candidate_role")) == "PRIMARY" else 1,
            int(str(r.get("candidate_evidence_level", "S9")).replace("S", "") or 9),
            str(r.get("candidate_model_id", "")),
        ),
        axis=1,
    )
    frame = frame.sort_values("sort_key", kind="stable")
    global_max = max(float(frame["upper_one_sided_bound_95"].max()), float(frame["margin"].max()))
    x_max = max(0.12, min(0.48, global_max * 1.08 + 0.01))

    def add_dataset(fig: go.Figure, local: pd.DataFrame, *, row: int | None = None, col: int | None = None, showlegend: bool = True) -> None:
        emitted_legend: set[str] = set()
        for _, rec in local.iterrows():
            label = str(rec["candidate_label"])
            status_name = "NON_INFERIOR" if bool(rec["non_inferior"]) else "INFERIOR"
            kwargs = {"row": row, "col": col} if row is not None and col is not None else {}
            fig.add_trace(
                go.Scatter(
                    x=[float(rec["mean_reference_minus_candidate"]), float(rec["upper_one_sided_bound_95"])],
                    y=[label, label],
                    mode="lines",
                    line={"color": "#D0D5DD", "width": 2},
                    hoverinfo="skip",
                    showlegend=False,
                ),
                **kwargs,
            )
            fig.add_trace(
                go.Scatter(
                    x=[float(rec["upper_one_sided_bound_95"])],
                    y=[label],
                    mode="markers",
                    marker={
                        "size": 10,
                        "color": "#0F766E" if bool(rec["non_inferior"]) else "#FFFFFF",
                        "line": {"color": "#0F766E" if bool(rec["non_inferior"]) else "#667085", "width": 2},
                        "symbol": "circle",
                    },
                    customdata=[[str(rec.get("dataset_scope")), str(rec["candidate_option_id"]), str(rec.get("candidate_model_id")), str(rec.get("candidate_evidence_level")), str(rec["reference_option_id"]), float(rec["mean_reference_minus_candidate"]), float(rec["upper_one_sided_bound_95"]), float(rec["margin"]), str(rec["status"]), int(rec["paired_case_count"]) ]],
                    name=status_name,
                    legendgroup="ni" if bool(rec["non_inferior"]) else "inferior",
                    showlegend=showlegend and status_name not in emitted_legend,
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Upper one-sided 95% bound: <b>%{x:.4f}</b><br>"
                        "Mean reference − candidate: %{customdata[5]:.4f}<br>"
                        "Certified margin: δ=%{customdata[7]:.2f}<br>"
                        "Paired cases: %{customdata[9]}<br>"
                        "Status: %{customdata[8]}<extra>Click để xem evidence</extra>"
                    ),
                ),
                **kwargs,
            )
            emitted_legend.add(status_name)

    if not cross_dataset:
        figure = go.Figure()
        add_dataset(figure, frame)
        margin = float(frame.iloc[0]["margin"])
        figure.add_vline(x=margin, line_dash="dash", line_color="#B42318", line_width=1.5, annotation_text=f"δ={margin:.2f}", annotation_position="top right")
        figure.update_xaxes(range=[0, x_max], title="Upper one-sided 95% bound", fixedrange=True)
        figure.update_yaxes(autorange="reversed", fixedrange=True, tickfont={"size": 10})
        return _base_layout(figure, height=500, margin={"l": 190, "r": 34, "t": 50, "b": 48})

    figure = make_subplots(rows=1, cols=2, shared_xaxes=True, horizontal_spacing=0.08, subplot_titles=("Home Credit", "Freddie Mac"))
    for col, scope in ((1, "HOME_CREDIT"), (2, "FREDDIE")):
        local = frame.loc[frame["dataset_scope"].astype(str).eq(scope)].reset_index(drop=True)
        add_dataset(figure, local, row=1, col=col, showlegend=col == 1)
        margin = float(local.iloc[0]["margin"])
        xref = "x" if col == 1 else "x2"
        figure.add_shape(type="line", x0=margin, x1=margin, y0=0, y1=1, xref=xref, yref="paper", line={"color": "#B42318", "dash": "dash", "width": 1.5})
    figure.update_xaxes(range=[0, x_max], title="Upper 95% bound", fixedrange=True)
    figure.update_yaxes(autorange="reversed", fixedrange=True, tickfont={"size": 9})
    figure.update_layout(annotations=[*figure.layout.annotations, dict(x=0.5, y=1.08, xref="paper", yref="paper", text="Dashed reference = certified δ=0.03", showarrow=False, font={"size": 10, "color": "#667085"})])
    return _base_layout(figure, height=520, margin={"l": 170, "r": 34, "t": 80, "b": 46})


def _decision_scatter_trace(frame: pd.DataFrame, *, x: str, y: str, selected_option: str | None, name: str) -> list[go.Scatter]:
    traces: list[go.Scatter] = []
    for model_id in _MODEL_ORDER:
        local = frame.loc[frame["model_id"].astype(str).eq(model_id)].copy()
        if local.empty:
            continue
        custom = []
        sizes = []
        widths = []
        for _, rec in local.iterrows():
            option_id = str(rec["option_id"])
            custom.append([
                option_id,
                str(rec["model_id"]),
                str(rec.get("model_label") or _MODEL_LABELS.get(model_id, model_id)),
                str(rec["evidence_level"]),
                str(rec.get("dataset_scope")),
                str(rec.get("dataset_label")),
                str(rec.get("option_role")),
                bool(rec.get("hard_gate_pass")),
                bool(rec.get("non_inferior")),
                bool(rec.get("robust_eligible")),
                float(rec.get("mean_e2e", 0)),
                float(rec.get("p10_e2e", 0)),
                float(rec.get("mean_total_tokens", 0)),
            ])
            selected = option_id == selected_option
            sizes.append(15 if selected else 10)
            widths.append(3 if selected else 1.2)
        traces.append(
            go.Scatter(
                x=local[x],
                y=local[y],
                mode="markers+text",
                text=local["evidence_level"],
                textposition="top center",
                textfont={"size": 9, "color": "#667085"},
                marker={
                    "size": sizes,
                    "color": _DECISION_MODEL_COLORS.get(model_id, "#475467"),
                    "opacity": 0.86,
                    "line": {"color": "#FFFFFF", "width": widths},
                },
                customdata=custom,
                name=_MODEL_LABELS.get(model_id, model_id),
                hovertemplate=(
                    "<b>%{customdata[2]} · %{customdata[3]}</b><br>"
                    "%{customdata[5]}<br>"
                    "Quality: %{customdata[10]:.2%}<br>"
                    "P10 reliability: %{customdata[11]:.2%}<br>"
                    "Token burden: %{customdata[12]:,.0f}<br>"
                    "Role: %{customdata[6]}<br>"
                    "Hard gate: %{customdata[7]} · NI: %{customdata[8]}<br>"
                    "Robust eligible: %{customdata[9]}<extra>Click để xem option</extra>"
                ),
            )
        )
    return traces


def decision_quality_reliability_plot(rows: Iterable[Mapping[str, object]], *, selected_option: str | None = None) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    figure = go.Figure()
    if frame.empty:
        return _base_layout(figure, height=410)
    for trace in _decision_scatter_trace(frame, x="mean_e2e", y="p10_e2e", selected_option=selected_option, name="quality_reliability"):
        figure.add_trace(trace)
    figure.update_xaxes(range=[0, 1.02], tickformat=".0%", title="Decision quality basis", fixedrange=True)
    figure.update_yaxes(range=[0, 1.02], tickformat=".0%", title="P10 reliability", fixedrange=True)
    figure.update_layout(legend={"orientation": "h", "y": -0.20, "x": 0})
    return _base_layout(figure, height=420, margin={"l": 62, "r": 24, "t": 42, "b": 86})


def decision_quality_efficiency_plot(rows: Iterable[Mapping[str, object]], *, selected_option: str | None = None) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    figure = go.Figure()
    if frame.empty:
        return _base_layout(figure, height=410)
    for trace in _decision_scatter_trace(frame, x="mean_total_tokens", y="mean_e2e", selected_option=selected_option, name="quality_efficiency"):
        figure.add_trace(trace)
    max_tokens = max(1000.0, float(frame["mean_total_tokens"].max()) * 1.08)
    figure.update_xaxes(range=[0, max_tokens], title="Certified token burden", fixedrange=True, tickformat=",.0f")
    figure.update_yaxes(range=[0, 1.02], tickformat=".0%", title="Decision quality basis", fixedrange=True)
    figure.update_layout(legend={"orientation": "h", "y": -0.20, "x": 0})
    return _base_layout(figure, height=420, margin={"l": 62, "r": 24, "t": 42, "b": 86})


# ---------------------------------------------------------------------------
# Page 5 — Robustness redesign (0053)
# ---------------------------------------------------------------------------


def robustness_effect_dumbbell(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return _base_layout(go.Figure(), height=320)
    effect_labels = {"model": "Model", "evidence": "Evidence", "model:evidence": "Model × Evidence"}
    frame["effect_label"] = frame["effect"].astype(str).map(effect_labels).fillna(frame["effect"].astype(str))

    def add_local(fig: go.Figure, local: pd.DataFrame, *, row: int | None = None, col: int | None = None, showlegend: bool = True) -> None:
        kwargs = {"row": row, "col": col} if row is not None and col is not None else {}
        for _, rec in local.iterrows():
            label = str(rec["effect_label"])
            fig.add_trace(go.Scatter(x=[float(rec["partial_eta_squared_primary"]), float(rec["partial_eta_squared_complete_case"])], y=[label, label], mode="lines", line={"color": "#D0D5DD", "width": 3}, hoverinfo="skip", showlegend=False), **kwargs)
        fig.add_trace(
            go.Scatter(
                x=local["partial_eta_squared_primary"], y=local["effect_label"], mode="markers",
                marker={"size": 10, "color": "#4F46E5"}, name="Primary",
                customdata=[[str(r["dataset_scope"]), str(r["effect"]), int(r["subject_count_primary"]), float(r["p_value_used_primary"]), bool(r["significant_primary"])] for _, r in local.iterrows()],
                hovertemplate="<b>%{y}</b><br>Primary Partial η²: <b>%{x:.3f}</b><br>N: %{customdata[2]}<br>p: %{customdata[3]:.4g}<br>Significant: %{customdata[4]}<extra></extra>",
                showlegend=showlegend,
            ), **kwargs,
        )
        fig.add_trace(
            go.Scatter(
                x=local["partial_eta_squared_complete_case"], y=local["effect_label"], mode="markers",
                marker={"size": 10, "color": "#0F766E", "symbol": "diamond"}, name="Complete-case",
                customdata=[[str(r["dataset_scope"]), str(r["effect"]), int(r["subject_count_complete_case"]), float(r["p_value_used_complete_case"]), bool(r["significant_complete_case"]), float(r["partial_eta_squared_delta_complete_minus_primary"]), bool(r["significance_conclusion_stable"])] for _, r in local.iterrows()],
                hovertemplate="<b>%{y}</b><br>Complete-case Partial η²: <b>%{x:.3f}</b><br>N: %{customdata[2]}<br>p: %{customdata[3]:.4g}<br>Δ η²: %{customdata[5]:+.3f}<br>Significance stable: %{customdata[6]}<extra></extra>",
                showlegend=showlegend,
            ), **kwargs,
        )

    if not cross_dataset:
        figure = go.Figure()
        add_local(figure, frame)
        figure.update_xaxes(range=[0, 1], title="Partial η²", fixedrange=True)
        figure.update_yaxes(autorange="reversed", fixedrange=True)
        figure.update_layout(legend={"orientation": "h", "y": -0.22})
        return _base_layout(figure, height=320, margin={"l": 120, "r": 24, "t": 35, "b": 72})

    figure = make_subplots(rows=1, cols=2, shared_xaxes=True, shared_yaxes=True, horizontal_spacing=0.08, subplot_titles=("Home Credit", "Freddie Mac"))
    for col, scope in ((1, "HOME_CREDIT"), (2, "FREDDIE")):
        local = frame.loc[frame["dataset_scope"].astype(str).eq(scope)]
        add_local(figure, local, row=1, col=col, showlegend=col == 1)
    figure.update_xaxes(range=[0, 1], title="Partial η²", fixedrange=True)
    figure.update_yaxes(autorange="reversed", fixedrange=True)
    figure.update_layout(legend={"orientation": "h", "y": -0.20})
    return _base_layout(figure, height=350, margin={"l": 112, "r": 24, "t": 62, "b": 72})


def robustness_contrast_stability_map(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return _base_layout(go.Figure(), height=430)
    max_abs = max(float(frame["mean_difference_primary"].abs().max()), float(frame["mean_difference_complete_case"].abs().max()), 0.10)
    bound = min(1.0, max_abs * 1.12)

    def traces_for(local: pd.DataFrame, showlegend: bool) -> list[go.Scatter]:
        traces: list[go.Scatter] = []
        groups = (
            (True, True, "Stable direction + significance", "circle", "#0F766E"),
            (False, True, "Direction changed", "diamond", "#B54708"),
            (True, False, "Significance changed", "circle-open", "#4F46E5"),
            (False, False, "Direction + significance changed", "diamond-open", "#B42318"),
        )
        for direction_stable, significance_stable, label, symbol, color in groups:
            subset = local.loc[
                local["direction_stable"].astype(bool).eq(direction_stable)
                & local["significance_conclusion_stable"].astype(bool).eq(significance_stable)
            ]
            if subset.empty:
                continue
            custom = [[str(r["dataset_scope"]), str(r["contrast_id"]), str(r["contrast_family"]), float(r["adjusted_p_value_primary"]), float(r["adjusted_p_value_complete_case"]), bool(r["direction_stable"]), bool(r["significance_conclusion_stable"]), bool(r["significant_adjusted_primary"]), bool(r["significant_adjusted_complete_case"])] for _, r in subset.iterrows()]
            traces.append(go.Scatter(
                x=subset["mean_difference_primary"], y=subset["mean_difference_complete_case"], mode="markers",
                marker={"size": 9, "symbol": symbol, "color": color, "line": {"color": color, "width": 1.5}},
                customdata=custom, name=label, showlegend=showlegend,
                hovertemplate=(
                    "<b>%{customdata[1]}</b><br>"
                    "Primary mean Δ: %{x:+.4f}<br>Complete-case mean Δ: %{y:+.4f}<br>"
                    "Primary Holm p: %{customdata[3]:.4g}<br>Complete Holm p: %{customdata[4]:.4g}<br>"
                    "Direction stable: %{customdata[5]}<br>Significance stable: %{customdata[6]}<extra>Click để xem exact sensitivity</extra>"
                ),
            ))
        return traces

    if not cross_dataset:
        figure = go.Figure()
        for trace in traces_for(frame, True): figure.add_trace(trace)
        figure.add_shape(type="line", x0=-bound, x1=bound, y0=-bound, y1=bound, line={"color": "#98A2B3", "dash": "dash", "width": 1})
        figure.add_hline(y=0, line_color="#EAECF0", line_width=1)
        figure.add_vline(x=0, line_color="#EAECF0", line_width=1)
        figure.update_xaxes(range=[-bound, bound], title="Primary mean Δ", fixedrange=True)
        figure.update_yaxes(range=[-bound, bound], title="Complete-case mean Δ", fixedrange=True)
        figure.update_layout(legend={"orientation": "h", "y": -0.24})
        return _base_layout(figure, height=470, margin={"l": 66, "r": 26, "t": 42, "b": 96})

    figure = make_subplots(rows=1, cols=2, shared_xaxes=True, shared_yaxes=True, horizontal_spacing=0.07, subplot_titles=("Home Credit", "Freddie Mac"))
    for col, scope in ((1, "HOME_CREDIT"), (2, "FREDDIE")):
        local = frame.loc[frame["dataset_scope"].astype(str).eq(scope)]
        for trace in traces_for(local, col == 1): figure.add_trace(trace, row=1, col=col)
        xref = "x" if col == 1 else "x2"; yref = "y" if col == 1 else "y2"
        figure.add_shape(type="line", x0=-bound, x1=bound, y0=-bound, y1=bound, xref=xref, yref=yref, line={"color": "#98A2B3", "dash": "dash", "width": 1})
    figure.update_xaxes(range=[-bound, bound], title="Primary mean Δ", fixedrange=True, zeroline=True, zerolinecolor="#EAECF0")
    figure.update_yaxes(range=[-bound, bound], title="Complete-case mean Δ", fixedrange=True, zeroline=True, zerolinecolor="#EAECF0")
    figure.update_layout(legend={"orientation": "h", "y": -0.22})
    return _base_layout(figure, height=500, margin={"l": 64, "r": 22, "t": 66, "b": 104})


def robustness_rank_shift_heatmap(rows: Iterable[Mapping[str, object]], *, cross_dataset: bool) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return _base_layout(go.Figure(), height=450)
    metric_labels = {
        "resolved_faithfulness": "Resolved",
        "verifiability": "Verifiability",
        "conservative_faithfulness": "Conservative",
    }
    frame = frame.loc[frame["metric_id"].astype(str).isin(metric_labels)].copy()
    frame["metric_label"] = frame["metric_id"].astype(str).map(metric_labels)
    frame["option_label"] = frame.apply(lambda r: f"{r.get('model_label', r['model_id'])} · {r['evidence_level']}", axis=1)
    frame["sort_model"] = frame["model_id"].astype(str).map({m: i for i, m in enumerate(_MODEL_ORDER)}).fillna(99)
    frame["sort_evidence"] = frame["evidence_level"].astype(str).str.replace("S", "", regex=False).astype(int)
    z_bound = 18

    def matrix(local: pd.DataFrame):
        ordered = local[["option_id", "option_label", "model_id", "evidence_level", "sort_model", "sort_evidence"]].drop_duplicates().sort_values(["sort_model", "sort_evidence"], kind="stable")
        option_ids = list(ordered["option_id"])
        labels = list(ordered["option_label"])
        metrics = [m for m in ("resolved_faithfulness", "verifiability", "conservative_faithfulness") if m in set(local["metric_id"].astype(str))]
        pivot = local.set_index(["option_id", "metric_id"])
        z=[]; custom=[]; text=[]
        for oid in option_ids:
            zr=[]; cr=[]; tr=[]
            for metric_id in metrics:
                rec = pivot.loc[(oid, metric_id)]
                if isinstance(rec, pd.DataFrame): rec = rec.iloc[0]
                shift=int(rec["rank_shift_vs_primary"])
                zr.append(shift); tr.append(f"{shift:+d}")
                cr.append([str(rec["dataset_scope"]), str(oid), str(rec["model_id"]), str(rec["evidence_level"]), str(metric_id), int(rec["primary_rank"]), int(rec["quality_rank"]), shift, float(rec["metric_mean"])])
            z.append(zr); custom.append(cr); text.append(tr)
        return labels, metrics, z, custom, text

    colorscale=[[0.0,"#1D4ED8"],[0.48,"#DBEAFE"],[0.5,"#FFFFFF"],[0.52,"#FEE2E2"],[1.0,"#B42318"]]
    if not cross_dataset:
        labels, metrics, z, custom, text = matrix(frame)
        figure=go.Figure(go.Heatmap(z=z,x=[metric_labels[m] for m in metrics],y=labels,customdata=custom,zmin=-z_bound,zmax=z_bound,zmid=0,colorscale=colorscale,colorbar={"title":"Rank shift","thickness":10,"len":0.76,"outlinewidth":0},text=text,texttemplate="%{text}",textfont={"size":10},xgap=4,ygap=2,hovertemplate="<b>%{y} · %{x}</b><br>Primary rank: %{customdata[5]}<br>Sensitivity rank: %{customdata[6]}<br>Rank shift: %{customdata[7]:+d}<br>Metric mean: %{customdata[8]:.2%}<extra>Certified 18-option rank</extra>"))
        figure.update_xaxes(side="top", fixedrange=True); figure.update_yaxes(autorange="reversed", fixedrange=True, tickfont={"size":9})
        return _base_layout(figure,height=560,margin={"l":180,"r":54,"t":58,"b":24})

    figure=make_subplots(rows=1,cols=2,shared_yaxes=True,horizontal_spacing=0.06,subplot_titles=("Home Credit","Freddie Mac"))
    for col,scope in ((1,"HOME_CREDIT"),(2,"FREDDIE")):
        local=frame.loc[frame["dataset_scope"].astype(str).eq(scope)]
        labels,metrics,z,custom,text=matrix(local)
        figure.add_trace(go.Heatmap(z=z,x=[metric_labels[m] for m in metrics],y=labels,customdata=custom,zmin=-z_bound,zmax=z_bound,zmid=0,colorscale=colorscale,showscale=col==2,colorbar={"title":"Rank shift","thickness":10,"len":0.72,"x":1.025,"outlinewidth":0},text=text,texttemplate="%{text}",textfont={"size":9},xgap=4,ygap=2,hovertemplate="<b>%{y} · %{x}</b><br>Primary rank: %{customdata[5]}<br>Sensitivity rank: %{customdata[6]}<br>Rank shift: %{customdata[7]:+d}<br>Metric mean: %{customdata[8]:.2%}<extra>Certified 18-option rank</extra>"),row=1,col=col)
    figure.update_xaxes(side="top",fixedrange=True,tickfont={"size":9}); figure.update_yaxes(autorange="reversed",fixedrange=True,tickfont={"size":8})
    return _base_layout(figure,height=590,margin={"l":170,"r":54,"t":70,"b":24})


def robustness_margin_sensitivity_plot(rows: Iterable[Mapping[str, object]], *, selected_margin: float = 0.03) -> go.Figure:
    frame = pd.DataFrame(list(rows)).sort_values("margin")
    figure = go.Figure()
    if frame.empty:
        return _base_layout(figure, height=300)
    sizes=[18 if abs(float(m)-float(selected_margin))<1e-9 else 11 for m in frame["margin"]]
    symbols=["diamond" if str(status)=="PRIMARY_CERTIFIED" else "circle" for status in frame["analysis_status"]]
    colors=["#0F766E" if str(status)=="PRIMARY_CERTIFIED" else "#667085" for status in frame["analysis_status"]]
    custom=[]
    for _,r in frame.iterrows():
        ids=r.get("robust_eligible_option_ids")
        custom.append([str(r["margin_lane_id"]),str(r["analysis_status"]),str(r["active_pool_mode"]),"—" if pd.isna(ids) else str(ids),int(r["robust_primary_candidate_count"]),int(r["robust_fallback_candidate_count"])])
    figure.add_trace(go.Scatter(x=frame["margin"],y=frame["robust_primary_candidate_count"],mode="lines+markers+text",text=[str(int(v)) for v in frame["robust_primary_candidate_count"]],textposition="top center",line={"color":"#98A2B3","width":2},marker={"size":sizes,"symbol":symbols,"color":colors,"line":{"color":"#FFFFFF","width":2}},customdata=custom,hovertemplate="<b>δ=%{x:.2f}</b><br>Robust primary candidates: <b>%{y}</b><br>Lane: %{customdata[0]}<br>Analysis role: %{customdata[1]}<br>Pool: %{customdata[2]}<br>Eligible IDs: %{customdata[3]}<extra>Click để xem lane</extra>"))
    figure.add_vline(x=0.03,line_dash="dash",line_color="#0F766E",line_width=1.5,annotation_text="PRIMARY δ=0.03",annotation_position="top left")
    figure.update_xaxes(tickvals=[0.02,0.03,0.05],ticktext=["0.02","0.03 PRIMARY","0.05"],range=[0.015,0.055],title="Certified NI margin lane",fixedrange=True)
    figure.update_yaxes(range=[-0.15,max(2.5,float(frame["robust_primary_candidate_count"].max())+0.6)],dtick=1,title="Robust candidate count",fixedrange=True)
    return _base_layout(figure,height=330,margin={"l":66,"r":24,"t":54,"b":54})

# ---------------------------------------------------------------------------
# Page 6 — Case Explorer (0055)
# ---------------------------------------------------------------------------

def cases_performance_landscape(rows: Iterable[Mapping[str, object]], *, selected_generation_id: str | None = None) -> go.Figure:
    """Render the certified 3×6 case landscape with a deterministic click layer.

    The Heatmap remains the visual encoding.  A transparent Scatter trace is
    layered above *usable* cells only so Dash/Plotly exposes real SVG point
    targets for clickData.  This avoids relying on coordinate clicks against
    Plotly's drag layer, which can hover a heatmap cell without producing a
    stable plotly_click event in browser automation/runtime combinations.
    """
    frame = pd.DataFrame(list(rows))
    figure = go.Figure()
    if frame.empty:
        return _base_layout(figure, height=330)
    frame = frame.sort_values(["model_order", "evidence_order"], kind="stable")
    case_ids = tuple(frame["case_id"].astype(str).unique())
    if len(case_ids) != 1:
        raise ValueError("Case landscape requires exactly one canonical case")

    z: list[list[float | None]] = []
    text: list[list[str]] = []
    custom: list[list[list[object]]] = []
    click_x: list[str] = []
    click_y: list[str] = []
    click_custom: list[list[object]] = []
    for model_id in _MODEL_ORDER:
        subset = frame.loc[frame["model_id"].astype(str).eq(model_id)].set_index("evidence_level")
        z_row: list[float | None] = []
        text_row: list[str] = []
        custom_row: list[list[object]] = []
        for evidence in _EVIDENCE_ORDER:
            rec = subset.loc[evidence]
            if isinstance(rec, pd.DataFrame):
                rec = rec.iloc[0]
            unusable = bool(rec.get("is_unusable", False))
            value = None if unusable or pd.isna(rec.get("end_to_end_faithfulness_yield")) else float(rec["end_to_end_faithfulness_yield"])
            generation_id = str(rec["generation_id"])
            meta = [
                str(rec["dataset_scope"]),
                str(rec["case_id"]),
                str(rec["model_id"]),
                str(evidence),
                generation_id,
                "UNUSABLE" if unusable else "USABLE",
                int(rec.get("claim_count", 0)),
                str(rec.get("runtime_status", "")),
                int(rec.get("total_token_count", 0)) if pd.notna(rec.get("total_token_count")) else 0,
                "N/A" if value is None else f"{value:.0%}",
            ]
            z_row.append(value)
            text_row.append(meta[9])
            custom_row.append(meta)
            if value is not None:
                click_x.append(str(evidence))
                click_y.append(_MODEL_LABELS[model_id])
                click_custom.append(meta)
        z.append(z_row)
        text.append(text_row)
        custom.append(custom_row)

    figure.add_trace(go.Heatmap(
        z=z,
        x=list(_EVIDENCE_ORDER),
        y=[_MODEL_LABELS[m] for m in _MODEL_ORDER],
        customdata=custom,
        zmin=0,
        zmax=1,
        colorscale=_E2E_COLORSCALE,
        colorbar={"title": "E2E", "tickformat": ".0%", "thickness": 10, "len": 0.76, "outlinewidth": 0},
        text=text,
        texttemplate="%{text}",
        textfont={"size": 12},
        xgap=5,
        ygap=5,
        hoverongaps=False,
        hovertemplate=(
            "<b>%{y} × %{x}</b><br>"
            "E2E: %{text}<br>"
            "State: %{customdata[5]}<br>"
            "Claims: %{customdata[6]}<br>"
            "Runtime: %{customdata[7]}<br>"
            "Generation: %{customdata[4]}"
            "<extra>Certified case landscape</extra>"
        ),
    ))

    # Interaction trace: one SVG point per usable certified generation.  It is
    # visually transparent but owns hover/click events and the same customdata
    # identity contract as the heatmap cell beneath it.
    figure.add_trace(go.Scatter(
        x=click_x,
        y=click_y,
        mode="markers",
        customdata=click_custom,
        marker={
            "symbol": "square",
            "size": 54,
            "color": "rgba(0,0,0,0.002)",
            "line": {"width": 0},
        },
        showlegend=False,
        cliponaxis=True,
        hovertemplate=(
            "<b>%{y} × %{x}</b><br>"
            "E2E: %{customdata[9]}<br>"
            "State: %{customdata[5]}<br>"
            "Claims: %{customdata[6]}<br>"
            "Runtime: %{customdata[7]}<br>"
            "Generation: %{customdata[4]}"
            "<extra>Click để chọn generation</extra>"
        ),
        name="Certified usable generation",
    ))

    if selected_generation_id:
        selected = frame.loc[frame["generation_id"].astype(str).eq(str(selected_generation_id))]
        if len(selected) == 1:
            rec = selected.iloc[0]
            try:
                evidence_index = _EVIDENCE_ORDER.index(str(rec["evidence_level"]))
                model_index = _MODEL_ORDER.index(str(rec["model_id"]))
            except ValueError:
                evidence_index = model_index = None
            if evidence_index is not None and model_index is not None:
                figure.add_shape(
                    type="rect",
                    x0=evidence_index - 0.48,
                    x1=evidence_index + 0.48,
                    y0=model_index - 0.48,
                    y1=model_index + 0.48,
                    xref="x",
                    yref="y",
                    line={"color": "#101828", "width": 2.4},
                    fillcolor="rgba(0,0,0,0)",
                )
    _style_heatmap_axes(figure)
    figure.update_layout(coloraxis_showscale=False, clickmode="event")
    return _base_layout(figure, height=330, margin={"l": 160, "r": 54, "t": 44, "b": 32})


def cases_validation_composition(rows: Iterable[Mapping[str, object]]) -> go.Figure:
    records = list(rows)
    figure = go.Figure()
    total = int(records[0].get("denominator", 0)) if records else 0
    if total <= 0:
        figure.add_annotation(text="Generation không có certified claim để phân rã.", x=0.5, y=0.5, showarrow=False, font={"color": "#667085"})
        figure.update_xaxes(visible=False); figure.update_yaxes(visible=False)
        return _base_layout(figure, height=220, margin={"l": 20, "r": 20, "t": 20, "b": 20})
    label_map = {
        "SUPPORTED": "Supported",
        "NOT_VERIFIABLE": "Not verifiable",
        "UNSUPPORTED": "Unsupported",
        "CONTRADICTED": "Contradicted",
        "NOT_APPLICABLE": "Not applicable",
    }
    by_status = {str(row["validation_status"]): row for row in records}
    for status in _VALIDATION_COLORS:
        row = by_status.get(status, {"claim_count": 0, "share": 0.0})
        count = int(row.get("claim_count", 0))
        share = float(row.get("share") or 0.0)
        figure.add_trace(go.Bar(
            x=[share * 100], y=["Selected generation"], orientation="h",
            name=label_map.get(status, status), marker={"color": _VALIDATION_COLORS[status]},
            customdata=[[count, total, status]],
            hovertemplate="<b>%{customdata[2]}</b><br>%{customdata[0]} / %{customdata[1]} claims<br>%{x:.1f}%<extra></extra>",
        ))
    figure.update_layout(barmode="stack", legend={"orientation": "h", "y": -0.36, "x": 0})
    figure.update_xaxes(range=[0, 100], ticksuffix="%", dtick=20, title=None, fixedrange=True)
    figure.update_yaxes(title=None, fixedrange=True)
    return _base_layout(figure, height=245, margin={"l": 125, "r": 18, "t": 28, "b": 72})


def cases_claim_type_status_matrix(rows: Iterable[Mapping[str, object]]) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    figure = go.Figure()
    if frame.empty:
        figure.add_annotation(text="Không có claim diagnostics cho generation này.", x=0.5, y=0.5, showarrow=False, font={"color": "#667085"})
        figure.update_xaxes(visible=False); figure.update_yaxes(visible=False)
        return _base_layout(figure, height=300)
    type_totals = frame.groupby("claim_type")["claim_count"].sum().sort_values(ascending=False)
    claim_types = list(type_totals.index.astype(str))
    max_count = max(1, int(frame["claim_count"].max()))
    lookup = frame.set_index(["claim_type", "validation_status"])
    z=[]; text=[]; custom=[]
    for claim_type in claim_types:
        zr=[]; tr=[]; cr=[]
        for status in _VALIDATION_COLORS:
            if (claim_type, status) in lookup.index:
                rec = lookup.loc[(claim_type, status)]
                if isinstance(rec, pd.DataFrame): rec = rec.iloc[0]
                count=int(rec["claim_count"]); denom=int(rec["claim_type_denominator"])
                share=float(rec["share_within_type"])
            else:
                count=0; denom=int(type_totals.loc[claim_type]); share=0.0
            zr.append(count); tr.append(str(count) if count else "·"); cr.append([claim_type,status,count,denom,share])
        z.append(zr); text.append(tr); custom.append(cr)
    figure.add_trace(go.Heatmap(
        z=z, x=list(_VALIDATION_COLORS), y=claim_types, customdata=custom,
        zmin=0, zmax=max_count, colorscale=[[0,"#F8FAFC"],[0.18,"#DBEAFE"],[0.55,"#60A5FA"],[1,"#1D4ED8"]],
        colorbar={"title":"Claims","thickness":10,"outlinewidth":0,"len":0.7},
        text=text, texttemplate="%{text}", textfont={"size":10}, xgap=3, ygap=2,
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}: %{customdata[2]} / %{customdata[3]} (%{customdata[4]:.1%})<extra>Certified claim rows</extra>",
    ))
    figure.update_xaxes(side="top", fixedrange=True, tickfont={"size":9}); figure.update_yaxes(autorange="reversed", fixedrange=True, tickfont={"size":9})
    height=max(330, min(620, 160 + len(claim_types)*31))
    return _base_layout(figure, height=height, margin={"l":180,"r":54,"t":62,"b":32})


def cases_section_profile(rows: Iterable[Mapping[str, object]]) -> go.Figure:
    frame = pd.DataFrame(list(rows))
    figure = go.Figure()
    if frame.empty:
        figure.add_annotation(text="Không có narrative-section diagnostics.", x=0.5, y=0.5, showarrow=False, font={"color":"#667085"})
        figure.update_xaxes(visible=False); figure.update_yaxes(visible=False)
        return _base_layout(figure, height=260)
    frame = frame.sort_values(["claim_count", "source_section"], ascending=[True, True], kind="stable")
    figure.add_trace(go.Bar(
        x=frame["claim_count"], y=frame["source_section"], orientation="h", marker={"color":"#667085"},
        customdata=[[str(r["source_section"]), int(r["claim_count"])] for _,r in frame.iterrows()],
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} certified claims<extra></extra>",
        text=frame["claim_count"], textposition="outside",
    ))
    figure.update_xaxes(title="Certified claim count", fixedrange=True, rangemode="tozero")
    figure.update_yaxes(title=None, fixedrange=True)
    height=max(270, min(430, 120 + len(frame)*34))
    return _base_layout(figure, height=height, margin={"l":190,"r":48,"t":30,"b":52})
