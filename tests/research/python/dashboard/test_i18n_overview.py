"""Patch 0034 — explicit bilingual Executive Overview certification."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder

from research.python.dashboard.export.static_figures import build_overview_export_archive
from research.python.dashboard.i18n import localize_plotly_figure, t, validate_catalogs
from research.python.dashboard.pages.overview import build_overview_children

ROOT = Path(__file__).resolve().parents[4]


def test_overview_catalog_is_strict_and_bilingual() -> None:
    assert validate_catalogs().passed is True
    assert t("vi", "overview.title") == "Tổng quan điều hành"
    assert t("en", "overview.title") == "Executive Overview"
    assert "con người" in t("vi", "overview.disclaimer")
    assert "human ground truth" in t("en", "overview.disclaimer")


def test_plotly_localizer_preserves_analytical_customdata_and_meta() -> None:
    figure = go.Figure(
        go.Scatter(
            x=["S0"],
            y=[0.9],
            customdata=[["stable-id", "Mean E2E"]],
            hovertemplate="Mean E2E: %{y:.1%}<extra>Certified option performance</extra>",
        )
    )
    figure.update_layout(meta={"metric": "mean_end_to_end_yield"})
    localized = localize_plotly_figure(
        figure, "vi", prefixes=("overview.figure.",)
    )
    assert "E2E trung bình" in localized.data[0].hovertemplate
    assert localized.data[0].customdata[0][0] == "stable-id"
    assert localized.layout.meta["metric"] == "mean_end_to_end_yield"
    assert figure.data[0].hovertemplate.startswith("Mean E2E")


def test_plotly_localizer_uses_one_numeric_representation_for_all_locales() -> None:
    figure = go.Figure(
        go.Heatmap(
            z=np.asarray([[0.25, 0.75], [1.0, 0.0]], dtype=float),
            hovertemplate="Mean E2E: %{z:.1%}<extra></extra>",
        )
    )
    english = localize_plotly_figure(
        figure, "en", prefixes=("overview.figure.",)
    )
    vietnamese = localize_plotly_figure(
        figure, "vi", prefixes=("overview.figure.",)
    )

    english_z = json.dumps(
        english.data[0].z, cls=PlotlyJSONEncoder, sort_keys=True
    )
    vietnamese_z = json.dumps(
        vietnamese.data[0].z, cls=PlotlyJSONEncoder, sort_keys=True
    )
    assert english_z == vietnamese_z
    assert english.data[0].hovertemplate != vietnamese.data[0].hovertemplate


def test_plotly_localizer_translates_numpy_categorical_axes_without_numeric_drift() -> None:
    figure = go.Figure(
        go.Bar(
            x=np.asarray([216, 206], dtype=int),
            y=np.asarray(["Planned", "Usable"], dtype=object),
            orientation="h",
            hovertemplate="%{y}: %{x}<extra></extra>",
        )
    )
    english = localize_plotly_figure(
        figure, "en", prefixes=("mechanisms.figure.",)
    )
    vietnamese = localize_plotly_figure(
        figure, "vi", prefixes=("mechanisms.figure.",)
    )

    assert list(english.data[0].y) == ["Planned", "Usable"]
    assert list(vietnamese.data[0].y) == ["Theo kế hoạch", "Sử dụng được"]
    english_x = json.dumps(
        english.data[0].x, cls=PlotlyJSONEncoder, sort_keys=True
    )
    vietnamese_x = json.dumps(
        vietnamese.data[0].x, cls=PlotlyJSONEncoder, sort_keys=True
    )
    assert english_x == vietnamese_x


def test_overview_builder_renders_both_locales_without_repository_mutation() -> None:
    vi = build_overview_children("vi")
    en = build_overview_children("en")
    assert vi and en
    assert vi[0].children[0].children[0].children == "Tổng quan điều hành"
    assert en[0].children[0].children[0].children == "Executive Overview"


def test_overview_export_records_display_locale_and_localized_readme() -> None:
    for locale, expected in (("vi", "Bản phát hành phân tích"), ("en", "Analytical release")):
        payload = build_overview_export_archive(locale=locale)
        with ZipFile(BytesIO(payload)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            readme = archive.read("README.txt").decode("utf-8")
        assert manifest["display_locale"] == locale
        assert expected in readme
        assert len(manifest["figures"]) == 2


def test_overview_uses_server_rendering_not_dom_translation() -> None:
    page = (ROOT / "research/python/dashboard/pages/overview.py").read_text()
    callback = (ROOT / "research/python/dashboard/callbacks/overview.py").read_text()
    client = (ROOT / "research/python/dashboard/assets/clientside.js").read_text()
    assert "build_overview_children" in page
    assert 'Output(OVERVIEW_CONTENT_ID, "children")' in callback
    assert "MutationObserver" not in client
    assert "translateText" not in client
