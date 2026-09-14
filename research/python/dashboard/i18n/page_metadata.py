"""Locale-aware browser metadata derived from stable route identities."""

from __future__ import annotations

from dataclasses import dataclass

from .domain_labels import page_label
from .locale import normalize_locale
from .translator import t
from .types import LocaleCode


_PATH_TO_PAGE = {
    "/": "overview",
    "/effectiveness": "effectiveness",
    "/mechanisms": "mechanisms",
    "/decision": "decision",
    "/robustness": "robustness",
    "/cases": "cases",
    "/methods": "methods",
}


@dataclass(frozen=True)
class DocumentMetadata:
    lang: LocaleCode
    title: str

    def to_dict(self) -> dict[str, str]:
        return {"lang": self.lang, "title": self.title}


def normalize_pathname(pathname: object) -> str:
    value = str(pathname or "/").strip() or "/"
    if value != "/":
        value = "/" + value.strip("/")
    return value


def document_metadata(locale: object, pathname: object) -> DocumentMetadata:
    resolved_locale = normalize_locale(locale)
    normalized_path = normalize_pathname(pathname)
    page_id = _PATH_TO_PAGE.get(normalized_path)
    page_title = page_label(resolved_locale, page_id) if page_id else t(
        resolved_locale, "app.title"
    )
    return DocumentMetadata(
        lang=resolved_locale,
        title=f"{page_title} · LLM-XAI" if page_id else page_title,
    )


__all__ = ["DocumentMetadata", "document_metadata", "normalize_pathname"]
