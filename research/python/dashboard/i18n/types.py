"""Types shared by the dashboard internationalization foundation."""

from __future__ import annotations

from typing import Literal, TypeAlias


LocaleCode: TypeAlias = Literal["vi", "en"]
TranslationParameters: TypeAlias = dict[str, object]


__all__ = ["LocaleCode", "TranslationParameters"]
