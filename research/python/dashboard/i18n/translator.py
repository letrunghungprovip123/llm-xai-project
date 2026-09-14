"""Strict translation catalog loading and message interpolation."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from string import Formatter
from typing import Mapping

from .locale import normalize_locale
from .types import LocaleCode


class TranslationError(RuntimeError):
    """Base class for deterministic translation failures."""


class TranslationCatalogError(TranslationError):
    """Raised when a catalog cannot be read or has an invalid structure."""


class MissingTranslationError(TranslationError, KeyError):
    """Raised when a requested semantic key is absent from a locale catalog."""


class TranslationInterpolationError(TranslationError, ValueError):
    """Raised when message parameters do not match the frozen template."""


def _catalog_resource(locale: LocaleCode):
    return files("research.python.dashboard.i18n").joinpath(
        "catalogs", f"{locale}.json"
    )


def _flatten_catalog(
    value: object,
    *,
    prefix: str = "",
    output: dict[str, str] | None = None,
) -> dict[str, str]:
    flattened = output if output is not None else {}
    if not isinstance(value, Mapping):
        raise TranslationCatalogError(
            "The root of a translation catalog must be a JSON object."
        )

    for raw_key, child in value.items():
        key = str(raw_key).strip()
        if not key or "." in key:
            raise TranslationCatalogError(
                f"Catalog path segments must be non-empty and contain no dots: {raw_key!r}."
            )
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, Mapping):
            _flatten_catalog(child, prefix=path, output=flattened)
            continue
        if not isinstance(child, str):
            raise TranslationCatalogError(
                f"Catalog leaf {path!r} must be a string, got {type(child).__name__}."
            )
        if path in flattened:
            raise TranslationCatalogError(f"Duplicate catalog key: {path}.")
        flattened[path] = child
    return flattened


@lru_cache(maxsize=len(("vi", "en")))
def load_catalog(locale: LocaleCode | str) -> dict[str, str]:
    """Load and flatten one UTF-8 JSON catalog.

    A defensive copy is returned by :func:`catalog`; internal cached mappings
    are never exposed for mutation.
    """

    normalized = normalize_locale(locale, strict=True)
    resource = _catalog_resource(normalized)
    try:
        raw = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TranslationCatalogError(
            f"Unable to load translation catalog for locale {normalized!r}: {error}"
        ) from error
    flattened = _flatten_catalog(raw)
    for key, text in flattened.items():
        if not text.strip():
            raise TranslationCatalogError(
                f"Catalog {normalized!r} contains a blank translation for {key!r}."
            )
    return flattened


def catalog(locale: LocaleCode | str) -> dict[str, str]:
    """Return a copy of the flattened catalog for safe inspection."""

    return dict(load_catalog(locale))


def translation_keys(locale: LocaleCode | str) -> frozenset[str]:
    return frozenset(load_catalog(locale))


def template_fields(template: str) -> frozenset[str]:
    """Return named ``str.format`` fields used by one message template."""

    fields: set[str] = set()
    try:
        parsed = Formatter().parse(template)
        for _, field_name, _, _ in parsed:
            if field_name:
                # Nested/indexed access would make parity and safety harder to
                # audit. Catalog templates intentionally use simple names.
                if any(token in field_name for token in (".", "[", "]")):
                    raise TranslationCatalogError(
                        f"Translation fields must be simple names: {field_name!r}."
                    )
                fields.add(field_name)
    except ValueError as error:
        raise TranslationCatalogError(
            f"Invalid translation template {template!r}: {error}"
        ) from error
    return frozenset(fields)


def t(locale: LocaleCode | str, key: str, /, **parameters: object) -> str:
    """Translate one semantic key with strict parameter checking.

    There is deliberately no implicit English fallback. A missing key or a
    placeholder mismatch must fail tests instead of creating a mixed-language
    page in production.
    """

    normalized = normalize_locale(locale, strict=True)
    messages = load_catalog(normalized)
    try:
        template = messages[key]
    except KeyError as error:
        raise MissingTranslationError(
            f"Missing translation key {key!r} for locale {normalized!r}."
        ) from error

    required = template_fields(template)
    supplied = frozenset(parameters)
    missing = required - supplied
    unexpected = supplied - required
    if missing or unexpected:
        raise TranslationInterpolationError(
            f"Invalid parameters for {key!r} ({normalized}): "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}."
        )
    try:
        return template.format(**parameters)
    except (KeyError, ValueError, TypeError) as error:
        raise TranslationInterpolationError(
            f"Unable to interpolate {key!r} ({normalized}): {error}"
        ) from error


__all__ = [
    "MissingTranslationError",
    "TranslationCatalogError",
    "TranslationError",
    "TranslationInterpolationError",
    "catalog",
    "load_catalog",
    "t",
    "template_fields",
    "translation_keys",
]
