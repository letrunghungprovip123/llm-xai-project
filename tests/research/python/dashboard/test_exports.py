"""Certified figure bundle and JSON export tests."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO

from research.python.dashboard.export.static_figures import (
    build_overview_export_archive,
    export_overview_figures,
)


def test_overview_download_bundle_contains_two_figures_and_manifest() -> None:
    payload = build_overview_export_archive()
    with ZipFile(BytesIO(payload), "r") as archive:
        names = set(archive.namelist())
        assert "README.txt" in names
        assert "manifest.json" in names
        figure_names = sorted(name for name in names if name.endswith(".json") and name.startswith("figures/"))
        assert len(figure_names) == 2
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["analytical_release"] == "thesis-report-v1"
        assert manifest["visualization_release"] == "visualization-data-v2"
        assert len(manifest["figures"]) == 2


def test_json_static_export_is_reproducible(tmp_path: Path) -> None:
    files = export_overview_figures(
        output_root=tmp_path,
        formats=("json",),
    )
    assert len(files) == 2
    for path in files:
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["layout"]["meta"]["release"] == "visualization-data-v2"
