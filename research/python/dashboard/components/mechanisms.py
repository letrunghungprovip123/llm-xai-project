"""Locale-aware Page-3 components and explicit diagnostic labels."""

from __future__ import annotations

from dash import html
import pandas as pd

from ..data.contracts import EvidenceConditionProfile
from ..i18n import (
    DEFAULT_LOCALE,
    claim_type_label,
    evidence_label,
    failure_type_label,
    format_integer,
    format_number,
    format_percent,
    normalize_locale,
    reason_code_label,
    t,
)


def _format_optional(
    locale: object,
    value: float | None,
    *,
    percent: bool = False,
    digits: int = 0,
) -> str:
    resolved = normalize_locale(locale)
    if value is None or pd.isna(value):
        return t(resolved, "mechanisms.panel.not_applicable")
    if percent:
        return format_percent(resolved, value, decimals=digits)
    return format_number(
        resolved,
        value,
        decimals=digits,
        trim_trailing_zeros=digits == 0,
    )


def humanize_code(
    value: object,
    locale: object = DEFAULT_LOCALE,
    *,
    namespace: str | None = None,
) -> str:
    """Resolve a known diagnostic identity without a user-facing fallback."""

    resolved = normalize_locale(locale)
    if value is None or pd.isna(value):
        return t(resolved, "mechanisms.panel.not_recorded")
    if namespace == "reason_code":
        return reason_code_label(resolved, value)
    if namespace == "claim_type":
        return claim_type_label(resolved, value)
    if namespace == "failure_type":
        return failure_type_label(resolved, value)
    # Backwards-compatible technical display only. User-facing call sites in
    # Page 3 always provide a semantic namespace.
    return str(value).replace("_", " ").strip().capitalize()


def evidence_condition_blueprint(
    profiles: tuple[EvidenceConditionProfile, ...],
    *,
    locale: object = DEFAULT_LOCALE,
):
    resolved = normalize_locale(locale)
    columns = []
    for item in profiles:
        composition = (
            t(resolved, "mechanisms.blueprint.no_evidence")
            if item.median_evidence_item_count is None
            else t(
                resolved,
                "mechanisms.blueprint.composition",
                feature=_format_optional(
                    resolved, item.median_feature_item_count, digits=0
                ),
                concept=_format_optional(
                    resolved, item.median_concept_item_count, digits=0
                ),
            )
        )
        guidance = []
        if item.has_semantic_guidance:
            guidance.append(t(resolved, "mechanisms.blueprint.semantic_guidance"))
        if item.has_concept_evidence:
            guidance.append(t(resolved, "mechanisms.blueprint.concept_evidence"))
        if item.has_structural_skeleton:
            guidance.append(t(resolved, "mechanisms.blueprint.structural_skeleton"))
        columns.append(
            html.Article(
                [
                    html.Div(
                        item.evidence_level,
                        className="condition-blueprint__level",
                    ),
                    html.H3(
                        evidence_label(resolved, item.evidence_level),
                        className="condition-blueprint__title",
                    ),
                    html.P(
                        composition,
                        className="condition-blueprint__composition",
                    ),
                    html.Dl(
                        [
                            html.Div(
                                [
                                    html.Dt(
                                        t(
                                            resolved,
                                            "mechanisms.blueprint.evidence_items",
                                        )
                                    ),
                                    html.Dd(
                                        _format_optional(
                                            resolved,
                                            item.median_selected_evidence_count,
                                        )
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Dt(
                                        t(
                                            resolved,
                                            "mechanisms.blueprint.coverage",
                                        )
                                    ),
                                    html.Dd(
                                        _format_optional(
                                            resolved,
                                            item.mean_coverage,
                                            percent=True,
                                        )
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Dt(
                                        t(
                                            resolved,
                                            "mechanisms.blueprint.diversity",
                                        )
                                    ),
                                    html.Dd(
                                        _format_optional(
                                            resolved,
                                            item.mean_diversity,
                                            digits=2,
                                        )
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Dt(
                                        t(
                                            resolved,
                                            "mechanisms.blueprint.guidance",
                                        )
                                    ),
                                    html.Dd(
                                        " · ".join(guidance)
                                        if guidance
                                        else t(
                                            resolved,
                                            "mechanisms.blueprint.none",
                                        )
                                    ),
                                ]
                            ),
                        ],
                        className="condition-blueprint__facts",
                    ),
                ],
                className=(
                    "condition-blueprint condition-blueprint--"
                    f"{item.evidence_level.lower()}"
                ),
            )
        )
    return html.Section(
        columns,
        className="condition-blueprint-grid",
        **{"aria-label": t(resolved, "mechanisms.blueprint.aria")},
    )


def design_interpretation_panel(
    profiles: tuple[EvidenceConditionProfile, ...],
    *,
    locale: object = DEFAULT_LOCALE,
):
    resolved = normalize_locale(locale)
    rich = next(item for item in profiles if item.evidence_level == "S4")
    structured = next(item for item in profiles if item.evidence_level == "S5")
    return html.Aside(
        [
            html.H3(t(resolved, "mechanisms.panel.interpretation_title")),
            html.P(t(resolved, "mechanisms.panel.categorical")),
            html.P(t(resolved, "mechanisms.panel.diversity_scope")),
            html.P(
                t(
                    resolved,
                    "mechanisms.panel.s4_rich",
                    items=_format_optional(
                        resolved, rich.median_evidence_item_count, digits=1
                    ),
                )
            ),
            html.P(
                t(
                    resolved,
                    "mechanisms.panel.s5_structure",
                    sections=_format_optional(
                        resolved, structured.median_required_sections
                    ),
                )
            ),
            html.P(
                t(resolved, "mechanisms.panel.noncausal"),
                className="mechanisms-emphasis",
            ),
        ],
        className="mechanisms-context-panel",
    )


def utilization_interpretation_panel(
    summary: pd.DataFrame,
    *,
    metric_id: str,
    metric_label: str,
    locale: object = DEFAULT_LOCALE,
):
    resolved = normalize_locale(locale)
    available = summary.dropna(subset=["mean_value"]).sort_values(
        "mean_value", ascending=False
    )
    highest = available.iloc[0] if not available.empty else None
    lowest = available.iloc[-1] if not available.empty else None
    children = [
        html.H3(t(resolved, "mechanisms.panel.utilization_title")),
        html.P(t(resolved, "mechanisms.panel.utilization_dots")),
        html.P(t(resolved, "mechanisms.panel.na_zero")),
    ]
    if highest is not None and lowest is not None:
        children.extend(
            [
                html.Hr(),
                html.Span(
                    t(resolved, "mechanisms.panel.observed_range"),
                    className="mechanisms-panel__eyebrow",
                ),
                html.P(
                    t(
                        resolved,
                        "mechanisms.panel.highest",
                        model=str(highest["generator_label"]),
                        evidence=str(highest["evidence_level"]),
                        value=format_percent(
                            resolved, float(highest["mean_value"]), decimals=1
                        ),
                    )
                ),
                html.P(
                    t(
                        resolved,
                        "mechanisms.panel.lowest",
                        model=str(lowest["generator_label"]),
                        evidence=str(lowest["evidence_level"]),
                        value=format_percent(
                            resolved, float(lowest["mean_value"]), decimals=1
                        ),
                    )
                ),
            ]
        )
    if metric_id == "feature_use":
        children.append(html.P(t(resolved, "mechanisms.panel.feature_s5")))
    children.append(
        html.P(
            t(
                resolved,
                "mechanisms.panel.utilization_noncausal",
                metric=metric_label,
            ),
            className="mechanisms-emphasis",
        )
    )
    return html.Aside(children, className="mechanisms-context-panel")


def claim_mechanism_findings(
    difficulty: pd.DataFrame,
    *,
    locale: object = DEFAULT_LOCALE,
):
    resolved = normalize_locale(locale)
    rows = {
        "not_verifiable": difficulty.sort_values(
            "not_verifiable_share", ascending=False
        ).iloc[0],
        "unsupported": difficulty.sort_values(
            "unsupported_share", ascending=False
        ).iloc[0],
        "contradicted": difficulty.sort_values(
            "contradicted_share", ascending=False
        ).iloc[0],
    }

    def sentence(row: pd.Series, *, label_key: str, stem: str) -> str:
        share = float(row[f"{stem}_share"])
        total = int(row["claim_count"])
        raw_count = row.get(f"{stem}_count")
        count = (
            int(raw_count)
            if raw_count is not None and not pd.isna(raw_count)
            else int(round(share * total))
        )
        return t(
            resolved,
            "mechanisms.panel.claim_sentence",
            label=t(resolved, label_key),
            claim_type=claim_type_label(resolved, row["claim_type"]),
            share=format_percent(resolved, share, decimals=1),
            count=format_integer(resolved, count),
            total=format_integer(resolved, total),
        )

    return html.Aside(
        [
            html.H3(t(resolved, "mechanisms.panel.mechanism_title")),
            html.P(
                sentence(
                    rows["not_verifiable"],
                    label_key="mechanisms.panel.highest_not_verifiable",
                    stem="not_verifiable",
                )
            ),
            html.P(
                sentence(
                    rows["unsupported"],
                    label_key="mechanisms.panel.highest_unsupported",
                    stem="unsupported",
                )
            ),
            html.P(
                sentence(
                    rows["contradicted"],
                    label_key="mechanisms.panel.highest_contradiction",
                    stem="contradicted",
                )
            ),
            html.P(
                t(resolved, "mechanisms.panel.claims_not_independent"),
                className="mechanisms-emphasis",
            ),
        ],
        className="mechanisms-context-panel",
    )


def pipeline_failure_summary(
    failures: pd.DataFrame,
    *,
    locale: object = DEFAULT_LOCALE,
):
    resolved = normalize_locale(locale)
    model_rows = []
    for label, group in failures.groupby("model_label", sort=False):
        model_rows.append(
            html.Div(
                [
                    html.H4(label),
                    html.P(
                        t(
                            resolved,
                            "mechanisms.panel.failure_count",
                            count=format_integer(resolved, len(group)),
                        )
                    ),
                    html.P(
                        t(
                            resolved,
                            "mechanisms.panel.median_latency",
                            value=format_number(
                                resolved,
                                group["latency_ms"].median() / 1000,
                                decimals=2,
                                trim_trailing_zeros=False,
                            ),
                        )
                    ),
                    html.P(
                        t(
                            resolved,
                            "mechanisms.panel.median_tokens",
                            value=format_integer(
                                resolved,
                                round(group["total_token_count"].median()),
                            ),
                        )
                    ),
                    html.P(t(resolved, "mechanisms.panel.length_truncated")),
                ],
                className="pipeline-model-summary",
            )
        )
    return html.Aside(
        [
            html.H3(t(resolved, "mechanisms.panel.failure_title")),
            *model_rows,
            html.P(
                t(resolved, "mechanisms.panel.qwen_no_failure"),
                className="mechanisms-emphasis",
            ),
        ],
        className="mechanisms-context-panel pipeline-summary-panel",
    )


def lexical_signal_disclosure(
    safe_phrase_summary: pd.DataFrame,
    *,
    locale: object = DEFAULT_LOCALE,
):
    resolved = normalize_locale(locale)
    overall = safe_phrase_summary.loc[
        safe_phrase_summary["group_type"] == "overall"
    ].iloc[0]
    eligible = int(overall["safe_phrase_eligible_claim_count"])
    strong = int(overall["strong_safe_phrase_signal_count"])
    no_match = int(overall["safe_phrase_best_none_claim_count"])
    strong_rate = strong / eligible if eligible else 0.0
    no_match_rate = no_match / eligible if eligible else 0.0
    return html.Div(
        [
            html.Div(
                [
                    html.Strong(format_integer(resolved, eligible)),
                    html.Span(
                        " " + t(resolved, "mechanisms.panel.eligible_claims")
                    ),
                ]
            ),
            html.Div(
                [
                    html.Strong(format_percent(resolved, strong_rate, decimals=1)),
                    html.Span(
                        " " + t(resolved, "mechanisms.panel.strong_signal")
                    ),
                ]
            ),
            html.Div(
                [
                    html.Strong(
                        format_percent(resolved, no_match_rate, decimals=1)
                    ),
                    html.Span(
                        " " + t(resolved, "mechanisms.panel.no_match_rate")
                    ),
                ]
            ),
            html.P(t(resolved, "mechanisms.claims.lexical_disclaimer")),
        ],
        className="lexical-signal-disclosure",
    )
