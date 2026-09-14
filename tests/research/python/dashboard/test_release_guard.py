"""Release-guard tests for the certified visualization snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from research.python.common.paths import DEFAULT_PATHS
from research.python.dashboard.data.release_guard import (
    verify_visualization_release,
)
from research.python.dashboard.settings import (
    VISUALIZATION_MANIFEST_PATH,
    VISUALIZATION_VALIDATION_PATH,
)


def test_visualization_release_is_ready_and_fully_verified() -> None:
    result = verify_visualization_release(
        project_root=DEFAULT_PATHS.project_root,
        verify_all_datasets=True,
    )

    assert result.ready is True
    assert result.errors == ()
    assert result.release is not None
    assert result.release.dataset_count == 31
    assert result.release.validation_check_count == 54
    assert result.release.research_question_count == 6
    assert {gate.gate_id for gate in result.release.gates} == {
        "REPORT_WRITING_READY",
        "BASELINE_COMPARISON_READY",
        "VISUALIZATION_DATA_V2_READY",
    }


def test_release_guard_fails_closed_when_visualization_gate_changes(
    tmp_path: Path,
) -> None:
    validation = json.loads(
        VISUALIZATION_VALIDATION_PATH.read_text(encoding="utf-8")
    )
    validation["passed"] = False
    validation["failed_check_count"] = 1
    validation["exit_gate"] = "VISUALIZATION_DATA_V2_INVALID"
    invalid_path = tmp_path / "visualization_validation.json"
    invalid_path.write_text(
        json.dumps(validation, indent=2) + "\n",
        encoding="utf-8",
    )

    result = verify_visualization_release(
        project_root=DEFAULT_PATHS.project_root,
        manifest_path=VISUALIZATION_MANIFEST_PATH,
        validation_path=invalid_path,
        verify_all_datasets=False,
    )

    assert result.ready is False
    assert any("did not pass" in error for error in result.errors)
    assert any("VISUALIZATION_DATA_V2_READY" in error for error in result.errors)
