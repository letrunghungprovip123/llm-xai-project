"""Page-3 i18n, stable identity and export contracts."""

from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZipFile

from plotly.utils import PlotlyJSONEncoder

from research.python.dashboard.callbacks.mechanisms import (
    build_mechanisms_archive,
    mechanisms_figures,
    merge_mechanisms_state,
    utilization_updates,
)
from research.python.dashboard.data.repository import get_dashboard_repository
from research.python.dashboard.i18n import (
    claim_type_label,
    reason_code_label,
    t,
    utilization_metric_label,
)
from research.python.dashboard.pages.mechanisms import (
    localized_failure_frame,
    localized_reason_frame,
    normalize_mechanisms_focus,
    normalize_mechanisms_state,
)


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
    return _collect_text(getattr(component, "children", None))


def test_mechanisms_state_uses_locale_neutral_ids() -> None:
    assert normalize_mechanisms_state(None) == {
        "tab": "design",
        "utilization_metric": "feature_use",
        "claim_measure": "rate",
    }
    current = {
        "tab": "claims",
        "utilization_metric": "concept_use",
        "claim_measure": "count",
    }
    assert merge_mechanisms_state(current) == current
    assert merge_mechanisms_state(current, tab="pipeline")["tab"] == "pipeline"
    assert normalize_mechanisms_state({"tab": "Bằng chứng"})["tab"] == "design"


def test_domain_identifiers_have_explicit_vi_en_labels() -> None:
    assert utilization_metric_label("vi", "feature_use") == "Mức sử dụng đặc trưng"
    assert utilization_metric_label("en", "feature_use") == "Feature use"
    assert claim_type_label("vi", "prediction") == "Dự đoán"
    assert claim_type_label("en", "prediction") == "Prediction"
    assert "khái niệm" in reason_code_label(
        "vi", "CONCEPT_NOT_FOUND_IN_EVIDENCE"
    ).lower()


def test_focus_normalization_preserves_valid_model_and_evidence_ids() -> None:
    repository = get_dashboard_repository()
    focus = normalize_mechanisms_focus(
        repository,
        "feature_use",
        {"model_id": "phi4_mini_instruct", "evidence_level": "S4"},
    )
    assert focus == {
        "model_id": "phi4_mini_instruct",
        "evidence_level": "S4",
    }


def test_utilization_outputs_change_copy_not_analytical_focus() -> None:
    current = {"model_id": "phi4_mini_instruct", "evidence_level": "S4"}
    vi = utilization_updates("feature_use", None, current, "vi")
    en = utilization_updates("feature_use", None, current, "en")
    assert vi[1] == current == en[1]
    assert vi[0].layout.meta == en[0].layout.meta
    assert list(vi[0].data[0].customdata[:, 0]) == list(en[0].data[0].customdata[:, 0])
    assert list(vi[0].data[0].customdata[:, 2]) == list(en[0].data[0].customdata[:, 2])
    assert vi[2].layout.meta == en[2].layout.meta
    vi_stage_status = {str(row[0]) for row in vi[2].data[0].customdata}
    en_stage_status = {str(row[0]) for row in en[2].data[0].customdata}
    assert vi_stage_status <= {"Đã xác định", "Không áp dụng"}
    assert en_stage_status <= {"Defined", "Not applicable"}
    assert "Mức sử dụng đặc trưng" in str(vi[0].data[0].hovertemplate)
    assert "Feature use" in str(en[0].data[0].hovertemplate)
    assert vi[5][0]["case_id"] == en[5][0]["case_id"]
    assert "Cách đọc mức sử dụng" in " ".join(_collect_text(vi[4]))
    assert "How to read utilization" in " ".join(_collect_text(en[4]))


def test_reason_and_failure_display_frames_preserve_certified_row_counts() -> None:
    data = get_dashboard_repository().mechanisms_data()
    vi_reasons = localized_reason_frame(data.evidence_utilization, "vi")
    en_reasons = localized_reason_frame(data.evidence_utilization, "en")
    assert len(vi_reasons) == len(en_reasons)
    assert set(vi_reasons["generation_count"]) == set(en_reasons["generation_count"])
    vi_failures = localized_failure_frame(data.pipeline_failures, "vi")
    en_failures = localized_failure_frame(data.pipeline_failures, "en")
    assert len(vi_failures) == len(en_failures) == 10
    assert set(vi_failures["case_id"]) == set(en_failures["case_id"])
    assert vi_failures["failure_type"].eq("Bị cắt ngắn").all()
    assert en_failures["failure_type"].eq("Truncated").all()



def test_claim_and_pipeline_figure_axes_are_localized_without_value_drift() -> None:
    vi = mechanisms_figures("vi")
    en = mechanisms_figures("en")
    claim_id = "FIG_MECHANISMS_CLAIM_DIFFICULTY"
    pipeline_id = "FIG_MECHANISMS_PIPELINE_COMPLETION"
    assert "Dự đoán" in list(vi[claim_id].data[0].y)
    assert "Prediction" in list(en[claim_id].data[0].y)
    vi_z = json.dumps(vi[claim_id].data[0].z, cls=PlotlyJSONEncoder, sort_keys=True)
    en_z = json.dumps(en[claim_id].data[0].z, cls=PlotlyJSONEncoder, sort_keys=True)
    assert vi_z == en_z
    assert "Theo kế hoạch" in list(vi[pipeline_id].data[0].y)
    assert "Planned" in list(en[pipeline_id].data[0].y)

def test_mechanisms_export_records_display_locale_and_nine_figures() -> None:
    for locale in ("vi", "en"):
        with ZipFile(BytesIO(build_mechanisms_archive(locale))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["schema_version"] == "mechanisms_export_manifest_v1"
            assert manifest["display_locale"] == locale
            assert len(manifest["figures"]) == 9


def test_mechanisms_interpretation_boundaries_exist_in_both_catalogs() -> None:
    for locale in ("vi", "en"):
        assert t(locale, "mechanisms.panel.categorical")
        assert t(locale, "mechanisms.utilization.disclaimer")
        assert t(locale, "mechanisms.utilization.narrative_note")
        assert t(locale, "mechanisms.claims.lexical_disclaimer")
