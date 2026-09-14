"""Case Explorer i18n, privacy and state-preservation contracts."""

from __future__ import annotations

from io import BytesIO
import json
from typing import Any
from zipfile import ZipFile

from dash import dcc, html
from plotly.utils import PlotlyJSONEncoder

from research.python.dashboard.callbacks.cases import (
    cohort_updates,
    evidence_package_update,
    focused_diagnostics_updates,
    matrix_focus_from_click,
    matrix_updates,
)
from research.python.dashboard.data.repository import get_dashboard_repository
from research.python.dashboard.export.case_figures import build_case_archive, case_figures
from research.python.dashboard.ids import (
    CASES_COMPLETENESS_FILTER_ID,
    CASES_EVIDENCE_ID,
    CASES_MATRIX_METRIC_ID,
    CASES_MODEL_ID,
    CASES_OUTCOME_FILTER_ID,
    CASES_SELECTED_CASE_ID,
    CASES_STRATUM_FILTER_ID,
)
from research.python.dashboard.i18n.plotly_locale import (
    catalog_replacements,
    replace_catalog_text,
)
from research.python.dashboard.pages.cases import ALL, layout
from research.python.dashboard.settings import (
    DEFAULT_CASE_EVIDENCE,
    DEFAULT_CASE_MATRIX_METRIC,
    DEFAULT_CASE_MODEL,
)


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        output: list[str] = []
        for item in value:
            output.extend(_strings(item))
        return output
    if hasattr(value, "children"):
        return _strings(value.children)
    return []


def _find(component: Any, component_id: str):
    """Find any Dash component, including leaf controls without ``children``."""

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


def test_component_finder_reaches_leaf_controls_without_children_prop() -> None:
    tree = html.Div([dcc.Dropdown(id="leaf-control", value="stable-id")])
    found = _find(tree, "leaf-control")
    assert found is not None
    assert found.value == "stable-id"


def _stable_payload(figure) -> str:
    payload = figure.to_plotly_json()
    for trace in payload.get("data", []):
        for key in (
            "name", "text", "hovertext", "hovertemplate", "texttemplate",
            "x", "y", "labels",
        ):
            trace.pop(key, None)
    layout_payload = payload.get("layout", {})
    for key in ("title", "xaxis", "yaxis", "legend", "annotations"):
        layout_payload.pop(key, None)
    return json.dumps(payload, cls=PlotlyJSONEncoder, sort_keys=True)


def _first_case_id() -> int:
    return int(get_dashboard_repository().case_catalog().iloc[0]["case_id"])


def test_case_layout_defaults_to_vietnamese_and_preserves_control_values() -> None:
    vi_page = layout(
        case=_first_case_id(),
        model=DEFAULT_CASE_MODEL,
        evidence="S4",
        metric="verifiability",
        stratum_filter="near_threshold",
        outcome_filter="FP",
        completeness_filter="INCOMPLETE",
    )
    en_page = layout(
        case=_first_case_id(),
        model=DEFAULT_CASE_MODEL,
        evidence="S4",
        metric="verifiability",
        locale="en",
        stratum_filter="near_threshold",
        outcome_filter="FP",
        completeness_filter="INCOMPLETE",
    )
    vi_text = " ".join(_strings(vi_page))
    en_text = " ".join(_strings(en_page))
    assert "Khám phá hồ sơ" in vi_text
    assert "Bộ lọc đoàn hệ" in vi_text
    assert "Case Explorer" in en_text
    assert "Cohort filters" in en_text

    expected = {
        CASES_SELECTED_CASE_ID: _first_case_id(),
        CASES_MODEL_ID: DEFAULT_CASE_MODEL,
        CASES_EVIDENCE_ID: "S4",
        CASES_MATRIX_METRIC_ID: "verifiability",
        CASES_STRATUM_FILTER_ID: "near_threshold",
        CASES_OUTCOME_FILTER_ID: "FP",
        CASES_COMPLETENESS_FILTER_ID: "INCOMPLETE",
    }
    for component_id, value in expected.items():
        assert _find(vi_page, component_id).value == value
        assert _find(en_page, component_id).value == value


def test_cohort_updates_translate_display_only_and_keep_selected_case_fixed() -> None:
    case_id = _first_case_id()
    vi = cohort_updates(ALL, ALL, ALL, case_id, "vi")
    en = cohort_updates(ALL, ALL, ALL, case_id, "en")
    assert vi[0].layout.meta == en[0].layout.meta
    assert _stable_payload(vi[0]) == _stable_payload(en[0])
    assert [item["value"] for item in vi[1]] == [item["value"] for item in en[1]]
    assert vi[1][0]["label"] != en[1][0]["label"]
    assert vi[2][0]["canonical_case"] != en[2][0]["canonical_case"]
    assert vi[2][0]["prediction_probability"] == en[2][0]["prediction_probability"]


def test_matrix_updates_preserve_analytical_payload_and_stable_click_identity() -> None:
    case_id = _first_case_id()
    vi = matrix_updates(
        case_id,
        DEFAULT_CASE_MATRIX_METRIC,
        DEFAULT_CASE_MODEL,
        DEFAULT_CASE_EVIDENCE,
        "vi",
    )
    en = matrix_updates(
        case_id,
        DEFAULT_CASE_MATRIX_METRIC,
        DEFAULT_CASE_MODEL,
        DEFAULT_CASE_EVIDENCE,
        "en",
    )
    assert vi[0].layout.meta == en[0].layout.meta
    assert _stable_payload(vi[0]) == _stable_payload(en[0])
    assert "Lần sinh đang tập trung" in " ".join(_strings(vi[1]))
    assert "Focused generation" in " ".join(_strings(en[1]))

    click = {
        "points": [
            {
                "customdata": [
                    "Nhãn có thể đổi",
                    "LLM",
                    DEFAULT_CASE_MODEL,
                    "S4",
                    True,
                    "SUCCESS",
                    0.9,
                ]
            }
        ]
    }
    assert matrix_focus_from_click(click) == (DEFAULT_CASE_MODEL, "S4")
    template_click = {
        "points": [
            {
                "customdata": [
                    "Template tất định",
                    "TEMPLATE",
                    "template_baseline",
                    "S3",
                    True,
                    "SUCCESS",
                    0.8,
                ]
            }
        ]
    }
    assert matrix_focus_from_click(template_click) == (None, "S3")


def test_evidence_and_focused_diagnostics_localize_without_data_drift() -> None:
    case_id = _first_case_id()
    vi_package = evidence_package_update(case_id, "S4", "vi")
    en_package = evidence_package_update(case_id, "S4", "en")
    assert "Gói bằng chứng" in " ".join(_strings(vi_package))
    assert "Evidence package" in " ".join(_strings(en_package))

    vi = focused_diagnostics_updates(case_id, DEFAULT_CASE_MODEL, "S4", "vi")
    en = focused_diagnostics_updates(case_id, DEFAULT_CASE_MODEL, "S4", "en")
    for index in (0, 1, 3):
        assert vi[index].layout.meta == en[index].layout.meta
        assert _stable_payload(vi[index]) == _stable_payload(en[index])
    assert "Cấu trúc tường thuật" in " ".join(_strings(vi[2]))
    assert "Narrative structure" in " ".join(_strings(en[2]))
    assert "LLM đang tập trung so với Template" in " ".join(_strings(vi[4]))
    assert "Focused LLM versus Template" in " ".join(_strings(en[4]))


def test_case_figure_customdata_keeps_stable_ids_across_locales() -> None:
    vi = case_figures(locale="vi")
    en = case_figures(locale="en")
    assert set(vi) == set(en)
    for figure_id in vi:
        assert vi[figure_id].layout.meta == en[figure_id].layout.meta
        assert _stable_payload(vi[figure_id]) == _stable_payload(en[figure_id])

    matrix = next(figure for key, figure in vi.items() if key == "FIG-CASES-02")
    custom = matrix.data[0].customdata[0][0]
    assert str(custom[1]) in {"LLM", "TEMPLATE"}
    assert str(custom[2]) in {
        DEFAULT_CASE_MODEL,
        "deepseek_v4_flash",
        "phi4_mini_instruct",
        "template_baseline",
    }
    assert str(custom[3]).startswith("S")


def test_case_archive_records_display_locale_without_changing_privacy_contract() -> None:
    payload = build_case_archive(
        case_id=_first_case_id(),
        model_id=DEFAULT_CASE_MODEL,
        evidence_level=DEFAULT_CASE_EVIDENCE,
        metric_id=DEFAULT_CASE_MATRIX_METRIC,
        locale="vi",
    )
    with ZipFile(BytesIO(payload)) as archive:
        manifest = json.loads(archive.read("case_export_manifest.json"))
    assert manifest["display_locale"] == "vi"
    assert manifest["raw_applicant_record_included"] is False
    assert manifest["direct_personal_identifier_included"] is False
    assert manifest["template_is_fourth_llm"] is False


def test_case_plotly_phrase_catalog_has_no_partial_english_replacements() -> None:
    replacements = catalog_replacements("vi", ("cases.",))
    expected = {
        "Generator family:": "Họ bộ sinh:",
        "Runtime status:": "Trạng thái thời gian chạy:",
        "Not applicable": "Không áp dụng",
        "N/A": "Không áp dụng",
        "Candidate: N/A": "Candidate: Không áp dụng",
        "V4: N/A": "V4: Không áp dụng",
        "Conservative faithfulness": "Độ trung thành bảo thủ",
        "Resolved faithfulness": "Độ trung thành đã phân giải",
    }
    for english, vietnamese in expected.items():
        assert replace_catalog_text(english, replacements) == vietnamese
    assert "family" not in replace_catalog_text("Generator family:", replacements)
    assert "status" not in replace_catalog_text("Runtime status:", replacements)
