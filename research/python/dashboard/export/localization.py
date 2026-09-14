"""Locale-aware presentation helpers and archive certification contracts.

Machine-readable file names, schema keys, stable IDs and numeric values remain
locale-neutral.  README text and optional display-layer CSV copies follow the
active dashboard locale.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
from typing import Iterable
from zipfile import ZipFile

from ..i18n import DEFAULT_LOCALE, normalize_locale, t


@dataclass(frozen=True)
class ArchiveLocaleContract:
    manifest_name: str
    display_locale: str
    files: tuple[str, ...]


def export_readme(
    locale: object,
    page_key: str,
    *,
    analytical_release: str,
    visualization_release: str,
    details: Iterable[str] = (),
) -> str:
    resolved = normalize_locale(locale)
    lines = [
        t(resolved, f"exports.pages.{page_key}.title"),
        t(resolved, "exports.common.analytical_release", release=analytical_release),
        t(resolved, "exports.common.visualization_release", release=visualization_release),
        t(resolved, "exports.common.locale", locale=resolved),
        t(resolved, "exports.common.machine_schema"),
        t(resolved, "exports.common.presentation_note"),
        *[str(item) for item in details if str(item).strip()],
    ]
    return "\n".join(lines) + "\n"


def inspect_archive_locale(
    payload: bytes,
    *,
    manifest_name: str = "manifest.json",
) -> ArchiveLocaleContract:
    with ZipFile(BytesIO(payload)) as archive:
        names = tuple(sorted(archive.namelist()))
        manifest = json.loads(archive.read(manifest_name))
    locale = normalize_locale(manifest.get("display_locale"), strict=True)
    return ArchiveLocaleContract(
        manifest_name=manifest_name,
        display_locale=locale,
        files=names,
    )


__all__ = ["ArchiveLocaleContract", "export_readme", "inspect_archive_locale"]
