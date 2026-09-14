from __future__ import annotations

from dash import Input, Output, State, ctx, dcc, no_update

from .settings import DATASET_SCOPES
from .shell import (
    EXPORT_BUTTON,
    EXPORT_DOWNLOAD,
    LOCATION,
    LOCALE_STORE,
    SCOPE_SELECT,
    SCOPE_STORE,
)


def register_foundation_callbacks(app):
    @app.callback(
        Output(SCOPE_STORE, "data"),
        Input(SCOPE_SELECT, "value"),
        prevent_initial_call=True,
    )
    def scope(value):
        return value if value in DATASET_SCOPES else no_update


def register_overview_callbacks(app):
    from .overview_model import build_overview_model
    from .pages.overview import (
        CONTENT_ID,
        DETAIL_DRAWER_BODY_ID,
        DETAIL_DRAWER_ID,
        DETAIL_DRAWER_TITLE_ID,
        EFFECTS_ID,
        LANDSCAPE_ID,
        VALIDATION_ID,
        detail_from_click,
        render,
    )
    from .repository import get_v3_repository

    @app.callback(
        Output(CONTENT_ID, "children"),
        Input(SCOPE_STORE, "data"),
    )
    def overview(scope):
        return render(build_overview_model(get_v3_repository(), scope or "CROSS_DATASET", "vi"))

    @app.callback(
        Output(DETAIL_DRAWER_ID, "opened"),
        Output(DETAIL_DRAWER_TITLE_ID, "children"),
        Output(DETAIL_DRAWER_BODY_ID, "children"),
        Input(LANDSCAPE_ID, "clickData"),
        Input(EFFECTS_ID, "clickData"),
        Input(VALIDATION_ID, "clickData"),
        State(SCOPE_STORE, "data"),
        prevent_initial_call=True,
    )
    def overview_detail(landscape_click, effects_click, validation_click, scope):
        triggered = ctx.triggered_id
        kind = {
            LANDSCAPE_ID: "landscape",
            EFFECTS_ID: "effects",
            VALIDATION_ID: "validation",
        }.get(triggered)
        payload = {
            "landscape": landscape_click,
            "effects": effects_click,
            "validation": validation_click,
        }.get(kind)
        if not kind:
            return no_update, no_update, no_update
        detail = detail_from_click(kind, payload, scope or "CROSS_DATASET")
        if detail is None:
            return no_update, no_update, no_update
        title, body = detail
        return True, title, body


def register_effectiveness_callbacks(app):
    from .effectiveness_model import build_effectiveness_model
    from .figures import (
        effectiveness_contrast_plot,
        effectiveness_evidence_profiles,
        effectiveness_metric_matrix,
        effectiveness_reliability_map,
    )
    from .pages.effectiveness import (
        CONTENT_ID,
        CONTRAST_FAMILY_ID,
        CONTRAST_GRID_ID,
        CONTRAST_PLOT_ID,
        DETAIL_DRAWER_BODY_ID,
        DETAIL_DRAWER_ID,
        DETAIL_DRAWER_TITLE_ID,
        EVIDENCE_FILTER_ID,
        EVIDENCE_PROFILE_ID,
        METRIC_MATRIX_ID,
        MODEL_FILTER_ID,
        OPTION_PANEL_ID,
        PRIMARY_PANEL_ID,
        SECONDARY_PANEL_ID,
        STATISTICS_PANEL_ID,
        TABS_ID,
        RELIABILITY_ID,
        best_option_row,
        contrast_drawer,
        contrast_grid_records,
        filter_contrast_rows,
        filter_metric_rows,
        filter_option_rows,
        option_drawer,
        option_from_reliability_click,
        option_panel,
        render,
        tab_panel_style,
    )
    from .repository import get_v3_repository

    @app.callback(
        Output(CONTENT_ID, "children"),
        Input(SCOPE_STORE, "data"),
        Input(LOCALE_STORE, "data"),
        Input(LOCATION, "pathname"),
        Input(LOCATION, "search"),
    )
    def effectiveness(scope, locale, _pathname, search):
        return render(
            build_effectiveness_model(
                get_v3_repository(),
                scope or "CROSS_DATASET",
                locale or "vi",
                search=search,
            )
        )

    @app.callback(
        Output(PRIMARY_PANEL_ID, "style"),
        Output(SECONDARY_PANEL_ID, "style"),
        Output(STATISTICS_PANEL_ID, "style"),
        Input(TABS_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def effectiveness_tabs(active_tab):
        return (
            tab_panel_style(active_tab, "primary"),
            tab_panel_style(active_tab, "secondary"),
            tab_panel_style(active_tab, "statistics"),
        )

    @app.callback(
        Output(RELIABILITY_ID, "figure"),
        Output(EVIDENCE_PROFILE_ID, "figure"),
        Output(METRIC_MATRIX_ID, "figure"),
        Input(MODEL_FILTER_ID, "value", allow_optional=True),
        Input(EVIDENCE_FILTER_ID, "value", allow_optional=True),
        State(SCOPE_STORE, "data"),
        prevent_initial_call=True,
    )
    def effectiveness_descriptive_views(model_id, evidence, scope):
        resolved = scope or "CROSS_DATASET"
        model = build_effectiveness_model(get_v3_repository(), resolved, "vi")
        options = filter_option_rows(model.option_rows, model_id, evidence)
        metrics = filter_metric_rows(model.secondary_metric_rows, model_id, evidence)
        cross = resolved == "CROSS_DATASET"
        return (
            effectiveness_reliability_map(options, cross_dataset=cross),
            effectiveness_evidence_profiles(options, cross_dataset=cross),
            effectiveness_metric_matrix(metrics, cross_dataset=cross),
        )

    @app.callback(
        Output(OPTION_PANEL_ID, "children"),
        Input(RELIABILITY_ID, "clickData", allow_optional=True),
        Input(MODEL_FILTER_ID, "value", allow_optional=True),
        Input(EVIDENCE_FILTER_ID, "value", allow_optional=True),
        State(SCOPE_STORE, "data"),
        State(LOCATION, "search"),
        prevent_initial_call=True,
    )
    def effectiveness_selected_option(click_data, model_id, evidence, scope, search):
        if ctx.triggered_id == RELIABILITY_ID:
            row = option_from_reliability_click(click_data)
            return option_panel(row) if row else no_update
        resolved = scope or "CROSS_DATASET"
        model = build_effectiveness_model(get_v3_repository(), resolved, "vi", search=search)
        rows = filter_option_rows(model.option_rows, model_id, evidence)
        return option_panel(best_option_row(rows, model.focus_dataset))

    @app.callback(
        Output(CONTRAST_PLOT_ID, "figure"),
        Output(CONTRAST_GRID_ID, "rowData"),
        Input(CONTRAST_FAMILY_ID, "value", allow_optional=True),
        Input(MODEL_FILTER_ID, "value", allow_optional=True),
        Input(EVIDENCE_FILTER_ID, "value", allow_optional=True),
        State(SCOPE_STORE, "data"),
        prevent_initial_call=True,
    )
    def effectiveness_contrasts(family, model_id, evidence, scope):
        resolved = scope or "CROSS_DATASET"
        selected_family = family if family in {"all", "model_within_evidence", "evidence_vs_s0"} else "evidence_vs_s0"
        model = build_effectiveness_model(get_v3_repository(), resolved, "vi")
        rows = filter_contrast_rows(model.contrast_rows, selected_family, model_id, evidence)
        return (
            effectiveness_contrast_plot(rows, cross_dataset=resolved == "CROSS_DATASET", family="all"),
            contrast_grid_records(rows),
        )

    @app.callback(
        Output(DETAIL_DRAWER_ID, "opened"),
        Output(DETAIL_DRAWER_TITLE_ID, "children"),
        Output(DETAIL_DRAWER_BODY_ID, "children"),
        Input(RELIABILITY_ID, "clickData", allow_optional=True),
        Input(CONTRAST_PLOT_ID, "clickData", allow_optional=True),
        prevent_initial_call=True,
    )
    def effectiveness_detail(reliability_click, contrast_click):
        if ctx.triggered_id == RELIABILITY_ID:
            row = option_from_reliability_click(reliability_click)
            if not row:
                return no_update, no_update, no_update
            title, body = option_drawer(row)
            return True, title, body
        if ctx.triggered_id == CONTRAST_PLOT_ID:
            detail = contrast_drawer(contrast_click)
            if detail is None:
                return no_update, no_update, no_update
            title, body = detail
            return True, title, body
        return no_update, no_update, no_update


def register_mechanisms_callbacks(app):
    from .figures import mechanism_claim_matrix, mechanism_quality_map
    from .mechanisms_model import build_mechanisms_model
    from .pages.mechanisms import (
        CLAIM_MATRIX_ID,
        CLAIM_MEASURE_ID,
        CLAIM_TYPE_FILTER_ID,
        CLAIMS_PANEL_ID,
        CONTENT_ID,
        DETAIL_DRAWER_BODY_ID,
        DETAIL_DRAWER_ID,
        DETAIL_DRAWER_TITLE_ID,
        LOSS_PANEL_ID,
        QUALITY_EVIDENCE_FILTER_ID,
        QUALITY_MAP_ID,
        QUALITY_MODEL_FILTER_ID,
        QUALITY_PANEL_ID,
        QUALITY_PANEL_TAB_ID,
        TABS_ID,
        VALIDATION_FILTER_ID,
        best_quality_row,
        claim_drawer,
        filter_quality_rows,
        quality_drawer,
        quality_from_click,
        quality_panel,
        render,
        tab_panel_style,
    )
    from .repository import get_v3_repository

    @app.callback(
        Output(CONTENT_ID, "children"),
        Input(SCOPE_STORE, "data"),
        Input(LOCALE_STORE, "data"),
        Input(LOCATION, "pathname"),
        Input(LOCATION, "search"),
    )
    def mechanisms(scope, locale, _pathname, search):
        return render(
            build_mechanisms_model(
                get_v3_repository(),
                scope or "CROSS_DATASET",
                locale or "vi",
                search=search,
            )
        )

    @app.callback(
        Output(LOSS_PANEL_ID, "style"),
        Output(CLAIMS_PANEL_ID, "style"),
        Output(QUALITY_PANEL_TAB_ID, "style"),
        Input(TABS_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def mechanisms_tabs(active_tab):
        return (
            tab_panel_style(active_tab, "loss"),
            tab_panel_style(active_tab, "claims"),
            tab_panel_style(active_tab, "quality"),
        )

    @app.callback(
        Output(CLAIM_MATRIX_ID, "figure"),
        Input(CLAIM_TYPE_FILTER_ID, "value", allow_optional=True),
        Input(VALIDATION_FILTER_ID, "value", allow_optional=True),
        Input(CLAIM_MEASURE_ID, "value", allow_optional=True),
        State(SCOPE_STORE, "data"),
        prevent_initial_call=True,
    )
    def mechanisms_claim_matrix(claim_type, validation_status, measure, scope):
        resolved = scope or "CROSS_DATASET"
        model = build_mechanisms_model(get_v3_repository(), resolved, "vi")
        return mechanism_claim_matrix(
            model.claim_rows,
            cross_dataset=resolved == "CROSS_DATASET",
            measure="count" if measure == "count" else "share",
            claim_type=claim_type or "ALL",
            validation_status=validation_status or "ALL",
        )

    @app.callback(
        Output(QUALITY_MAP_ID, "figure"),
        Input(QUALITY_MODEL_FILTER_ID, "value", allow_optional=True),
        Input(QUALITY_EVIDENCE_FILTER_ID, "value", allow_optional=True),
        State(SCOPE_STORE, "data"),
        prevent_initial_call=True,
    )
    def mechanisms_quality_map(model_id, evidence, scope):
        resolved = scope or "CROSS_DATASET"
        model = build_mechanisms_model(get_v3_repository(), resolved, "vi")
        rows = filter_quality_rows(model.quality_rows, model_id, evidence)
        return mechanism_quality_map(rows, cross_dataset=resolved == "CROSS_DATASET")

    @app.callback(
        Output(QUALITY_PANEL_ID, "children"),
        Input(QUALITY_MAP_ID, "clickData", allow_optional=True),
        Input(QUALITY_MODEL_FILTER_ID, "value", allow_optional=True),
        Input(QUALITY_EVIDENCE_FILTER_ID, "value", allow_optional=True),
        State(SCOPE_STORE, "data"),
        State(LOCATION, "search"),
        prevent_initial_call=True,
    )
    def mechanisms_selected_option(click_data, model_id, evidence, scope, search):
        if ctx.triggered_id == QUALITY_MAP_ID:
            row = quality_from_click(click_data)
            return quality_panel(row) if row else no_update
        resolved = scope or "CROSS_DATASET"
        model = build_mechanisms_model(get_v3_repository(), resolved, "vi", search=search)
        rows = filter_quality_rows(model.quality_rows, model_id, evidence)
        return quality_panel(best_quality_row(rows, model.focus_dataset))

    @app.callback(
        Output(DETAIL_DRAWER_ID, "opened"),
        Output(DETAIL_DRAWER_TITLE_ID, "children"),
        Output(DETAIL_DRAWER_BODY_ID, "children"),
        Input(CLAIM_MATRIX_ID, "clickData", allow_optional=True),
        Input(QUALITY_MAP_ID, "clickData", allow_optional=True),
        prevent_initial_call=True,
    )
    def mechanisms_detail(claim_click, quality_click):
        if ctx.triggered_id == CLAIM_MATRIX_ID:
            detail = claim_drawer(claim_click)
            if detail is None:
                return no_update, no_update, no_update
            title, body = detail
            return True, title, body
        if ctx.triggered_id == QUALITY_MAP_ID:
            row = quality_from_click(quality_click)
            if not row:
                return no_update, no_update, no_update
            title, body = quality_drawer(row)
            return True, title, body
        return no_update, no_update, no_update

def register_decision_callbacks(app):
    from .decision_model import build_decision_model
    from .figures import decision_quality_efficiency_plot, decision_quality_reliability_plot
    from .pages.decision import (
        CERTIFIED_PANEL_ID,
        CONTENT_ID,
        DETAIL_DRAWER_BODY_ID,
        DETAIL_DRAWER_ID,
        DETAIL_DRAWER_TITLE_ID,
        EVIDENCE_FILTER_ID,
        MODEL_FILTER_ID,
        NI_PLOT_ID,
        OPTION_PANEL_ID,
        QUALITY_EFFICIENCY_ID,
        QUALITY_RELIABILITY_ID,
        SCENARIO_DETAIL_ID,
        SCENARIO_ID,
        SCENARIO_PANEL_ID,
        SELECTED_OPTION_STORE_ID,
        TABS_ID,
        TRADEOFF_OPTION_PANEL_ID,
        TRADEOFF_PANEL_ID,
        _find_option,
        _initial_option,
        filter_option_rows,
        ni_drawer,
        ni_from_click,
        option_drawer,
        option_from_click,
        option_panel,
        render,
        scenario_detail,
        tab_panel_style,
        with_drill_dataset,
    )
    from .repository import get_v3_repository

    @app.callback(
        Output(CONTENT_ID, "children"),
        Input(SCOPE_STORE, "data"),
        Input(LOCALE_STORE, "data"),
        Input(LOCATION, "pathname"),
        Input(LOCATION, "search"),
    )
    def decision(scope, locale, _pathname, search):
        return render(
            build_decision_model(
                get_v3_repository(),
                scope or "CROSS_DATASET",
                locale or "vi",
                search=search,
            )
        )

    @app.callback(
        Output(CERTIFIED_PANEL_ID, "style"),
        Output(TRADEOFF_PANEL_ID, "style"),
        Output(SCENARIO_PANEL_ID, "style"),
        Input(TABS_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def decision_tabs(active_tab):
        return (
            tab_panel_style(active_tab, "certified"),
            tab_panel_style(active_tab, "tradeoffs"),
            tab_panel_style(active_tab, "scenarios"),
        )

    @app.callback(
        Output(QUALITY_RELIABILITY_ID, "figure"),
        Output(QUALITY_EFFICIENCY_ID, "figure"),
        Output(TRADEOFF_OPTION_PANEL_ID, "children"),
        Output(SELECTED_OPTION_STORE_ID, "data"),
        Input(MODEL_FILTER_ID, "value", allow_optional=True),
        Input(EVIDENCE_FILTER_ID, "value", allow_optional=True),
        Input(QUALITY_RELIABILITY_ID, "clickData", allow_optional=True),
        Input(QUALITY_EFFICIENCY_ID, "clickData", allow_optional=True),
        State(SCOPE_STORE, "data"),
        State(LOCATION, "search"),
        prevent_initial_call=True,
    )
    def decision_tradeoffs(model_id, evidence, quality_click, efficiency_click, scope, search):
        resolved = scope or "CROSS_DATASET"
        model = build_decision_model(get_v3_repository(), resolved, "vi", search=search)
        visible = filter_option_rows(model.options, model_id, evidence)
        selected_id = None
        if ctx.triggered_id == QUALITY_RELIABILITY_ID:
            selected_id = option_from_click(quality_click)
        elif ctx.triggered_id == QUALITY_EFFICIENCY_ID:
            selected_id = option_from_click(efficiency_click)
        selected = _find_option(visible, selected_id) if selected_id else None
        if selected is None:
            selected = _initial_option(model, visible)
        selected_id = str(selected["option_id"]) if selected else None
        return (
            decision_quality_reliability_plot(visible, selected_option=selected_id),
            decision_quality_efficiency_plot(visible, selected_option=selected_id),
            option_panel(with_drill_dataset(selected, model.focus_dataset)),
            {"option_id": selected_id, "dataset": model.focus_dataset} if selected_id else None,
        )

    @app.callback(
        Output(SCENARIO_DETAIL_ID, "children"),
        Input(SCENARIO_ID, "value", allow_optional=True),
        State(SCOPE_STORE, "data"),
        State(LOCATION, "search"),
        prevent_initial_call=True,
    )
    def decision_scenario(scenario_id, scope, search):
        model = build_decision_model(get_v3_repository(), scope or "CROSS_DATASET", "vi", search=search)
        row = next((dict(r) for r in model.scenarios if str(r["scenario_id"]) == str(scenario_id)), None)
        return scenario_detail(row)

    @app.callback(
        Output(DETAIL_DRAWER_ID, "opened"),
        Output(DETAIL_DRAWER_TITLE_ID, "children"),
        Output(DETAIL_DRAWER_BODY_ID, "children"),
        Input(NI_PLOT_ID, "clickData", allow_optional=True),
        Input(QUALITY_RELIABILITY_ID, "clickData", allow_optional=True),
        Input(QUALITY_EFFICIENCY_ID, "clickData", allow_optional=True),
        State(SCOPE_STORE, "data"),
        State(LOCATION, "search"),
        prevent_initial_call=True,
    )
    def decision_detail(ni_click, quality_click, efficiency_click, scope, search):
        if ctx.triggered_id == NI_PLOT_ID:
            detail = ni_from_click(ni_click)
            if detail is None:
                return no_update, no_update, no_update
            title, body = ni_drawer(detail)
            return True, title, body
        click = quality_click if ctx.triggered_id == QUALITY_RELIABILITY_ID else efficiency_click
        option_id = option_from_click(click)
        if not option_id:
            return no_update, no_update, no_update
        model = build_decision_model(get_v3_repository(), scope or "CROSS_DATASET", "vi", search=search)
        row = _find_option(model.options, option_id)
        if row is None:
            return no_update, no_update, no_update
        title, body = option_drawer(with_drill_dataset(row, model.focus_dataset))
        return True, title, body


def register_robustness_callbacks(app):
    from .figures import (
        robustness_contrast_stability_map,
        robustness_margin_sensitivity_plot,
        robustness_rank_shift_heatmap,
    )
    from .pages.robustness import (
        CONTENT_ID,
        CONTRAST_FAMILY_ID,
        CONTRAST_MAP_ID,
        DECISION_PANEL_ID,
        DETAIL_DRAWER_BODY_ID,
        DETAIL_DRAWER_ID,
        DETAIL_DRAWER_TITLE_ID,
        MARGIN_DETAIL_ID,
        MARGIN_PLOT_ID,
        MARGIN_SELECT_ID,
        METRIC_EVIDENCE_FILTER_ID,
        METRIC_MODEL_FILTER_ID,
        METRIC_PANEL_ID,
        METRIC_SELECT_ID,
        POPULATION_PANEL_ID,
        RANK_SHIFT_ID,
        TABS_ID,
        contrast_drawer,
        contrast_from_click,
        filter_metric_rows,
        filter_population_contrasts,
        margin_detail,
        margin_drawer,
        margin_from_click,
        metric_drawer,
        metric_from_click,
        render,
        tab_panel_style,
    )
    from .repository import get_v3_repository
    from .robustness_model import build_robustness_model

    @app.callback(
        Output(CONTENT_ID, "children"),
        Input(SCOPE_STORE, "data"),
        Input(LOCALE_STORE, "data"),
        Input(LOCATION, "pathname"),
        Input(LOCATION, "search"),
    )
    def robustness(scope, locale, _pathname, search):
        return render(
            build_robustness_model(
                get_v3_repository(),
                scope or "CROSS_DATASET",
                locale or "vi",
                search=search,
            )
        )

    @app.callback(
        Output(POPULATION_PANEL_ID, "style"),
        Output(METRIC_PANEL_ID, "style"),
        Output(DECISION_PANEL_ID, "style"),
        Input(TABS_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def robustness_tabs(active_tab):
        return (
            tab_panel_style(active_tab, "population"),
            tab_panel_style(active_tab, "metric"),
            tab_panel_style(active_tab, "decision"),
        )

    @app.callback(
        Output(CONTRAST_MAP_ID, "figure"),
        Input(CONTRAST_FAMILY_ID, "value", allow_optional=True),
        State(SCOPE_STORE, "data"),
        State(LOCATION, "search"),
        prevent_initial_call=True,
    )
    def robustness_contrasts(family, scope, search):
        resolved = scope or "CROSS_DATASET"
        model = build_robustness_model(get_v3_repository(), resolved, "vi", search=search)
        rows = filter_population_contrasts(model.population_contrasts, family or "evidence_vs_s0")
        return robustness_contrast_stability_map(rows, cross_dataset=resolved == "CROSS_DATASET")

    @app.callback(
        Output(RANK_SHIFT_ID, "figure"),
        Input(METRIC_MODEL_FILTER_ID, "value", allow_optional=True),
        Input(METRIC_EVIDENCE_FILTER_ID, "value", allow_optional=True),
        Input(METRIC_SELECT_ID, "value", allow_optional=True),
        State(SCOPE_STORE, "data"),
        State(LOCATION, "search"),
        prevent_initial_call=True,
    )
    def robustness_metric(model_id, evidence, metric, scope, search):
        resolved = scope or "CROSS_DATASET"
        model = build_robustness_model(get_v3_repository(), resolved, "vi", search=search)
        rows = filter_metric_rows(model.metric_rows, model_id, evidence, metric)
        return robustness_rank_shift_heatmap(rows, cross_dataset=resolved == "CROSS_DATASET")

    @app.callback(
        Output(MARGIN_PLOT_ID, "figure"),
        Output(MARGIN_DETAIL_ID, "children"),
        Input(MARGIN_SELECT_ID, "value", allow_optional=True),
        State(SCOPE_STORE, "data"),
        State(LOCATION, "search"),
        prevent_initial_call=True,
    )
    def robustness_margin(margin_value, scope, search):
        try:
            selected = float(margin_value)
        except (TypeError, ValueError):
            selected = 0.03
        if selected not in {0.02, 0.03, 0.05}:
            selected = 0.03
        model = build_robustness_model(get_v3_repository(), scope or "CROSS_DATASET", "vi", search=search)
        row = next((dict(r) for r in model.margin_rows if abs(float(r["margin"]) - selected) < 1e-9), None)
        return robustness_margin_sensitivity_plot(model.margin_rows, selected_margin=selected), margin_detail(row)

    @app.callback(
        Output(DETAIL_DRAWER_ID, "opened"),
        Output(DETAIL_DRAWER_TITLE_ID, "children"),
        Output(DETAIL_DRAWER_BODY_ID, "children"),
        Input(CONTRAST_MAP_ID, "clickData", allow_optional=True),
        Input(RANK_SHIFT_ID, "clickData", allow_optional=True),
        Input(MARGIN_PLOT_ID, "clickData", allow_optional=True),
        State(SCOPE_STORE, "data"),
        State(LOCATION, "search"),
        prevent_initial_call=True,
    )
    def robustness_detail(contrast_click, metric_click, margin_click, scope, search):
        if ctx.triggered_id == CONTRAST_MAP_ID:
            detail = contrast_from_click(contrast_click)
            if detail is None:
                return no_update, no_update, no_update
            title, body = contrast_drawer(detail)
            return True, title, body
        if ctx.triggered_id == RANK_SHIFT_ID:
            detail = metric_from_click(metric_click)
            if detail is None:
                return no_update, no_update, no_update
            title, body = metric_drawer(detail)
            return True, title, body
        if ctx.triggered_id == MARGIN_PLOT_ID:
            selected = margin_from_click(margin_click)
            if selected is None:
                return no_update, no_update, no_update
            model = build_robustness_model(get_v3_repository(), scope or "CROSS_DATASET", "vi", search=search)
            row = next((dict(r) for r in model.margin_rows if abs(float(r["margin"]) - selected) < 1e-9), None)
            if row is None:
                return no_update, no_update, no_update
            title, body = margin_drawer(row)
            return True, title, body
        return no_update, no_update, no_update


def register_cases_callbacks(app):
    from .cases_model import (
        build_cases_model,
        canonical_cases_state,
        case_option_records,
        claim_by_id,
        control_cases_intent,
        generation_from_landscape_click,
        initial_cases_intent,
        landscape_cases_intent,
        stratum_options,
        url_cases_intent,
    )
    from .figures import (
        cases_claim_type_status_matrix,
        cases_performance_landscape,
        cases_section_profile,
        cases_validation_composition,
    )
    from .pages.cases import (
        CAPABILITY_ID,
        CASE_ID,
        CLAIM_GRID_ID,
        CLAIM_TYPE_ID,
        CLAIMS_PANEL_ID,
        CONTEXT_HOST_ID,
        DATASET_ID,
        DETAIL_DRAWER_BODY_ID,
        DETAIL_DRAWER_ID,
        DETAIL_DRAWER_TITLE_ID,
        DIAGNOSTICS_PANEL_ID,
        EVIDENCE_ID,
        GENERATION_SUMMARY_HOST_ID,
        HEADER_DATASET_VALUE_ID,
        HYDRATED_STORE_ID,
        LANDSCAPE_ID,
        LANDSCAPE_PANEL_ID,
        LANDSCAPE_SELECTION_STORE_ID,
        MODEL_ID,
        SECTION_ID,
        SELECTED_GENERATION_STORE_ID,
        STRATUM_ID,
        TABS_ID,
        VALIDATION_ID,
        capability_boundary,
        case_context,
        claim_drawer,
        claim_grid_records,
        generation_summary,
        tab_panel_style,
    )
    from .repository import get_v3_repository
    from .effectiveness_model import MODEL_LABELS

    _CONTROL_FIELD_BY_ID = {
        DATASET_ID: "dataset",
        STRATUM_ID: "stratum",
        CASE_ID: "case_id",
        MODEL_ID: "model_id",
        EVIDENCE_ID: "evidence_level",
        TABS_ID: "tab",
    }

    @app.callback(
        Output(DATASET_ID, "value"),
        Output(STRATUM_ID, "data"),
        Output(STRATUM_ID, "value"),
        Output(CASE_ID, "data"),
        Output(CASE_ID, "value"),
        Output(MODEL_ID, "data"),
        Output(MODEL_ID, "value"),
        Output(EVIDENCE_ID, "data"),
        Output(EVIDENCE_ID, "value"),
        Output(TABS_ID, "value"),
        Output(SELECTED_GENERATION_STORE_ID, "data"),
        Output(HYDRATED_STORE_ID, "data"),
        Input(SCOPE_STORE, "data"),
        Input(LOCATION, "pathname"),
        Input(LOCATION, "search"),
        Input(DATASET_ID, "value", allow_optional=True),
        Input(STRATUM_ID, "value", allow_optional=True),
        Input(CASE_ID, "value", allow_optional=True),
        Input(MODEL_ID, "value", allow_optional=True),
        Input(EVIDENCE_ID, "value", allow_optional=True),
        Input(TABS_ID, "value", allow_optional=True),
        Input(LANDSCAPE_SELECTION_STORE_ID, "data", allow_optional=True),
        State(HYDRATED_STORE_ID, "data", allow_optional=True),
        State(SELECTED_GENERATION_STORE_ID, "data", allow_optional=True),
    )
    def cases_resolve_state(
        global_scope,
        pathname,
        search,
        local_scope,
        stratum,
        case_id,
        model_id,
        evidence,
        tab,
        landscape_selection,
        hydrated,
        canonical,
    ):
        """Resolve every Case interaction into one canonical certified selection.

        Dash supports circular synchronization inside one callback.  Keeping the
        six Case controls in this single owner avoids the unsupported and racy
        multi-callback dependency cycle that previously let URL/global/control
        events overwrite one another.  Resolver-emitted control echoes are
        ignored by comparing the triggered value against the canonical store;
        transient DMC ``None`` values are never treated as user intent.
        """
        if pathname != "/cases":
            return (no_update,) * 12

        triggered_ids = {
            str(item.get("prop_id", "")).split(".", 1)[0]
            for item in (ctx.triggered or [])
            if str(item.get("prop_id", "")) not in {"", "."}
        }

        if not bool(hydrated) or not isinstance(canonical, dict):
            intent = initial_cases_intent(global_scope, search)
        elif LOCATION in triggered_ids:
            intent = url_cases_intent(search, canonical)
            if intent is None:
                return (no_update,) * 12
        elif LANDSCAPE_SELECTION_STORE_ID in triggered_ids:
            intent = landscape_cases_intent(landscape_selection, canonical)
            if intent is None:
                return (no_update,) * 12
        elif SCOPE_STORE in triggered_ids:
            # Case Explorer has a local single-study dataset selector.  The
            # global comparison scope is only an initial default and must not
            # overwrite an already hydrated canonical Case selection.
            return (no_update,) * 12
        else:
            control_triggers = [item for item in triggered_ids if item in _CONTROL_FIELD_BY_ID]
            if len(control_triggers) != 1:
                # Resolver output can update several controls at once.  Those
                # echoes are not a new user intent and must not be re-resolved.
                return (no_update,) * 12
            trigger_id = control_triggers[0]
            value_by_id = {
                DATASET_ID: local_scope,
                STRATUM_ID: stratum,
                CASE_ID: case_id,
                MODEL_ID: model_id,
                EVIDENCE_ID: evidence,
                TABS_ID: tab,
            }
            intent = control_cases_intent(
                _CONTROL_FIELD_BY_ID[trigger_id],
                value_by_id[trigger_id],
                canonical,
            )
            if intent is None:
                return (no_update,) * 12

        requested_scope = str(intent.get("dataset") or "HOME_CREDIT")
        model = build_cases_model(
            get_v3_repository(),
            requested_scope,
            "vi",
            case_id=intent.get("case_id"),
            model_id=intent.get("model_id"),
            evidence_level=intent.get("evidence_level"),
            stratum=intent.get("stratum"),
            tab=intent.get("tab"),
        )
        return (
            model.scope,
            stratum_options(model),
            model.selected_stratum,
            case_option_records(model),
            model.selected_case_id,
            [{"value": value, "label": MODEL_LABELS.get(value, value)} for value in model.model_ids],
            model.selected_model_id,
            [{"value": value, "label": value} for value in model.evidence_levels],
            model.selected_evidence_level,
            model.initial_tab,
            canonical_cases_state(model),
            True,
        )

    @app.callback(
        Output(LANDSCAPE_SELECTION_STORE_ID, "data"),
        Input(LANDSCAPE_ID, "clickData", allow_optional=True),
        State(DATASET_ID, "value", allow_optional=True),
        State(CASE_ID, "value", allow_optional=True),
        State(SELECTED_GENERATION_STORE_ID, "data", allow_optional=True),
        State(LANDSCAPE_SELECTION_STORE_ID, "data", allow_optional=True),
        prevent_initial_call=True,
    )
    def cases_landscape_selection(click_data, dataset, case_id, identity, previous_selection):
        clicked = generation_from_landscape_click(click_data)
        if not clicked or clicked.get("usable") != "USABLE":
            return no_update
        if dataset in ("HOME_CREDIT", "FREDDIE") and clicked["dataset"] != dataset:
            return no_update
        if case_id and clicked["case_id"] != str(case_id):
            return no_update
        if identity and str(identity.get("generation_id") or "") == clicked["generation_id"]:
            return no_update
        prior_seq = 0
        if isinstance(previous_selection, dict):
            try:
                prior_seq = int(previous_selection.get("event_seq", 0))
            except (TypeError, ValueError):
                prior_seq = 0
        return {**clicked, "event_seq": prior_seq + 1}

    @app.callback(
        Output(LANDSCAPE_PANEL_ID, "style"),
        Output(DIAGNOSTICS_PANEL_ID, "style"),
        Output(CLAIMS_PANEL_ID, "style"),
        Input(TABS_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def cases_tabs(active_tab):
        return (
            tab_panel_style(active_tab, "landscape"),
            tab_panel_style(active_tab, "diagnostics"),
            tab_panel_style(active_tab, "claims"),
        )

    @app.callback(
        Output(LANDSCAPE_ID, "figure"),
        Output(CONTEXT_HOST_ID, "children"),
        Output(GENERATION_SUMMARY_HOST_ID, "children"),
        Output(VALIDATION_ID, "figure"),
        Output(CLAIM_TYPE_ID, "figure"),
        Output(SECTION_ID, "figure"),
        Output(CLAIM_GRID_ID, "rowData"),
        Output(CAPABILITY_ID, "children"),
        Output(HEADER_DATASET_VALUE_ID, "children"),
        Input(SELECTED_GENERATION_STORE_ID, "data", allow_optional=True),
        prevent_initial_call=True,
    )
    def cases_selected_generation(identity):
        if not identity:
            return (no_update,) * 9
        model = build_cases_model(
            get_v3_repository(),
            str(identity.get("dataset") or "HOME_CREDIT"),
            "vi",
            case_id=str(identity.get("case_id") or ""),
            model_id=str(identity.get("model_id") or ""),
            evidence_level=str(identity.get("evidence_level") or ""),
        )
        return (
            cases_performance_landscape(model.generation_rows, selected_generation_id=model.selected_generation_id),
            case_context(model),
            generation_summary(model),
            cases_validation_composition(model.status_counts),
            cases_claim_type_status_matrix(model.claim_type_status),
            cases_section_profile(model.section_profile),
            claim_grid_records(model),
            capability_boundary(model).children,
            "Home Credit" if model.scope == "HOME_CREDIT" else "Freddie Mac",
        )

    @app.callback(
        Output(DETAIL_DRAWER_ID, "opened"),
        Output(DETAIL_DRAWER_TITLE_ID, "children"),
        Output(DETAIL_DRAWER_BODY_ID, "children"),
        Input(CLAIM_GRID_ID, "cellClicked", allow_optional=True),
        Input(SELECTED_GENERATION_STORE_ID, "data", allow_optional=True),
        prevent_initial_call=True,
    )
    def cases_claim_detail(cell_click, identity):
        if ctx.triggered_id == SELECTED_GENERATION_STORE_ID:
            return False, no_update, no_update
        if ctx.triggered_id != CLAIM_GRID_ID or not cell_click or not identity:
            return no_update, no_update, no_update
        row_data = cell_click.get("data") if isinstance(cell_click.get("data"), dict) else {}
        claim_id = cell_click.get("rowId") or row_data.get("claim_id")
        if not claim_id:
            return no_update, no_update, no_update
        model = build_cases_model(
            get_v3_repository(),
            str(identity.get("dataset") or "HOME_CREDIT"),
            "vi",
            case_id=str(identity.get("case_id") or ""),
            model_id=str(identity.get("model_id") or ""),
            evidence_level=str(identity.get("evidence_level") or ""),
        )
        row = claim_by_id(model, str(claim_id))
        if row is None:
            return no_update, no_update, no_update
        title, body = claim_drawer(row)
        return True, title, body

def register_methods_callbacks(app):
    from .methods_model import build_methods_model, finding_by_id, metric_by_key, report_by_id, schema_for_table
    from .pages.methods import (
        FINDING_DETAIL_ID,
        FINDING_DETAIL_HOST_ID,
        FINDING_SELECT_ID,
        FINDINGS_PANEL_ID,
        METRIC_DETAIL_ID,
        METRIC_DETAIL_HOST_ID,
        METRIC_SELECT_ID,
        METRICS_PANEL_ID,
        REPORT_DETAIL_ID,
        REPORT_DETAIL_HOST_ID,
        REPORT_SELECT_ID,
        SCHEMA_GRID_ID,
        STUDY_PANEL_ID,
        TABLE_SELECT_ID,
        TABS_ID,
        TRACE_PANEL_ID,
        finding_detail,
        metric_detail,
        report_detail,
        tab_panel_style,
    )
    from .repository import get_v3_repository

    @app.callback(
        Output(TABS_ID, "value"),
        Output(METRIC_SELECT_ID, "value"),
        Output(REPORT_SELECT_ID, "value"),
        Output(TABLE_SELECT_ID, "value"),
        Output(FINDING_SELECT_ID, "value"),
        Input(LOCATION, "pathname"),
        Input(LOCATION, "search"),
    )
    def methods_url_state(pathname, search):
        if pathname != "/methods":
            return (no_update,) * 5
        model = build_methods_model(get_v3_repository(), "vi", search=search)
        return model.initial_tab, model.selected_metric_key, model.selected_report_id, model.selected_table_name, model.selected_finding_id

    @app.callback(
        Output(STUDY_PANEL_ID, "style"),
        Output(METRICS_PANEL_ID, "style"),
        Output(TRACE_PANEL_ID, "style"),
        Output(FINDINGS_PANEL_ID, "style"),
        Input(TABS_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def methods_tabs(active_tab):
        return (
            tab_panel_style(active_tab, "study"),
            tab_panel_style(active_tab, "metrics"),
            tab_panel_style(active_tab, "traceability"),
            tab_panel_style(active_tab, "findings"),
        )

    @app.callback(
        Output(METRIC_DETAIL_HOST_ID, "children"),
        Input(METRIC_SELECT_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def methods_metric(metric_key):
        model = build_methods_model(get_v3_repository(), "vi")
        component = metric_detail(model, metric_key)
        return component

    @app.callback(
        Output(REPORT_DETAIL_HOST_ID, "children"),
        Input(REPORT_SELECT_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def methods_report(report_id):
        model = build_methods_model(get_v3_repository(), "vi")
        component = report_detail(model, report_id)
        return component

    @app.callback(
        Output(SCHEMA_GRID_ID, "rowData"),
        Input(TABLE_SELECT_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def methods_schema(table_name):
        model = build_methods_model(get_v3_repository(), "vi")
        return schema_for_table(model, table_name)

    @app.callback(
        Output(FINDING_DETAIL_HOST_ID, "children"),
        Input(FINDING_SELECT_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def methods_finding(finding_id):
        model = build_methods_model(get_v3_repository(), "vi")
        component = finding_detail(model, finding_id)
        return component

def register_export_callbacks(app):
    from .exports import build_page_export, resolve_export_scope
    from .pages.cases import HYDRATED_STORE_ID, SELECTED_GENERATION_STORE_ID
    from .repository import get_v3_repository

    @app.callback(
        Output(EXPORT_DOWNLOAD, "data"),
        Input(EXPORT_BUTTON, "n_clicks"),
        State(LOCATION, "pathname"),
        State(SCOPE_STORE, "data"),
        State(LOCALE_STORE, "data"),
        State(SELECTED_GENERATION_STORE_ID, "data", allow_optional=True),
        State(HYDRATED_STORE_ID, "data", allow_optional=True),
        prevent_initial_call=True,
    )
    def export_current(n_clicks, path, scope, locale, case_identity, cases_hydrated):
        if not n_clicks:
            return no_update
        route = path or "/"
        if route == "/cases":
            local_dataset = str(case_identity.get("dataset") or "") if isinstance(case_identity, dict) else ""
            if not bool(cases_hydrated) or local_dataset not in {"HOME_CREDIT", "FREDDIE"}:
                return no_update
        export_scope = resolve_export_scope(route, scope, case_identity)
        filename, payload = build_page_export(
            get_v3_repository(),
            route,
            export_scope,
            locale or "vi",
        )
        return dcc.send_bytes(lambda handle: handle.write(payload), filename)
