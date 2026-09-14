"""Locale-aware callbacks and deterministic export helpers for Page 3."""

from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from dash import Input, Output, State, ctx, dcc, no_update

from ..components.mechanisms import utilization_interpretation_panel
from ..data.repository import get_dashboard_repository
from ..export.localization import export_readme
from ..figures.mechanisms import (
    FIG_MECHANISMS_CLAIM_DIFFICULTY,
    FIG_MECHANISMS_CLAIM_STATUS,
    FIG_MECHANISMS_COVERAGE_DIVERSITY,
    FIG_MECHANISMS_EVIDENCE_COMPOSITION,
    FIG_MECHANISMS_FAILURE_MATRIX,
    FIG_MECHANISMS_PIPELINE_COMPLETION,
    FIG_MECHANISMS_UTILIZATION_MATRIX,
    FIG_MECHANISMS_UTILIZATION_PROFILE,
    FIG_MECHANISMS_UTILIZATION_QUALITY,
    build_claim_difficulty_matrix,
    build_claim_status_small_multiples,
    build_coverage_diversity_scatter,
    build_evidence_composition_chart,
    build_failure_matrix,
    build_pipeline_completion_chart,
    build_utilization_matrix,
    build_utilization_quality_scatter,
    build_utilization_stage_profile,
)
from ..i18n import (
    DEFAULT_LOCALE,
    evidence_label,
    localize_plotly_figure,
    normalize_locale,
    t,
    utilization_metric_label,
)
from ..ids import (
    APP_LOCALE_STORE_ID,
    MECHANISMS_CLAIM_DIFFICULTY_ID,
    MECHANISMS_CLAIM_MEASURE_ID,
    MECHANISMS_CONTENT_ID,
    MECHANISMS_DOWNLOAD_ID,
    MECHANISMS_EXPORT_ID,
    MECHANISMS_FOCUS_STORE_ID,
    MECHANISMS_TABS_ID,
    MECHANISMS_UI_STATE_ID,
    MECHANISMS_UTILIZATION_GRID_ID,
    MECHANISMS_UTILIZATION_MATRIX_ID,
    MECHANISMS_UTILIZATION_METRIC_ID,
    MECHANISMS_UTILIZATION_PANEL_ID,
    MECHANISMS_UTILIZATION_PROFILE_ID,
    MECHANISMS_UTILIZATION_SCATTER_ID,
)
from ..pages.mechanisms import (
    build_mechanisms_children,
    localized_utilization_rows,
    normalize_mechanisms_focus,
    normalize_mechanisms_state,
)
from ..settings import DEFAULT_UTILIZATION_METRIC


_FIGURE_PREFIXES = (
    "mechanisms.figure.",
    "domain.claim_type.",
    "domain.pipeline_stage.",
    "domain.claim_status.",
)
_VALID_UTILIZATION_METRICS = {
    "feature_use",
    "concept_use",
    "supported_claim_yield",
}


def _localized_evidence_frame(frame, locale: object):
    result = frame.copy(deep=True)
    if "evidence_level" in result:
        result["evidence_label"] = result["evidence_level"].map(
            lambda value: evidence_label(locale, value)
        )
    return result


def _focus_from_click(click_data, current, summary):
    if click_data and isinstance(click_data.get("points"), list) and click_data["points"]:
        customdata = click_data["points"][0].get("customdata")
        if isinstance(customdata, (list, tuple)) and len(customdata) >= 3:
            candidate = {
                "model_id": str(customdata[0]),
                "evidence_level": str(customdata[2]),
            }
            valid = (
                (summary["generator_id"] == candidate["model_id"])
                & (summary["evidence_level"] == candidate["evidence_level"])
            ).any()
            if valid:
                return candidate
    if isinstance(current, dict):
        model = current.get("model_id")
        evidence = current.get("evidence_level")
        if (
            (summary["generator_id"] == model)
            & (summary["evidence_level"] == evidence)
        ).any():
            return {"model_id": str(model), "evidence_level": str(evidence)}
    repository = get_dashboard_repository()
    return normalize_mechanisms_focus(repository, str(summary.iloc[0]["metric_id"]), current)


def utilization_updates(
    metric_id,
    click_data=None,
    current_focus=None,
    locale: object = DEFAULT_LOCALE,
):
    """Return localized utilization outputs while preserving stable focus IDs."""

    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    resolved_metric = (
        metric_id
        if metric_id in _VALID_UTILIZATION_METRICS
        else DEFAULT_UTILIZATION_METRIC
    )
    label = utilization_metric_label(resolved_locale, resolved_metric)
    summary = repository.utilization_option_summary(resolved_metric).copy()
    summary["evidence_label"] = summary["evidence_level"].map(
        lambda value: evidence_label(resolved_locale, value)
    )
    focus = _focus_from_click(click_data, current_focus, summary)
    model_id = focus["model_id"]
    evidence_level = focus["evidence_level"]
    selected = summary.loc[
        (summary["generator_id"] == model_id)
        & (summary["evidence_level"] == evidence_level)
    ].iloc[0]
    profile = repository.utilization_stage_profile(model_id, evidence_level)
    utilization = _localized_evidence_frame(
        repository.evidence_utilization_summary(), resolved_locale
    )
    matrix = localize_plotly_figure(
        build_utilization_matrix(
            summary,
            metric_label=label,
            metric_id=resolved_metric,
            focused_model_id=model_id,
            focused_evidence_level=evidence_level,
        ),
        resolved_locale,
        prefixes=_FIGURE_PREFIXES,
    )
    profile_figure = localize_plotly_figure(
        build_utilization_stage_profile(
            profile,
            model_id=model_id,
            model_label=str(selected["generator_label"]),
            evidence_level=evidence_level,
            defined_label=t(resolved_locale, "mechanisms.figure.defined"),
            not_applicable_label=t(
                resolved_locale, "mechanisms.figure.not_applicable"
            ),
        ),
        resolved_locale,
        prefixes=_FIGURE_PREFIXES,
    )
    scatter = localize_plotly_figure(
        build_utilization_quality_scatter(
            utilization,
            metric_id=resolved_metric,
            metric_label=label,
        ),
        resolved_locale,
        prefixes=_FIGURE_PREFIXES,
    )
    panel = utilization_interpretation_panel(
        summary,
        metric_id=resolved_metric,
        metric_label=label,
        locale=resolved_locale,
    )
    rows = localized_utilization_rows(utilization, resolved_locale).astype(object)
    rows = rows.where(rows.notna(), None).to_dict("records")
    return matrix, focus, profile_figure, scatter, panel, rows


def mechanisms_figures(locale: object = DEFAULT_LOCALE):
    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    data = repository.mechanisms_data()
    evidence_design = _localized_evidence_frame(data.evidence_design, resolved_locale)
    utilization = _localized_evidence_frame(data.evidence_utilization, resolved_locale)
    summary = repository.utilization_option_summary(DEFAULT_UTILIZATION_METRIC).copy()
    summary["evidence_label"] = summary["evidence_level"].map(
        lambda value: evidence_label(resolved_locale, value)
    )
    focus = normalize_mechanisms_focus(
        repository, DEFAULT_UTILIZATION_METRIC, None
    )
    model_id = focus["model_id"]
    evidence_level = focus["evidence_level"]
    selected = summary.loc[
        (summary["generator_id"] == model_id)
        & (summary["evidence_level"] == evidence_level)
    ].iloc[0]
    profile = repository.utilization_stage_profile(model_id, evidence_level)
    label = utilization_metric_label(resolved_locale, DEFAULT_UTILIZATION_METRIC)
    raw = {
        FIG_MECHANISMS_EVIDENCE_COMPOSITION: build_evidence_composition_chart(
            evidence_design
        ),
        FIG_MECHANISMS_COVERAGE_DIVERSITY: build_coverage_diversity_scatter(
            evidence_design
        ),
        FIG_MECHANISMS_UTILIZATION_MATRIX: build_utilization_matrix(
            summary,
            metric_label=label,
            metric_id=DEFAULT_UTILIZATION_METRIC,
            focused_model_id=model_id,
            focused_evidence_level=evidence_level,
        ),
        FIG_MECHANISMS_UTILIZATION_PROFILE: build_utilization_stage_profile(
            profile,
            model_id=model_id,
            model_label=str(selected["generator_label"]),
            evidence_level=evidence_level,
            defined_label=t(resolved_locale, "mechanisms.figure.defined"),
            not_applicable_label=t(
                resolved_locale, "mechanisms.figure.not_applicable"
            ),
        ),
        FIG_MECHANISMS_UTILIZATION_QUALITY: build_utilization_quality_scatter(
            utilization,
            metric_id=DEFAULT_UTILIZATION_METRIC,
            metric_label=label,
        ),
        FIG_MECHANISMS_CLAIM_STATUS: build_claim_status_small_multiples(
            data.claim_status_by_option
        ),
        FIG_MECHANISMS_CLAIM_DIFFICULTY: build_claim_difficulty_matrix(
            data.claim_difficulty_by_type
        ),
        FIG_MECHANISMS_PIPELINE_COMPLETION: build_pipeline_completion_chart(
            data.pipeline_stage_summary
        ),
        FIG_MECHANISMS_FAILURE_MATRIX: build_failure_matrix(data.failure_matrix),
    }
    return {
        figure_id: localize_plotly_figure(
            figure, resolved_locale, prefixes=_FIGURE_PREFIXES
        )
        for figure_id, figure in raw.items()
    }


def build_mechanisms_archive(locale: object = DEFAULT_LOCALE) -> bytes:
    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        manifest = []
        for figure_id, figure in mechanisms_figures(resolved_locale).items():
            path = f"figures/json/{figure_id}.json"
            archive.writestr(path, figure.to_json(pretty=True))
            manifest.append(
                {
                    "figure_id": figure_id,
                    "path": path,
                    "metadata": dict(figure.layout.meta),
                }
            )
        archive.writestr(
            "README.txt",
            export_readme(
                resolved_locale,
                "mechanisms",
                analytical_release=repository.release.analytical_release_id,
                visualization_release=repository.release.visualization_release_id,
            ),
        )
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema_version": "mechanisms_export_manifest_v1",
                    "analytical_release": repository.release.analytical_release_id,
                    "visualization_release": repository.release.visualization_release_id,
                    "display_locale": resolved_locale,
                    "figures": manifest,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    return buffer.getvalue()


def merge_mechanisms_state(
    current: object | None,
    *,
    tab: object | None = None,
    metric: object | None = None,
    measure: object | None = None,
) -> dict[str, str]:
    candidate = dict(current) if isinstance(current, dict) else {}
    if tab is not None:
        candidate["tab"] = tab
    if metric is not None:
        candidate["utilization_metric"] = metric
    if measure is not None:
        candidate["claim_measure"] = measure
    return normalize_mechanisms_state(candidate)


def register_mechanisms_callbacks(app) -> None:
    @app.callback(
        Output(MECHANISMS_CONTENT_ID, "children"),
        Input(APP_LOCALE_STORE_ID, "data"),
        State(MECHANISMS_UI_STATE_ID, "data"),
        State(MECHANISMS_FOCUS_STORE_ID, "data"),
    )
    def render_mechanisms_locale(locale, ui_state, focus):
        return build_mechanisms_children(
            locale, ui_state=ui_state, focus=focus
        )

    @app.callback(
        Output(MECHANISMS_UI_STATE_ID, "data"),
        Input(MECHANISMS_TABS_ID, "value", allow_optional=True),
        Input(MECHANISMS_UTILIZATION_METRIC_ID, "value", allow_optional=True),
        Input(MECHANISMS_CLAIM_MEASURE_ID, "value", allow_optional=True),
        State(MECHANISMS_UI_STATE_ID, "data"),
        prevent_initial_call=True,
    )
    def remember_mechanisms_state(tab, metric, measure, current):
        merged = merge_mechanisms_state(
            current, tab=tab, metric=metric, measure=measure
        )
        return no_update if merged == normalize_mechanisms_state(current) else merged

    @app.callback(
        Output(MECHANISMS_UTILIZATION_MATRIX_ID, "figure"),
        Output(MECHANISMS_FOCUS_STORE_ID, "data"),
        Output(MECHANISMS_UTILIZATION_PROFILE_ID, "figure"),
        Output(MECHANISMS_UTILIZATION_SCATTER_ID, "figure"),
        Output(MECHANISMS_UTILIZATION_PANEL_ID, "children"),
        Output(MECHANISMS_UTILIZATION_GRID_ID, "rowData"),
        Input(MECHANISMS_UTILIZATION_METRIC_ID, "value", allow_optional=True),
        Input(MECHANISMS_UTILIZATION_MATRIX_ID, "clickData", allow_optional=True),
        Input(APP_LOCALE_STORE_ID, "data"),
        State(MECHANISMS_FOCUS_STORE_ID, "data"),
    )
    def update_utilization(metric_id, click_data, locale, current_focus):
        # Locale changes rebuild labels but must not replay an old chart click.
        effective_click = (
            click_data
            if ctx.triggered_id == MECHANISMS_UTILIZATION_MATRIX_ID
            else None
        )
        return utilization_updates(
            metric_id or DEFAULT_UTILIZATION_METRIC,
            effective_click,
            current_focus,
            locale,
        )

    @app.callback(
        Output(MECHANISMS_CLAIM_DIFFICULTY_ID, "figure"),
        Input(MECHANISMS_CLAIM_MEASURE_ID, "value", allow_optional=True),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_claim_measure(measure, locale):
        value = measure if measure in {"rate", "count"} else "rate"
        return localize_plotly_figure(
            build_claim_difficulty_matrix(
                get_dashboard_repository().claim_difficulty_by_type(),
                measure=value,
            ),
            locale,
            prefixes=_FIGURE_PREFIXES,
        )

    @app.callback(
        Output(MECHANISMS_DOWNLOAD_ID, "data"),
        Input(MECHANISMS_EXPORT_ID, "n_clicks", allow_optional=True),
        State(APP_LOCALE_STORE_ID, "data"),
        prevent_initial_call=True,
    )
    def download_mechanisms(n_clicks, locale):
        if not n_clicks:
            return no_update
        payload = build_mechanisms_archive(locale)
        return dcc.send_bytes(
            lambda target: target.write(payload),
            "LLM_XAI_Evidence_Mechanisms_certified_figures.zip",
        )
