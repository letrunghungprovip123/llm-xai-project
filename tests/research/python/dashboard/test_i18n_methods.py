"""Page 7 internationalization and analytical-identity contracts."""

from __future__ import annotations

from typing import Any

import pandas as pd

from research.python.dashboard.data.repository import get_dashboard_repository
from research.python.dashboard.figures.methods import build_metric_visibility_profile
from research.python.dashboard.i18n import methods_identifier_label, methods_unknown_identifier_tokens, t
from research.python.dashboard.pages.methods import layout


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            out.extend(_strings(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            if key not in {"value", "id", "field", "customdata", "meta"}:
                out.extend(_strings(item))
        return out
    if hasattr(value, "children"):
        return _strings(value.children)
    return []


def test_methods_layout_defaults_to_vietnamese_and_supports_english() -> None:
    vi = " ".join(_strings(layout()))
    en = " ".join(_strings(layout(locale="en")))
    assert "Khả năng tái lập & Phương pháp" in vi
    assert "Sổ mẫu số" in vi
    assert "Quy trình tái lập" in vi
    assert "Reproducibility & Methods" in en
    assert "Denominator ledger" in en
    assert "Reproduction workflow" in en


def test_methods_figure_changes_copy_not_analytical_metadata() -> None:
    frame = get_dashboard_repository().metric_visibility_registry()
    vi = build_metric_visibility_profile(frame, locale="vi")
    en = build_metric_visibility_profile(frame, locale="en")
    assert list(vi.data[0].x) == list(en.data[0].x)
    assert vi.layout.meta == en.layout.meta
    assert "Chỉ số chính" in list(vi.data[0].y)
    assert "Headline" in list(en.data[0].y)


def test_methods_dictionary_labels_never_fallback_to_english_copy() -> None:
    frame = get_dashboard_repository().visualization_dictionary()
    labels = [methods_identifier_label("vi", value) for value in frame["field_name"]]
    assert len(labels) == len(frame)
    assert all(label.strip() for label in labels)
    assert methods_identifier_label("vi", "planned_llm_generations") == "Số lần sinh LLM theo kế hoạch"
    assert methods_identifier_label("en", "planned_llm_generations") == "Planned LLM generations"


def test_methods_repository_exposes_stable_ids_for_dynamic_registries() -> None:
    data = get_dashboard_repository().methods_data()
    assert data.statistical_families["family_id"].is_unique
    assert data.limitations["limitation_id"].is_unique
    assert data.limitations["category_id"].notna().all()
    assert data.reproduction_steps["step_id"].is_unique
    assert data.artifact_inventory["dashboard_role_id"].notna().all()
    assert data.denominator_ledger["domain_id"].notna().all()


def test_methods_catalog_covers_all_six_research_questions() -> None:
    for rq in [f"RQ{index}" for index in range(1, 7)]:
        assert t("vi", f"methods.rq.{rq}.title")
        assert t("vi", f"methods.rq.{rq}.question")
        assert t("en", f"methods.rq.{rq}.title")


def _find(component: Any, component_id: str):
    if getattr(component, "id", None) == component_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    for child in children if isinstance(children, (list, tuple)) else [children]:
        found = _find(child, component_id)
        if found is not None:
            return found
    return None


def test_methods_locale_roundtrip_preserves_stable_control_values() -> None:
    from research.python.dashboard.ids import (
        METHODS_DICTIONARY_DATASET_ID,
        METHODS_DICTIONARY_INTERNAL_ID,
        METHODS_DICTIONARY_ROLE_ID,
        METHODS_DICTIONARY_SEARCH_ID,
        METHODS_DICTIONARY_TIER_ID,
        METHODS_HEADLINE_SECTION_ID,
        METHODS_LIMITATION_CATEGORY_ID,
        METHODS_RQ_FILTER_ID,
        METHODS_TABS_ID,
    )
    kwargs = dict(
        tab="metrics",
        rq_filter="RQ4",
        headline_section="primary_metric",
        dictionary_search="faithfulness",
        dictionary_dataset="baseline_generation_metrics",
        dictionary_tier="B_EXPLANATORY",
        dictionary_role="RATE",
        dictionary_internal=["INCLUDE"],
        limitation_category="Measurement system",
    )
    expected = {
        METHODS_TABS_ID: "metrics",
        METHODS_RQ_FILTER_ID: "RQ4",
        METHODS_HEADLINE_SECTION_ID: "primary_metric",
        METHODS_DICTIONARY_SEARCH_ID: "faithfulness",
        METHODS_DICTIONARY_DATASET_ID: "baseline_generation_metrics",
        METHODS_DICTIONARY_TIER_ID: "B_EXPLANATORY",
        METHODS_DICTIONARY_ROLE_ID: "RATE",
        METHODS_DICTIONARY_INTERNAL_ID: ["INCLUDE"],
        METHODS_LIMITATION_CATEGORY_ID: "Measurement system",
    }
    for locale in ("vi", "en"):
        page = layout(locale=locale, **kwargs)
        for component_id, value in expected.items():
            component = _find(page, component_id)
            assert component is not None, component_id
            assert component.value == value
