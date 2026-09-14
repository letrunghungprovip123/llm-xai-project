"""Reusable explanatory components for Page 5."""

from __future__ import annotations

from dash import html
import pandas as pd

from ..settings import (
    ROBUSTNESS_METRIC_LABELS,
    ROBUSTNESS_MODEL_LABELS,
    TEMPLATE_METRIC_LABELS,
)


def _format_p(value: object) -> str:
    if value is None or pd.isna(value):
        return "Not tested"
    number = float(value)
    return "<0.0001" if number < 0.0001 else f"{number:.4f}"


def _format_measurement_delta(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    number = float(value)
    sign = "+" if number >= 0 else "−"
    return f"{sign}{abs(number) * 100:.2f} pp"


def _format_template_delta(value: object, metric_id: str) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    number = float(value)
    sign = "+" if number >= 0 else "−"
    magnitude = abs(number)
    if metric_id in {"end_to_end_faithfulness_yield", "conservative_faithfulness"}:
        return f"{sign}{magnitude * 100:.2f} pp"
    if metric_id == "supported_claim_count":
        return f"{sign}{magnitude:.2f} claims"
    if metric_id == "supported_claims_per_100_words":
        return f"{sign}{magnitude:.2f} claims / 100 words"
    if metric_id == "output_word_count":
        return f"{sign}{magnitude:,.1f} words"
    return f"{sign}{magnitude:.2f}"


def result_badge(significant: object, delta: object, *, descriptive_only: bool = False):
    """Humanize a frozen test result without asserting equivalence or a winner."""

    if descriptive_only:
        label = "Descriptive only"
        tone = "neutral"
    elif significant is None or pd.isna(significant):
        label = "Not tested"
        tone = "neutral"
    elif bool(significant):
        label = "Adjusted paired difference"
        tone = "warning"
    else:
        label = "No adjusted statistical difference"
        tone = "neutral"
    return html.Span(label, className=f"robustness-result-badge robustness-result-badge--{tone}")


def template_result_badge(significant: object, delta: object, *, descriptive_only: bool):
    """State direction without treating a non-significant result as equivalence."""

    if delta is None or pd.isna(delta):
        label = "Not tested"
        tone = "neutral"
    elif descriptive_only:
        label = (
            "Adjusted descriptive difference"
            if bool(significant)
            else "Descriptive length difference"
        )
        tone = "neutral"
    elif bool(significant):
        label = "LLM advantage supported" if float(delta) > 0 else "Template advantage supported"
        tone = "warning"
    elif float(delta) > 0:
        label = "Descriptive LLM advantage only"
        tone = "neutral"
    elif float(delta) < 0:
        label = "Descriptive Template advantage only"
        tone = "neutral"
    else:
        label = "No adjusted statistical difference"
        tone = "neutral"
    return html.Span(label, className=f"robustness-result-badge robustness-result-badge--{tone}")


def measurement_interpretation_panel(summary: pd.DataFrame, *, metric_label: str):
    """Explain measurement roles and summarize the largest descriptive shifts."""

    frame = summary.copy()
    frame["absolute_delta"] = frame["mean_delta_v4_minus_candidate"].abs()
    largest = frame.sort_values("absolute_delta", ascending=False).iloc[0]
    median_abs = float(frame["absolute_delta"].median())
    return html.Aside(
        [
            html.H2("How to interpret measurement shifts"),
            html.Div(
                [
                    html.Div([html.Span("Candidate"), html.Strong("Primary artifact")], className="robustness-role-row"),
                    html.Div([html.Span("V4"), html.Strong("Sensitivity artifact")], className="robustness-role-row"),
                ],
                className="robustness-role-list",
            ),
            html.Div(
                [
                    html.P("Largest absolute shift", className="robustness-panel-label"),
                    html.Strong(
                        f"{largest['model_label']} · {largest['evidence_level']} · "
                        f"{abs(float(largest['mean_delta_v4_minus_candidate'])) * 100:.2f} pp"
                    ),
                    html.P(
                        f"Median absolute shift across the displayed configurations: {median_abs * 100:.2f} pp.",
                        className="robustness-panel-copy",
                    ),
                ],
                className="robustness-panel-highlight",
            ),
            html.P(
                f"The chart describes changes in {metric_label.lower()} when the same generation is measured by a sensitivity artifact.",
                className="robustness-panel-copy",
            ),
            html.P(
                "A shift does not establish that either artifact is more correct or constitutes human ground truth.",
                className="robustness-boundary-copy",
            ),
        ],
        className="robustness-interpretation-panel",
    )


def measurement_test_summary(row: pd.Series):
    """Render one frozen Candidate–V4 test without recomputing inference."""

    scope_id = str(row["scope_id"])
    scope_label = (
        "All configurations"
        if scope_id == "ALL"
        else ROBUSTNESS_MODEL_LABELS.get(scope_id, scope_id)
    )
    return html.Section(
        [
            html.H2("Certified sensitivity result", className="robustness-summary-title"),
            html.Div(
                [
                    html.Div([html.Span("Metric"), html.Strong(ROBUSTNESS_METRIC_LABELS[str(row["metric_id"])])]),
                    html.Div([html.Span("Scope"), html.Strong(scope_label)]),
                    html.Div([html.Span("Paired cases"), html.Strong(str(int(row["paired_case_count"])))]),
                    html.Div([html.Span("Mean V4 − Candidate"), html.Strong(_format_measurement_delta(row["mean_delta_v4_minus_candidate"]))]),
                    html.Div([html.Span("Adjusted p"), html.Strong(_format_p(row["adjusted_p_value"]))]),
                    html.Div([html.Span("Rank-biserial"), html.Strong(f"{float(row['rank_biserial_correlation']):.3f}")]),
                ],
                className="robustness-test-facts robustness-test-facts--six",
            ),
            html.Div(
                [
                    result_badge(row["significant_adjusted"], row["mean_delta_v4_minus_candidate"]),
                    html.P(str(row["interpretation"]), className="robustness-test-interpretation"),
                ],
                className="robustness-test-result",
            ),
        ],
        className="robustness-test-summary",
    )


def template_interpretation_panel():
    """State exactly what the deterministic reference can and cannot establish."""

    return html.Aside(
        [
            html.H2("Interpretation boundaries"),
            html.H3("This comparison can show"),
            html.Ul(
                [
                    html.Li("Relative operational faithfulness under the same controlled evidence."),
                    html.Li("Supported information volume and information density."),
                    html.Li("Output-length and structure trade-offs."),
                ]
            ),
            html.H3("This comparison cannot show"),
            html.Ul(
                [
                    html.Li("Human preference, naturalness, usefulness or trust."),
                    html.Li("Production cost or a precise runtime advantage."),
                    html.Li("That the deterministic reference should be interpreted as another LLM or a decision-ranking option."),
                ]
            ),
            html.P(
                "Template timing is measurement-floor limited. Its structured claim adapter is deterministic but is not identical to the LLM extraction channel.",
                className="robustness-boundary-copy",
            ),
        ],
        className="robustness-interpretation-panel robustness-template-boundaries",
    )


def template_test_summary(
    row: pd.Series,
    *,
    metric_id: str,
    scope_label: str,
):
    """Render one frozen LLM–Template paired test."""

    model_label = ROBUSTNESS_MODEL_LABELS.get(str(row["model_id"]), str(row["model_id"]))
    descriptive_only = metric_id == "output_word_count"
    return html.Section(
        [
            html.H2("Frozen LLM–Template paired evidence", className="robustness-summary-title"),
            html.Div(
                [
                    html.Div([html.Span("Configuration"), html.Strong(model_label)]),
                    html.Div([html.Span("Scope"), html.Strong(scope_label)]),
                    html.Div([html.Span("Paired cases"), html.Strong(str(int(row["paired_case_count"])))]),
                    html.Div([html.Span("Mean LLM − Template"), html.Strong(_format_template_delta(row["mean_delta_llm_minus_template"], metric_id))]),
                    html.Div([html.Span("Adjusted p"), html.Strong(_format_p(row["adjusted_p_value"]))]),
                    html.Div([html.Span("Rank-biserial"), html.Strong(f"{float(row['rank_biserial_correlation']):.3f}")]),
                ],
                className="robustness-test-facts robustness-test-facts--template",
            ),
            html.Div(
                [
                    template_result_badge(
                        row["significant_adjusted"],
                        row["mean_delta_llm_minus_template"],
                        descriptive_only=descriptive_only,
                    ),
                    html.P(
                        f"Frozen paired evidence for {TEMPLATE_METRIC_LABELS[metric_id].lower()}. "
                        "A non-significant result is not evidence of equivalence.",
                        className="robustness-test-interpretation",
                    ),
                ],
                className="robustness-test-result",
            ),
        ],
        className="robustness-test-summary",
    )


def research_boundaries(kind: str):
    """Compact, page-specific anti-overclaim disclosure."""

    if kind == "measurement":
        items = [
            "Candidate remains the primary artifact; V4 is sensitivity-only.",
            "Neither artifact is human-calibrated ground truth.",
            "The dashboard displays frozen paired tests and does not recompute inference.",
            "A non-significant result is not interpreted as equivalence.",
        ]
    else:
        items = [
            "The Template Baseline is not a fourth LLM and is excluded from decision ranking.",
            "The 216 Template runs remain separate from the 648-generation LLM denominator.",
            "More supported claims do not automatically imply a better human explanation.",
            "Naturalness, usefulness, trust, monetary cost and precise Template latency are not evaluated.",
        ]
    return html.Section(
        [html.H3("Research boundaries"), html.Ul([html.Li(item) for item in items])],
        className="robustness-boundaries",
    )
