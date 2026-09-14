"""Local filters and export callbacks for Page 7."""

from __future__ import annotations

from dash import Input, Output, State, dcc, no_update
import pandas as pd

from ..components.methods import (
    certified_headline_grid,
    limitation_register,
    metric_dictionary_grid,
    research_question_cards,
)
from ..data.repository import get_dashboard_repository
from ..i18n import DEFAULT_LOCALE, localize_component_tree, normalize_locale
from ..export.methods_package import build_methods_archive
from ..ids import (
    APP_LOCALE_STORE_ID,
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
    METHODS_PAGE_ID,
    METHODS_TABS_ID,
    METHODS_LIMITATION_CONTAINER_ID,
    METHODS_RQ_CONTAINER_ID,
    METHODS_RQ_FILTER_ID,
)
from ..pages.methods import DICTIONARY_DASHBOARD_ENABLED, LIMITATION_ALL, _METHODS_PREFIXES, layout
from ..settings import (
    METHODS_DICTIONARY_DATASET_ALL,
    METHODS_DICTIONARY_ROLE_ALL,
    METHODS_DICTIONARY_TIER_ALL,
    METHODS_REPORT_SECTION_ALL,
    METHODS_RQ_ALL,
)


def filter_certified_numbers(frame: pd.DataFrame, section: object) -> pd.DataFrame:
    selected = str(section or METHODS_REPORT_SECTION_ALL)
    if selected == METHODS_REPORT_SECTION_ALL:
        return frame.copy()
    return frame.loc[frame["report_section"].astype(str) == selected].copy()


def filter_dictionary(
    frame: pd.DataFrame,
    *,
    search: object,
    dataset: object,
    tier: object,
    role: object,
    include_internal: object,
) -> pd.DataFrame:
    output = frame.copy()
    include = isinstance(include_internal, list) and "INCLUDE" in include_internal
    selected_dataset = str(dataset or METHODS_DICTIONARY_DATASET_ALL)
    selected_tier = str(tier or DICTIONARY_DASHBOARD_ENABLED)
    selected_role = str(role or METHODS_DICTIONARY_ROLE_ALL)

    if not include:
        output = output.loc[
            output["visibility_tier"].isin(["A_HEADLINE", "B_EXPLANATORY"])
            & ~output["is_identifier"].astype(bool)
        ]
    if selected_dataset != METHODS_DICTIONARY_DATASET_ALL:
        output = output.loc[output["dataset_name"].astype(str) == selected_dataset]
    if selected_tier == DICTIONARY_DASHBOARD_ENABLED and not include:
        output = output.loc[output["visibility_tier"].isin(["A_HEADLINE", "B_EXPLANATORY"])]
    elif selected_tier not in {DICTIONARY_DASHBOARD_ENABLED, METHODS_DICTIONARY_TIER_ALL}:
        output = output.loc[output["visibility_tier"].astype(str) == selected_tier]

    if selected_role == "IDENTIFIER":
        output = output.loc[output["is_identifier"].astype(bool)]
    elif selected_role == "RATE":
        output = output.loc[output["is_rate"].astype(bool) & ~output["is_identifier"].astype(bool)]
    elif selected_role == "METRIC":
        output = output.loc[~output["is_identifier"].astype(bool)]

    query = str(search or "").strip().lower()
    if query:
        haystack = (
            output["dataset_name"].astype(str)
            + " "
            + output["field_name"].astype(str)
            + " "
            + output["visibility_tier"].astype(str)
        ).str.lower()
        output = output.loc[haystack.str.contains(query, regex=False)]
    return output.sort_values(["dataset_name", "field_name"], kind="stable").reset_index(drop=True)


def filter_limitations(frame: pd.DataFrame, category: object) -> pd.DataFrame:
    selected = str(category or LIMITATION_ALL)
    if selected == LIMITATION_ALL:
        return frame.copy()
    return frame.loc[frame["category"].astype(str) == selected].copy()


def register_methods_callbacks(app) -> None:
    @app.callback(
        Output(METHODS_PAGE_ID, "children"),
        Input(APP_LOCALE_STORE_ID, "data"),
        State(METHODS_TABS_ID, "value", allow_optional=True),
        State(METHODS_RQ_FILTER_ID, "value", allow_optional=True),
        State(METHODS_HEADLINE_SECTION_ID, "value", allow_optional=True),
        State(METHODS_DICTIONARY_SEARCH_ID, "value", allow_optional=True),
        State(METHODS_DICTIONARY_DATASET_ID, "value", allow_optional=True),
        State(METHODS_DICTIONARY_TIER_ID, "value", allow_optional=True),
        State(METHODS_DICTIONARY_ROLE_ID, "value", allow_optional=True),
        State(METHODS_DICTIONARY_INTERNAL_ID, "value", allow_optional=True),
        State(METHODS_LIMITATION_CATEGORY_ID, "value", allow_optional=True),
        prevent_initial_call=True,
    )
    def relocalize_methods_page(
        locale, tab, rq_filter, headline_section, dictionary_search,
        dictionary_dataset, dictionary_tier, dictionary_role,
        dictionary_internal, limitation_category,
    ):
        page = layout(
            tab=tab,
            locale=locale,
            rq_filter=rq_filter,
            headline_section=headline_section,
            dictionary_search=dictionary_search,
            dictionary_dataset=dictionary_dataset,
            dictionary_tier=dictionary_tier,
            dictionary_role=dictionary_role,
            dictionary_internal=dictionary_internal,
            limitation_category=limitation_category,
        )
        return page.children

    @app.callback(
        Output(METHODS_RQ_CONTAINER_ID, "children"),
        Input(METHODS_RQ_FILTER_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_rq_cards(selected_rq, locale):
        data = get_dashboard_repository().methods_data()
        selected = str(selected_rq or METHODS_RQ_ALL)
        valid = {item.rq_id for item in data.research_questions} | {METHODS_RQ_ALL}
        if selected not in valid:
            selected = METHODS_RQ_ALL
        return localize_component_tree(
            research_question_cards(data.research_questions, selected=selected),
            normalize_locale(locale),
            prefixes=_METHODS_PREFIXES,
        )

    @app.callback(
        Output(METHODS_HEADLINE_CONTAINER_ID, "children"),
        Input(METHODS_HEADLINE_SECTION_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_headline_registry(section, locale):
        frame = get_dashboard_repository().methods_data().certified_numbers
        resolved = normalize_locale(locale)
        return localize_component_tree(
            certified_headline_grid(filter_certified_numbers(frame, section), locale=resolved),
            resolved,
            prefixes=_METHODS_PREFIXES,
        )

    @app.callback(
        Output(METHODS_DICTIONARY_CONTAINER_ID, "children"),
        Input(METHODS_DICTIONARY_SEARCH_ID, "value"),
        Input(METHODS_DICTIONARY_DATASET_ID, "value"),
        Input(METHODS_DICTIONARY_TIER_ID, "value"),
        Input(METHODS_DICTIONARY_ROLE_ID, "value"),
        Input(METHODS_DICTIONARY_INTERNAL_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_dictionary(search, dataset, tier, role, include_internal, locale):
        frame = get_dashboard_repository().methods_data().visualization_dictionary
        filtered = filter_dictionary(
            frame,
            search=search,
            dataset=dataset,
            tier=tier,
            role=role,
            include_internal=include_internal,
        )
        resolved = normalize_locale(locale)
        return localize_component_tree(
            metric_dictionary_grid(filtered, locale=resolved),
            resolved,
            prefixes=_METHODS_PREFIXES,
        )

    @app.callback(
        Output(METHODS_LIMITATION_CONTAINER_ID, "children"),
        Input(METHODS_LIMITATION_CATEGORY_ID, "value"),
        Input(APP_LOCALE_STORE_ID, "data"),
    )
    def update_limitations(category, locale):
        frame = get_dashboard_repository().methods_data().limitations
        return localize_component_tree(
            limitation_register(filter_limitations(frame, category)),
            normalize_locale(locale),
            prefixes=_METHODS_PREFIXES,
        )

    @app.callback(
        Output(METHODS_DOWNLOAD_ID, "data"),
        Input(METHODS_EXPORT_ID, "n_clicks"),
        State(APP_LOCALE_STORE_ID, "data"),
        prevent_initial_call=True,
    )
    def export_methods(n_clicks, locale):
        # Locale changes must never re-trigger a completed export.
        if type(n_clicks) is not int or n_clicks <= 0:
            return no_update
        payload = build_methods_archive(locale=locale)
        return dcc.send_bytes(
            lambda target: target.write(payload),
            "LLM_XAI_Reproducibility_Methods_package.zip",
        )
