from __future__ import annotations

import json
from pathlib import Path

from research.python.researchops.mlflow_tracking.reporting import write_json_report


def test_write_json_report_is_canonical_atomic_and_leaves_no_temp_file(tmp_path: Path):
    target = tmp_path / "nested" / "report.json"
    write_json_report(target, {"z": 1, "a": {"value": True}})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "a": {"value": True},
        "z": 1,
    }
    assert target.read_text(encoding="utf-8").endswith("\n")
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_write_json_report_replaces_existing_document(tmp_path: Path):
    target = tmp_path / "report.json"
    target.write_text('{"old": true}\n', encoding="utf-8")

    write_json_report(target, {"new": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
