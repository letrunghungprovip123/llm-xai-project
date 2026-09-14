"""Research-safe Page 6 components for canonical-case drill-down."""

from __future__ import annotations

import json
import math
from typing import Iterable

from dash import html
import pandas as pd

from ..data.contracts import CaseSummary
from ..i18n import DEFAULT_LOCALE, localize_component_tree
_CASES_PREFIXES = ("cases.", "common.")

from ..settings import (
    CASE_OUTCOME_LABELS,
    CASE_STRATUM_LABELS,
    ROBUSTNESS_MODEL_LABELS,
)


def _optional_float(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(parsed) if pd.notna(parsed) else None


def _format_percent(value: object, *, digits: int = 1) -> str:
    number = _optional_float(value)
    return "N/A" if number is None else f"{number:.{digits}%}"


def _format_number(value: object, *, digits: int = 0) -> str:
    number = _optional_float(value)
    if number is None:
        return "N/A"
    return f"{number:,.{digits}f}"


def _humanize(value: object) -> str:
    if value is None or pd.isna(value):
        return "Not available"
    text = str(value)
    labels = {
        "low_default_risk": "Low default risk",
        "high_default_risk": "High default risk",
        "prediction_only": "Prediction only",
        "fixed_raw_shap_top10": "Fixed raw SHAP top 10",
        "fixed_semantic_enrichment_of_raw_shap_top10": (
            "Fixed semantic enrichment of raw SHAP top 10"
        ),
        "adaptive_shap_coverage_0.60_k3_10": "Adaptive SHAP coverage 0.60 · k3–10",
        "adaptive_shap_coverage_0.70_entropy_concept_direction_grouping_k5_20": (
            "Adaptive SHAP coverage 0.70 · entropy/concept/direction grouping · k5–20"
        ),
        "backend_overguided_from_s4_same_evidence": (
            "Backend-guided from S4 with the same evidence"
        ),
        "SUCCESS": "Success",
    }
    return labels.get(text, text.replace("_", " ").strip().capitalize())


def _fact(label: str, value: str, *, tone: str = "neutral"):
    return html.Div(
        [
            html.Span(label, className="cases-fact__label"),
            html.Strong(value, className=f"cases-fact__value cases-fact__value--{tone}"),
        ],
        className="cases-fact",
    )


def _case_snapshot_en(summary: CaseSummary):
    """Render a compact privacy-preserving identity strip for one case."""

    completeness = (
        "Complete 18-condition LLM matrix"
        if summary.complete_llm_case
        else f"Structured missingness · {summary.unusable_slot_count} unusable slot(s)"
    )
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Selected canonical case", className="cases-eyebrow"),
                            html.H2(f"Case {summary.case_id}", className="cases-snapshot__title"),
                            html.P(
                                "Privacy-preserving cohort identity; no raw applicant record is displayed.",
                                className="cases-snapshot__subtitle",
                            ),
                        ]
                    ),
                    html.Span(
                        completeness,
                        className=(
                            "cases-status-badge cases-status-badge--ready"
                            if summary.complete_llm_case
                            else "cases-status-badge cases-status-badge--warning"
                        ),
                    ),
                ],
                className="cases-snapshot__header",
            ),
            html.Div(
                [
                    _fact("Selection stratum", CASE_STRATUM_LABELS.get(summary.selection_stratum, _humanize(summary.selection_stratum))),
                    _fact("Prediction outcome", CASE_OUTCOME_LABELS.get(summary.prediction_outcome, summary.prediction_outcome)),
                    _fact("Observed label", _humanize(summary.true_label_text)),
                    _fact("Predicted label", _humanize(summary.predicted_label)),
                    _fact("Prediction probability", f"{summary.prediction_probability:.2%}"),
                    _fact("Distance from threshold", f"{summary.distance_from_threshold:.2%}"),
                ],
                className="cases-snapshot__facts",
            ),
            (
                html.P(
                    "Conditional metrics remain missing—not zero—for unusable generations; operational end-to-end yield remains 0 under the frozen policy.",
                    className="cases-structured-missingness-note",
                )
                if not summary.complete_llm_case
                else None
            ),
        ],
        className="cases-card cases-snapshot",
    )


def _focused_generation_panel_en(row: pd.Series):
    """Summarize one focused LLM generation without exposing raw narrative text."""

    usable = bool(row.get("usable", False))
    model_label = str(row.get("generator_label", row.get("model_label", "Focused LLM")))
    evidence_level = str(row.get("evidence_level", ""))
    status = "Usable" if usable else "Unusable · retained in planned denominator"
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Focused generation", className="cases-eyebrow"),
                            html.H2(f"{model_label} · {evidence_level}", className="cases-panel__title"),
                        ]
                    ),
                    html.Span(
                        status,
                        className=(
                            "cases-status-badge cases-status-badge--ready"
                            if usable
                            else "cases-status-badge cases-status-badge--critical"
                        ),
                    ),
                ],
                className="cases-panel__header",
            ),
            html.Div(
                [
                    _fact("Operational E2E", _format_percent(row.get("end_to_end_faithfulness_yield"))),
                    _fact("Conservative faithfulness", _format_percent(row.get("conservative_faithfulness"))),
                    _fact("Verifiability", _format_percent(row.get("verifiability"))),
                    _fact("Claims", _format_number(row.get("claim_count"))),
                    _fact("Output words", _format_number(row.get("output_word_count"))),
                    _fact("Latency", f"{_format_number(row.get('latency_seconds'), digits=2)} s" if pd.notna(row.get("latency_seconds")) else "Not available"),
                ],
                className="cases-panel__facts",
            ),
            html.P(
                "A single generation is descriptive evidence and is not a statistical comparison.",
                className="cases-panel__note",
            ),
        ],
        className="cases-card cases-focused-generation",
    )


def _policy_state(required: object, compliant: object) -> tuple[str, str]:
    required_bool = bool(required) if pd.notna(required) else False
    if not required_bool:
        return "Not required", "neutral"
    if pd.isna(compliant):
        return "Not available", "neutral"
    return ("Passed", "ready") if bool(compliant) else ("Failed", "critical")


def _status_item(label: str, state: str, tone: str):
    return html.Div(
        [
            html.Span(label),
            html.Strong(state, className=f"cases-check__state cases-check__state--{tone}"),
        ],
        className="cases-check",
    )


def _evidence_package_panel_en(package: pd.Series):
    """Explain what the selected case × evidence condition actually contains."""

    evidence_level = str(package["evidence_level"])
    evidence_label = str(package["evidence_label"])
    s0 = evidence_level == "S0"
    feature_ids = []
    concept_ids = []
    for field, target in (
        ("selected_feature_ids_json", feature_ids),
        ("selected_concept_ids_json", concept_ids),
    ):
        try:
            value = json.loads(str(package.get(field, "[]")))
            if isinstance(value, list):
                target.extend(str(item) for item in value)
        except json.JSONDecodeError:
            pass

    policy_rows = [
        _status_item(
            "Uncertainty note",
            "Required" if bool(package.get("policy_must_include_uncertainty", False)) else "Not required",
            "information" if bool(package.get("policy_must_include_uncertainty", False)) else "neutral",
        ),
        _status_item(
            "Distributed-evidence note",
            "Required" if bool(package.get("policy_must_include_distributed_note", False)) else "Not required",
            "information" if bool(package.get("policy_must_include_distributed_note", False)) else "neutral",
        ),
        _status_item(
            "Partial-evidence note",
            "Required" if pd.notna(package.get("policy_must_include_partial_note")) and bool(package.get("policy_must_include_partial_note")) else "Not required",
            "information" if pd.notna(package.get("policy_must_include_partial_note")) and bool(package.get("policy_must_include_partial_note")) else "neutral",
        ),
        _status_item(
            "Avoid single-cause wording",
            "Required" if bool(package.get("policy_avoid_single_cause_wording", False)) else "Not required",
            "information" if bool(package.get("policy_avoid_single_cause_wording", False)) else "neutral",
        ),
    ]

    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Evidence package", className="cases-eyebrow"),
                            html.H2(f"{evidence_level} · {evidence_label}", className="cases-panel__title"),
                            html.P(
                                "This package is shared across generators for the selected case and evidence condition.",
                                className="cases-panel__subtitle",
                            ),
                        ]
                    ),
                    html.Span(
                        "Categorical condition · not an ordinal scale",
                        className="cases-status-badge cases-status-badge--neutral",
                    ),
                ],
                className="cases-panel__header",
            ),
            html.Div(
                [
                    _fact("Selected evidence items", _format_number(package.get("selected_evidence_count"))),
                    _fact("Feature items", "Not applicable" if s0 else _format_number(package.get("feature_item_count"))),
                    _fact("Concept items", "Not applicable" if s0 else _format_number(package.get("concept_item_count"))),
                    _fact("Distinct features", "Not applicable" if s0 else _format_number(package.get("distinct_feature_count"))),
                    _fact("Distinct concepts", "Not applicable" if s0 else _format_number(package.get("distinct_concept_count"))),
                    _fact("Coverage", "Not applicable for prediction-only control" if s0 else _format_percent(package.get("coverage"))),
                    _fact("Normalized diversity", "Not applicable for prediction-only control" if s0 else _format_number(package.get("normalized_entropy"), digits=2)),
                    _fact("Selection method", _humanize(package.get("selection_method"))),
                ],
                className="cases-panel__facts cases-panel__facts--evidence",
            ),
            html.Div(policy_rows, className="cases-policy-requirements"),
            html.Details(
                [
                    html.Summary("View selected feature and concept identifiers"),
                    html.Div(
                        [
                            html.Div(
                                [html.Strong("Feature identifiers"), html.P(", ".join(feature_ids) if feature_ids else "None")]
                            ),
                            html.Div(
                                [html.Strong("Concept identifiers"), html.P(", ".join(concept_ids) if concept_ids else "None")]
                            ),
                        ],
                        className="cases-identifier-grid",
                    ),
                ],
                className="cases-inline-details",
            ),
        ],
        className="cases-card cases-evidence-package",
    )


def _narrative_structure_panel_en(row: pd.Series):
    """Render structural and policy measurements without claiming human quality."""

    checks = [
        ("Prediction summary present", row.get("has_prediction_summary"), True),
        ("Factor section present", row.get("has_factors"), True),
        ("Uncertainty policy", *_policy_state(row.get("uncertainty_required"), row.get("uncertainty_compliant"))),
        ("Distributed-evidence policy", *_policy_state(row.get("distributed_note_required"), row.get("distributed_note_compliant"))),
        ("Partial-evidence policy", *_policy_state(row.get("partial_evidence_note_required"), row.get("partial_evidence_note_compliant"))),
        ("Single-cause violation absent", not bool(row.get("single_cause_violation", False)), True),
        ("Forbidden phrase violation absent", not bool(row.get("forbidden_phrase_violation", False)), True),
        ("Overall policy compliant", row.get("overall_policy_compliant"), True),
    ]
    rendered = []
    for item in checks:
        label = item[0]
        if len(item) == 3 and isinstance(item[1], str):
            rendered.append(_status_item(label, item[1], item[2]))
            continue
        value = item[1]
        if pd.isna(value):
            rendered.append(_status_item(label, "Not available", "neutral"))
        elif bool(value):
            rendered.append(_status_item(label, "Passed", "ready"))
        else:
            rendered.append(_status_item(label, "Failed", "critical"))

    return html.Section(
        [
            html.Div(
                [
                    html.Span("Narrative structure and policy", className="cases-eyebrow"),
                    html.H2("Measured structure of the focused output", className="cases-panel__title"),
                ]
            ),
            html.Div(
                [
                    html.Div(
                        [
                            _fact("Output words", _format_number(row.get("output_word_count"))),
                            _fact("Sentences", _format_number(row.get("sentence_count"))),
                            _fact("Main factors", _format_number(row.get("main_factor_count"))),
                            _fact("Supporting factors", _format_number(row.get("supporting_factor_count"))),
                            _fact("Technical-term ratio", _format_percent(row.get("technical_term_ratio"))),
                            _fact("Total tokens", _format_number(row.get("total_token_count"))),
                        ],
                        className="cases-panel__facts cases-panel__facts--structure",
                    ),
                    html.Div(rendered, className="cases-compliance-list"),
                ],
                className="cases-structure-grid",
            ),
            html.P(
                "Structure and policy metrics do not measure human naturalness, usefulness, trust or preference.",
                className="cases-boundary-note",
            ),
        ],
        className="cases-card cases-narrative-structure",
    )


def _template_comparison_panel_en(pair: pd.Series):
    """Compare one LLM generation with the same-case deterministic Template."""

    rows = [
        ("End-to-end yield", "llm_end_to_end_faithfulness_yield", "template_end_to_end_faithfulness_yield", "delta_end_to_end_faithfulness_yield_llm_minus_template", "percent"),
        ("Conservative faithfulness", "llm_conservative_faithfulness", "template_conservative_faithfulness", "delta_conservative_faithfulness_llm_minus_template", "percent"),
        ("Verifiability", "llm_verifiability", "template_verifiability", "delta_verifiability_llm_minus_template", "percent"),
        ("Supported claims", "llm_supported_count", "template_supported_count", "delta_supported_count_llm_minus_template", "number"),
        ("Claims / 100 words", "llm_supported_claims_per_100_words", "template_supported_claims_per_100_words", "delta_supported_claims_per_100_words_llm_minus_template", "decimal"),
        ("Output words", "llm_output_word_count", "template_output_word_count", "delta_output_word_count_llm_minus_template", "number"),
    ]

    def display(value: object, kind: str, *, delta: bool = False) -> str:
        number = _optional_float(value)
        if number is None:
            return "N/A"
        sign = "+" if delta and number >= 0 else ""
        if kind == "percent":
            return f"{sign}{number * 100:.1f}{' pp' if delta else '%'}"
        if kind == "number":
            return f"{sign}{number:,.0f}"
        return f"{sign}{number:.2f}"

    table_rows = []
    for label, llm_col, template_col, delta_col, kind in rows:
        table_rows.append(
            html.Tr(
                [
                    html.Th(label),
                    html.Td(display(pair.get(llm_col), kind)),
                    html.Td(display(pair.get(template_col), kind)),
                    html.Td(display(pair.get(delta_col), kind, delta=True)),
                ]
            )
        )
    return html.Section(
        [
            html.Div(
                [
                    html.Span("Deterministic reference", className="cases-eyebrow"),
                    html.H2("Focused LLM versus Template", className="cases-panel__title"),
                    html.P(
                        "Same canonical case and controlled evidence condition; different narrative-generation mechanism.",
                        className="cases-panel__subtitle",
                    ),
                ]
            ),
            html.Div(
                html.Table(
                    [
                        html.Thead(html.Tr([html.Th("Metric"), html.Th("Focused LLM"), html.Th("Template"), html.Th("LLM − Template")])),
                        html.Tbody(table_rows),
                    ],
                    className="cases-comparison-table",
                ),
                className="cases-comparison-table-wrap",
            ),
            html.P(
                "The Template is a deterministic reference, not a fourth LLM, and is excluded from decision ranking.",
                className="cases-boundary-note",
            ),
            html.P(
                "Template latency is measurement-floor limited and is not interpreted as precise zero latency or zero computational cost.",
                className="cases-panel__note",
            ),
        ],
        className="cases-card cases-template-comparison",
    )


def _case_interpretation_boundaries_en():
    items = (
        "A single case is descriptive evidence, not statistical evidence.",
        "The paired analyses retain the canonical case—not atomic claims—as the inference unit.",
        "Evidence conditions S0–S5 are categorical experimental conditions, not a linear scale.",
        "Unusable generations remain in the operational denominator; conditional metrics remain missing, not zero.",
        "Candidate is the primary measurement artifact; V4 is sensitivity-only and neither is human ground truth.",
        "The Template is not a fourth LLM and is excluded from decision ranking.",
        "Evidence-utilization patterns are explanatory associations, not causal mediation.",
        "Human naturalness is not measured by structure or policy fields.",
        "No raw applicant record or direct personal identifier is displayed.",
    )
    return html.Section(
        [
            html.H2("How to interpret a case drill-down"),
            html.Ul([html.Li(item) for item in items]),
        ],
        className="cases-card cases-boundaries",
    )


def case_snapshot(summary: CaseSummary, *, locale: object = DEFAULT_LOCALE):
    return localize_component_tree(
        _case_snapshot_en(summary), locale, prefixes=_CASES_PREFIXES
    )


def focused_generation_panel(row: pd.Series, *, locale: object = DEFAULT_LOCALE):
    return localize_component_tree(
        _focused_generation_panel_en(row), locale, prefixes=_CASES_PREFIXES
    )


def evidence_package_panel(package: pd.Series, *, locale: object = DEFAULT_LOCALE):
    return localize_component_tree(
        _evidence_package_panel_en(package), locale, prefixes=_CASES_PREFIXES
    )


def narrative_structure_panel(row: pd.Series, *, locale: object = DEFAULT_LOCALE):
    return localize_component_tree(
        _narrative_structure_panel_en(row), locale, prefixes=_CASES_PREFIXES
    )


def template_comparison_panel(pair: pd.Series, *, locale: object = DEFAULT_LOCALE):
    return localize_component_tree(
        _template_comparison_panel_en(pair), locale, prefixes=_CASES_PREFIXES
    )


def case_interpretation_boundaries(*, locale: object = DEFAULT_LOCALE):
    return localize_component_tree(
        _case_interpretation_boundaries_en(), locale, prefixes=_CASES_PREFIXES
    )
