from sqlalchemy import LargeBinary
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from research.python.researchops.ops_core.db.base import Base
from research.python.researchops.ops_core.db import models  # noqa: F401


def test_expected_tables_are_registered():
    assert set(Base.metadata.tables) == {
        "environment_snapshots",
        "pipeline_runs",
        "pipeline_run_receipts",
        "orchestration_bindings",
        "stage_runs",
        "stage_run_outputs",
        "run_events",
        "approvals",
        "artifacts",
        "artifact_files",
        "lineage_edges",
        "releases",
        "release_artifacts",
        "gate_evaluations",
        "gate_results",
        "gate_waivers",
        "promotion_decisions",
        "api_idempotency_requests",
        "control_operations",
        "audit_events",
    }


def test_schema_compiles_for_postgresql():
    rendered = "\n".join(
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for table in Base.metadata.sorted_tables
    )
    assert "CREATE TABLE artifacts" in rendered
    assert "CREATE TABLE pipeline_runs" in rendered
    assert "CREATE TABLE orchestration_bindings" in rendered
    assert "CREATE TABLE pipeline_run_receipts" in rendered
    assert "CREATE TABLE stage_run_outputs" in rendered
    assert "JSONB" in rendered


def test_no_artifact_bytes_are_stored_in_database():
    for table in Base.metadata.tables.values():
        assert all(not isinstance(column.type, LargeBinary) for column in table.columns)
