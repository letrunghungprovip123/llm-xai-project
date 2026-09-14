"""Page 6 — privacy-preserving canonical Case Explorer."""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import dcc, html
import pandas as pd

from ..components.cases import (
    case_interpretation_boundaries,
    case_snapshot,
    evidence_package_panel,
    focused_generation_panel,
    narrative_structure_panel,
    template_comparison_panel,
)
from ..components.chart_card import chart_card
from ..components.data_grid import data_grid
from ..components.page_header import page_header
from ..data.repository import get_dashboard_repository
from ..figures.cases import (
    FIG_CASES_CLAIM_COMPOSITION,
    FIG_CASES_COHORT,
    FIG_CASES_MATRIX,
    FIG_CASES_UTILIZATION,
    FIG_CASES_VALIDATOR_SENSITIVITY,
    build_candidate_v4_case_dumbbell,
    build_case_performance_matrix,
    build_claim_composition,
    build_cohort_landscape,
    build_evidence_utilization_profile,
)
from ..i18n import (
    DEFAULT_LOCALE,
    localize_component_tree,
    localize_plotly_figure,
    normalize_locale,
    t,
)
from ..ids import (
    CASES_BROWSER_GRID_ID,
    CASES_CLAIM_COMPOSITION_ID,
    CASES_COHORT_ID,
    CASES_COMPLETENESS_FILTER_ID,
    CASES_DOWNLOAD_ID,
    CASES_EVIDENCE_ID,
    CASES_EVIDENCE_PACKAGE_ID,
    CASES_EXPORT_ID,
    CASES_FOCUSED_GENERATION_ID,
    CASES_FULL_GRID_ID,
    CASES_MATRIX_ID,
    CASES_MATRIX_METRIC_ID,
    CASES_MODEL_ID,
    CASES_NARRATIVE_STRUCTURE_ID,
    CASES_OUTCOME_FILTER_ID,
    CASES_PAGE_ID,
    CASES_RESET_FILTERS_ID,
    CASES_SELECTED_CASE_ID,
    CASES_SELECTED_OUTSIDE_NOTE_ID,
    CASES_SNAPSHOT_ID,
    CASES_STRATUM_FILTER_ID,
    CASES_TEMPLATE_COMPARISON_ID,
    CASES_UTILIZATION_ID,
    CASES_VALIDATOR_ID,
)
from ..settings import (
    CASE_COMPLETENESS_LABELS,
    CASE_MATRIX_METRIC_LABELS,
    CASE_OUTCOME_LABELS,
    CASE_STRATUM_LABELS,
    DEFAULT_CASE_EVIDENCE,
    DEFAULT_CASE_MATRIX_METRIC,
    DEFAULT_CASE_MODEL,
    EXPECTED_EVIDENCE_ORDER,
    EXPECTED_MODEL_ORDER,
    ROBUSTNESS_MODEL_LABELS,
    VISUALIZATION_RELEASE_ID,
)


PAGE_MODULE = "llm_xai_dashboard.cases"
ALL = "ALL"
_CASES_PREFIXES = ("cases.", "common.")


def register_page() -> None:
    if PAGE_MODULE not in dash.page_registry:
        dash.register_page(
            PAGE_MODULE,
            path="/cases",
            name="Cases",
            title="Case Explorer · LLM-XAI",
            description=(
                "Privacy-preserving canonical-case drill-down across RQ2, RQ3 and RQ6."
            ),
            order=5,
            layout=layout,
        )


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return frame.astype(object).where(pd.notna(frame), None).to_dict("records")


def _locale_tag(locale: object) -> str:
    return "vi-VN" if normalize_locale(locale) == "vi" else "en-US"


def _percent_formatter(locale: object = DEFAULT_LOCALE) -> dict[str, str]:
    return {
        "function": (
            "params.value == null ? '' : "
            f"new Intl.NumberFormat('{_locale_tag(locale)}', "
            "{style:'percent',minimumFractionDigits:1,maximumFractionDigits:1})"
            ".format(Number(params.value))"
        )
    }


def _stratum_label(locale: object, value: object) -> str:
    key = str(value)
    if key in CASE_STRATUM_LABELS:
        return t(locale, f"cases.stratum.{key}")
    return key


def _outcome_label(locale: object, value: object) -> str:
    key = str(value)
    if key in CASE_OUTCOME_LABELS:
        return t(locale, f"cases.outcome_labels.{key}")
    return key


def _case_catalog_display(
    catalog: pd.DataFrame,
    locale: object = DEFAULT_LOCALE,
) -> pd.DataFrame:
    resolved = normalize_locale(locale)
    display = catalog.copy()
    display["canonical_case"] = display["case_id"].map(
        lambda value: t(resolved, "cases.case_label", case_id=int(value))
    )
    display["stratum"] = display["selection_stratum"].map(
        lambda value: _stratum_label(resolved, value)
    )
    display["outcome"] = display["prediction_outcome"].map(
        lambda value: _outcome_label(resolved, value)
    )
    display["matrix_status"] = display.apply(
        lambda row: (
            t(resolved, "cases.complete")
            if bool(row["complete_llm_case"])
            else t(
                resolved,
                "cases.structured_failures",
                count=int(row["unusable_slot_count"]),
            )
        ),
        axis=1,
    )
    return display


def _case_options(
    catalog: pd.DataFrame,
    locale: object = DEFAULT_LOCALE,
) -> list[dict[str, object]]:
    display = _case_catalog_display(catalog, locale)
    return [
        {
            "value": int(row.case_id),
            "label": (
                f"{t(locale, 'cases.case_label', case_id=int(row.case_id))} · "
                f"{row.stratum} · {row.outcome}"
            ),
        }
        for row in display.itertuples()
    ]


def _case_browser_grid(catalog: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    display = _case_catalog_display(catalog, locale)
    columns = [
        {"field": "canonical_case", "headerName": "Canonical case", "minWidth": 135},
        {"field": "stratum", "headerName": "Selection stratum", "minWidth": 145},
        {"field": "outcome", "headerName": "Outcome", "minWidth": 130},
        {
            "field": "prediction_probability",
            "headerName": "Prediction",
            "valueFormatter": _percent_formatter(locale),
            "maxWidth": 120,
            "filter": False,
        },
        {
            "field": "distance_from_threshold",
            "headerName": "Threshold distance",
            "valueFormatter": _percent_formatter(locale),
            "maxWidth": 145,
            "filter": False,
        },
        {"field": "matrix_status", "headerName": "LLM matrix", "minWidth": 175},
    ]
    return data_grid(
        grid_id=CASES_BROWSER_GRID_ID,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=350,
        page_size=9,
        class_name="cases-data-grid",
        locale=locale,
    )


def _full_case_grid(frame: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    display = frame.copy()
    display["generator_family_label"] = display["generator_family"].replace(
        {"TEMPLATE": t(locale, "cases.deterministic_reference"), "LLM": "LLM"}
    )
    display["usable_label"] = display["usable"].map(
        {True: t(locale, "cases.usable"), False: t(locale, "cases.unusable")}
    )
    display["runtime_status"] = display["runtime_status"].replace(
        {"SUCCESS": t(locale, "cases.runtime_success")}
    )
    columns = [
        {"field": "generator_label", "headerName": "Generator", "minWidth": 185},
        {"field": "generator_family_label", "headerName": "Family", "minWidth": 145},
        {"field": "evidence_level", "headerName": "Evidence", "maxWidth": 95},
        {"field": "usable_label", "headerName": "Status", "minWidth": 110},
        {"field": "runtime_status", "headerName": "Runtime", "minWidth": 120},
        {"field": "end_to_end_faithfulness_yield", "headerName": "E2E", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "conservative_faithfulness", "headerName": "Conservative", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "verifiability", "headerName": "Verifiability", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "supported_count", "headerName": "Supported", "filter": False},
        {"field": "not_verifiable_count", "headerName": "Not verifiable", "filter": False},
        {"field": "unsupported_count", "headerName": "Unsupported", "filter": False},
        {"field": "contradicted_count", "headerName": "Contradicted", "filter": False},
        {"field": "output_word_count", "headerName": "Words", "filter": False},
        {"field": "latency_seconds", "headerName": "Latency (s)", "filter": False},
    ]
    return data_grid(
        grid_id=CASES_FULL_GRID_ID,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=430,
        page_size=12,
        class_name="cases-data-grid",
        locale=locale,
    )


def _focused_generation_row(repository, case_id: int, model_id: str, evidence_level: str) -> pd.Series:
    selected = repository.case_generations(case_id).loc[
        lambda frame: (frame["generator_id"] == model_id)
        & (frame["evidence_level"] == evidence_level)
    ]
    if len(selected) != 1:
        raise ValueError("Focused LLM generation is not unique")
    return selected.iloc[0].copy()


def _initial_state(
    repository,
    *,
    case: object,
    model: object,
    evidence: object,
    metric: object,
) -> tuple[int, str, str, str]:
    catalog = repository.case_catalog()
    case_ids = set(catalog["case_id"].astype(int))
    try:
        parsed_case = int(case)
    except (TypeError, ValueError):
        parsed_case = int(catalog.iloc[0]["case_id"])
    if parsed_case not in case_ids:
        parsed_case = int(catalog.iloc[0]["case_id"])
    resolved_model = str(model) if str(model) in EXPECTED_MODEL_ORDER else DEFAULT_CASE_MODEL
    resolved_evidence = str(evidence) if str(evidence) in EXPECTED_EVIDENCE_ORDER else DEFAULT_CASE_EVIDENCE
    resolved_metric = str(metric) if str(metric) in CASE_MATRIX_METRIC_LABELS else DEFAULT_CASE_MATRIX_METRIC
    return parsed_case, resolved_model, resolved_evidence, resolved_metric


def layout(
    case: object = None,
    model: object = None,
    evidence: object = None,
    metric: object = None,
    locale: object = DEFAULT_LOCALE,
    stratum_filter: object = ALL,
    outcome_filter: object = ALL,
    completeness_filter: object = ALL,
    **_: object,
):
    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    catalog = repository.case_catalog()
    case_id, model_id, evidence_level, metric_id = _initial_state(
        repository,
        case=case,
        model=model,
        evidence=evidence,
        metric=metric,
    )
    focused = repository.focused_case_data(case_id, model_id, evidence_level)
    focused_row = _focused_generation_row(repository, case_id, model_id, evidence_level)

    cohort_figure = build_cohort_landscape(catalog, selected_case_id=case_id)
    matrix_figure = build_case_performance_matrix(
        repository.case_generation_matrix(case_id, metric_id),
        metric_id=metric_id,
        focused_model_id=model_id,
        focused_evidence_level=evidence_level,
    )
    utilization_figure = build_evidence_utilization_profile(
        focused.utilization,
        model_id=model_id,
        model_label=ROBUSTNESS_MODEL_LABELS[model_id],
        evidence_level=evidence_level,
    )
    claim_figure = build_claim_composition(focused.validator_pair)
    validator_figure = build_candidate_v4_case_dumbbell(
        focused.validator_pair,
        model_label=ROBUSTNESS_MODEL_LABELS[model_id],
        evidence_level=evidence_level,
    )
    cohort_figure = localize_plotly_figure(cohort_figure, resolved_locale, prefixes=_CASES_PREFIXES)
    matrix_figure = localize_plotly_figure(matrix_figure, resolved_locale, prefixes=_CASES_PREFIXES)
    utilization_figure = localize_plotly_figure(utilization_figure, resolved_locale, prefixes=_CASES_PREFIXES)
    claim_figure = localize_plotly_figure(claim_figure, resolved_locale, prefixes=_CASES_PREFIXES)
    validator_figure = localize_plotly_figure(validator_figure, resolved_locale, prefixes=_CASES_PREFIXES)

    page = html.Main(
        [
            page_header(
                title="Case Explorer",
                subtitle=(
                    "Privacy-preserving drill-down across the frozen canonical cohort, "
                    "from case-selection context to generation-level quality, evidence "
                    "use, structure and sensitivity."
                ),
                endpoint="RQ2, RQ3 and RQ6",
                inference_unit="Certified descriptive drill-down",
                endpoint_label="Research scope",
                inference_label="Analysis mode",
                locale=resolved_locale,
            ),
            html.Div(
                [
                    html.Span(
                        "36 canonical cases · 6 balanced selection strata · "
                        "648 LLM generations · 216 deterministic-template generations"
                    ),
                    html.Button(
                        "Export case view",
                        id=CASES_EXPORT_ID,
                        type="button",
                        className="cases-export-button",
                    ),
                ],
                className="cases-context-line",
            ),
            dcc.Download(id=CASES_DOWNLOAD_ID),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2("Cohort filters"),
                            html.P(
                                "Filters guide navigation only; they never replace the selected case or rank cases by performance."
                            ),
                        ],
                        className="cases-filter-bar__header",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Selection stratum"),
                                    dcc.Dropdown(
                                        id=CASES_STRATUM_FILTER_ID,
                                        value=stratum_filter if str(stratum_filter) in {ALL, *CASE_STRATUM_LABELS} else ALL,
                                        clearable=False,
                                        options=[
                                            {"value": ALL, "label": "All strata"},
                                            *[
                                                {"value": key, "label": label}
                                                for key, label in CASE_STRATUM_LABELS.items()
                                            ],
                                        ],
                                    ),
                                ],
                                className="cases-control-group",
                            ),
                            html.Div(
                                [
                                    html.Label("Prediction outcome"),
                                    dcc.Dropdown(
                                        id=CASES_OUTCOME_FILTER_ID,
                                        value=outcome_filter if str(outcome_filter) in {ALL, *CASE_OUTCOME_LABELS} else ALL,
                                        clearable=False,
                                        options=[
                                            {"value": ALL, "label": "All outcomes"},
                                            *[
                                                {"value": key, "label": label}
                                                for key, label in CASE_OUTCOME_LABELS.items()
                                            ],
                                        ],
                                    ),
                                ],
                                className="cases-control-group",
                            ),
                            html.Div(
                                [
                                    html.Label("LLM matrix completeness"),
                                    dcc.Dropdown(
                                        id=CASES_COMPLETENESS_FILTER_ID,
                                        value=completeness_filter if str(completeness_filter) in CASE_COMPLETENESS_LABELS else ALL,
                                        clearable=False,
                                        options=[
                                            {"value": key, "label": label}
                                            for key, label in CASE_COMPLETENESS_LABELS.items()
                                        ],
                                    ),
                                ],
                                className="cases-control-group",
                            ),
                            html.Button(
                                "Reset cohort filters",
                                id=CASES_RESET_FILTERS_ID,
                                type="button",
                                className="cases-action-button",
                            ),
                        ],
                        className="cases-filter-controls",
                    ),
                ],
                className="cases-filter-bar",
            ),
            html.Section(
                [
                    chart_card(
                        graph_id=CASES_COHORT_ID,
                        title="Canonical cohort landscape",
                        subtitle="Prediction probability across the six frozen selection strata · one point per case",
                        figure=cohort_figure,
                        figure_id=FIG_CASES_COHORT,
                        source="case_heterogeneity_summary.csv",
                        metric="Prediction probability and selection stratum",
                        denominator="36 canonical cases",
                        release=VISUALIZATION_RELEASE_ID,
                        locale=resolved_locale,
                    ),
                    html.Section(
                        [
                            html.H2("Select canonical case"),
                            html.P(
                                "The default follows stable cohort order and is not selected for performance or diagnostic extremity."
                            ),
                            dcc.Dropdown(
                                id=CASES_SELECTED_CASE_ID,
                                value=case_id,
                                clearable=False,
                                options=_case_options(catalog, resolved_locale),
                            ),
                            html.Div(id=CASES_SELECTED_OUTSIDE_NOTE_ID),
                            html.Details(
                                [
                                    html.Summary("Browse all 36 canonical cases"),
                                    html.Div(
                                        _case_browser_grid(catalog, resolved_locale),
                                        className="cases-details__body",
                                    ),
                                ],
                                className="cases-details",
                            ),
                        ],
                        className="cases-browser-card",
                    ),
                ],
                className="cases-navigator-grid",
            ),
            html.Div(case_snapshot(focused.case_summary, locale=resolved_locale), id=CASES_SNAPSHOT_ID),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2("Case performance matrix"),
                            html.P(
                                "All 18 LLM and six deterministic-reference slots for the selected case."
                            ),
                        ],
                        className="cases-section-header",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Matrix metric"),
                                    dmc.SegmentedControl(
                                        id=CASES_MATRIX_METRIC_ID,
                                        value=metric_id,
                                        data=[
                                            {"value": key, "label": label}
                                            for key, label in CASE_MATRIX_METRIC_LABELS.items()
                                        ],
                                        fullWidth=True,
                                    ),
                                ],
                                className="cases-control-group",
                            ),
                        ],
                        className="cases-local-controls",
                    ),
                    html.Div(
                        [
                            chart_card(
                                graph_id=CASES_MATRIX_ID,
                                title="Generator × evidence results for the selected case",
                                subtitle="S0–S5 are categorical experimental conditions; Template is a separate reference row",
                                figure=matrix_figure,
                                figure_id=FIG_CASES_MATRIX,
                                source="case_heterogeneity_summary.csv",
                                metric=CASE_MATRIX_METRIC_LABELS[metric_id],
                                denominator="24 generation slots for one canonical case",
                                release=VISUALIZATION_RELEASE_ID,
                                locale=resolved_locale,
                            ),
                            html.Div(
                                focused_generation_panel(focused_row, locale=resolved_locale),
                                id=CASES_FOCUSED_GENERATION_ID,
                            ),
                        ],
                        className="cases-matrix-grid",
                    ),
                ],
                className="cases-focused-section",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2("Evidence condition"),
                            html.P(
                                "This local control updates the generator-independent evidence package and every focused-generation section below."
                            ),
                        ],
                        className="cases-section-header",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Evidence condition"),
                                    dcc.Dropdown(
                                        id=CASES_EVIDENCE_ID,
                                        value=evidence_level,
                                        clearable=False,
                                        options=[
                                            {"value": value, "label": value}
                                            for value in EXPECTED_EVIDENCE_ORDER
                                        ],
                                    ),
                                ],
                                className="cases-control-group",
                            ),
                        ],
                        className="cases-local-controls",
                    ),
                    html.Div(
                        evidence_package_panel(focused.evidence_package, locale=resolved_locale),
                        id=CASES_EVIDENCE_PACKAGE_ID,
                    ),
                ],
                className="cases-focused-section",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2("Focused LLM diagnostics"),
                            html.P(
                                "Focused LLM changes utilization, claims, structure and paired comparisons; it does not change the evidence package above."
                            ),
                        ],
                        className="cases-section-header",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Focused LLM"),
                                    dcc.Dropdown(
                                        id=CASES_MODEL_ID,
                                        value=model_id,
                                        clearable=False,
                                        options=[
                                            {"value": value, "label": ROBUSTNESS_MODEL_LABELS[value]}
                                            for value in EXPECTED_MODEL_ORDER
                                        ],
                                    ),
                                ],
                                className="cases-control-group",
                            ),
                        ],
                        className="cases-local-controls",
                    ),
                    html.Div(
                        [
                            chart_card(
                                graph_id=CASES_UTILIZATION_ID,
                                title="How the focused LLM used the supplied evidence",
                                subtitle="Defined utilization rates only · not applicable values remain N/A",
                                figure=utilization_figure,
                                figure_id=FIG_CASES_UTILIZATION,
                                source="evidence_utilization_summary.csv",
                                metric="Evidence-utilization profile",
                                denominator="One focused LLM generation",
                                release=VISUALIZATION_RELEASE_ID,
                                locale=resolved_locale,
                            ),
                            chart_card(
                                graph_id=CASES_CLAIM_COMPOSITION_ID,
                                title="Candidate claim outcomes",
                                subtitle="Primary artifact claim composition for the focused generation",
                                figure=claim_figure,
                                figure_id=FIG_CASES_CLAIM_COMPOSITION,
                                source="validator_generation_pairs.csv",
                                metric="Candidate claim-status counts",
                                denominator="One focused LLM generation",
                                release=VISUALIZATION_RELEASE_ID,
                                locale=resolved_locale,
                            ),
                        ],
                        className="cases-diagnostics-grid",
                    ),
                    html.Div(
                        narrative_structure_panel(focused.narrative_structure, locale=resolved_locale),
                        id=CASES_NARRATIVE_STRUCTURE_ID,
                    ),
                ],
                className="cases-focused-section",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            chart_card(
                                graph_id=CASES_VALIDATOR_ID,
                                title="How the focused generation changes under the sensitivity artifact",
                                subtitle="Candidate primary · V4 sensitivity-only · descriptive single-generation comparison",
                                figure=validator_figure,
                                figure_id=FIG_CASES_VALIDATOR_SENSITIVITY,
                                source="validator_generation_pairs.csv",
                                metric="Four paired generation-level rates",
                                denominator="One paired generation",
                                release=VISUALIZATION_RELEASE_ID,
                                locale=resolved_locale,
                            ),
                            html.Div(
                                template_comparison_panel(focused.template_pair, locale=resolved_locale),
                                id=CASES_TEMPLATE_COMPARISON_ID,
                            ),
                        ],
                        className="cases-sensitivity-grid",
                    ),
                ],
                className="cases-focused-section",
            ),
            html.Details(
                [
                    html.Summary("View all 24 generations for this case"),
                    html.Div(
                        _full_case_grid(focused.generations, resolved_locale),
                        className="cases-details__body",
                    ),
                ],
                className="cases-details",
            ),
            case_interpretation_boundaries(locale=resolved_locale),
        ],
        id=CASES_PAGE_ID,
        className="research-page cases-page",
        **{"data-rq": "RQ2-RQ3-RQ6", "data-analysis-mode": "certified-descriptive-drilldown"},
    )
    return localize_component_tree(page, resolved_locale, prefixes=_CASES_PREFIXES)
