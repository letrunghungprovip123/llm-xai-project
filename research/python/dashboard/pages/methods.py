"""Page 7 — certified Reproducibility & Methods audit console."""

from __future__ import annotations

import dash
from dash import dcc, html

from ..components.chart_card import chart_card
from ..components.methods import (
    analysis_design_lanes,
    artifact_inventory_panel,
    certified_headline_grid,
    denominator_ledger_panel,
    experimental_design_snapshot,
    interpretation_checklist,
    limitation_register,
    methods_context_header,
    methods_global_boundary,
    metric_alias_rules,
    metric_dictionary_grid,
    metric_visibility_cards,
    release_identity_card,
    release_lineage,
    reproduction_status_table,
    reproduction_workflow,
    research_question_cards,
    statistical_family_panel,
    validation_gate_matrix,
)
from ..components.page_header import page_header
from ..data.repository import get_dashboard_repository
from ..i18n import (
    DEFAULT_LOCALE,
    localize_component_tree,
    methods_identifier_label,
    normalize_locale,
    t,
)
from ..figures.methods import (
    FIG_METHODS_VISIBILITY_PROFILE,
    build_metric_visibility_profile,
)
from ..ids import (
    METHODS_DICTIONARY_CONTAINER_ID,
    METHODS_DICTIONARY_DATASET_ID,
    METHODS_DICTIONARY_INTERNAL_ID,
    METHODS_DICTIONARY_ROLE_ID,
    METHODS_DICTIONARY_SEARCH_ID,
    METHODS_DICTIONARY_TIER_ID,
    METHODS_DOWNLOAD_ID,
    METHODS_EXPORT_ID,
    METHODS_HEADLINE_CONTAINER_ID,
    METHODS_HEADLINE_SECTION_ID,
    METHODS_LIMITATION_CATEGORY_ID,
    METHODS_LIMITATION_CONTAINER_ID,
    METHODS_PAGE_ID,
    METHODS_RQ_CONTAINER_ID,
    METHODS_RQ_FILTER_ID,
    METHODS_TABS_ID,
    METHODS_VISIBILITY_PROFILE_ID,
)
from ..settings import (
    METHODS_DEFAULT_TAB,
    METHODS_DICTIONARY_DATASET_ALL,
    METHODS_DICTIONARY_ROLE_ALL,
    METHODS_DICTIONARY_TIER_ALL,
    METHODS_REPORT_SECTION_ALL,
    METHODS_RQ_ALL,
    METHODS_TAB_LABELS,
    METHODS_TAB_LIMITATIONS,
    METHODS_TAB_METRICS,
    METHODS_TAB_RELEASE,
    METHODS_TAB_RESEARCH,
    METHODS_VISIBILITY_TIER_LABELS,
    VISUALIZATION_RELEASE_ID,
)


PAGE_MODULE = "llm_xai_dashboard.methods"
DICTIONARY_DASHBOARD_ENABLED = "DASHBOARD_ENABLED"
LIMITATION_ALL = "ALL"
_METHODS_PREFIXES = ("methods.", "common.", "domain.")


def register_page() -> None:
    if PAGE_MODULE not in dash.page_registry:
        dash.register_page(
            PAGE_MODULE,
            path="/methods",
            name="Methods",
            title="Reproducibility & Methods · LLM-XAI",
            description=(
                "Certified release lineage, research design, denominator rules, "
                "metric governance, limitations and reproduction workflow."
            ),
            order=6,
            layout=layout,
        )


def _release_tab(data, locale=DEFAULT_LOCALE):
    return html.Div(
        [
            release_identity_card(data.release_audit),
            release_lineage(data.validation_gates),
            validation_gate_matrix(data.validation_gates),
            artifact_inventory_panel(data.artifact_inventory, locale=locale),
        ],
        className="methods-tab-panel",
    )


def _research_tab(data, locale=DEFAULT_LOCALE, selected_rq=METHODS_RQ_ALL):
    return html.Div(
        [
            experimental_design_snapshot(),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2("Six-question research map"),
                            html.P(
                                "Each card preserves its frozen population, inference unit, metrics and interpretation restrictions."
                            ),
                        ],
                        className="methods-section-heading",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Research question"),
                                    dcc.Dropdown(
                                        id=METHODS_RQ_FILTER_ID,
                                        value=selected_rq if selected_rq in ({item.rq_id for item in data.research_questions} | {METHODS_RQ_ALL}) else METHODS_RQ_ALL,
                                        clearable=False,
                                        options=[
                                            {"value": METHODS_RQ_ALL, "label": "All research questions"},
                                            *[
                                                {
                                                    "value": item.rq_id,
                                                    "label": f"{item.rq_id} · {item.title}",
                                                }
                                                for item in data.research_questions
                                            ],
                                        ],
                                    ),
                                ],
                                className="methods-control-group methods-control-group--grow",
                            )
                        ],
                        className="methods-local-controls",
                    ),
                    html.Div(
                        research_question_cards(
                            data.research_questions,
                            selected=selected_rq,
                            locale=locale,
                        ),
                        id=METHODS_RQ_CONTAINER_ID,
                    ),
                ],
                className="methods-card",
            ),
            analysis_design_lanes(),
            statistical_family_panel(data.statistical_families, locale=locale),
        ],
        className="methods-tab-panel",
    )


def _metrics_tab(
    data,
    locale=DEFAULT_LOCALE,
    *,
    section=METHODS_REPORT_SECTION_ALL,
    search="",
    dataset=METHODS_DICTIONARY_DATASET_ALL,
    tier=DICTIONARY_DASHBOARD_ENABLED,
    role=METHODS_DICTIONARY_ROLE_ALL,
    include_internal=None,
):
    dictionary = data.visualization_dictionary.copy()
    include = isinstance(include_internal, list) and "INCLUDE" in include_internal
    initial_dictionary = dictionary.copy()
    if not include:
        initial_dictionary = initial_dictionary.loc[
            initial_dictionary["visibility_tier"].isin(["A_HEADLINE", "B_EXPLANATORY"])
            & ~initial_dictionary["is_identifier"].astype(bool)
        ]
    if dataset != METHODS_DICTIONARY_DATASET_ALL:
        initial_dictionary = initial_dictionary.loc[initial_dictionary["dataset_name"].astype(str) == str(dataset)]
    if tier not in {DICTIONARY_DASHBOARD_ENABLED, METHODS_DICTIONARY_TIER_ALL}:
        initial_dictionary = initial_dictionary.loc[initial_dictionary["visibility_tier"].astype(str) == str(tier)]
    if role == "IDENTIFIER":
        initial_dictionary = initial_dictionary.loc[initial_dictionary["is_identifier"].astype(bool)]
    elif role == "RATE":
        initial_dictionary = initial_dictionary.loc[initial_dictionary["is_rate"].astype(bool) & ~initial_dictionary["is_identifier"].astype(bool)]
    elif role == "METRIC":
        initial_dictionary = initial_dictionary.loc[~initial_dictionary["is_identifier"].astype(bool)]
    query = str(search or "").strip().lower()
    if query:
        haystack = (
            initial_dictionary["dataset_name"].astype(str) + " "
            + initial_dictionary["field_name"].astype(str) + " "
            + initial_dictionary["visibility_tier"].astype(str)
        ).str.lower()
        initial_dictionary = initial_dictionary.loc[haystack.str.contains(query, regex=False)]
    initial_dictionary = initial_dictionary.sort_values(["dataset_name", "field_name"], kind="stable").reset_index(drop=True)
    sections = sorted(data.certified_numbers["report_section"].astype(str).unique())
    headline_frame = data.certified_numbers.copy()
    if section != METHODS_REPORT_SECTION_ALL:
        headline_frame = headline_frame.loc[headline_frame["report_section"].astype(str) == str(section)].copy()
    datasets = sorted(dictionary["dataset_name"].astype(str).unique())
    visibility_figure = build_metric_visibility_profile(data.metric_visibility, locale=locale)

    return html.Div(
        [
            denominator_ledger_panel(data.denominator_ledger, locale=locale),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2("Certified headline registry"),
                            html.P(
                                "Values and denominator semantics are read from the frozen report-number registry."
                            ),
                        ],
                        className="methods-section-heading",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Report section"),
                                    dcc.Dropdown(
                                        id=METHODS_HEADLINE_SECTION_ID,
                                        value=section if section in ({METHODS_REPORT_SECTION_ALL} | set(sections)) else METHODS_REPORT_SECTION_ALL,
                                        clearable=False,
                                        options=[
                                            {"value": METHODS_REPORT_SECTION_ALL, "label": "All sections"},
                                            *[
                                                {
                                                    "value": item,
                                                    "label": methods_identifier_label(locale, item),
                                                }
                                                for item in sections
                                            ],
                                        ],
                                    ),
                                ],
                                className="methods-control-group",
                            )
                        ],
                        className="methods-local-controls",
                    ),
                    html.Div(certified_headline_grid(headline_frame, locale=locale), id=METHODS_HEADLINE_CONTAINER_ID),
                ],
                className="methods-card",
            ),
            html.Div(
                [
                    chart_card(
                        graph_id=METHODS_VISIBILITY_PROFILE_ID,
                        title="Frozen metric visibility profile",
                        subtitle="Governance categories define where metrics may appear; they are not quality scores",
                        figure=visibility_figure,
                        figure_id=FIG_METHODS_VISIBILITY_PROFILE,
                        source="metric_visibility_registry.csv",
                        metric="Registered metrics by visibility tier",
                        denominator=f"{len(data.metric_visibility)} registered metrics",
                        release=VISUALIZATION_RELEASE_ID,
                        locale=locale,
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.H2("Metric-governance tiers"),
                                    html.P(
                                        "Disabled metrics require additional data and must not be interpreted as zero."
                                    ),
                                ],
                                className="methods-section-heading",
                            ),
                            metric_visibility_cards(data.metric_visibility, locale=locale),
                        ],
                        className="methods-card",
                    ),
                ],
                className="methods-metrics-governance-grid",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H2("Metric dictionary explorer"),
                            html.P(
                                "Default view shows report-facing fields. Internal and identifier fields remain hidden until explicitly requested."
                            ),
                        ],
                        className="methods-section-heading",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Search field"),
                                    dcc.Input(
                                        id=METHODS_DICTIONARY_SEARCH_ID,
                                        value=str(search or ""),
                                        type="search",
                                        debounce=True,
                                        placeholder="Search field or technical name",
                                        className="methods-text-input",
                                    ),
                                ],
                                className="methods-control-group methods-control-group--grow",
                            ),
                            html.Div(
                                [
                                    html.Label("Dataset"),
                                    dcc.Dropdown(
                                        id=METHODS_DICTIONARY_DATASET_ID,
                                        value=dataset if dataset in ({METHODS_DICTIONARY_DATASET_ALL} | set(datasets)) else METHODS_DICTIONARY_DATASET_ALL,
                                        clearable=False,
                                        options=[
                                            {"value": METHODS_DICTIONARY_DATASET_ALL, "label": "All datasets"},
                                            *[{"value": item, "label": item} for item in datasets],
                                        ],
                                    ),
                                ],
                                className="methods-control-group",
                            ),
                            html.Div(
                                [
                                    html.Label("Visibility tier"),
                                    dcc.Dropdown(
                                        id=METHODS_DICTIONARY_TIER_ID,
                                        value=tier if tier in ({DICTIONARY_DASHBOARD_ENABLED, METHODS_DICTIONARY_TIER_ALL} | set(METHODS_VISIBILITY_TIER_LABELS)) else DICTIONARY_DASHBOARD_ENABLED,
                                        clearable=False,
                                        options=[
                                            {"value": DICTIONARY_DASHBOARD_ENABLED, "label": "Headline + explanatory"},
                                            {"value": METHODS_DICTIONARY_TIER_ALL, "label": "All tiers"},
                                            *[
                                                {
                                                    "value": key,
                                                    "label": label,
                                                }
                                                for key, label in METHODS_VISIBILITY_TIER_LABELS.items()
                                            ],
                                        ],
                                    ),
                                ],
                                className="methods-control-group",
                            ),
                            html.Div(
                                [
                                    html.Label("Field role"),
                                    dcc.Dropdown(
                                        id=METHODS_DICTIONARY_ROLE_ID,
                                        value=role if role in {METHODS_DICTIONARY_ROLE_ALL, "METRIC", "RATE", "IDENTIFIER"} else METHODS_DICTIONARY_ROLE_ALL,
                                        clearable=False,
                                        options=[
                                            {"value": METHODS_DICTIONARY_ROLE_ALL, "label": "All field roles"},
                                            {"value": "METRIC", "label": "Metric / supporting field"},
                                            {"value": "RATE", "label": "Rate"},
                                            {"value": "IDENTIFIER", "label": "Identifier"},
                                        ],
                                    ),
                                ],
                                className="methods-control-group",
                            ),
                            html.Div(
                                dcc.Checklist(
                                    id=METHODS_DICTIONARY_INTERNAL_ID,
                                    options=[
                                        {
                                            "label": "Include internal and identifier fields",
                                            "value": "INCLUDE",
                                        }
                                    ],
                                    value=["INCLUDE"] if include else [],
                                    className="methods-check-control",
                                ),
                                className="methods-control-group methods-control-group--check",
                            ),
                        ],
                        className="methods-local-controls methods-dictionary-controls",
                    ),
                    html.Div(
                        metric_dictionary_grid(initial_dictionary, locale=locale),
                        id=METHODS_DICTIONARY_CONTAINER_ID,
                    ),
                    metric_alias_rules(),
                ],
                className="methods-card",
            ),
        ],
        className="methods-tab-panel",
    )


def _limitations_tab(data, locale=DEFAULT_LOCALE, category=LIMITATION_ALL):
    categories = sorted(data.limitations["category"].astype(str).unique())
    selected_category = category if category in ({LIMITATION_ALL} | set(categories)) else LIMITATION_ALL
    limitations = data.limitations.copy()
    if selected_category != LIMITATION_ALL:
        limitations = limitations.loc[limitations["category"].astype(str) == str(selected_category)].copy()
    return html.Div(
        [
            html.Section(
                [
                    html.Div(
                        [
                            html.H2("Limitation register"),
                            html.P(
                                "Each limitation states what cannot be concluded and what remains reportable."
                            ),
                        ],
                        className="methods-section-heading",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Limitation category"),
                                    dcc.Dropdown(
                                        id=METHODS_LIMITATION_CATEGORY_ID,
                                        value=selected_category,
                                        clearable=False,
                                        options=[
                                            {"value": LIMITATION_ALL, "label": "All categories"},
                                            *[{"value": item, "label": item} for item in categories],
                                        ],
                                    ),
                                ],
                                className="methods-control-group methods-control-group--grow",
                            )
                        ],
                        className="methods-local-controls",
                    ),
                    html.Div(
                        limitation_register(limitations),
                        id=METHODS_LIMITATION_CONTAINER_ID,
                    ),
                ],
                className="methods-card",
            ),
            interpretation_checklist(),
            html.Div(
                [
                    reproduction_workflow(data.reproduction_steps),
                    reproduction_status_table(),
                ],
                className="methods-reproduction-grid",
            ),
        ],
        className="methods-tab-panel",
    )


def layout(
    tab: str | None = None,
    locale: object = DEFAULT_LOCALE,
    rq_filter: object = METHODS_RQ_ALL,
    headline_section: object = METHODS_REPORT_SECTION_ALL,
    dictionary_search: object = "",
    dictionary_dataset: object = METHODS_DICTIONARY_DATASET_ALL,
    dictionary_tier: object = DICTIONARY_DASHBOARD_ENABLED,
    dictionary_role: object = METHODS_DICTIONARY_ROLE_ALL,
    dictionary_internal: object = None,
    limitation_category: object = LIMITATION_ALL,
    **_: object,
):
    resolved_locale = normalize_locale(locale)
    repository = get_dashboard_repository()
    data = repository.methods_data()
    selected_tab = tab if tab in METHODS_TAB_LABELS else METHODS_DEFAULT_TAB
    passed_gates = sum(item.passed for item in data.validation_gates)

    page = html.Main(
        [
            html.Section(
                [
                    page_header(
                        title="Reproducibility & Methods",
                        subtitle=(
                            "Audit the certified release, research design, denominator rules, "
                            "metric visibility, validation gates and interpretation boundaries "
                            "behind every dashboard result."
                        ),
                        endpoint="RQ1–RQ6",
                        inference_unit="Canonical case",
                        endpoint_label="Research scope",
                        inference_label="Primary inference unit",
                        locale=resolved_locale,
                    ),
                    html.Div(
                        [
                            methods_context_header(
                                data.release_audit,
                                passed_gates=passed_gates,
                                gate_count=len(data.validation_gates),
                                locale=resolved_locale,
                            ),
                            html.Button(
                                "Export methods package",
                                id=METHODS_EXPORT_ID,
                                type="button",
                                className="methods-export-button",
                            ),
                        ],
                        className="methods-header-actions",
                    ),
                ],
                className="methods-page-intro",
                **{"aria-label": "Reproducibility and methods page introduction"},
            ),
            dcc.Download(id=METHODS_DOWNLOAD_ID),
            dcc.Tabs(
                id=METHODS_TABS_ID,
                value=selected_tab,
                className="dashboard-tabs methods-tabs",
                parent_className="methods-tabs-parent",
                children=[
                    dcc.Tab(
                        label=t(resolved_locale, "methods.tabs.release"),
                        value=METHODS_TAB_RELEASE,
                        className="tab",
                        selected_className="tab--selected",
                        children=_release_tab(data, resolved_locale),
                    ),
                    dcc.Tab(
                        label=t(resolved_locale, "methods.tabs.research"),
                        value=METHODS_TAB_RESEARCH,
                        className="tab",
                        selected_className="tab--selected",
                        children=_research_tab(data, resolved_locale, selected_rq=str(rq_filter or METHODS_RQ_ALL)),
                    ),
                    dcc.Tab(
                        label=t(resolved_locale, "methods.tabs.metrics"),
                        value=METHODS_TAB_METRICS,
                        className="tab",
                        selected_className="tab--selected",
                        children=_metrics_tab(
                            data,
                            resolved_locale,
                            section=str(headline_section or METHODS_REPORT_SECTION_ALL),
                            search=dictionary_search,
                            dataset=str(dictionary_dataset or METHODS_DICTIONARY_DATASET_ALL),
                            tier=str(dictionary_tier or DICTIONARY_DASHBOARD_ENABLED),
                            role=str(dictionary_role or METHODS_DICTIONARY_ROLE_ALL),
                            include_internal=dictionary_internal,
                        ),
                    ),
                    dcc.Tab(
                        label=t(resolved_locale, "methods.tabs.limitations"),
                        value=METHODS_TAB_LIMITATIONS,
                        className="tab",
                        selected_className="tab--selected",
                        children=_limitations_tab(data, resolved_locale, category=str(limitation_category or LIMITATION_ALL)),
                    ),
                ],
            ),
            methods_global_boundary(),
        ],
        id=METHODS_PAGE_ID,
        className="research-page methods-page",
        **{
            "data-rq": "RQ1-RQ6",
            "data-analysis-mode": "certified-audit-console",
        },
    )
    return localize_component_tree(page, resolved_locale, prefixes=_METHODS_PREFIXES)
