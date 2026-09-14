"""Reusable Page-4 components with cautious decision language."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

import dash_mantine_components as dmc
from dash import dcc, html
import pandas as pd

from ..data.contracts import DecisionCriterion, ScenarioDefinition
from ..i18n import DEFAULT_LOCALE, localize_component_tree, localize_text, normalize_locale
from ..settings import DECISION_CONTRIBUTION_LABELS

_DECISION_PREFIXES = ("decision.",)


_REASON_LABELS = {
    "MEETS_ALL_CONSTRAINTS": "Meets all certified constraints",
    "PARETO_OPTIMAL": "Pareto-efficient",
    "TOP_SCENARIO_UTILITY": "Highest scenario utility",
    "TOP_PARETO_ALTERNATIVE": "Strong Pareto alternative",
    "FULL_USABILITY": "Full usability",
    "HIGH_MEAN_QUALITY": "High average E2E quality",
    "HIGH_CASE_ROBUSTNESS": "Strong lower-tail reliability",
    "TOKEN_EFFICIENT": "Token-efficient",
    "LOW_STRONG_OVERLAP_SIGNAL": "Low strong lexical-signal share",
}

_CAUTION_LABELS = {
    "HIGH_LATENCY": "Higher latency than several alternatives",
    "HIGH_TOKEN_USAGE": "Higher token use than several alternatives",
    "HIGH_STRONG_OVERLAP_SIGNAL": "Higher strong lexical-signal share",
    "HIGH_WEAK_OVERLAP_SIGNAL": "Higher weak lexical-signal share",
    "QUALITY_BELOW_SCENARIO_LEADER": "Quality below the scenario leader",
    "STATISTICAL_ADVANTAGE_NOT_TESTED": (
        "Statistical advantage is not established against every comparator"
    ),
}


def _decode_codes(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        loaded = json.loads(str(value))
    except json.JSONDecodeError:
        return [str(value)]
    return [str(item) for item in loaded] if isinstance(loaded, list) else []


def humanize_reason_codes(value: object, locale: object = DEFAULT_LOCALE) -> list[str]:
    return [
        localize_text(
            _REASON_LABELS.get(code, code.replace("_", " ").title()),
            locale,
            prefixes=_DECISION_PREFIXES,
        )
        for code in _decode_codes(value)
    ]


def humanize_caution_codes(value: object, locale: object = DEFAULT_LOCALE) -> list[str]:
    return [
        localize_text(
            _CAUTION_LABELS.get(code, code.replace("_", " ").title()),
            locale,
            prefixes=_DECISION_PREFIXES,
        )
        for code in _decode_codes(value)
    ]


def _as_sentence(items: Sequence[str], locale: object = DEFAULT_LOCALE) -> str:
    clean = [str(item).strip().rstrip(".") for item in items if str(item).strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return f"{clean[0]}."
    if normalize_locale(locale) == "vi":
        if len(clean) == 2:
            return f"{clean[0]} và {clean[1][0].lower() + clean[1][1:]}."
        return f"{', '.join(clean[:-1])} và {clean[-1][0].lower() + clean[-1][1:]}."
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1][0].lower() + clean[1][1:]}."
    return f"{', '.join(clean[:-1])}, and {clean[-1][0].lower() + clean[-1][1:]}."


def contribution_label(criterion_id: object, fallback: object, locale: object = DEFAULT_LOCALE) -> str:
    return localize_text(
        DECISION_CONTRIBUTION_LABELS.get(str(criterion_id), str(fallback)),
        locale,
        prefixes=_DECISION_PREFIXES,
    )


def scenario_selector(
    scenarios: Sequence[ScenarioDefinition],
    *,
    selected: str,
    component_id: str,
    locale: object = DEFAULT_LOCALE,
):
    """Render a compact five-scenario selector."""

    short_labels = {
        "QUALITY_FIRST": "Quality",
        "RELIABILITY_FIRST": "Reliability",
        "BALANCED": "Balanced",
        "EFFICIENCY_AWARE": "Efficiency",
        "INDEPENDENCE_SENSITIVE": "Independence",
    }
    component = dmc.SegmentedControl(
        id=component_id,
        value=selected,
        data=[
            {
                "value": item.scenario_id,
                "label": short_labels[item.scenario_id],
            }
            for item in scenarios
        ],
        fullWidth=True,
        className="decision-scenario-selector",
        persistence=True,
        persistence_type="session",
    )
    return localize_component_tree(component, locale, prefixes=_DECISION_PREFIXES)


def recommendation_panel(
    recommendations: pd.DataFrame,
    *,
    scenario_label: str,
    locale: object = DEFAULT_LOCALE,
):
    """Render one primary recommendation and one certified alternative."""

    primary_rows = recommendations.loc[
        recommendations["recommendation_role"] == "PRIMARY"
    ]
    alternative_rows = recommendations.loc[
        recommendations["recommendation_role"] == "ALTERNATIVE"
    ]
    if primary_rows.empty:
        return localize_component_tree(
            html.Aside(
                [html.H3("No certified recommendation"), html.P("No eligible option is available.")],
                className="decision-recommendation-panel",
            ),
            locale,
            prefixes=_DECISION_PREFIXES,
        )
    primary = primary_rows.iloc[0]
    alternative = alternative_rows.iloc[0] if not alternative_rows.empty else None
    reasons = humanize_reason_codes(primary.get("reason_codes"), locale)[:3]
    cautions = humanize_caution_codes(primary.get("caution_codes"), locale)[:2]

    children = [
        html.Span("Recommended configuration", className="decision-panel__eyebrow"),
        html.H2(
            f"{primary['model_label']} · {primary['evidence_level']}",
            className="decision-recommendation-panel__title",
        ),
        html.P(
            [
                html.Strong(
                    f"Decision rank {int(primary['scenario_rank'])}"
                ),
                " under ",
                scenario_label,
                " · Utility ",
                html.Strong(f"{float(primary['utility_score']):.3f}"),
            ],
            className="decision-recommendation-panel__summary",
        ),
        html.P(
            "Utility is a scenario-specific decision-support score, not a probability or confidence measure.",
            className="decision-utility-caveat",
        ),
        html.H3("Why this option", className="decision-recommendation-panel__heading"),
        html.P(
            _as_sentence(reasons, locale),
            className="decision-reason-summary",
        ),
    ]
    if cautions:
        children.extend(
            [
                html.H3("Main caution", className="decision-recommendation-panel__heading"),
                html.Ul([html.Li(item) for item in cautions], className="decision-caution-list"),
            ]
        )
    if alternative is not None:
        children.append(
            html.P(
                [
                    html.Span("Strong alternative · "),
                    html.Strong(
                        f"{alternative['model_label']} · {alternative['evidence_level']}"
                    ),
                ],
                className="decision-alternative",
            )
        )
    children.append(
        html.P(
            "Pareto-efficient among observed certified options; this does not establish statistical superiority.",
            className="decision-boundary-copy",
        )
    )
    return localize_component_tree(html.Aside(children, className="decision-recommendation-panel"), locale, prefixes=_DECISION_PREFIXES)


def contribution_summary(profile: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    available = profile.dropna(subset=["weighted_contribution"]).copy()
    if available.empty:
        return html.Div()
    largest = available.sort_values("weighted_contribution", ascending=False).iloc[0]
    label = contribution_label(
        largest.get("criterion_id"),
        largest.get("criterion_label"),
        locale,
    )
    component = html.P(
        [
            html.Strong("Largest contribution · "),
            f"{label} ({largest['weighted_contribution']:.3f})",
        ],
        className="decision-contribution-summary",
    )
    return localize_component_tree(component, locale, prefixes=_DECISION_PREFIXES)


def decision_boundaries(locale: object = DEFAULT_LOCALE):
    component = html.Section(
        [
            html.H3("Decision-support boundaries"),
            html.Ul(
                [
                    html.Li(
                        "Decision rank places eligible, scored Pareto-efficient options first and then orders them by utility."
                    ),
                    html.Li(
                        "Utility rank is the direct descending order of scenario utility among eligible scored options."
                    ),
                    html.Li("Utility is not a probability or significance measure."),
                    html.Li("Pareto efficiency does not establish superiority."),
                    html.Li("Template Reference and alternative measurement releases are not ranked."),
                    html.Li("Human trust, naturalness and monetary cost are not included."),
                ]
            ),
        ],
        className="decision-boundaries",
    )
    return localize_component_tree(component, locale, prefixes=_DECISION_PREFIXES)


def what_if_warning(locale: object = DEFAULT_LOCALE):
    component = html.Div(
        [
            html.Strong("User-specified exploration"),
            html.Span(
                "Custom weights do not redefine certified research findings or statistical results."
            ),
        ],
        className="decision-what-if-warning",
    )
    return localize_component_tree(component, locale, prefixes=_DECISION_PREFIXES)


def weight_editor(
    criteria: Sequence[DecisionCriterion],
    *,
    values: Mapping[str, float],
    locale: object = DEFAULT_LOCALE,
):
    groups = ("Quality", "Reliability", "Efficiency", "Measurement robustness")
    blocks = []
    for group in groups:
        rows = []
        for criterion in [item for item in criteria if item.group == group]:
            raw = float(values.get(criterion.criterion_id, criterion.default_weight * 100))
            rows.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Label(criterion.label),
                                html.Span(f"{raw:.0f}", id={"type": "decision-weight-value", "criterion": criterion.criterion_id}),
                            ],
                            className="decision-weight-row__header",
                        ),
                        dcc.Slider(
                            id={"type": "decision-weight-slider", "criterion": criterion.criterion_id},
                            min=0,
                            max=100,
                            step=1,
                            value=raw,
                            marks=None,
                            tooltip={"placement": "bottom", "always_visible": False},
                            className="decision-weight-slider",
                        ),
                        html.P(
                            f"Direction: {'higher' if criterion.direction == 'MAX' else 'lower'} is better",
                            className="decision-weight-row__note",
                        ),
                    ],
                    className="decision-weight-row",
                )
            )
        blocks.append(
            html.Details(
                [html.Summary(group), html.Div(rows, className="decision-weight-group__body")],
                open=group in {"Quality", "Reliability"},
                className="decision-weight-group",
            )
        )
    return localize_component_tree(html.Div(blocks, className="decision-weight-editor"), locale, prefixes=_DECISION_PREFIXES)


def certified_custom_recommendation_panel(
    certified: pd.Series,
    custom: pd.Series | None,
    *,
    certified_label: str,
    locale: object = DEFAULT_LOCALE,
):
    custom_children = (
        [
            html.H3("Custom what-if"),
            html.Strong(f"{custom['model_label']} · {custom['evidence_level']}"),
            html.P(f"Custom rank {int(custom['custom_rank'])}"),
        ]
        if custom is not None
        else [
            html.H3("Custom what-if"),
            html.Strong("No custom result"),
            html.P("At least one criterion must have a positive weight."),
        ]
    )
    changed = custom is not None and custom["option_id"] != certified["option_id"]
    component = html.Section(
        [
            html.Div(
                [
                    html.H3(f"Certified · {certified_label}"),
                    html.Strong(
                        f"{certified['model_label']} · {certified['evidence_level']}"
                    ),
                    html.P(f"Certified rank {int(certified['scenario_rank'])}"),
                ],
                className="decision-comparison-column",
            ),
            html.Div(custom_children, className="decision-comparison-column"),
            html.P(
                (
                    "The preferred configuration changes because the custom weight vector defines a different objective."
                    if changed
                    else "The custom priorities retain the certified recommendation."
                    if custom is not None
                    else "No ranking is produced for an all-zero weight vector."
                ),
                className="decision-comparison-explanation",
            ),
        ],
        className="decision-certified-custom-panel",
    )
    return localize_component_tree(component, locale, prefixes=_DECISION_PREFIXES)


def rank_change_summary(
    certified: pd.DataFrame,
    custom: pd.DataFrame,
    locale: object = DEFAULT_LOCALE,
):
    merged = certified[["option_id", "model_label", "evidence_level", "scenario_rank"]].merge(
        custom[["option_id", "custom_rank"]], on="option_id", how="left"
    )
    merged["rank_change"] = merged["scenario_rank"] - merged["custom_rank"]
    eligible = merged.dropna(subset=["custom_rank"]).copy()
    if eligible.empty:
        return html.Div()
    upward = eligible.sort_values("rank_change", ascending=False).iloc[0]
    downward = eligible.sort_values("rank_change", ascending=True).iloc[0]
    component = html.Div(
        [
            html.P(
                [
                    html.Strong("Largest upward movement · "),
                    f"{upward['model_label']} · {upward['evidence_level']} ({int(upward['rank_change']):+d} ranks)",
                ]
            ),
            html.P(
                [
                    html.Strong("Largest downward movement · "),
                    f"{downward['model_label']} · {downward['evidence_level']} ({int(downward['rank_change']):+d} ranks)",
                ]
            ),
        ],
        className="decision-rank-change-summary",
    )
    return localize_component_tree(component, locale, prefixes=_DECISION_PREFIXES)
