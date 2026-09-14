"""Callbacks and pure update helpers for Page 6 Case Explorer."""

from __future__ import annotations

from urllib.parse import urlencode

from dash import Input, Output, State, dcc, html, no_update
import pandas as pd

from ..components.cases import (
    case_snapshot,
    evidence_package_panel,
    focused_generation_panel,
    narrative_structure_panel,
    template_comparison_panel,
)
from ..data.repository import get_dashboard_repository
from ..export.case_figures import build_case_archive
from ..i18n import (
    DEFAULT_LOCALE,
    localize_component_tree,
    localize_plotly_figure,
    normalize_locale,
    t,
)
from ..figures.cases import (
    build_candidate_v4_case_dumbbell,
    build_case_performance_matrix,
    build_claim_composition,
    build_cohort_landscape,
    build_evidence_utilization_profile,
)
from ..ids import (
    APP_LOCALE_STORE_ID,
    APP_LOCATION_ID,
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
from ..pages.cases import (
    ALL,
    _case_catalog_display,
    _case_options,
    _focused_generation_row,
    layout as cases_layout,
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
)


_CASES_PREFIXES = ("cases.", "common.")

def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return frame.astype(object).where(pd.notna(frame), None).to_dict("records")


def _resolved_case(repository, case_id: object) -> int:
    catalog = repository.case_catalog()
    valid = set(catalog["case_id"].astype(int))
    try:
        parsed = int(case_id)
    except (TypeError, ValueError):
        return int(catalog.iloc[0]["case_id"])
    return parsed if parsed in valid else int(catalog.iloc[0]["case_id"])


def _resolved_model(model_id: object) -> str:
    return str(model_id) if str(model_id) in EXPECTED_MODEL_ORDER else DEFAULT_CASE_MODEL


def _resolved_evidence(evidence_level: object) -> str:
    return str(evidence_level) if str(evidence_level) in EXPECTED_EVIDENCE_ORDER else DEFAULT_CASE_EVIDENCE


def _resolved_metric(metric_id: object) -> str:
    return str(metric_id) if str(metric_id) in CASE_MATRIX_METRIC_LABELS else DEFAULT_CASE_MATRIX_METRIC


def filter_case_catalog(
    catalog: pd.DataFrame,
    stratum: object,
    outcome: object,
    completeness: object,
) -> pd.DataFrame:
    """Apply navigation filters without ranking or replacing the selected case."""

    filtered = catalog.copy()
    if str(stratum) in CASE_STRATUM_LABELS:
        filtered = filtered.loc[filtered["selection_stratum"] == str(stratum)]
    if str(outcome) in CASE_OUTCOME_LABELS:
        filtered = filtered.loc[filtered["prediction_outcome"] == str(outcome)]
    if str(completeness) == "COMPLETE":
        filtered = filtered.loc[filtered["complete_llm_case"].astype(bool)]
    elif str(completeness) == "INCOMPLETE":
        filtered = filtered.loc[~filtered["complete_llm_case"].astype(bool)]
    return filtered.sort_values(["selection_rank", "case_id"], kind="stable").reset_index(drop=True)


def cohort_updates(
    stratum: object,
    outcome: object,
    completeness: object,
    selected_case_id: object,
    locale: object = DEFAULT_LOCALE,
):
    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    catalog = repository.case_catalog()
    selected_case = _resolved_case(repository, selected_case_id)
    filtered = filter_case_catalog(catalog, stratum, outcome, completeness)
    selected_outside = selected_case not in set(filtered["case_id"].astype(int))

    options_frame = filtered.copy()
    if selected_outside:
        selected_row = catalog.loc[catalog["case_id"] == selected_case]
        options_frame = pd.concat([selected_row, options_frame], ignore_index=True)
        options_frame = options_frame.drop_duplicates("case_id", keep="first")

    note = (
        localize_component_tree(
            html.P(
                "Selected case is outside the current cohort filter. Its drill-down remains fixed until you explicitly select another case.",
                className="cases-selected-outside-note",
            ),
            resolved_locale,
            prefixes=_CASES_PREFIXES,
        )
        if selected_outside
        else ""
    )
    display = _case_catalog_display(filtered, resolved_locale)
    browser_columns = [
        "canonical_case", "stratum", "outcome", "prediction_probability",
        "distance_from_threshold", "matrix_status",
    ]
    return (
        localize_plotly_figure(
            build_cohort_landscape(filtered, selected_case_id=selected_case),
            resolved_locale,
            prefixes=_CASES_PREFIXES,
        ),
        _case_options(options_frame, resolved_locale),
        _records(display[browser_columns]),
        note,
    )


def case_from_cohort_click(click_data: object) -> int | None:
    if not isinstance(click_data, dict):
        return None
    points = click_data.get("points")
    if not isinstance(points, list) or not points:
        return None
    custom = points[0].get("customdata")
    if not isinstance(custom, (list, tuple)) or not custom:
        return None
    try:
        return int(custom[0])
    except (TypeError, ValueError):
        return None


def matrix_focus_from_click(click_data: object) -> tuple[str | None, str | None]:
    """Return model/evidence focus; Template clicks preserve the current LLM."""

    if not isinstance(click_data, dict):
        return None, None
    points = click_data.get("points")
    if not isinstance(points, list) or not points:
        return None, None
    custom = points[0].get("customdata")
    if not isinstance(custom, (list, tuple)) or len(custom) < 4:
        return None, None
    generator_family = str(custom[1])
    generator_id = str(custom[2])
    evidence_level = str(custom[3])
    if evidence_level not in EXPECTED_EVIDENCE_ORDER:
        return None, None
    if generator_family == "TEMPLATE" or generator_id == "template_baseline":
        return None, evidence_level
    if generator_id not in EXPECTED_MODEL_ORDER:
        return None, None
    return generator_id, evidence_level


def case_identity_updates(case_id: object, locale: object = DEFAULT_LOCALE):
    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    resolved_case = _resolved_case(repository, case_id)
    summary = repository.case_summary(resolved_case)
    generations = repository.case_generations(resolved_case).copy()
    generations["generator_family_label"] = generations["generator_family"].replace(
        {"TEMPLATE": t(resolved_locale, "cases.deterministic_reference"), "LLM": "LLM"}
    )
    generations["usable_label"] = generations["usable"].map(
        {
            True: t(resolved_locale, "cases.usable"),
            False: t(resolved_locale, "cases.unusable"),
        }
    )
    generations["runtime_status"] = generations["runtime_status"].replace(
        {"SUCCESS": t(resolved_locale, "cases.runtime_success")}
    )
    columns = [
        "generator_label", "generator_family_label", "evidence_level",
        "usable_label", "runtime_status", "end_to_end_faithfulness_yield",
        "conservative_faithfulness", "verifiability", "supported_count",
        "not_verifiable_count", "unsupported_count", "contradicted_count",
        "output_word_count", "latency_seconds",
    ]
    return case_snapshot(summary, locale=resolved_locale), _records(generations[columns])


def matrix_updates(
    case_id: object,
    metric_id: object,
    model_id: object,
    evidence_level: object,
    locale: object = DEFAULT_LOCALE,
):
    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    case = _resolved_case(repository, case_id)
    metric = _resolved_metric(metric_id)
    model = _resolved_model(model_id)
    evidence = _resolved_evidence(evidence_level)
    figure = build_case_performance_matrix(
        repository.case_generation_matrix(case, metric),
        metric_id=metric,
        focused_model_id=model,
        focused_evidence_level=evidence,
    )
    row = _focused_generation_row(repository, case, model, evidence)
    return (
        localize_plotly_figure(figure, resolved_locale, prefixes=_CASES_PREFIXES),
        focused_generation_panel(row, locale=resolved_locale),
    )


def evidence_package_update(
    case_id: object,
    evidence_level: object,
    locale: object = DEFAULT_LOCALE,
):
    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    case = _resolved_case(repository, case_id)
    evidence = _resolved_evidence(evidence_level)
    return evidence_package_panel(
        repository.case_evidence_package(case, evidence),
        locale=resolved_locale,
    )


def focused_diagnostics_updates(
    case_id: object,
    model_id: object,
    evidence_level: object,
    locale: object = DEFAULT_LOCALE,
):
    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    case = _resolved_case(repository, case_id)
    model = _resolved_model(model_id)
    evidence = _resolved_evidence(evidence_level)
    focused = repository.focused_case_data(case, model, evidence)
    return (
        localize_plotly_figure(
            build_evidence_utilization_profile(
            focused.utilization,
            model_id=model,
            model_label=ROBUSTNESS_MODEL_LABELS[model],
            evidence_level=evidence,
            ),
            resolved_locale,
            prefixes=_CASES_PREFIXES,
        ),
        localize_plotly_figure(
            build_claim_composition(focused.validator_pair),
            resolved_locale,
            prefixes=_CASES_PREFIXES,
        ),
        narrative_structure_panel(
            focused.narrative_structure, locale=resolved_locale
        ),
        localize_plotly_figure(
            build_candidate_v4_case_dumbbell(
            focused.validator_pair,
            model_label=ROBUSTNESS_MODEL_LABELS[model],
            evidence_level=evidence,
            ),
            resolved_locale,
            prefixes=_CASES_PREFIXES,
        ),
        template_comparison_panel(focused.template_pair, locale=resolved_locale),
    )


def register_case_callbacks(app) -> None:
    @app.callback(
        Output(CASES_PAGE_ID, "children"),
        Input(APP_LOCALE_STORE_ID, "data"),
        State(CASES_STRATUM_FILTER_ID, "value", allow_optional=True),
        State(CASES_OUTCOME_FILTER_ID, "value", allow_optional=True),
        State(CASES_COMPLETENESS_FILTER_ID, "value", allow_optional=True),
        State(CASES_SELECTED_CASE_ID, "value", allow_optional=True),
        State(CASES_MODEL_ID, "value", allow_optional=True),
        State(CASES_EVIDENCE_ID, "value", allow_optional=True),
        State(CASES_MATRIX_METRIC_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def relocalize_cases_page(
        locale, stratum, outcome, completeness, case_id, model_id, evidence, metric
    ):
        page = cases_layout(
            case=case_id,
            model=model_id,
            evidence=evidence,
            metric=metric,
            locale=locale,
            stratum_filter=stratum,
            outcome_filter=outcome,
            completeness_filter=completeness,
        )
        return page.children

    @app.callback(
        Output(CASES_COHORT_ID, "figure"),
        Output(CASES_SELECTED_CASE_ID, "options"),
        Output(CASES_BROWSER_GRID_ID, "rowData"),
        Output(CASES_SELECTED_OUTSIDE_NOTE_ID, "children"),
        Input(CASES_STRATUM_FILTER_ID, "value"),
        Input(CASES_OUTCOME_FILTER_ID, "value"),
        Input(CASES_COMPLETENESS_FILTER_ID, "value"),
        Input(CASES_SELECTED_CASE_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_cohort(stratum, outcome, completeness, selected_case, locale):
        return cohort_updates(
            stratum, outcome, completeness, selected_case, locale
        )

    @app.callback(
        Output(CASES_STRATUM_FILTER_ID, "value"),
        Output(CASES_OUTCOME_FILTER_ID, "value"),
        Output(CASES_COMPLETENESS_FILTER_ID, "value"),
        Input(CASES_RESET_FILTERS_ID, "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_filters(n_clicks):
        if not n_clicks:
            return no_update, no_update, no_update
        return ALL, ALL, ALL

    @app.callback(
        Output(CASES_SELECTED_CASE_ID, "value"),
        Input(CASES_COHORT_ID, "clickData"),
        prevent_initial_call=True,
    )
    def select_case_from_cohort(click_data):
        case_id = case_from_cohort_click(click_data)
        if case_id is None:
            return no_update
        return case_id

    @app.callback(
        Output(CASES_MODEL_ID, "value"),
        Output(CASES_EVIDENCE_ID, "value"),
        Input(CASES_MATRIX_ID, "clickData"),
        prevent_initial_call=True,
    )
    def select_generation_from_matrix(click_data):
        model_id, evidence_level = matrix_focus_from_click(click_data)
        if evidence_level is None:
            return no_update, no_update
        if model_id is None:
            return no_update, evidence_level
        return model_id, evidence_level

    @app.callback(
        Output(CASES_SNAPSHOT_ID, "children"),
        Output(CASES_FULL_GRID_ID, "rowData"),
        Input(CASES_SELECTED_CASE_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_case_identity(case_id, locale):
        return case_identity_updates(case_id, locale)

    @app.callback(
        Output(CASES_MATRIX_ID, "figure"),
        Output(CASES_FOCUSED_GENERATION_ID, "children"),
        Input(CASES_SELECTED_CASE_ID, "value"),
        Input(CASES_MATRIX_METRIC_ID, "value"),
        Input(CASES_MODEL_ID, "value"),
        Input(CASES_EVIDENCE_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_matrix(case_id, metric_id, model_id, evidence_level, locale):
        return matrix_updates(
            case_id, metric_id, model_id, evidence_level, locale
        )

    @app.callback(
        Output(CASES_EVIDENCE_PACKAGE_ID, "children"),
        Input(CASES_SELECTED_CASE_ID, "value"),
        Input(CASES_EVIDENCE_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_evidence_package(case_id, evidence_level, locale):
        return evidence_package_update(case_id, evidence_level, locale)

    @app.callback(
        Output(CASES_UTILIZATION_ID, "figure"),
        Output(CASES_CLAIM_COMPOSITION_ID, "figure"),
        Output(CASES_NARRATIVE_STRUCTURE_ID, "children"),
        Output(CASES_VALIDATOR_ID, "figure"),
        Output(CASES_TEMPLATE_COMPARISON_ID, "children"),
        Input(CASES_SELECTED_CASE_ID, "value"),
        Input(CASES_MODEL_ID, "value"),
        Input(CASES_EVIDENCE_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_focused_diagnostics(case_id, model_id, evidence_level, locale):
        return focused_diagnostics_updates(
            case_id, model_id, evidence_level, locale
        )

    @app.callback(
        Output(APP_LOCATION_ID, "search", allow_duplicate=True),
        Input(CASES_SELECTED_CASE_ID, "value"),
        Input(CASES_MODEL_ID, "value"),
        Input(CASES_EVIDENCE_ID, "value"),
        Input(CASES_MATRIX_METRIC_ID, "value"),
        prevent_initial_call=True,
    )
    def update_case_url(case_id, model_id, evidence_level, metric_id):
        repository = get_dashboard_repository()
        query = urlencode(
            {
                "case": _resolved_case(repository, case_id),
                "model": _resolved_model(model_id),
                "evidence": _resolved_evidence(evidence_level),
                "metric": _resolved_metric(metric_id),
            }
        )
        return f"?{query}"

    @app.callback(
        Output(CASES_DOWNLOAD_ID, "data"),
        Input(CASES_EXPORT_ID, "n_clicks"),
        State(CASES_SELECTED_CASE_ID, "value"),
        State(CASES_MODEL_ID, "value"),
        State(CASES_EVIDENCE_ID, "value"),
        State(CASES_MATRIX_METRIC_ID, "value"),
        State(APP_LOCALE_STORE_ID, "data"),
        prevent_initial_call=True,
    )
    def export_case_view(
        n_clicks, case_id, model_id, evidence_level, metric_id, locale
    ):
        if not n_clicks:
            return no_update
        repository = get_dashboard_repository()
        resolved_case = _resolved_case(repository, case_id)
        payload = build_case_archive(
            case_id=resolved_case,
            model_id=_resolved_model(model_id),
            evidence_level=_resolved_evidence(evidence_level),
            metric_id=_resolved_metric(metric_id),
            locale=locale,
        )
        return dcc.send_bytes(
            lambda target: target.write(payload),
            f"LLM_XAI_Case_Explorer_{resolved_case}.zip",
        )
