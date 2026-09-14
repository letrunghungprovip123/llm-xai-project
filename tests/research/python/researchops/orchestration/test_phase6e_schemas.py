import json
from pathlib import Path

from jsonschema import Draft202012Validator


def test_phase6e_operational_schemas_are_valid():
    for name in (
        "prefect_ops_reconciliation_v1.schema.json",
        "orchestration_approval_v1.schema.json",
    ):
        payload = json.loads(
            (Path("config/platform/schemas") / name).read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(payload)


def test_reconciliation_report_instance_matches_schema():
    schema = json.loads(
        Path(
            "config/platform/schemas/prefect_ops_reconciliation_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    payload = {
        "schema_version": "prefect_ops_reconciliation_v1",
        "mode": "report-only",
        "passed": True,
        "checked_pipeline_runs": 1,
        "checked_stage_runs": 2,
        "checked_flow_runs": 1,
        "checked_task_runs": 2,
        "issue_count": 1,
        "error_count": 0,
        "warning_count": 1,
        "repaired_count": 0,
        "issues": [
            {
                "code": "FLOW_CATALOG_HASH_MISMATCH",
                "severity": "WARNING",
                "message": "Historical run uses a previous catalog hash.",
                "pipeline_run_id": "pipeline_01J00000000000000000000000",
                "stage_run_id": None,
                "prefect_flow_run_id": "00000000-0000-0000-0000-000000000001",
                "prefect_task_run_id": None,
                "approval_id": None,
                "repairable": False,
                "repaired": False,
            }
        ],
    }
    Draft202012Validator(schema).validate(payload)


def test_complete_live_acceptance_is_session_scoped_and_evidence_backed():
    script = Path(
        "scripts/researchops/prefect_phase6_complete_live_acceptance.sh"
    ).read_text(encoding="utf-8")
    assert (
        "RESEARCHOPS_PHASE5_SOURCE_ARTIFACT_ID for the accepted "
        "trained-model artifact"
    ) in script
    assert '"$PREFECT_CLI" flow-run cancel "$CANCEL_ID"' in script
    assert 'REPORT_DIR="$REPORT_ROOT/$SESSION_ID"' in script
    assert '"acceptance_session": session_id' in script
    assert 'a["stage_attempts"] == b["stage_attempts"]' in script
    assert "PREFECT_APPROVAL_RUN_INPUT_KEY_CONTRACT=PASS" in script
    assert "PREFECT_APPROVAL_INTEGRATION_SMOKE=PASS" in script
    assert script.index("PREFECT_APPROVAL_INTEGRATION_SMOKE=PASS") < script.index(
        "PREFECT_FLOW_IDEMPOTENCY=PASS"
    )
    assert "MLFLOW_REGISTRATION_FLOW_REUSE=PASS" in script
    assert "MLFLOW_PHASE5_CURRENT_STATE_ACCEPTANCE=PASS" in script
    assert "MLFLOW_PHASE5_REGRESSION=PASS" not in script
    assert "PATCH_BATCH_0062_0064_LIVE_ACCEPTANCE=PASS" in script
    assert "failure.json" in script
    assert "SKIPPED_BY_POLICY" not in script


def test_stranded_cleanup_is_fixture_scoped_and_never_mutates_databases_directly():
    script = Path(
        "scripts/researchops/prefect_phase6_cleanup_stranded_acceptance.sh"
    ).read_text(encoding="utf-8")
    assert 'flow_id" != "prefect_approval_acceptance_fixture' in script
    assert '"$PREFECT_CLI" flow-run cancel "$flow_run_id"' in script
    assert '"direct_database_mutation": False' in script
    assert "docker compose down -v" not in script
