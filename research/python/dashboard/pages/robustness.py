"""Page 5 — Measurement Robustness and deterministic Template Baseline."""

from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import dcc, html
import pandas as pd

from ..components.chart_card import chart_card
from ..components.data_grid import data_grid
from ..components.page_header import page_header
from ..components.robustness import (
    measurement_interpretation_panel,
    measurement_test_summary,
    research_boundaries,
    template_interpretation_panel,
    template_test_summary,
)
from ..data.repository import get_dashboard_repository
from ..figures.robustness import (
    FIG_ROBUSTNESS_MEASUREMENT_DELTA,
    FIG_ROBUSTNESS_MEASUREMENT_SHIFT,
    FIG_ROBUSTNESS_TEMPLATE_COVERAGE,
    FIG_ROBUSTNESS_TEMPLATE_DELTA,
    FIG_ROBUSTNESS_TEMPLATE_PROGRESSION,
    FIG_ROBUSTNESS_TEMPLATE_UPLIFT,
    build_candidate_v4_delta_distribution,
    build_candidate_v4_dumbbell,
    build_template_coverage_scatter,
    build_template_delta_distribution,
    build_template_evidence_progression,
    build_template_uplift_matrix,
)
from ..i18n import DEFAULT_LOCALE, localize_component_tree, normalize_locale
from ..ids import (
    ROBUSTNESS_DOWNLOAD_ID,
    ROBUSTNESS_EXPORT_ID,
    ROBUSTNESS_MEASUREMENT_DELTA_ID,
    ROBUSTNESS_MEASUREMENT_FOCUS_STORE_ID,
    ROBUSTNESS_MEASUREMENT_METRIC_ID,
    ROBUSTNESS_MEASUREMENT_MODEL_ID,
    ROBUSTNESS_MEASUREMENT_PANEL_ID,
    ROBUSTNESS_MEASUREMENT_SHIFT_ID,
    ROBUSTNESS_MEASUREMENT_TEST_GRID_ID,
    ROBUSTNESS_MEASUREMENT_TEST_SUMMARY_ID,
    ROBUSTNESS_PAGE_ID,
    ROBUSTNESS_TABS_ID,
    ROBUSTNESS_TEMPLATE_COVERAGE_ID,
    ROBUSTNESS_TEMPLATE_DELTA_ID,
    ROBUSTNESS_TEMPLATE_GENERATION_GRID_ID,
    ROBUSTNESS_TEMPLATE_METRIC_ID,
    ROBUSTNESS_TEMPLATE_MODEL_ID,
    ROBUSTNESS_TEMPLATE_PROGRESSION_ID,
    ROBUSTNESS_TEMPLATE_SCOPE_ID,
    ROBUSTNESS_TEMPLATE_TEST_GRID_ID,
    ROBUSTNESS_TEMPLATE_TEST_SUMMARY_ID,
    ROBUSTNESS_TEMPLATE_UPLIFT_ID,
)
from ..settings import (
    DEFAULT_ROBUSTNESS_METRIC,
    DEFAULT_TEMPLATE_METRIC,
    DEFAULT_TEMPLATE_SCOPE,
    EXPECTED_MODEL_ORDER,
    ROBUSTNESS_METRIC_LABELS,
    ROBUSTNESS_MODEL_LABELS,
    TEMPLATE_METRIC_LABELS,
    TEMPLATE_SCOPE_LABELS,
    VISUALIZATION_RELEASE_ID,
)


PAGE_MODULE = "llm_xai_dashboard.robustness"
ALL_MODELS = "ALL"
_ROBUSTNESS_PREFIXES = ("robustness.",)


def register_page() -> None:
    if PAGE_MODULE not in dash.page_registry:
        dash.register_page(
            PAGE_MODULE,
            path="/robustness",
            name="Robustness",
            title="Robustness & Template Baseline · LLM-XAI",
            description=(
                "Certified measurement sensitivity and deterministic Template "
                "Baseline comparison for RQ5–RQ6."
            ),
            order=4,
            layout=layout,
        )


def _locale_tag(locale: object) -> str:
    return "vi-VN" if normalize_locale(locale) == "vi" else "en-US"


def _percent_formatter(locale: object) -> dict[str, str]:
    return {
        "function": (
            "params.value == null ? '' : "
            f"new Intl.NumberFormat('{_locale_tag(locale)}', "
            "{style:'percent',minimumFractionDigits:1,maximumFractionDigits:1})"
            ".format(Number(params.value))"
        )
    }


def _number_formatter(locale: object, digits: int = 3) -> dict[str, str]:
    return {
        "function": (
            "params.value == null ? '' : "
            f"new Intl.NumberFormat('{_locale_tag(locale)}', "
            f"{{minimumFractionDigits:{digits},maximumFractionDigits:{digits}}})"
            ".format(Number(params.value))"
        )
    }


def _p_formatter(locale: object) -> dict[str, str]:
    decimal = "," if normalize_locale(locale) == "vi" else "."
    return {
        "function": (
            "params.value == null ? '' : "
            f"(params.value < 0.0001 ? '<0{decimal}0001' : "
            f"Number(params.value).toFixed(4).replace('.', '{decimal}'))"
        )
    }

def _scope_label(value: object) -> str:
    text = str(value)
    if text == "ALL":
        return "All configurations"
    if text in ROBUSTNESS_MODEL_LABELS:
        return ROBUSTNESS_MODEL_LABELS[text]
    return TEMPLATE_SCOPE_LABELS.get(text, text)


def _measurement_test_grid(frame: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    display = frame.copy()
    display["metric"] = display["metric_id"].map(ROBUSTNESS_METRIC_LABELS)
    display["scope"] = display["scope_id"].map(_scope_label)
    display["result"] = display["significant_adjusted"].map(
        {True: "Material paired difference", False: "No adjusted statistical difference"}
    )
    columns = [
        {"field": "metric", "headerName": "Metric", "minWidth": 180},
        {"field": "scope_family", "headerName": "Scope type", "maxWidth": 125},
        {"field": "scope", "headerName": "Scope", "minWidth": 160},
        {"field": "paired_case_count", "headerName": "Paired cases", "maxWidth": 115, "filter": False},
        {"field": "mean_delta_v4_minus_candidate", "headerName": "Mean Δ", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "median_delta_v4_minus_candidate", "headerName": "Median Δ", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "adjusted_p_value", "headerName": "Holm p", "valueFormatter": _p_formatter(locale), "filter": False},
        {"field": "rank_biserial_correlation", "headerName": "Effect size", "valueFormatter": _number_formatter(locale, 3), "filter": False},
        {"field": "result", "headerName": "Result", "minWidth": 205},
    ]
    return data_grid(
        grid_id=ROBUSTNESS_MEASUREMENT_TEST_GRID_ID,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=420,
        page_size=12,
        class_name="robustness-data-grid",
        locale=locale,
    )



def _template_delta_text(value: object, metric_id: str) -> str:
    if value is None or pd.isna(value):
        return "—"
    number = float(value)
    sign = "+" if number >= 0 else "−"
    magnitude = abs(number)
    if metric_id in {"end_to_end_faithfulness_yield", "conservative_faithfulness"}:
        return f"{sign}{magnitude * 100:.2f} pp"
    if metric_id == "output_word_count":
        return f"{sign}{magnitude:,.1f} words"
    return f"{sign}{magnitude:.2f}"

def _template_result(row: pd.Series) -> str:
    if row["metric_id"] == "output_word_count":
        return "Adjusted descriptive difference" if row["significant_adjusted"] else "No adjusted statistical difference"
    delta = float(row["mean_delta_llm_minus_template"])
    if bool(row["significant_adjusted"]):
        return "LLM advantage supported" if delta > 0 else "Template advantage supported"
    if delta > 0:
        return "Descriptive LLM advantage only"
    if delta < 0:
        return "Descriptive Template advantage only"
    return "No adjusted statistical difference"


def _template_tests_with_labels(frame: pd.DataFrame) -> pd.DataFrame:
    display = frame.copy()
    display["model_label"] = display["model_id"].map(ROBUSTNESS_MODEL_LABELS)
    display["model_order"] = display["model_id"].map(
        {model_id: index for index, model_id in enumerate(EXPECTED_MODEL_ORDER, start=1)}
    )
    display["metric"] = display["metric_id"].map(TEMPLATE_METRIC_LABELS)
    display["scope"] = display["evidence_scope"].map(TEMPLATE_SCOPE_LABELS)
    display["mean_delta_display"] = display.apply(
        lambda row: _template_delta_text(
            row["mean_delta_llm_minus_template"], str(row["metric_id"])
        ),
        axis=1,
    )
    display["median_delta_display"] = display.apply(
        lambda row: _template_delta_text(
            row["median_delta_llm_minus_template"], str(row["metric_id"])
        ),
        axis=1,
    )
    display["result"] = display.apply(_template_result, axis=1)
    return display


def _template_test_grid(frame: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    display = _template_tests_with_labels(frame)
    columns = [
        {"field": "model_label", "headerName": "Model", "minWidth": 160},
        {"field": "scope", "headerName": "Scope", "minWidth": 135},
        {"field": "metric", "headerName": "Metric", "minWidth": 180},
        {"field": "planned_pair_count", "headerName": "Planned", "maxWidth": 95, "filter": False},
        {"field": "paired_case_count", "headerName": "Observed", "maxWidth": 100, "filter": False},
        {"field": "excluded_pair_count", "headerName": "Excluded", "maxWidth": 95, "filter": False},
        {"field": "mean_delta_display", "headerName": "Mean Δ", "minWidth": 120, "filter": False},
        {"field": "median_delta_display", "headerName": "Median Δ", "minWidth": 120, "filter": False},
        {"field": "adjusted_p_value", "headerName": "Holm p", "valueFormatter": _p_formatter(locale), "filter": False},
        {"field": "rank_biserial_correlation", "headerName": "Effect size", "valueFormatter": _number_formatter(locale, 3), "filter": False},
        {"field": "result", "headerName": "Result", "minWidth": 205},
    ]
    return data_grid(
        grid_id=ROBUSTNESS_TEMPLATE_TEST_GRID_ID,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=440,
        page_size=12,
        class_name="robustness-data-grid",
        locale=locale,
    )


def _template_generation_grid(frame: pd.DataFrame, locale: object = DEFAULT_LOCALE):
    display = frame.copy()
    display["latency_status"] = "Measurement floor limited"
    columns = [
        {"field": "case_id", "headerName": "Case", "maxWidth": 110},
        {"field": "evidence_level", "headerName": "Evidence", "maxWidth": 100},
        {"field": "end_to_end_faithfulness_yield", "headerName": "E2E", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "conservative_faithfulness", "headerName": "Conservative", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "verifiability", "headerName": "Verifiability", "valueFormatter": _percent_formatter(locale), "filter": False},
        {"field": "supported_count", "headerName": "Supported", "filter": False},
        {"field": "supported_claims_per_100_words", "headerName": "Claims / 100 words", "valueFormatter": _number_formatter(locale, 2), "filter": False},
        {"field": "output_word_count", "headerName": "Words", "filter": False},
        {"field": "policy_violation_count", "headerName": "Policy violations", "filter": False},
        {"field": "latency_status", "headerName": "Latency status", "minWidth": 185},
    ]
    return data_grid(
        grid_id=ROBUSTNESS_TEMPLATE_GENERATION_GRID_ID,
        frame=display[[item["field"] for item in columns]],
        column_defs=columns,
        height=440,
        page_size=12,
        class_name="robustness-data-grid",
        locale=locale,
    )


def _measurement_focus(repository, metric_id: str, model_id: str) -> tuple[str, str]:
    summary = repository.measurement_shift_summary(
        metric_id,
        None if model_id == ALL_MODELS else model_id,
    )
    row = summary.iloc[summary["mean_delta_v4_minus_candidate"].abs().argmax()]
    return str(row["model_id"]), str(row["evidence_level"])


def _measurement_scope_test(repository, metric_id: str, model_id: str) -> pd.Series:
    if model_id == ALL_MODELS:
        return repository.measurement_test(metric_id, scope_family="OVERALL", scope_id="ALL")
    return repository.measurement_test(metric_id, scope_family="MODEL", scope_id=model_id)


def _measurement_tab(repository, data, metric_id: str, model_id: str, locale: object = DEFAULT_LOCALE, current_focus: object = None):
    resolved_model = model_id if model_id in EXPECTED_MODEL_ORDER else ALL_MODELS
    summary = repository.measurement_shift_summary(
        metric_id,
        None if resolved_model == ALL_MODELS else resolved_model,
    )
    valid_focuses = set(zip(summary["model_id"].astype(str), summary["evidence_level"].astype(str), strict=False))
    candidate_focus = (
        (str(current_focus.get("model_id")), str(current_focus.get("evidence_level")))
        if isinstance(current_focus, dict)
        else None
    )
    if candidate_focus in valid_focuses:
        focus_model, focus_evidence = candidate_focus
    else:
        focus_model, focus_evidence = _measurement_focus(repository, metric_id, resolved_model)
    cases = repository.measurement_case_deltas(metric_id, focus_model, focus_evidence)
    test = _measurement_scope_test(repository, metric_id, resolved_model)
    shift = build_candidate_v4_dumbbell(
        summary,
        metric_id=metric_id,
        focused_option_id=f"{focus_model}__{focus_evidence}",
    )
    distribution = build_candidate_v4_delta_distribution(
        cases,
        metric_id=metric_id,
        focus_label=f"{ROBUSTNESS_MODEL_LABELS[focus_model]} · {focus_evidence}",
    )
    return html.Div(
        [
            html.Section(
                [
                    html.Div(
                        [
                            html.Label("Measurement metric"),
                            dmc.SegmentedControl(
                                id=ROBUSTNESS_MEASUREMENT_METRIC_ID,
                                value=metric_id,
                                data=[
                                    {"value": key, "label": label}
                                    for key, label in ROBUSTNESS_METRIC_LABELS.items()
                                ],
                                fullWidth=True,
                            ),
                        ],
                        className="robustness-control-group",
                    ),
                    html.Div(
                        [
                            html.Label("Displayed scope"),
                            dcc.Dropdown(
                                id=ROBUSTNESS_MEASUREMENT_MODEL_ID,
                                value=resolved_model,
                                clearable=False,
                                options=[
                                    {"value": ALL_MODELS, "label": "All configurations"},
                                    *[
                                        {"value": item, "label": ROBUSTNESS_MODEL_LABELS[item]}
                                        for item in EXPECTED_MODEL_ORDER
                                    ],
                                ],
                            ),
                        ],
                        className="robustness-control-group",
                    ),
                ],
                className="robustness-controls",
            ),
            dcc.Store(
                id=ROBUSTNESS_MEASUREMENT_FOCUS_STORE_ID,
                data={"model_id": focus_model, "evidence_level": focus_evidence},
            ),
            html.Section(
                [
                    chart_card(
                        graph_id=ROBUSTNESS_MEASUREMENT_SHIFT_ID,
                        title="How much results change under the sensitivity artifact",
                        subtitle="Candidate and V4 measurements across the displayed LLM configurations",
                        figure=shift,
                        figure_id=FIG_ROBUSTNESS_MEASUREMENT_SHIFT,
                        source="648 paired generations",
                        metric=ROBUSTNESS_METRIC_LABELS[metric_id],
                        denominator="36 paired generations per configuration",
                        release=VISUALIZATION_RELEASE_ID,
                        locale=locale,
                    ),
                    html.Div(
                        measurement_interpretation_panel(
                            summary,
                            metric_label=ROBUSTNESS_METRIC_LABELS[metric_id],
                        ),
                        id=ROBUSTNESS_MEASUREMENT_PANEL_ID,
                    ),
                ],
                className="robustness-hero-grid",
            ),
            html.Section(
                [
                    chart_card(
                        graph_id=ROBUSTNESS_MEASUREMENT_DELTA_ID,
                        title="Case-level distribution of measurement shifts",
                        subtitle="V4 minus Candidate · one point per paired canonical case",
                        figure=distribution,
                        figure_id=FIG_ROBUSTNESS_MEASUREMENT_DELTA,
                        source="36 paired canonical cases",
                        metric=ROBUSTNESS_METRIC_LABELS[metric_id],
                        denominator="Focused model–evidence configuration",
                        release=VISUALIZATION_RELEASE_ID,
                        locale=locale,
                    ),
                    html.Div(
                        measurement_test_summary(test),
                        id=ROBUSTNESS_MEASUREMENT_TEST_SUMMARY_ID,
                    ),
                ],
                className="robustness-distribution-grid",
            ),
            html.Details(
                [
                    html.Summary("View all 40 measurement-sensitivity tests"),
                    html.Div(
                        _measurement_test_grid(data.validator_tests, locale),
                        className="robustness-details__body",
                    ),
                ],
                className="robustness-details",
            ),
            research_boundaries("measurement"),
        ],
        className="robustness-tab-content",
    )


def _resolved_template_focus(repository, metric_id: str, model_id: str, scope: str) -> str:
    if model_id in EXPECTED_MODEL_ORDER:
        return model_id
    summary = repository.template_uplift_summary(metric_id, scope)
    row = summary.iloc[summary["mean_delta_llm_minus_template"].abs().argmax()]
    return str(row["model_id"])


def _template_tab(repository, data, metric_id: str, model_id: str, scope: str, locale: object = DEFAULT_LOCALE):
    resolved_scope = scope if scope in TEMPLATE_SCOPE_LABELS else DEFAULT_TEMPLATE_SCOPE
    resolved_model = model_id if model_id in EXPECTED_MODEL_ORDER else ALL_MODELS
    focus_model = _resolved_template_focus(repository, metric_id, resolved_model, resolved_scope)
    progression = build_template_evidence_progression(
        data.baseline_summary,
        data.baseline_options,
        metric_id=metric_id,
    )
    tests = _template_tests_with_labels(data.baseline_tests)
    uplift = build_template_uplift_matrix(tests, evidence_scope=resolved_scope)
    cases = repository.template_case_deltas(metric_id, focus_model, resolved_scope)
    delta = build_template_delta_distribution(
        cases,
        metric_id=metric_id,
        focus_label=(
            f"{ROBUSTNESS_MODEL_LABELS[focus_model]} · "
            f"{TEMPLATE_SCOPE_LABELS[resolved_scope]}"
        ),
    )
    test = repository.template_test(metric_id, focus_model, resolved_scope)
    coverage = build_template_coverage_scatter(data.baseline_summary, data.baseline_options)
    return html.Div(
        [
            html.Div(
                [
                    html.Strong("Deterministic reference."),
                    html.Span(
                        " The Template Baseline is deterministic only at narrative generation. "
                        "It is not a fourth LLM and is excluded from decision ranking."
                    ),
                ],
                className="robustness-template-note",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Label("Comparison metric"),
                            dcc.Dropdown(
                                id=ROBUSTNESS_TEMPLATE_METRIC_ID,
                                value=metric_id,
                                clearable=False,
                                options=[
                                    {"value": key, "label": label}
                                    for key, label in TEMPLATE_METRIC_LABELS.items()
                                ],
                            ),
                        ],
                        className="robustness-control-group",
                    ),
                ],
                className="robustness-controls",
            ),
            html.Section(
                [
                    chart_card(
                        graph_id=ROBUSTNESS_TEMPLATE_PROGRESSION_ID,
                        title="LLM and deterministic-template profiles across evidence conditions",
                        subtitle="S0–S5 are categorical experimental conditions",
                        figure=progression,
                        figure_id=FIG_ROBUSTNESS_TEMPLATE_PROGRESSION,
                        source="648 LLM + 216 Template generations",
                        metric=TEMPLATE_METRIC_LABELS[metric_id],
                        denominator="36 generations per generator–condition profile",
                        release=VISUALIZATION_RELEASE_ID,
                        locale=locale,
                    ),
                    template_interpretation_panel(),
                ],
                className="robustness-hero-grid",
            ),
            html.Section(
                [
                    chart_card(
                        graph_id=ROBUSTNESS_TEMPLATE_UPLIFT_ID,
                        title="Paired LLM uplift relative to the template",
                        subtitle="Direction-aware case-paired deltas across the five planned RQ6 metrics",
                        figure=uplift,
                        figure_id=FIG_ROBUSTNESS_TEMPLATE_UPLIFT,
                        source="Frozen paired tests",
                        metric="Five planned RQ6 metrics",
                        denominator="36 paired canonical cases per model and scope",
                        release=VISUALIZATION_RELEASE_ID,
                        locale=locale,
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label("Focused LLM"),
                                            dcc.Dropdown(
                                                id=ROBUSTNESS_TEMPLATE_MODEL_ID,
                                                value=resolved_model,
                                                clearable=False,
                                                options=[
                                                    {
                                                        "value": ALL_MODELS,
                                                        "label": "Auto-focus largest paired shift",
                                                    },
                                                    *[
                                                        {
                                                            "value": item,
                                                            "label": ROBUSTNESS_MODEL_LABELS[item],
                                                        }
                                                        for item in EXPECTED_MODEL_ORDER
                                                    ],
                                                ],
                                            ),
                                            html.Span(
                                                "Updates the case distribution and frozen test summary.",
                                                className="robustness-local-control__hint",
                                            ),
                                        ],
                                        className=(
                                            "robustness-control-group "
                                            "robustness-local-control"
                                        ),
                                    ),
                                    html.Div(
                                        [
                                            html.Label("Evidence scope"),
                                            dcc.Dropdown(
                                                id=ROBUSTNESS_TEMPLATE_SCOPE_ID,
                                                value=resolved_scope,
                                                clearable=False,
                                                options=[
                                                    {"value": key, "label": label}
                                                    for key, label in TEMPLATE_SCOPE_LABELS.items()
                                                ],
                                            ),
                                            html.Span(
                                                "Updates the uplift matrix, case distribution, and frozen test summary.",
                                                className="robustness-local-control__hint",
                                            ),
                                        ],
                                        className=(
                                            "robustness-control-group "
                                            "robustness-local-control"
                                        ),
                                    ),
                                ],
                                className="robustness-local-controls-row",
                            ),
                            chart_card(
                                graph_id=ROBUSTNESS_TEMPLATE_DELTA_ID,
                                title="Case-level paired differences",
                                subtitle=(
                                    "LLM minus Template · one point per paired "
                                    "canonical case"
                                ),
                                figure=delta,
                                figure_id=FIG_ROBUSTNESS_TEMPLATE_DELTA,
                                source="36 paired canonical cases",
                                metric=TEMPLATE_METRIC_LABELS[metric_id],
                                denominator=TEMPLATE_SCOPE_LABELS[resolved_scope],
                                release=VISUALIZATION_RELEASE_ID,
                                locale=locale,
                            ),
                        ],
                        className="robustness-focused-comparison",
                    ),
                ],
                className="robustness-paired-grid",
            ),
            html.Div(
                template_test_summary(
                    test,
                    metric_id=metric_id,
                    scope_label=TEMPLATE_SCOPE_LABELS[resolved_scope],
                ),
                id=ROBUSTNESS_TEMPLATE_TEST_SUMMARY_ID,
            ),
            html.Details(
                [
                    html.Summary("Explore informational coverage"),
                    html.Div(
                        [
                            chart_card(
                                graph_id=ROBUSTNESS_TEMPLATE_COVERAGE_ID,
                                title="Informational coverage and operational faithfulness",
                                subtitle="Supported claim volume is descriptive and does not establish human usefulness",
                                figure=coverage,
                                figure_id=FIG_ROBUSTNESS_TEMPLATE_COVERAGE,
                                source="18 LLM options + 6 Template conditions",
                                metric="Mean E2E × supported claims per generation",
                                denominator="Generator–evidence profile",
                                release=VISUALIZATION_RELEASE_ID,
                                locale=locale,
                            )
                        ],
                        className="robustness-details__body",
                    ),
                ],
                className="robustness-details",
            ),
            html.Details(
                [
                    html.Summary("View all 105 LLM–Template paired tests"),
                    html.Div(
                        _template_test_grid(data.baseline_tests, locale),
                        className="robustness-details__body",
                    ),
                ],
                className="robustness-details",
            ),
            html.Details(
                [
                    html.Summary("View the 216 template generations"),
                    html.Div(
                        _template_generation_grid(data.baseline_generations, locale),
                        className="robustness-details__body",
                    ),
                ],
                className="robustness-details",
            ),
            research_boundaries("template"),
        ],
        className="robustness-tab-content",
    )


def layout(
    tab: str | None = None,
    metric: str | None = None,
    model: str | None = None,
    evidence: str | None = None,
    scope: str | None = None,
    locale: object = DEFAULT_LOCALE,
    measurement_metric_id: str | None = None,
    template_metric_id: str | None = None,
    measurement_model_id: str | None = None,
    template_model_id: str | None = None,
    measurement_focus: object = None,
    **_: object,
):
    repository = get_dashboard_repository()
    data = repository.robustness_data()
    selected_tab = tab if tab in {"measurement", "template"} else "measurement"
    measurement_metric = (
        measurement_metric_id
        if measurement_metric_id in ROBUSTNESS_METRIC_LABELS
        else metric if metric in ROBUSTNESS_METRIC_LABELS
        else DEFAULT_ROBUSTNESS_METRIC
    )
    template_metric = (
        template_metric_id
        if template_metric_id in TEMPLATE_METRIC_LABELS
        else metric if selected_tab == "template" and metric in TEMPLATE_METRIC_LABELS
        else DEFAULT_TEMPLATE_METRIC
    )
    selected_measurement_model = (
        measurement_model_id if measurement_model_id in EXPECTED_MODEL_ORDER
        else model if model in EXPECTED_MODEL_ORDER else ALL_MODELS
    )
    selected_template_model = (
        template_model_id if template_model_id in EXPECTED_MODEL_ORDER
        else model if model in EXPECTED_MODEL_ORDER else ALL_MODELS
    )
    template_scope = scope or evidence or DEFAULT_TEMPLATE_SCOPE
    if template_scope not in TEMPLATE_SCOPE_LABELS:
        template_scope = DEFAULT_TEMPLATE_SCOPE

    page = html.Main(
        [
            page_header(
                title="Robustness & Template Baseline",
                subtitle=(
                    "Assess measurement sensitivity and compare LLM narratives with "
                    "a deterministic reference under the same controlled evidence."
                ),
                endpoint="RQ5–RQ6",
                inference_unit="Certified sensitivity analysis",
                endpoint_label="Research questions",
                inference_label="Analysis mode",
                locale=locale,
            ),
            html.Div(
                [
                    html.Span(
                        "648 Candidate–V4 pairs · 216 template generations · "
                        "648 LLM–template pairs · 105 planned baseline tests"
                    ),
                    html.Button(
                        "Export robustness view",
                        id=ROBUSTNESS_EXPORT_ID,
                        className="page-export-button robustness-action-button",
                        type="button",
                    ),
                ],
                className="robustness-context",
            ),
            dcc.Download(id=ROBUSTNESS_DOWNLOAD_ID),
            dcc.Tabs(
                id=ROBUSTNESS_TABS_ID,
                value=selected_tab,
                className="effectiveness-tabs dashboard-tabs robustness-tabs",
                parent_className="effectiveness-tabs__parent",
                children=[
                    dcc.Tab(
                        label="Measurement robustness",
                        value="measurement",
                        className="tab",
                        selected_className="tab--selected",
                        children=_measurement_tab(
                            repository,
                            data,
                            measurement_metric,
                            selected_measurement_model,
                            locale,
                            measurement_focus,
                        ),
                    ),
                    dcc.Tab(
                        label="Template baseline",
                        value="template",
                        className="tab",
                        selected_className="tab--selected",
                        children=_template_tab(
                            repository,
                            data,
                            template_metric,
                            selected_template_model,
                            template_scope,
                            locale,
                        ),
                    ),
                ],
            ),
        ],
        id=ROBUSTNESS_PAGE_ID,
        className="research-page robustness-page",
        **{"data-rq": "RQ5-RQ6", "data-analysis-mode": "certified-sensitivity"},
    )
    return localize_component_tree(page, locale, prefixes=_ROBUSTNESS_PREFIXES)
