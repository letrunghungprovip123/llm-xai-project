"""Cross-page export localization and machine-schema certification."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from research.python.dashboard.callbacks.decision import build_decision_archive
from research.python.dashboard.callbacks.effectiveness import build_effectiveness_archive
from research.python.dashboard.callbacks.mechanisms import build_mechanisms_archive
from research.python.dashboard.data.repository import get_dashboard_repository
from research.python.dashboard.export.case_figures import build_case_archive
from research.python.dashboard.export.localization import inspect_archive_locale
from research.python.dashboard.export.methods_package import build_methods_archive
from research.python.dashboard.export.robustness_figures import build_robustness_archive
from research.python.dashboard.export.static_figures import build_overview_export_archive
from research.python.dashboard.settings import (
    DEFAULT_CASE_EVIDENCE,
    DEFAULT_CASE_MATRIX_METRIC,
    DEFAULT_CASE_MODEL,
    DEFAULT_DECISION_SCENARIO,
)


def _first_case_id() -> int:
    return int(get_dashboard_repository().case_catalog().iloc[0]["case_id"])


def _default_decision_weights() -> dict[str, float]:
    repository = get_dashboard_repository()
    return {
        item.criterion_id: item.default_weight * 100
        for item in repository.decision_criteria()
    }


@lru_cache(maxsize=2)
def _archives(locale: str) -> dict[str, tuple[bytes, str]]:
    return {
        "overview": (build_overview_export_archive(locale=locale), "manifest.json"),
        "effectiveness": (build_effectiveness_archive(locale), "manifest.json"),
        "mechanisms": (build_mechanisms_archive(locale), "manifest.json"),
        "decision": (
            build_decision_archive(
                DEFAULT_DECISION_SCENARIO,
                _default_decision_weights(),
                locale,
            ),
            "manifest.json",
        ),
        "robustness": (build_robustness_archive(locale), "manifest.json"),
        "cases": (
            build_case_archive(
                case_id=_first_case_id(),
                model_id=DEFAULT_CASE_MODEL,
                evidence_level=DEFAULT_CASE_EVIDENCE,
                metric_id=DEFAULT_CASE_MATRIX_METRIC,
                locale=locale,
            ),
            "case_export_manifest.json",
        ),
        "methods": (build_methods_archive(locale=locale), "methods_manifest.json"),
    }




@pytest.fixture(scope="module", autouse=True)
def _release_cached_archives():
    yield
    _archives.cache_clear()


def _manifest(payload: bytes, name: str) -> dict:
    with ZipFile(BytesIO(payload)) as archive:
        return json.loads(archive.read(name))


def test_all_seven_archives_record_locale_and_include_localized_readme() -> None:
    expected = {
        "vi": ("Bản phát hành phân tích", "Bản phát hành trực quan hóa"),
        "en": ("Analytical release", "Visualization release"),
    }
    for locale in ("vi", "en"):
        for page, (payload, manifest_name) in _archives(locale).items():
            contract = inspect_archive_locale(payload, manifest_name=manifest_name)
            assert contract.display_locale == locale, page
            assert "README.txt" in contract.files, page
            with ZipFile(BytesIO(payload)) as archive:
                readme = archive.read("README.txt").decode("utf-8")
            for phrase in expected[locale]:
                assert phrase in readme, (page, phrase, readme)


def test_locale_switch_does_not_change_export_machine_identity() -> None:
    vi_archives = _archives("vi")
    en_archives = _archives("en")
    ignored = {"display_locale", "figures", "display_files"}

    for page in vi_archives:
        vi_payload, manifest_name = vi_archives[page]
        en_payload, _ = en_archives[page]
        vi_manifest = _manifest(vi_payload, manifest_name)
        en_manifest = _manifest(en_payload, manifest_name)
        for key in set(vi_manifest) | set(en_manifest):
            if key in ignored:
                continue
            assert vi_manifest.get(key) == en_manifest.get(key), (page, key)

        vi_figures = vi_manifest.get("figures", [])
        en_figures = en_manifest.get("figures", [])
        assert [item.get("figure_id") for item in vi_figures] == [
            item.get("figure_id") for item in en_figures
        ]
        assert [item.get("path") for item in vi_figures] == [
            item.get("path") for item in en_figures
        ]
        assert [item.get("metadata") for item in vi_figures] == [
            item.get("metadata") for item in en_figures
        ]


def test_methods_export_preserves_technical_csv_and_adds_localized_display_copies() -> None:
    vi_payload = build_methods_archive(locale="vi")
    en_payload = build_methods_archive(locale="en")
    technical = {
        "release_metadata.csv",
        "certified_report_numbers.csv",
        "research_question_registry.csv",
        "metric_visibility_registry.csv",
        "visualization_dictionary.csv",
        "validation_gate_registry.csv",
        "artifact_inventory.csv",
        "limitations_registry.csv",
        "reproduction_steps.csv",
    }
    display = {f"display/{name}" for name in technical if name != "release_metadata.csv"}

    with ZipFile(BytesIO(vi_payload)) as vi, ZipFile(BytesIO(en_payload)) as en:
        assert technical <= set(vi.namelist())
        assert display <= set(vi.namelist())
        assert display <= set(en.namelist())
        for name in technical:
            assert vi.read(name) == en.read(name), name
        assert vi.read("display/research_question_registry.csv") != en.read(
            "display/research_question_registry.csv"
        )
        assert vi.read("display/limitations_registry.csv") != en.read(
            "display/limitations_registry.csv"
        )
        vi_manifest = json.loads(vi.read("methods_manifest.json"))
        assert set(vi_manifest["display_files"]) == display
