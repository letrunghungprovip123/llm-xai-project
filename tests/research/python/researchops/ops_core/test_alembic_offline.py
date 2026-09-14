from pathlib import Path
import subprocess
import sys


def test_initial_migration_renders_offline_sql(tmp_path: Path):
    output = tmp_path / "migration.sql"
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output.write_text(completed.stdout, encoding="utf-8")
    sql = completed.stdout.lower()
    assert "create table artifacts" in sql
    assert "create table pipeline_runs" in sql
    assert "create table audit_events" in sql
    assert "create table orchestration_bindings" in sql
    assert "create table stage_run_outputs" in sql
