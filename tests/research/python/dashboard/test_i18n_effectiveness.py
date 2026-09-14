"""Page-2 i18n contracts and analytical-state preservation."""

from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZipFile

from research.python.dashboard.callbacks.effectiveness import (
    build_effectiveness_archive,
    conditional_updates,
    merge_effectiveness_state,
    primary_contrast_rows,
)
from research.python.dashboard.i18n import t
from research.python.dashboard.pages.effectiveness import (
    contrast_display_frame,
    normalize_effectiveness_state,
)
from research.python.dashboard.data.repository import get_dashboard_repository


def _collect_text(component) -> list[str]:
    if component is None:
        return []
    if isinstance(component, str):
        return [component]
    if isinstance(component, (list, tuple)):
        values: list[str] = []
        for item in component:
            values.extend(_collect_text(item))
        return values
    children = getattr(component, "children", None)
    return _collect_text(children)


def test_effectiveness_state_uses_stable_language_neutral_values() -> None:
    assert normalize_effectiveness_state(None) == {
        "tab": "operational",
        "conditional_metric": "conservative_faithfulness",
        "contrast_family": "all",
    }
    current = {
        "tab": "statistics",
        "conditional_metric": "verifiability",
        "contrast_family": "evidence_vs_s0",
    }
    assert merge_effectiveness_state(current) == current
    assert merge_effectiveness_state(current, tab="conditional")["tab"] == "conditional"
    assert normalize_effectiveness_state({"tab": "Tiếng Việt"})["tab"] == "operational"


def test_contrast_display_localizes_copy_without_changing_counts() -> None:
    frame = get_dashboard_repository().paired_tests().head(1)
    vi = contrast_display_frame(frame, "vi").iloc[0]
    en = contrast_display_frame(frame, "en").iloc[0]
    assert " so với " in vi["contrast"]
    assert " vs " in en["contrast"]
    assert vi["planned_pair_count"] == en["planned_pair_count"]
    assert vi["observed_pair_count"] == en["observed_pair_count"]


def test_conditional_outputs_localize_visible_plotly_copy_and_preserve_meta() -> None:
    vi_heatmap, vi_gap, vi_panel, vi_rows = conditional_updates("verifiability", "vi")
    en_heatmap, en_gap, en_panel, en_rows = conditional_updates("verifiability", "en")

    assert vi_heatmap.layout.meta == en_heatmap.layout.meta
    assert vi_gap.layout.meta == en_gap.layout.meta
    assert "Thiếu" in str(vi_heatmap.data[0].hovertemplate)
    assert "Missing" in str(en_heatmap.data[0].hovertemplate)
    assert vi_rows[0]["planned_pair_count"] == en_rows[0]["planned_pair_count"]
    assert "Diễn giải có điều kiện" in " ".join(_collect_text(vi_panel))
    assert "Conditional interpretation" in " ".join(_collect_text(en_panel))


def test_primary_contrast_rows_keep_certified_cardinality_in_both_locales() -> None:
    assert len(primary_contrast_rows("all", "vi")) == 33
    assert len(primary_contrast_rows("all", "en")) == 33
    assert len(primary_contrast_rows("model_within_evidence", "vi")) == 18
    assert len(primary_contrast_rows("evidence_vs_s0", "en")) == 15


def test_effectiveness_export_records_display_locale_without_schema_drift() -> None:
    for locale in ("vi", "en"):
        with ZipFile(BytesIO(build_effectiveness_archive(locale))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["schema_version"] == "effectiveness_export_manifest_v1"
            assert manifest["display_locale"] == locale
            assert len(manifest["figures"]) == 5


def test_effectiveness_semantic_catalog_is_complete_for_both_locales() -> None:
    keys = (
        "effectiveness.title",
        "effectiveness.tab_operational",
        "effectiveness.tab_conditional",
        "effectiveness.tab_statistics",
        "effectiveness.statistics.disclaimer",
    )
    for key in keys:
        assert t("vi", key).strip()
        assert t("en", key).strip()
