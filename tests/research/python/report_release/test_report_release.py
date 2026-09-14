"""Tests for report-number and source-index contracts."""

from research.python.report_release.build import build_source_index


def test_source_index_has_unique_report_items_and_denominators() -> None:
    source_index = build_source_index()

    assert source_index["report_item"].is_unique
    assert source_index["population_denominator"].notna().all()
    assert "primary_endpoint" in set(source_index["report_item"])
    assert "validator_sensitivity" in set(source_index["report_item"])
