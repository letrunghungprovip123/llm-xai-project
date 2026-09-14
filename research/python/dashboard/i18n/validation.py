"""Fail-closed validation for dashboard translation catalogs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .locale import SUPPORTED_LOCALES
from .translator import catalog, template_fields
from .types import LocaleCode


@dataclass(frozen=True)
class CatalogValidationReport:
    locales: tuple[LocaleCode, ...]
    key_count: int
    missing_by_locale: dict[str, list[str]]
    extra_by_locale: dict[str, list[str]]
    blank_by_locale: dict[str, list[str]]
    placeholder_mismatches: dict[str, dict[str, list[str]]]

    @property
    def passed(self) -> bool:
        return not any(
            (
                any(self.missing_by_locale.values()),
                any(self.extra_by_locale.values()),
                any(self.blank_by_locale.values()),
                self.placeholder_mismatches,
            )
        )

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["passed"] = self.passed
        return value


class CatalogParityError(RuntimeError):
    """Raised when EN/VI catalogs do not have identical safe contracts."""


def validate_catalogs() -> CatalogValidationReport:
    loaded = {locale: catalog(locale) for locale in SUPPORTED_LOCALES}
    reference_locale = SUPPORTED_LOCALES[0]
    reference = loaded[reference_locale]
    reference_keys = set(reference)

    missing_by_locale: dict[str, list[str]] = {}
    extra_by_locale: dict[str, list[str]] = {}
    blank_by_locale: dict[str, list[str]] = {}
    placeholder_mismatches: dict[str, dict[str, list[str]]] = {}

    for locale, messages in loaded.items():
        keys = set(messages)
        missing_by_locale[locale] = sorted(reference_keys - keys)
        extra_by_locale[locale] = sorted(keys - reference_keys)
        blank_by_locale[locale] = sorted(
            key for key, value in messages.items() if not value.strip()
        )

    common_keys = set.intersection(*(set(messages) for messages in loaded.values()))
    for key in sorted(common_keys):
        expected = template_fields(reference[key])
        observed = {
            locale: template_fields(messages[key]) for locale, messages in loaded.items()
        }
        if any(fields != expected for fields in observed.values()):
            placeholder_mismatches[key] = {
                locale: sorted(fields) for locale, fields in observed.items()
            }

    return CatalogValidationReport(
        locales=SUPPORTED_LOCALES,
        key_count=len(reference_keys),
        missing_by_locale=missing_by_locale,
        extra_by_locale=extra_by_locale,
        blank_by_locale=blank_by_locale,
        placeholder_mismatches=placeholder_mismatches,
    )


def require_valid_catalogs() -> CatalogValidationReport:
    report = validate_catalogs()
    if not report.passed:
        raise CatalogParityError(
            "Translation catalogs failed parity validation:\n"
            + json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
        )
    return report


def main() -> int:
    report = validate_catalogs()
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CatalogParityError",
    "CatalogValidationReport",
    "require_valid_catalogs",
    "validate_catalogs",
]
