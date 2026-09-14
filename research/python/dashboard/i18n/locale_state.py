"""Pure helpers for the global persisted dashboard locale state."""

from __future__ import annotations

from dataclasses import dataclass

from .locale import DEFAULT_LOCALE, normalize_locale
from .types import LocaleCode


@dataclass(frozen=True)
class LocaleControlState:
    """Presentation state for one language button."""

    locale: LocaleCode
    active: bool
    class_name: str
    aria_pressed: str


def locale_from_trigger(
    triggered_id: object,
    current: object,
    *,
    vietnamese_control_id: str,
    english_control_id: str,
) -> LocaleCode:
    """Resolve a language-button interaction using stable component IDs only."""

    if triggered_id == vietnamese_control_id:
        return "vi"
    if triggered_id == english_control_id:
        return "en"
    return normalize_locale(current)


def locale_control_state(current: object, target: object) -> LocaleControlState:
    """Return deterministic visual and accessibility state for one control."""

    locale = normalize_locale(current)
    target_locale = normalize_locale(target, strict=True)
    active = locale == target_locale
    class_name = "locale-switch__button"
    if active:
        class_name += " locale-switch__button--active"
    return LocaleControlState(
        locale=target_locale,
        active=active,
        class_name=class_name,
        aria_pressed="true" if active else "false",
    )


def locale_document_language(current: object) -> str:
    """Return the BCP-47 language code used on ``document.documentElement``."""

    return normalize_locale(current) if current is not None else DEFAULT_LOCALE


__all__ = [
    "LocaleControlState",
    "locale_control_state",
    "locale_document_language",
    "locale_from_trigger",
]
