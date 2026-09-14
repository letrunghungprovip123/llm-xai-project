"""Server-side localization of Plotly presentation strings.

Only explicit semantic catalog entries are used. Analytical arrays, customdata,
metadata and stable identifiers are never translated.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Iterable, Any

import numpy as np
import plotly.graph_objects as go

from .locale import normalize_locale
from .translator import catalog

_VISIBLE_KEYS = {
    "name", "text", "hovertext", "hovertemplate", "texttemplate",
    "ticktext", "label", "title", "x", "y", "labels",
}
_PRESERVED_KEYS = {"customdata", "meta", "ids", "id", "uid", "z", "values"}


def catalog_replacements(locale: object, prefixes: Iterable[str]) -> dict[str, str]:
    """Return longest-first canonical-English replacements for semantic prefixes."""

    resolved = normalize_locale(locale)
    if resolved == "en":
        return {}
    english = catalog("en")
    localized = catalog(resolved)
    accepted = tuple(prefixes)
    pairs = {
        english[key]: localized[key]
        for key in english
        if key.startswith(accepted) and english[key] != localized[key]
    }
    return dict(sorted(pairs.items(), key=lambda item: len(item[0]), reverse=True))


def replace_catalog_text(text: str, replacements: dict[str, str]) -> str:
    """Apply longest-first translations without replacing inside words.

    Short catalog entries such as ``No`` must not mutate unrelated words such
    as ``Not``. Phrases bounded by alphanumeric characters use Unicode-aware
    token boundaries; punctuation-bearing templates keep exact replacement
    semantics so Plotly hover fragments remain supported.
    """

    output = text
    for source, target in replacements.items():
        if not source:
            continue
        if source[0].isalnum() and source[-1].isalnum():
            pattern = rf"(?<!\w){re.escape(source)}(?!\w)"
            output = re.sub(pattern, lambda _: target, output)
        else:
            output = output.replace(source, target)
    return output


def _replace(text: str, replacements: dict[str, str]) -> str:
    return replace_catalog_text(text, replacements)


def _localize(value: Any, replacements: dict[str, str], *, visible: bool = False) -> Any:
    if isinstance(value, str):
        return _replace(value, replacements) if visible else value
    if isinstance(value, list):
        return [_localize(item, replacements, visible=visible) for item in value]
    if isinstance(value, tuple):
        return tuple(_localize(item, replacements, visible=visible) for item in value)
    if isinstance(value, np.ndarray):
        copied = value.copy()
        if not visible or copied.dtype.kind not in {"O", "S", "U"}:
            return copied
        # Plotly 6 can preserve categorical axes as NumPy object arrays in
        # ``to_plotly_json()``.  Localize only string elements while retaining
        # an ndarray so English and translated figures follow the same
        # representation path.  ``object`` prevents longer translations from
        # being truncated by a fixed-width Unicode dtype.
        localized = copied.astype(object, copy=True)
        for index, item in np.ndenumerate(localized):
            if isinstance(item, str):
                localized[index] = _replace(item, replacements)
        return localized
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if key in _PRESERVED_KEYS:
                output[key] = deepcopy(item)
                continue
            output[key] = _localize(
                item,
                replacements,
                visible=visible or key in _VISIBLE_KEYS,
            )
        return output
    return deepcopy(value)


def localize_plotly_figure(
    figure: go.Figure,
    locale: object,
    *,
    prefixes: Iterable[str],
) -> go.Figure:
    """Return a localized copy without mutating certified analytical values."""

    replacements = catalog_replacements(locale, prefixes)
    # Always clone through the same Plotly JSON representation for every locale.
    # Returning ``go.Figure(figure)`` for English while rebuilding localized
    # locales from ``to_plotly_json()`` can expose identical numeric arrays as
    # different Python representations (for example, a list versus Plotly 6's
    # typed-array ``{dtype, bdata, shape}`` mapping).  That representation drift
    # is not analytical drift, but it breaks the stronger contract that locale
    # changes affect presentation only.
    payload = figure.to_plotly_json()
    if replacements:
        payload = _localize(payload, replacements)
    return go.Figure(payload)


__all__ = ["catalog_replacements", "localize_plotly_figure", "replace_catalog_text"]
