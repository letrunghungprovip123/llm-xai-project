"""Callbacks and pure update helpers for Page 5."""

from __future__ import annotations

from dash import Input, Output, State, ctx, dcc, no_update
from ..components.robustness import (
    measurement_interpretation_panel,
    measurement_test_summary,
    template_test_summary,
)
from ..data.repository import get_dashboard_repository
from ..i18n import DEFAULT_LOCALE, localize_component_tree, localize_plotly_figure
from ..figures.robustness import (
    build_candidate_v4_delta_distribution,
    build_candidate_v4_dumbbell,
    build_template_delta_distribution,
    build_template_evidence_progression,
    build_template_uplift_matrix,
)
from ..export.robustness_figures import build_robustness_archive
from ..ids import (
    APP_LOCALE_STORE_ID,
    ROBUSTNESS_DOWNLOAD_ID,
    ROBUSTNESS_EXPORT_ID,
    ROBUSTNESS_MEASUREMENT_DELTA_ID,
    ROBUSTNESS_MEASUREMENT_FOCUS_STORE_ID,
    ROBUSTNESS_MEASUREMENT_METRIC_ID,
    ROBUSTNESS_MEASUREMENT_MODEL_ID,
    ROBUSTNESS_MEASUREMENT_PANEL_ID,
    ROBUSTNESS_MEASUREMENT_SHIFT_ID,
    ROBUSTNESS_MEASUREMENT_TEST_SUMMARY_ID,
    ROBUSTNESS_PAGE_ID,
    ROBUSTNESS_TABS_ID,
    ROBUSTNESS_TEMPLATE_DELTA_ID,
    ROBUSTNESS_TEMPLATE_METRIC_ID,
    ROBUSTNESS_TEMPLATE_MODEL_ID,
    ROBUSTNESS_TEMPLATE_PROGRESSION_ID,
    ROBUSTNESS_TEMPLATE_SCOPE_ID,
    ROBUSTNESS_TEMPLATE_TEST_SUMMARY_ID,
    ROBUSTNESS_TEMPLATE_UPLIFT_ID,
)
from ..pages.robustness import ALL_MODELS, _template_tests_with_labels, layout as robustness_layout
from ..settings import (
    DEFAULT_ROBUSTNESS_METRIC,
    DEFAULT_TEMPLATE_METRIC,
    DEFAULT_TEMPLATE_SCOPE,
    EXPECTED_EVIDENCE_ORDER,
    EXPECTED_MODEL_ORDER,
    ROBUSTNESS_METRIC_LABELS,
    ROBUSTNESS_MODEL_LABELS,
    TEMPLATE_METRIC_LABELS,
    TEMPLATE_SCOPE_LABELS,
)


def _focus_from_click(click_data: object) -> tuple[str, str] | None:
    if not isinstance(click_data, dict):
        return None
    points = click_data.get("points")
    if not isinstance(points, list) or not points:
        return None
    customdata = points[0].get("customdata")
    if not isinstance(customdata, (list, tuple)) or len(customdata) < 3:
        return None
    model_id = str(customdata[0])
    evidence_level = str(customdata[2])
    if model_id not in EXPECTED_MODEL_ORDER or evidence_level not in EXPECTED_EVIDENCE_ORDER:
        return None
    return model_id, evidence_level


def measurement_updates(
    metric_id: str | None,
    model_id: str | None,
    click_data: object,
    current_focus: object,
    *,
    accept_click: bool = True,
    locale: object = DEFAULT_LOCALE,
):
    repository = get_dashboard_repository()
    metric = metric_id if metric_id in ROBUSTNESS_METRIC_LABELS else DEFAULT_ROBUSTNESS_METRIC
    model = model_id if model_id in EXPECTED_MODEL_ORDER else ALL_MODELS
    summary = repository.measurement_shift_summary(
        metric,
        None if model == ALL_MODELS else model,
    )

    valid_keys = set(zip(summary["model_id"], summary["evidence_level"], strict=False))
    focus = _focus_from_click(click_data) if accept_click else None
    if focus not in valid_keys:
        focus = None
    if focus is None and isinstance(current_focus, dict):
        candidate = (
            str(current_focus.get("model_id")),
            str(current_focus.get("evidence_level")),
        )
        if candidate in valid_keys:
            focus = candidate
    if focus is None:
        row = summary.iloc[summary["mean_delta_v4_minus_candidate"].abs().argmax()]
        focus = str(row["model_id"]), str(row["evidence_level"])

    focus_model, focus_evidence = focus
    cases = repository.measurement_case_deltas(metric, focus_model, focus_evidence)
    if model == ALL_MODELS:
        test = repository.measurement_test(metric, scope_family="OVERALL", scope_id="ALL")
    else:
        test = repository.measurement_test(metric, scope_family="MODEL", scope_id=model)
    return (
        localize_plotly_figure(
            build_candidate_v4_dumbbell(
                summary,
                metric_id=metric,
                focused_option_id=f"{focus_model}__{focus_evidence}",
            ),
            locale,
            prefixes=("robustness.",),
        ),
        localize_component_tree(
            measurement_interpretation_panel(
                summary,
                metric_label=ROBUSTNESS_METRIC_LABELS[metric],
            ),
            locale,
            prefixes=("robustness.",),
        ),
        {"model_id": focus_model, "evidence_level": focus_evidence},
        localize_plotly_figure(
            build_candidate_v4_delta_distribution(
                cases,
                metric_id=metric,
                focus_label=f"{ROBUSTNESS_MODEL_LABELS[focus_model]} · {focus_evidence}",
            ),
            locale,
            prefixes=("robustness.",),
        ),
        localize_component_tree(measurement_test_summary(test), locale, prefixes=("robustness.",)),
    )


def _resolved_template_model(repository, metric_id: str, model_id: str, scope: str) -> str:
    if model_id in EXPECTED_MODEL_ORDER:
        return model_id
    summary = repository.template_uplift_summary(metric_id, scope)
    row = summary.iloc[summary["mean_delta_llm_minus_template"].abs().argmax()]
    return str(row["model_id"])


def template_progression_update(metric_id: str | None, locale: object = DEFAULT_LOCALE):
    """Update only the evidence-progression chart for the selected metric."""

    repository = get_dashboard_repository()
    metric = metric_id if metric_id in TEMPLATE_METRIC_LABELS else DEFAULT_TEMPLATE_METRIC
    return localize_plotly_figure(
        build_template_evidence_progression(
            repository.llm_vs_template_summary(),
            repository.baseline_option_performance(),
            metric_id=metric,
        ),
        locale,
        prefixes=("robustness.",),
    )


def template_uplift_update(evidence_scope: str | None, locale: object = DEFAULT_LOCALE):
    """Update only the five-metric uplift matrix for the selected scope."""

    repository = get_dashboard_repository()
    scope = evidence_scope if evidence_scope in TEMPLATE_SCOPE_LABELS else DEFAULT_TEMPLATE_SCOPE
    tests = _template_tests_with_labels(repository.llm_vs_template_tests())
    return localize_plotly_figure(build_template_uplift_matrix(tests, evidence_scope=scope), locale, prefixes=("robustness.",))


def template_focus_updates(
    metric_id: str | None,
    model_id: str | None,
    evidence_scope: str | None,
    locale: object = DEFAULT_LOCALE,
):
    """Update the case distribution and its frozen test summary only."""

    repository = get_dashboard_repository()
    metric = metric_id if metric_id in TEMPLATE_METRIC_LABELS else DEFAULT_TEMPLATE_METRIC
    scope = evidence_scope if evidence_scope in TEMPLATE_SCOPE_LABELS else DEFAULT_TEMPLATE_SCOPE
    model = model_id if model_id in EXPECTED_MODEL_ORDER else ALL_MODELS
    focus_model = _resolved_template_model(repository, metric, model, scope)
    cases = repository.template_case_deltas(metric, focus_model, scope)
    test = repository.template_test(metric, focus_model, scope)
    return (
        localize_plotly_figure(
            build_template_delta_distribution(
                cases,
                metric_id=metric,
                focus_label=(
                    f"{ROBUSTNESS_MODEL_LABELS[focus_model]} · "
                    f"{TEMPLATE_SCOPE_LABELS[scope]}"
                ),
            ),
            locale,
            prefixes=("robustness.",),
        ),
        localize_component_tree(
            template_test_summary(
                test,
                metric_id=metric,
                scope_label=TEMPLATE_SCOPE_LABELS[scope],
            ),
            locale,
            prefixes=("robustness.",),
        ),
    )


def register_robustness_callbacks(app) -> None:
    @app.callback(
        Output(ROBUSTNESS_PAGE_ID, "children"),
        Input(APP_LOCALE_STORE_ID, "data"),
        State(ROBUSTNESS_TABS_ID, "value", allow_optional=True),
        State(ROBUSTNESS_MEASUREMENT_METRIC_ID, "value", allow_optional=True),
        State(ROBUSTNESS_TEMPLATE_METRIC_ID, "value", allow_optional=True),
        State(ROBUSTNESS_MEASUREMENT_MODEL_ID, "value", allow_optional=True),
        State(ROBUSTNESS_TEMPLATE_MODEL_ID, "value", allow_optional=True),
        State(ROBUSTNESS_TEMPLATE_SCOPE_ID, "value", allow_optional=True),
        State(ROBUSTNESS_MEASUREMENT_FOCUS_STORE_ID, "data", allow_optional=True),
        prevent_initial_call=True,
    )
    def relocalize_robustness_page(
        locale, tab, measurement_metric, template_metric, measurement_model,
        template_model, scope, focus,
    ):
        page = robustness_layout(
            tab=tab,
            locale=locale,
            measurement_metric_id=measurement_metric,
            template_metric_id=template_metric,
            measurement_model_id=measurement_model,
            template_model_id=template_model,
            scope=scope,
            measurement_focus=focus,
        )
        return page.children
    @app.callback(
        Output(ROBUSTNESS_MEASUREMENT_SHIFT_ID, "figure"),
        Output(ROBUSTNESS_MEASUREMENT_PANEL_ID, "children"),
        Output(ROBUSTNESS_MEASUREMENT_FOCUS_STORE_ID, "data"),
        Output(ROBUSTNESS_MEASUREMENT_DELTA_ID, "figure"),
        Output(ROBUSTNESS_MEASUREMENT_TEST_SUMMARY_ID, "children"),
        Input(ROBUSTNESS_MEASUREMENT_METRIC_ID, "value"),
        Input(ROBUSTNESS_MEASUREMENT_MODEL_ID, "value"),
        Input(ROBUSTNESS_MEASUREMENT_SHIFT_ID, "clickData"),
        Input(APP_LOCALE_STORE_ID, "data"),
        State(ROBUSTNESS_MEASUREMENT_FOCUS_STORE_ID, "data"),
    )
    def update_measurement(metric_id, model_id, click_data, locale, current_focus):
        return measurement_updates(
            metric_id,
            model_id,
            click_data,
            current_focus,
            accept_click=ctx.triggered_id == ROBUSTNESS_MEASUREMENT_SHIFT_ID,
            locale=locale,
        )

    @app.callback(
        Output(ROBUSTNESS_TEMPLATE_PROGRESSION_ID, "figure"),
        Input(ROBUSTNESS_TEMPLATE_METRIC_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_template_progression(metric_id, locale):
        return template_progression_update(metric_id, locale)

    @app.callback(
        Output(ROBUSTNESS_TEMPLATE_UPLIFT_ID, "figure"),
        Input(ROBUSTNESS_TEMPLATE_SCOPE_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_template_uplift(evidence_scope, locale):
        return template_uplift_update(evidence_scope, locale)

    @app.callback(
        Output(ROBUSTNESS_TEMPLATE_DELTA_ID, "figure"),
        Output(ROBUSTNESS_TEMPLATE_TEST_SUMMARY_ID, "children"),
        Input(ROBUSTNESS_TEMPLATE_METRIC_ID, "value"),
        Input(ROBUSTNESS_TEMPLATE_MODEL_ID, "value"),
        Input(ROBUSTNESS_TEMPLATE_SCOPE_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_template_focus(metric_id, model_id, evidence_scope, locale):
        return template_focus_updates(metric_id, model_id, evidence_scope, locale)

    @app.callback(
        Output(ROBUSTNESS_DOWNLOAD_ID, "data"),
        Input(ROBUSTNESS_EXPORT_ID, "n_clicks"),
        State(APP_LOCALE_STORE_ID, "data"),
        prevent_initial_call=True,
    )
    def export_robustness(n_clicks, locale):
        if not n_clicks:
            return no_update
        payload = build_robustness_archive(locale=locale)
        return dcc.send_bytes(
            lambda target: target.write(payload),
            "LLM_XAI_Robustness_Template_Baseline_view.zip",
        )
