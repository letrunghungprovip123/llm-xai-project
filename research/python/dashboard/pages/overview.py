"""Page 1 — certified Executive Overview with explicit EN/VI rendering."""

from __future__ import annotations

from dataclasses import replace

import dash
from dash import dcc, html

from ..components import chart_card, metric_card, page_header
from ..data.contracts import OverviewFinding, OverviewKpi
from ..data.repository import DashboardRepository, get_dashboard_repository
from ..figures.overview import (
    FIG_OVERVIEW_E2E_HEATMAP,
    FIG_OVERVIEW_EVIDENCE_PROFILE,
    build_e2e_option_heatmap,
    build_evidence_profile,
)
from ..i18n import (
    DEFAULT_LOCALE,
    evidence_label,
    format_integer,
    format_percent,
    format_percentage_points,
    localize_plotly_figure,
    normalize_locale,
    t,
)
from ..ids import (
    OVERVIEW_CONTENT_ID,
    OVERVIEW_FINDINGS_ID,
    OVERVIEW_HEATMAP_ID,
    OVERVIEW_PAGE_ID,
    OVERVIEW_PROFILE_ID,
)
from ..settings import VISUALIZATION_RELEASE_ID


PAGE_MODULE = "llm_xai_dashboard.overview"
_FIGURE_PREFIXES = ("overview.figure.",)


def register_page() -> None:
    if PAGE_MODULE not in dash.page_registry:
        dash.register_page(
            PAGE_MODULE,
            path="/",
            name="Overview",
            title="Executive Overview · LLM-XAI Research Dashboard",
            description=(
                "Certified overview of operational faithfulness across all "
                "planned LLM generations."
            ),
            order=0,
            layout=layout,
        )


def _localized_option_frame(frame, locale: object):
    localized = frame.copy(deep=True)
    localized["evidence_label"] = localized["evidence_level"].map(
        lambda value: evidence_label(normalize_locale(locale), value)
    )
    return localized


def _localized_kpi(
    kpi: OverviewKpi,
    locale: object,
    *,
    unusable_count: int,
) -> OverviewKpi:
    resolved = normalize_locale(locale)
    key_by_metric = {
        "planned_llm_generations": "planned",
        "usable_llm_generations": "usable",
        "usability_rate": "usability",
        "mean_end_to_end_operational_faithfulness": "mean_e2e",
        "final_atomic_claims": "claims",
        "template_reference_generations": "template",
    }
    try:
        key = key_by_metric[kpi.metric_id]
    except KeyError as error:
        raise ValueError(f"Unsupported Overview KPI identity: {kpi.metric_id!r}") from error

    parameters: dict[str, object] = {}
    if key == "usable":
        parameters["unusable"] = format_integer(
            resolved,
            unusable_count,
        )

    display_value = (
        format_percent(resolved, kpi.value, decimals=2)
        if key in {"usability", "mean_e2e"}
        else format_integer(resolved, kpi.value)
    )
    return replace(
        kpi,
        label=t(resolved, f"overview.kpi.{key}.label"),
        display_value=display_value,
        subtext=t(resolved, f"overview.kpi.{key}.subtext", **parameters),
        denominator=t(resolved, f"overview.kpi.{key}.denominator"),
        tooltip=t(resolved, f"overview.kpi.{key}.tooltip"),
    )


def _join_effects(locale: str, effects: list[str]) -> str:
    if len(effects) == 1:
        return effects[0]
    if locale == "vi":
        return ", ".join(effects[:-1]) + " và " + effects[-1]
    return ", ".join(effects[:-1]) + " and " + effects[-1]


def _localized_findings(
    repository: DashboardRepository,
    locale: object,
) -> tuple[OverviewFinding, ...]:
    resolved = normalize_locale(locale)
    data = repository.overview_data()
    by_id = {item.finding_id: item for item in data.findings}

    significant = set(
        data.omnibus_tests.loc[
            data.omnibus_tests["significant"].astype(bool), "effect"
        ].astype(str)
    )
    effect_keys = {
        "model": "overview.finding.effect_model",
        "evidence": "overview.finding.effect_evidence",
        "model:evidence": "overview.finding.effect_interaction",
    }
    effects = [
        t(resolved, effect_keys[effect])
        for effect in ("model", "evidence", "model:evidence")
        if effect in significant
    ]
    if not effects:
        raise ValueError("Overview requires at least one certified significant effect")

    top = data.option_performance.sort_values(
        ["mean_end_to_end_yield", "p10_end_to_end_yield"], ascending=False
    ).iloc[0]
    counts = data.unusable_generations["evidence_level"].value_counts()
    concentrated = str(counts.index[0]) if not counts.empty else ""
    failure_key = (
        "overview.finding.failure_single"
        if len(counts) == 1
        else "overview.finding.failure_multiple"
    )

    sensitivity = repository.validator_metric_summary()
    overall = sensitivity.loc[
        (sensitivity["group_type"] == "overall")
        & (sensitivity["metric_id"] == "end_to_end_faithfulness_yield")
    ]
    if len(overall) != 1:
        raise ValueError("Expected one overall validator-sensitivity summary")
    delta = float(overall.iloc[0]["mean_delta_v4_minus_candidate"])

    return (
        replace(
            by_id["primary-effects"],
            title=t(resolved, "overview.finding.primary_title"),
            statement=t(
                resolved,
                "overview.finding.effects_statement",
                effects=_join_effects(resolved, effects),
            ),
        ),
        replace(
            by_id["highest-observed-option"],
            title=t(resolved, "overview.finding.top_title"),
            statement=t(
                resolved,
                "overview.finding.top_statement",
                model=str(top["model_label"]),
                evidence=str(top["evidence_level"]),
                value=format_percent(
                    resolved, float(top["mean_end_to_end_yield"]), decimals=2
                ),
            ),
        ),
        replace(
            by_id["structured-failures"],
            title=t(resolved, "overview.finding.failure_title"),
            statement=t(
                resolved,
                failure_key,
                count=format_integer(resolved, len(data.unusable_generations)),
                evidence=concentrated,
            ),
        ),
        replace(
            by_id["measurement-sensitivity"],
            title=t(resolved, "overview.finding.sensitivity_title"),
            statement=t(
                resolved,
                "overview.finding.sensitivity_statement",
                delta=format_percentage_points(resolved, delta, decimals=2),
            ),
        ),
    )


def _finding_item(finding: OverviewFinding, locale: object):
    resolved = normalize_locale(locale)
    link = (
        dcc.Link(
            t(resolved, "overview.supporting_link"),
            href=finding.target_path,
            className="finding-item__link",
        )
        if finding.target_path
        else None
    )
    return html.Article(
        [
            html.H3(finding.title, className="finding-item__title"),
            html.P(finding.statement, className="finding-item__statement"),
            link,
        ],
        className=f"finding-item finding-item--{finding.tone}",
        **{"data-finding-id": finding.finding_id, "data-source": finding.source},
    )


def build_overview_children(
    locale: object = DEFAULT_LOCALE,
    *,
    repository: DashboardRepository | None = None,
):
    """Build all Page-1 presentation content for one explicit locale."""

    resolved = normalize_locale(locale)
    repo = repository or get_dashboard_repository()
    data = repo.overview_data()
    options = _localized_option_frame(data.option_performance, resolved)
    heatmap = localize_plotly_figure(
        build_e2e_option_heatmap(options), resolved, prefixes=_FIGURE_PREFIXES
    )
    profile = localize_plotly_figure(
        build_evidence_profile(options), resolved, prefixes=_FIGURE_PREFIXES
    )
    unusable_count = len(data.unusable_generations)
    kpis = tuple(
        _localized_kpi(item, resolved, unusable_count=unusable_count)
        for item in data.kpis
    )
    findings = _localized_findings(repo, resolved)

    return [
        page_header(
            title=t(resolved, "overview.title"),
            subtitle=t(resolved, "overview.subtitle"),
            endpoint=t(resolved, "overview.endpoint"),
            inference_unit=t(resolved, "overview.inference_unit"),
            locale=resolved,
        ),
        html.Section(
            [metric_card(kpi, locale=resolved) for kpi in kpis],
            className="kpi-grid",
            **{"aria-label": t(resolved, "overview.headline_aria")},
        ),
        html.Section(
            [
                chart_card(
                    graph_id=OVERVIEW_HEATMAP_ID,
                    title=t(resolved, "overview.heatmap_title"),
                    subtitle=t(resolved, "overview.heatmap_subtitle"),
                    figure=heatmap,
                    figure_id=FIG_OVERVIEW_E2E_HEATMAP,
                    source="option_performance.csv",
                    metric=t(resolved, "overview.metric_mean_e2e"),
                    denominator=t(resolved, "overview.denominator_option"),
                    release=VISUALIZATION_RELEASE_ID,
                    class_name="overview-heatmap-card",
                    locale=resolved,
                ),
                chart_card(
                    graph_id=OVERVIEW_PROFILE_ID,
                    title=t(resolved, "overview.profile_title"),
                    subtitle=t(resolved, "overview.profile_subtitle"),
                    figure=profile,
                    figure_id=FIG_OVERVIEW_EVIDENCE_PROFILE,
                    source="option_performance.csv",
                    metric=t(resolved, "overview.metric_mean_e2e"),
                    denominator=t(resolved, "overview.denominator_option"),
                    release=VISUALIZATION_RELEASE_ID,
                    class_name="overview-profile-card",
                    locale=resolved,
                ),
            ],
            className="overview-hero-grid",
            **{"aria-label": t(resolved, "overview.primary_findings_aria")},
        ),
        html.Section(
            [
                html.Header(
                    [
                        html.H2(
                            t(resolved, "overview.findings_title"),
                            className="findings-panel__title",
                        ),
                        html.Span(
                            t(resolved, "overview.findings_note"),
                            className="findings-panel__note",
                        ),
                    ],
                    className="findings-panel__header",
                ),
                html.Div(
                    [_finding_item(item, resolved) for item in findings],
                    id=OVERVIEW_FINDINGS_ID,
                    className="findings-grid",
                ),
            ],
            className="findings-panel",
        ),
        html.P(
            t(resolved, "overview.disclaimer"),
            className="research-disclaimer",
        ),
    ]


def layout(**_: object):
    """Return the Vietnamese-first Page-1 shell."""

    data = get_dashboard_repository().overview_data()
    return html.Main(
        html.Div(
            build_overview_children(DEFAULT_LOCALE),
            id=OVERVIEW_CONTENT_ID,
        ),
        id=OVERVIEW_PAGE_ID,
        className="dashboard-page overview-page",
        **{
            "data-analytical-release": data.release.analytical_release_id,
            "data-visualization-release": data.release.visualization_release_id,
        },
    )


__all__ = ["build_overview_children", "layout", "register_page"]
