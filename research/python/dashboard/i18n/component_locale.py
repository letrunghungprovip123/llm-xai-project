"""Locale-aware cloning for Dash presentation components and row records.

The helper translates only catalog-backed presentation strings. Stable control
values, component IDs, routes, analytical identities, Plotly customdata and
metadata remain untouched.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Iterable, Mapping, Sequence

import plotly.graph_objects as go

from .locale import normalize_locale
from .plotly_locale import (
    catalog_replacements,
    localize_plotly_figure,
    replace_catalog_text,
)

try:  # Imported only in the dashboard runtime.
    from dash.development.base_component import Component
except ModuleNotFoundError:  # pragma: no cover - documentation/build tools.
    Component = ()  # type: ignore[assignment,misc]


_VISIBLE_COMPONENT_PROPS = frozenset(
    {
        "children",
        "label",
        "title",
        "description",
        "placeholder",
        "aria-label",
        "aria-description",
        "alt",
        "tooltip",
        "content",
        "data",
        "options",
        "columnDefs",
        "rowData",
        "dashGridOptions",
        "marks",
    }
)

_PRESERVED_COMPONENT_PROPS = frozenset(
    {
        "id",
        "value",
        "href",
        "pathname",
        "search",
        "hash",
        "figure",
        "download",
        "filename",
        "target",
        "className",
        "class_name",
        "style",
    }
)

_PRESERVED_DICT_KEYS = frozenset(
    {
        "id",
        "value",
        "field",
        "colId",
        "type",
        "criterion",
        "option_id",
        "model_id",
        "evidence_level",
        "scenario_id",
        "criterion_id",
        "case_id",
        "metric_id",
        "scope_id",
        "href",
        "path",
        "pathname",
        "customdata",
        "meta",
        "ids",
        "uid",
        "figure_id",
    }
)


_TECHNICAL_SPAN_RE = re.compile(
    r"(?:https?://\S+|"
    r"[A-Za-z0-9_./-]+\.(?:csv|json|py|md|txt)|"
    r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b|"
    r"\b(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+){1,}\b|"
    r"\b[a-f0-9]{12,64}\b)"
)


def _replace(
    text: str,
    replacements: Mapping[str, str],
    memo: dict[str, str] | None = None,
) -> str:
    """Translate full phrases first, then protect embedded technical IDs.

    Full catalog sentences can legitimately contain technical tokens such as
    ``Candidate-V4`` or ``SHA-256``. Translating those complete phrases before
    masking preserves their localized wording, while the second pass prevents
    short token replacements from mutating release IDs such as
    ``visualization-data-v2``.
    """

    if memo is not None and text in memo:
        return memo[text]
    replacement_map = dict(replacements)
    phrase_replacements = {
        source: target
        for source, target in replacement_map.items()
        if any(character.isspace() for character in source)
    }
    localized = replace_catalog_text(text, phrase_replacements)
    protected: list[str] = []

    def mask(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\uf000{len(protected) - 1}\uf001"

    masked = _TECHNICAL_SPAN_RE.sub(mask, localized)
    localized = replace_catalog_text(masked, replacement_map)
    for index, value in enumerate(protected):
        localized = localized.replace(f"\uf000{index}\uf001", value)
    if memo is not None:
        memo[text] = localized
    return localized


def _localize_value(
    value: Any,
    replacements: Mapping[str, str],
    *,
    visible: bool,
    memo: dict[str, str] | None = None,
) -> Any:
    if isinstance(value, str):
        return _replace(value, replacements, memo) if visible else value
    if isinstance(value, go.Figure):
        return value
    if Component and isinstance(value, Component):
        copied = deepcopy(value)
        for prop in getattr(copied, "_prop_names", ()):
            if prop in _PRESERVED_COMPONENT_PROPS or not hasattr(copied, prop):
                continue
            current = getattr(copied, prop)
            if current is None:
                continue
            if prop == "children":
                setattr(copied, prop, _localize_value(current, replacements, visible=True, memo=memo))
            elif prop in _VISIBLE_COMPONENT_PROPS:
                setattr(copied, prop, _localize_value(current, replacements, visible=True, memo=memo))
        return copied
    if isinstance(value, list):
        return [_localize_value(item, replacements, visible=visible, memo=memo) for item in value]
    if isinstance(value, tuple):
        return tuple(_localize_value(item, replacements, visible=visible, memo=memo) for item in value)
    if isinstance(value, Mapping):
        output: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in _PRESERVED_DICT_KEYS:
                output[key] = deepcopy(item)
            else:
                output[key] = _localize_value(item, replacements, visible=visible, memo=memo)
        return output
    return deepcopy(value)


def localize_text(text: object, locale: object, *, prefixes: Iterable[str]) -> str:
    """Translate one catalog-backed presentation string."""

    replacements = catalog_replacements(locale, prefixes)
    return _replace(str(text), replacements)


def localize_records(
    records: Sequence[Mapping[str, Any]],
    locale: object,
    *,
    prefixes: Iterable[str],
) -> list[dict[str, Any]]:
    """Translate display fields while preserving stable identity columns."""

    replacements = catalog_replacements(locale, prefixes)
    memo: dict[str, str] = {}
    return [
        dict(
            _localize_value(
                dict(record), replacements, visible=True, memo=memo
            )
        )
        for record in records
    ]


def localize_component_tree(
    component: Any,
    locale: object,
    *,
    prefixes: Iterable[str],
) -> Any:
    """Return a localized clone of a Dash component tree.

    Plotly figures attached to Graph components are localized separately using
    the same prefixes. All locales use the same cloning route.
    """

    resolved = normalize_locale(locale)
    replacements = catalog_replacements(resolved, prefixes)
    if not replacements:
        return component
    memo: dict[str, str] = {}
    localized = _localize_value(
        component, replacements, visible=True, memo=memo
    )

    def localize_figures(value: Any) -> Any:
        if Component and isinstance(value, Component):
            copied = value
            for prop in getattr(copied, "_prop_names", ()):
                if not hasattr(copied, prop):
                    continue
                current = getattr(copied, prop)
                if prop == "figure" and isinstance(current, go.Figure):
                    setattr(
                        copied,
                        prop,
                        localize_plotly_figure(current, resolved, prefixes=prefixes),
                    )
                elif prop == "children":
                    setattr(copied, prop, localize_figures(current))
            return copied
        if isinstance(value, list):
            return [localize_figures(item) for item in value]
        if isinstance(value, tuple):
            return tuple(localize_figures(item) for item in value)
        return value

    return localize_figures(localized)


__all__ = ["localize_component_tree", "localize_records", "localize_text"]
