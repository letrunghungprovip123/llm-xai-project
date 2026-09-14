"""Reproducible export contracts for Page 5."""

from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZipFile

from research.python.dashboard.export.robustness_figures import (
    build_robustness_archive,
    export_robustness_figures,
)


def test_robustness_archive_contains_six_figures_and_frozen_tables() -> None:
    payload = build_robustness_archive()
    with ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["figures"]) == 6
        assert manifest["candidate_role"] == "primary"
        assert manifest["v4_role"] == "sensitivity_only"
        assert manifest["template_is_fourth_llm"] is False
        assert manifest["template_eligible_for_decision_ranking"] is False
        assert "tables/validator_sensitivity_tests.csv" in names
        assert "tables/llm_vs_template_tests.csv" in names
        assert all(item["path"] in names for item in manifest["figures"])


def test_robustness_json_export_writes_six_canonical_figures(tmp_path) -> None:
    created = export_robustness_figures(
        output_root=tmp_path,
        formats=("json",),
    )
    assert len(created) == 6
    assert all(path.exists() and path.suffix == ".json" for path in created)
