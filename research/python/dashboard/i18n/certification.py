"""Runtime certification for complete Vietnamese/English dashboard coverage.

The certification layer renders every dashboard page in both locales, extracts
only user-visible component and Plotly presentation text, checks page markers,
and reports opposite-locale catalog phrases that escaped localization.
Analytical values, control identities and technical metadata are never used as
language evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import gc
import re
from string import Formatter
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import plotly.graph_objects as go

from .domain_labels import TECHNICAL_ALLOWLIST
from .locale import DEFAULT_LOCALE, SUPPORTED_LOCALES, normalize_locale
from .translator import catalog
from .validation import validate_catalogs


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
        "options",
        "columnDefs",
        "rowData",
        "dashGridOptions",
        "marks",
    }
)
_VISIBLE_MAPPING_KEYS = frozenset(
    {
        "label",
        "headerName",
        "description",
        "title",
        "placeholder",
        "tooltip",
        "aria-label",
        "aria-description",
        "text",
        "message",
        "display",
        "name",
        "status",
    }
)
_PLOTLY_TRACE_FIELDS = (
    "name",
    "text",
    "hovertext",
    "hovertemplate",
    "texttemplate",
    "labels",
    "ticktext",
)
_PLOTLY_LAYOUT_FIELDS = (
    "title",
    "xaxis",
    "yaxis",
    "legend",
    "annotations",
    "coloraxis",
    "hoverlabel",
)
_COMMAND_PREFIXES = (
    "python ",
    "python3 ",
    "pytest ",
    "git ",
    "DASH_E2E_BASE_URL=",
    "export ",
)


@dataclass(frozen=True)
class PageLocaleSpec:
    page_id: str
    route: str
    title_key: str
    renderer: Callable[[str], Any]


@dataclass(frozen=True)
class PageLocaleResult:
    page_id: str
    route: str
    locale: str
    expected_title: str
    visible_string_count: int
    title_present: bool
    opposite_locale_leaks: tuple[str, ...]
    heuristic_language_leaks: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return (
            self.title_present
            and not self.opposite_locale_leaks
            and not self.heuristic_language_leaks
        )


@dataclass(frozen=True)
class ExportLocaleResult:
    page_id: str
    locale: str
    manifest_name: str
    display_locale_matches: bool
    readme_present: bool
    readme_locale_marker_present: bool
    stable_identity_matches_other_locale: bool

    @property
    def passed(self) -> bool:
        return all(
            (
                self.display_locale_matches,
                self.readme_present,
                self.readme_locale_marker_present,
                self.stable_identity_matches_other_locale,
            )
        )


@dataclass(frozen=True)
class DashboardLocaleCertification:
    default_locale: str
    catalog: dict[str, object]
    pages: tuple[PageLocaleResult, ...]
    exports: tuple[ExportLocaleResult, ...]

    @property
    def passed(self) -> bool:
        return (
            bool(self.catalog.get("passed"))
            and all(item.passed for item in self.pages)
            and all(item.passed for item in self.exports)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "default_locale": self.default_locale,
            "catalog": self.catalog,
            "pages": [
                {**asdict(item), "passed": item.passed}
                for item in self.pages
            ],
            "exports": [
                {**asdict(item), "passed": item.passed}
                for item in self.exports
            ],
            "passed": self.passed,
        }


def _component_class() -> type | tuple[()]:
    try:
        from dash.development.base_component import Component
    except ModuleNotFoundError:  # pragma: no cover - docs-only environment.
        return ()
    return Component


def _flatten_strings(value: Any) -> list[str]:
    """Extract presentation strings while excluding stable identity fields."""

    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, go.Figure):
        payload = value.to_plotly_json()
        output: list[str] = []
        for trace in payload.get("data", []):
            for field in _PLOTLY_TRACE_FIELDS:
                if field in trace:
                    output.extend(_flatten_strings(trace[field]))
        layout = payload.get("layout", {})
        for field in _PLOTLY_LAYOUT_FIELDS:
            if field in layout:
                output.extend(_flatten_strings(layout[field]))
        return output
    if isinstance(value, np.ndarray):
        if value.dtype.kind not in {"O", "S", "U"}:
            return []
        return _flatten_strings(value.tolist())

    Component = _component_class()
    if Component and isinstance(value, Component):
        output: list[str] = []
        for prop in getattr(value, "_prop_names", ()):
            if prop not in _VISIBLE_COMPONENT_PROPS or not hasattr(value, prop):
                continue
            current = getattr(value, prop)
            if prop == "figure" and isinstance(current, go.Figure):
                output.extend(_flatten_strings(current))
            else:
                output.extend(_flatten_strings(current))
        # Some Graph stubs do not advertise figure in _prop_names.
        current_figure = getattr(value, "figure", None)
        if isinstance(current_figure, go.Figure):
            output.extend(_flatten_strings(current_figure))
        return output
    if isinstance(value, Mapping):
        output: list[str] = []
        for raw_key, item in value.items():
            key = str(raw_key)
            if key in _VISIBLE_MAPPING_KEYS:
                output.extend(_flatten_strings(item))
            elif key in {"children", "options", "columnDefs", "rowData", "localeText"}:
                output.extend(_flatten_strings(item))
            elif isinstance(item, Mapping):
                output.extend(_flatten_strings(item))
            elif isinstance(item, (list, tuple)) and key not in {
                "customdata",
                "ids",
                "values",
            }:
                output.extend(_flatten_strings(item))
        return output
    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in value:
            output.extend(_flatten_strings(item))
        return output
    return []


def visible_strings(component: Any) -> tuple[str, ...]:
    """Return de-duplicated visible strings in stable encounter order."""

    seen: set[str] = set()
    ordered: list[str] = []
    for text in _flatten_strings(component):
        if text not in seen:
            seen.add(text)
            ordered.append(text)
    return tuple(ordered)


def _literal_template_parts(template: str) -> tuple[str, ...]:
    parts: list[str] = []
    for literal, _, _, _ in Formatter().parse(template):
        cleaned = literal.strip()
        if len(cleaned) >= 4:
            parts.append(cleaned)
    return tuple(parts)


def _catalog_leaks(strings: Sequence[str], locale: str) -> tuple[str, ...]:
    other = "en" if locale == "vi" else "vi"
    current_catalog = catalog(locale)
    other_catalog = catalog(other)
    candidate_parts: set[str] = set()
    for key, other_value in other_catalog.items():
        if current_catalog.get(key) == other_value:
            continue
        candidate_parts.update(_literal_template_parts(other_value))

    leaks: set[str] = set()
    for text in strings:
        if _is_technical_or_command(text):
            continue
        for candidate in candidate_parts:
            if candidate == text or (
                len(candidate) >= 12 and candidate in text
            ):
                leaks.add(text)
                break
    return tuple(sorted(leaks))


def _is_technical_or_command(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped in TECHNICAL_ALLOWLIST:
        return True
    if stripped.startswith(_COMMAND_PREFIXES):
        return True
    if " --" in stripped or stripped.startswith(("/", "./", "../")):
        return True
    if re.fullmatch(r"[A-Z0-9_.:/+\-–× ]+", stripped):
        return True
    technical_items = [item.strip() for item in stripped.split(",")]
    if len(technical_items) >= 3 and all(
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", item) for item in technical_items
    ):
        return True
    technical_files = [item.strip() for item in stripped.split("·")]
    if len(technical_files) >= 2 and all(
        re.fullmatch(r"[A-Za-z0-9_./-]+\.(?:csv|json|py|md|txt)", item)
        for item in technical_files
    ):
        return True
    if re.fullmatch(r"(?:RQ[1-6]|S[0-5]|V4|P10)(?:[–—-](?:RQ[1-6]|S[0-5]))?", stripped):
        return True
    return False


_VI_DIACRITIC_RE = re.compile(
    r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]",
    re.IGNORECASE,
)
_ENGLISH_COMMON = frozenset(
    {
        "the", "and", "with", "without", "from", "for", "not", "this", "that",
        "selected", "available", "analysis", "results", "status", "view", "all",
        "model", "evidence", "metric", "case", "cases", "claims", "generation",
        "generations", "validation", "research", "release", "source", "comparison",
    }
)
_VIETNAMESE_COMMON = frozenset(
    {
        "và", "không", "được", "các", "cho", "trong", "kết", "quả", "phân",
        "tích", "mô", "hình", "bằng", "chứng", "hồ", "sơ", "chỉ", "số",
        "trạng", "thái", "nghiên", "cứu", "bản", "phát", "hành",
    }
)


def _heuristic_leaks(strings: Sequence[str], locale: str) -> tuple[str, ...]:
    leaks: set[str] = set()
    for text in strings:
        if _is_technical_or_command(text):
            continue
        words = re.findall(r"[A-Za-zÀ-ỹ]+", text.lower())
        if len(words) < 3:
            continue
        if locale == "vi":
            english_hits = sum(word in _ENGLISH_COMMON for word in words)
            vietnamese_hits = sum(word in _VIETNAMESE_COMMON for word in words)
            if english_hits >= 3 and vietnamese_hits == 0 and not _VI_DIACRITIC_RE.search(text):
                leaks.add(text)
        else:
            vietnamese_hits = sum(word in _VIETNAMESE_COMMON for word in words)
            if vietnamese_hits >= 3 or (
                vietnamese_hits >= 2 and _VI_DIACRITIC_RE.search(text)
            ):
                leaks.add(text)
    return tuple(sorted(leaks))


@lru_cache(maxsize=1)
def page_specs() -> tuple[PageLocaleSpec, ...]:
    """Return lazy page renderers to avoid importing Dash pages at module import."""

    from ..pages.cases import layout as cases_layout
    from ..pages.decision import layout as decision_layout
    from ..pages.effectiveness import build_effectiveness_children
    from ..pages.mechanisms import build_mechanisms_children
    from ..pages.methods import layout as methods_layout
    from ..pages.overview import build_overview_children
    from ..pages.robustness import layout as robustness_layout

    return (
        PageLocaleSpec("overview", "/", "overview.title", build_overview_children),
        PageLocaleSpec(
            "effectiveness",
            "/effectiveness",
            "effectiveness.title",
            build_effectiveness_children,
        ),
        PageLocaleSpec(
            "mechanisms",
            "/mechanisms",
            "mechanisms.title",
            build_mechanisms_children,
        ),
        PageLocaleSpec("decision", "/decision", "decision.title", lambda locale: decision_layout(locale=locale)),
        PageLocaleSpec("robustness", "/robustness", "robustness.title", lambda locale: robustness_layout(locale=locale)),
        PageLocaleSpec("cases", "/cases", "cases.title", lambda locale: cases_layout(locale=locale)),
        PageLocaleSpec("methods", "/methods", "methods.page.title", lambda locale: methods_layout(locale=locale)),
    )


@lru_cache(maxsize=1)
def certify_pages() -> tuple[PageLocaleResult, ...]:
    results: list[PageLocaleResult] = []
    for spec in page_specs():
        for locale in SUPPORTED_LOCALES:
            component = spec.renderer(locale)
            strings = visible_strings(component)
            expected_title = catalog(locale)[spec.title_key]
            results.append(
                PageLocaleResult(
                    page_id=spec.page_id,
                    route=spec.route,
                    locale=locale,
                    expected_title=expected_title,
                    visible_string_count=len(strings),
                    title_present=any(expected_title in item for item in strings),
                    opposite_locale_leaks=_catalog_leaks(strings, locale),
                    heuristic_language_leaks=_heuristic_leaks(strings, locale),
                )
            )
            del component
            gc.collect()
    return tuple(results)


def _export_payloads(locale: str) -> dict[str, tuple[bytes, str]]:
    from ..callbacks.decision import build_decision_archive
    from ..callbacks.effectiveness import build_effectiveness_archive
    from ..callbacks.mechanisms import build_mechanisms_archive
    from ..data.repository import get_dashboard_repository
    from ..export.case_figures import build_case_archive
    from ..export.methods_package import build_methods_archive
    from ..export.robustness_figures import build_robustness_archive
    from ..export.static_figures import build_overview_export_archive
    from ..settings import (
        DEFAULT_CASE_EVIDENCE,
        DEFAULT_CASE_MATRIX_METRIC,
        DEFAULT_CASE_MODEL,
        DEFAULT_DECISION_SCENARIO,
    )

    repository = get_dashboard_repository()
    weights = {
        item.criterion_id: item.default_weight * 100
        for item in repository.decision_criteria()
    }
    case_id = int(repository.case_catalog().iloc[0]["case_id"])
    return {
        "overview": (build_overview_export_archive(locale=locale), "manifest.json"),
        "effectiveness": (build_effectiveness_archive(locale), "manifest.json"),
        "mechanisms": (build_mechanisms_archive(locale), "manifest.json"),
        "decision": (
            build_decision_archive(DEFAULT_DECISION_SCENARIO, weights, locale),
            "manifest.json",
        ),
        "robustness": (build_robustness_archive(locale), "manifest.json"),
        "cases": (
            build_case_archive(
                case_id=case_id,
                model_id=DEFAULT_CASE_MODEL,
                evidence_level=DEFAULT_CASE_EVIDENCE,
                metric_id=DEFAULT_CASE_MATRIX_METRIC,
                locale=locale,
            ),
            "case_export_manifest.json",
        ),
        "methods": (build_methods_archive(locale=locale), "methods_manifest.json"),
    }


def _read_archive(payload: bytes, manifest_name: str) -> tuple[set[str], dict[str, Any], str]:
    from io import BytesIO
    import json
    from zipfile import ZipFile

    with ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read(manifest_name))
        readme = (
            archive.read("README.txt").decode("utf-8")
            if "README.txt" in names
            else ""
        )
    return names, manifest, readme


def _stable_manifest_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    projection = dict(manifest)
    projection.pop("display_locale", None)
    projection.pop("display_files", None)
    figures = []
    for item in projection.pop("figures", []) or []:
        figures.append(
            {
                "figure_id": item.get("figure_id"),
                "path": item.get("path"),
                "metadata": item.get("metadata"),
            }
        )
    if figures:
        projection["figures"] = figures
    return projection


@lru_cache(maxsize=1)
def certify_exports() -> tuple[ExportLocaleResult, ...]:
    all_payloads = {locale: _export_payloads(locale) for locale in SUPPORTED_LOCALES}
    parsed: dict[tuple[str, str], tuple[set[str], dict[str, Any], str]] = {}
    for locale, pages in all_payloads.items():
        for page_id, (payload, manifest_name) in pages.items():
            parsed[(page_id, locale)] = _read_archive(payload, manifest_name)

    results: list[ExportLocaleResult] = []
    markers = {
        "vi": "Bản phát hành phân tích",
        "en": "Analytical release",
    }
    for page_id in all_payloads[SUPPORTED_LOCALES[0]]:
        projections = {
            locale: _stable_manifest_projection(parsed[(page_id, locale)][1])
            for locale in SUPPORTED_LOCALES
        }
        stable = len({repr(projections[locale]) for locale in SUPPORTED_LOCALES}) == 1
        for locale in SUPPORTED_LOCALES:
            names, manifest, readme = parsed[(page_id, locale)]
            _, manifest_name = all_payloads[locale][page_id]
            results.append(
                ExportLocaleResult(
                    page_id=page_id,
                    locale=locale,
                    manifest_name=manifest_name,
                    display_locale_matches=manifest.get("display_locale") == locale,
                    readme_present="README.txt" in names,
                    readme_locale_marker_present=markers[locale] in readme,
                    stable_identity_matches_other_locale=stable,
                )
            )
    del all_payloads, parsed
    gc.collect()
    return tuple(results)


@lru_cache(maxsize=1)
def certify_dashboard_locales() -> DashboardLocaleCertification:
    catalog_report = validate_catalogs().to_dict()
    return DashboardLocaleCertification(
        default_locale=DEFAULT_LOCALE,
        catalog=catalog_report,
        pages=certify_pages(),
        exports=certify_exports(),
    )


__all__ = [
    "DashboardLocaleCertification",
    "ExportLocaleResult",
    "PageLocaleResult",
    "PageLocaleSpec",
    "certify_dashboard_locales",
    "certify_exports",
    "certify_pages",
    "page_specs",
    "visible_strings",
]
