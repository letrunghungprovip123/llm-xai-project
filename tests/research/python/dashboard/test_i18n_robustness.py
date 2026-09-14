"""Robustness and Template Baseline i18n contracts."""

from __future__ import annotations

import json
from typing import Any

from plotly.utils import PlotlyJSONEncoder

from research.python.dashboard.callbacks.robustness import (
    _focus_from_click,
    measurement_updates,
    template_focus_updates,
    template_progression_update,
    template_uplift_update,
)
from research.python.dashboard.i18n.plotly_locale import (
    catalog_replacements,
    replace_catalog_text,
)
from research.python.dashboard.pages.robustness import layout
from research.python.dashboard.settings import (
    DEFAULT_ROBUSTNESS_METRIC,
    DEFAULT_TEMPLATE_METRIC,
    DEFAULT_TEMPLATE_SCOPE,
    EXPECTED_MODEL_ORDER,
    TEMPLATE_METRIC_LABELS,
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
    output: list[str] = []
    for prop in ("children", "label", "title", "description", "placeholder"):
        if hasattr(value, prop):
            output.extend(_strings(getattr(value, prop)))
    return output


def _stable_payload(figure) -> str:
    payload = figure.to_plotly_json()
    for trace in payload.get("data", []):
        for key in (
            "name", "text", "hovertext", "hovertemplate", "texttemplate",
            "x", "y",
        ):
            trace.pop(key, None)
    layout_payload = payload.get("layout", {})
    for key in ("title", "xaxis", "yaxis", "legend", "annotations"):
        layout_payload.pop(key, None)
    return json.dumps(payload, cls=PlotlyJSONEncoder, sort_keys=True)


def test_robustness_layout_defaults_to_vietnamese_and_renders_english() -> None:
    vi = " ".join(_strings(layout()))
    en = " ".join(_strings(layout(locale="en")))
    assert "Độ vững & Đường cơ sở Template" in vi
    assert "Độ vững đo lường" in vi
    assert "Robustness & Template Baseline" in en
    assert "Measurement robustness" in en


def test_measurement_locale_change_preserves_focus_and_analytical_payload() -> None:
    focus = {"model_id": EXPECTED_MODEL_ORDER[0], "evidence_level": "S4"}
    vi = measurement_updates(
        DEFAULT_ROBUSTNESS_METRIC,
        EXPECTED_MODEL_ORDER[0],
        None,
        focus,
        accept_click=False,
        locale="vi",
    )
    en = measurement_updates(
        DEFAULT_ROBUSTNESS_METRIC,
        EXPECTED_MODEL_ORDER[0],
        None,
        focus,
        accept_click=False,
        locale="en",
    )
    assert vi[2] == focus == en[2]
    assert vi[0].layout.meta == en[0].layout.meta
    assert vi[3].layout.meta == en[3].layout.meta
    assert _stable_payload(vi[0]) == _stable_payload(en[0])
    assert _stable_payload(vi[3]) == _stable_payload(en[3])
    assert "Cách diễn giải" in " ".join(_strings(vi[1]))
    assert "How to interpret" in " ".join(_strings(en[1]))


def test_measurement_click_uses_stable_customdata_not_display_label() -> None:
    click = {
        "points": [
            {
                "y": "Nhãn hiển thị có thể đổi",
                "customdata": [EXPECTED_MODEL_ORDER[1], "DeepSeek V4 Flash", "S2"],
            }
        ]
    }
    assert _focus_from_click(click) == (EXPECTED_MODEL_ORDER[1], "S2")
    assert _focus_from_click({"points": [{"y": "Qwen3 8B · S1"}]}) is None


def test_template_callbacks_translate_visible_copy_only() -> None:
    vi_progression = template_progression_update(DEFAULT_TEMPLATE_METRIC, "vi")
    en_progression = template_progression_update(DEFAULT_TEMPLATE_METRIC, "en")
    assert vi_progression.layout.meta == en_progression.layout.meta
    assert _stable_payload(vi_progression) == _stable_payload(en_progression)
    template_trace = vi_progression.data[-1]
    assert str(template_trace.customdata[0][0]) == "template_baseline"
    assert "Đường cơ sở Template tất định" in str(template_trace.hovertext[0])

    vi_uplift = template_uplift_update(DEFAULT_TEMPLATE_SCOPE, "vi")
    en_uplift = template_uplift_update(DEFAULT_TEMPLATE_SCOPE, "en")
    assert vi_uplift.layout.meta == en_uplift.layout.meta
    assert _stable_payload(vi_uplift) == _stable_payload(en_uplift)
    assert str(vi_uplift.data[0].customdata[0][0][2]) in TEMPLATE_METRIC_LABELS
    assert "Độ trung thành" in str(vi_uplift.data[0].hovertext[0][0])

    vi_focus = template_focus_updates(
        DEFAULT_TEMPLATE_METRIC,
        EXPECTED_MODEL_ORDER[0],
        DEFAULT_TEMPLATE_SCOPE,
        "vi",
    )
    en_focus = template_focus_updates(
        DEFAULT_TEMPLATE_METRIC,
        EXPECTED_MODEL_ORDER[0],
        DEFAULT_TEMPLATE_SCOPE,
        "en",
    )
    assert vi_focus[0].layout.meta == en_focus[0].layout.meta
    assert _stable_payload(vi_focus[0]) == _stable_payload(en_focus[0])
    assert "Bằng chứng ghép cặp" in " ".join(_strings(vi_focus[1]))
    assert "Frozen LLM–Template" in " ".join(_strings(en_focus[1]))


def test_dumbbell_customdata_contains_stable_model_id() -> None:
    figure = measurement_updates(
        DEFAULT_ROBUSTNESS_METRIC,
        EXPECTED_MODEL_ORDER[0],
        None,
        None,
        accept_click=False,
        locale="en",
    )[0]
    marker_trace = next(trace for trace in figure.data if getattr(trace, "customdata", None) is not None)
    assert str(marker_trace.customdata[0][0]) == EXPECTED_MODEL_ORDER[0]
    assert str(marker_trace.customdata[0][2]).startswith("S")


def test_robustness_plotly_phrase_catalog_covers_hidden_axes_and_hover() -> None:
    replacements = catalog_replacements("vi", ("robustness.",))
    expected = {
        "V4 minus Candidate": "V4 trừ Candidate",
        "observed paired cases": "hồ sơ ghép cặp đã quan sát",
        "missing conditional values preserved": "giữ nguyên các giá trị có điều kiện bị thiếu",
        "E2E<br>yield": "Độ trung thành<br>E2E",
        "Mean E2E:": "E2E trung bình:",
        "Supported claims / generation:": "Mệnh đề được hỗ trợ / lần sinh:",
        "Not evaluated": "Chưa đánh giá",
        "Adjusted paired difference": "Khác biệt ghép cặp sau hiệu chỉnh",
        "Claims /<br>100 words": "Mệnh đề /<br>100 từ",
        "Output<br>words": "Số từ<br>đầu ra",
        "+101 words": "+101 từ",
        "Validator choice materially changes this metric at the planned case-level scope.": "Lựa chọn bộ kiểm định làm thay đổi đáng kể chỉ số này trong phạm vi hồ sơ đã hoạch định.",
    }
    for english, vietnamese in expected.items():
        assert replace_catalog_text(english, replacements) == vietnamese
