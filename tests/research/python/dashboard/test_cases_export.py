"""Archive export tests for Page 6 Case Explorer."""

from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZipFile

from research.python.dashboard.data.repository import DashboardRepository
from research.python.dashboard.export.case_figures import build_case_archive, case_figures
from research.python.dashboard.settings import (
    DEFAULT_CASE_EVIDENCE,
    DEFAULT_CASE_MATRIX_METRIC,
    DEFAULT_CASE_MODEL,
)


def test_case_archive_is_privacy_preserving_and_complete() -> None:
    repository = DashboardRepository()
    case_id = int(repository.case_catalog().iloc[0]["case_id"])
    payload = build_case_archive(
        case_id=case_id,
        model_id=DEFAULT_CASE_MODEL,
        evidence_level=DEFAULT_CASE_EVIDENCE,
        metric_id=DEFAULT_CASE_MATRIX_METRIC,
    )

    with ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "tables/case_summary.csv" in names
        assert "tables/case_generations_24_rows.csv" in names
        assert "tables/case_evidence_packages_6_rows.csv" in names
        assert "tables/candidate_v4_pair.csv" in names
        assert "tables/llm_template_pair.csv" in names
        assert "case_export_manifest.json" in names
        manifest = json.loads(archive.read("case_export_manifest.json"))

    assert manifest["case_id"] == case_id
    assert manifest["candidate_role"] == "primary"
    assert manifest["v4_role"] == "sensitivity_only"
    assert manifest["template_is_fourth_llm"] is False
    assert manifest["raw_applicant_record_included"] is False
    assert manifest["direct_personal_identifier_included"] is False
    assert len(manifest["figures"]) == 5


def test_case_figure_registry_builds_five_certified_figures() -> None:
    figures = case_figures()
    assert len(figures) == 5
    assert all(figure.layout.meta["release"] == "visualization-data-v2" for figure in figures.values())
