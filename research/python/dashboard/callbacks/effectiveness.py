"""Locale-aware callbacks and pure update helpers for Page 2."""

from __future__ import annotations

from io import BytesIO
import json
from urllib.parse import parse_qs
from zipfile import ZIP_DEFLATED, ZipFile

from dash import Input, Output, State, dcc, html, no_update

from ..components.effectiveness import conditional_context_panel, operational_interpretation_panel
from ..data.repository import get_dashboard_repository
from ..export.localization import export_readme
from ..figures.effectiveness import (
    build_conditional_quality_heatmap,
    build_effect_size_chart,
    build_operational_conditional_gap,
    build_operational_loss_decomposition,
    build_reliability_map,
)
from ..i18n import (
    DEFAULT_LOCALE,
    localize_plotly_figure,
    metric_label,
    normalize_locale,
    t,
)
from ..ids import (
    APP_LOCALE_STORE_ID,
    APP_LOCATION_ID,
    EFFECTIVENESS_CLEAR_FOCUS_ID,
    EFFECTIVENESS_CONDITIONAL_CONTRAST_GRID_ID,
    EFFECTIVENESS_CONDITIONAL_HEATMAP_ID,
    EFFECTIVENESS_CONDITIONAL_METRIC_ID,
    EFFECTIVENESS_CONDITIONAL_PANEL_ID,
    EFFECTIVENESS_CONTENT_ID,
    EFFECTIVENESS_CONTRAST_FAMILY_ID,
    EFFECTIVENESS_CONTRAST_GRID_ID,
    EFFECTIVENESS_DOWNLOAD_ID,
    EFFECTIVENESS_EXPORT_ID,
    EFFECTIVENESS_FOCUS_CHIP_ID,
    EFFECTIVENESS_FOCUS_PANEL_ID,
    EFFECTIVENESS_GAP_ID,
    EFFECTIVENESS_RELIABILITY_MAP_ID,
    EFFECTIVENESS_TABS_ID,
    EFFECTIVENESS_UI_STATE_ID,
)
from ..pages.effectiveness import (
    build_effectiveness_children,
    contrast_display_frame,
    normalize_effectiveness_state,
)
from ..settings import DEFAULT_CONDITIONAL_METRIC


_FIGURE_PREFIXES = ("effectiveness.figure.",)


def parse_focus(search: str | None) -> tuple[str | None, str | None]:
    """Parse a validated model/evidence focus from the query string."""

    if not search:
        return None, None
    values = parse_qs(search.lstrip("?"))
    return values.get("model", [None])[0], values.get("evidence", [None])[0]


def conditional_updates(metric_id: str, locale: object = DEFAULT_LOCALE):
    """Return certified conditional outputs localized for one explicit locale."""

    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    valid = {"conservative_faithfulness", "verifiability", "resolved_faithfulness"}
    resolved_metric = metric_id if metric_id in valid else DEFAULT_CONDITIONAL_METRIC
    label = metric_label(resolved_locale, resolved_metric)
    summary = repository.conditional_option_summary(resolved_metric)
    heatmap = localize_plotly_figure(
        build_conditional_quality_heatmap(summary, metric_id=resolved_metric, metric_label=label),
        resolved_locale,
        prefixes=_FIGURE_PREFIXES,
    )
    gap = localize_plotly_figure(
        build_operational_conditional_gap(summary, metric_id=resolved_metric, metric_label=label),
        resolved_locale,
        prefixes=_FIGURE_PREFIXES,
    )
    panel = conditional_context_panel(summary, metric_label=label, locale=resolved_locale)
    tests = repository.conditional_paired_tests()
    rows = contrast_display_frame(tests.loc[tests["metric_id"] == resolved_metric], resolved_locale)
    return heatmap, gap, panel, rows.astype(object).where(rows.notna(), None).to_dict("records")


def primary_contrast_rows(family: str | None, locale: object = DEFAULT_LOCALE) -> list[dict]:
    """Filter certified contrasts and localize only their presentation columns."""

    frame = get_dashboard_repository().paired_tests()
    if family and family != "all":
        frame = frame.loc[frame["contrast_family"] == family]
    display = contrast_display_frame(frame, locale)
    return display.astype(object).where(display.notna(), None).to_dict("records")


def build_effectiveness_archive(locale: object = DEFAULT_LOCALE) -> bytes:
    """Export locale-aware figure presentation with stable analytical payloads."""

    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    data = repository.effectiveness_data()
    summary = repository.conditional_option_summary(DEFAULT_CONDITIONAL_METRIC)
    label = metric_label(resolved_locale, DEFAULT_CONDITIONAL_METRIC)
    raw_figures = {
        "FIG_EFFECTIVENESS_RELIABILITY_MAP": build_reliability_map(data.option_performance),
        "FIG_EFFECTIVENESS_LOSS_DECOMPOSITION": build_operational_loss_decomposition(data.option_performance),
        "FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP": build_conditional_quality_heatmap(summary, metric_id=DEFAULT_CONDITIONAL_METRIC, metric_label=label),
        "FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP": build_operational_conditional_gap(summary, metric_id=DEFAULT_CONDITIONAL_METRIC, metric_label=label),
        "FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES": build_effect_size_chart(data.omnibus_tests),
    }
    figures = {
        figure_id: localize_plotly_figure(figure, resolved_locale, prefixes=_FIGURE_PREFIXES)
        for figure_id, figure in raw_figures.items()
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        manifest = []
        for figure_id, figure in figures.items():
            path = f"figures/json/{figure_id}.json"
            archive.writestr(path, figure.to_json(pretty=True))
            manifest.append({"figure_id": figure_id, "path": path, "metadata": dict(figure.layout.meta)})
        archive.writestr(
            "README.txt",
            export_readme(
                resolved_locale,
                "effectiveness",
                analytical_release=data.release.analytical_release_id,
                visualization_release=data.release.visualization_release_id,
            ),
        )
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema_version": "effectiveness_export_manifest_v1",
                    "analytical_release": data.release.analytical_release_id,
                    "visualization_release": data.release.visualization_release_id,
                    "display_locale": resolved_locale,
                    "figures": manifest,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    return buffer.getvalue()


def merge_effectiveness_state(
    current: object | None,
    *,
    tab: object | None = None,
    metric: object | None = None,
    family: object | None = None,
) -> dict[str, str]:
    """Merge optional mounted controls into the locale-neutral state store."""

    candidate = dict(current) if isinstance(current, dict) else {}
    if tab is not None:
        candidate["tab"] = tab
    if metric is not None:
        candidate["conditional_metric"] = metric
    if family is not None:
        candidate["contrast_family"] = family
    return normalize_effectiveness_state(candidate)


def register_effectiveness_callbacks(app) -> None:
    @app.callback(
        Output(EFFECTIVENESS_CONTENT_ID, "children"),
        Input(APP_LOCALE_STORE_ID, "data"),
        State(EFFECTIVENESS_UI_STATE_ID, "data"),
        State(APP_LOCATION_ID, "search"),
    )
    def render_effectiveness_locale(locale, ui_state, search):
        model, evidence = parse_focus(search)
        return build_effectiveness_children(locale, model=model, evidence=evidence, ui_state=ui_state)

    @app.callback(
        Output(EFFECTIVENESS_UI_STATE_ID, "data"),
        Input(EFFECTIVENESS_TABS_ID, "value", allow_optional=True),
        Input(EFFECTIVENESS_CONDITIONAL_METRIC_ID, "value", allow_optional=True),
        Input(EFFECTIVENESS_CONTRAST_FAMILY_ID, "value", allow_optional=True),
        State(EFFECTIVENESS_UI_STATE_ID, "data"),
        prevent_initial_call=True,
    )
    def remember_effectiveness_state(tab, metric, family, current):
        merged = merge_effectiveness_state(current, tab=tab, metric=metric, family=family)
        return no_update if merged == normalize_effectiveness_state(current) else merged

    @app.callback(
        Output(EFFECTIVENESS_RELIABILITY_MAP_ID, "figure"),
        Output(EFFECTIVENESS_FOCUS_PANEL_ID, "children"),
        Output(EFFECTIVENESS_FOCUS_CHIP_ID, "children"),
        Input(APP_LOCATION_ID, "search"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_focus(search, locale):
        resolved_locale = normalize_locale(locale)
        repository = get_dashboard_repository()
        model, evidence = parse_focus(search)
        focused = repository.focused_option(model, evidence)
        figure = localize_plotly_figure(
            build_reliability_map(repository.option_performance(), focused_option_id=focused.option_id if focused else None),
            resolved_locale,
            prefixes=_FIGURE_PREFIXES,
        )
        panel = operational_interpretation_panel(repository.option_performance(), focused, locale=resolved_locale)
        chip = (
            [
                html.Span(t(resolved_locale, "effectiveness.focused_configuration", model=focused.model_label, evidence=focused.evidence_level), className="focus-chip"),
                html.Button(t(resolved_locale, "effectiveness.clear_focus"), id=EFFECTIVENESS_CLEAR_FOCUS_ID, className="focus-clear", type="button"),
            ]
            if focused
            else []
        )
        return figure, panel, chip

    @app.callback(
        Output(APP_LOCATION_ID, "search"),
        Input(EFFECTIVENESS_CLEAR_FOCUS_ID, "n_clicks", allow_optional=True),
        prevent_initial_call=True,
    )
    def clear_focus(n_clicks):
        return "" if n_clicks else no_update

    @app.callback(
        Output(EFFECTIVENESS_CONDITIONAL_HEATMAP_ID, "figure"),
        Output(EFFECTIVENESS_GAP_ID, "figure"),
        Output(EFFECTIVENESS_CONDITIONAL_PANEL_ID, "children"),
        Output(EFFECTIVENESS_CONDITIONAL_CONTRAST_GRID_ID, "rowData"),
        Input(EFFECTIVENESS_CONDITIONAL_METRIC_ID, "value", allow_optional=True),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_conditional_metric(metric_id, locale):
        return conditional_updates(metric_id or DEFAULT_CONDITIONAL_METRIC, locale)

    @app.callback(
        Output(EFFECTIVENESS_CONTRAST_GRID_ID, "rowData"),
        Input(EFFECTIVENESS_CONTRAST_FAMILY_ID, "value", allow_optional=True),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_primary_contrasts(family, locale):
        return primary_contrast_rows(family or "all", locale)

    @app.callback(
        Output(EFFECTIVENESS_DOWNLOAD_ID, "data"),
        Input(EFFECTIVENESS_EXPORT_ID, "n_clicks", allow_optional=True),
        State(APP_LOCALE_STORE_ID, "data"),
        prevent_initial_call=True,
    )
    def download_effectiveness_figures(n_clicks, locale):
        if not n_clicks:
            return no_update
        payload = build_effectiveness_archive(locale)
        return dcc.send_bytes(lambda buffer: buffer.write(payload), "LLM_XAI_Effectiveness_Reliability_certified_figures.zip")
