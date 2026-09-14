from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from research.python.researchops.orchestration.execution.contracts import (
    PipelineExecutionReceipt,
    ReceiptArtifactIdentity,
    StageExecutionResult,
)
from research.python.researchops.orchestration.execution.validation import (
    validate_execution_contracts,
)


def _result() -> StageExecutionResult:
    now = datetime.now(timezone.utc)
    return StageExecutionResult(
        pipeline_run_id="run_1",
        stage_run_id="stage_run_1",
        node_id="verify",
        stage_id="data.audit",
        stage_version=1,
        status="SUCCEEDED",
        attempt=1,
        orchestration_key="a" * 64,
        command=("python3", "-m", "example"),
        started_at=now,
        ended_at=now,
        exit_code=0,
    )


def test_execution_json_schemas_are_current_and_valid():
    report = validate_execution_contracts()
    assert report["passed"] is True, report
    assert {item["contract_id"] for item in report["checked"]} == {
        "stage_execution_result_v1",
        "pipeline_execution_receipt_v1",
    }


def test_pipeline_receipt_validates_against_checked_in_schema():
    identity = ReceiptArtifactIdentity(
        artifact_id="artifact_trained_model_01J00000000000000000000000",
        artifact_type="trained_model",
        manifest_sha256="b" * 64,
    )
    receipt = PipelineExecutionReceipt(
        flow_id="verify_source_environment",
        flow_version=1,
        flow_catalog_sha256="c" * 64,
        stage_registry_sha256="d" * 64,
        prefect_flow_run_id="prefect-flow-1",
        pipeline_run_id="run_1",
        source_commit="e" * 40,
        environment_snapshot_id="env_1",
        terminal_status="SUCCEEDED",
        inputs={"model": identity},
        outputs={"model": identity},
        stages=(_result(),),
    )
    schema = json.loads(
        Path(
            "config/platform/schemas/pipeline_execution_receipt_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    errors = list(
        Draft202012Validator(schema).iter_errors(receipt.model_dump(mode="json"))
    )
    assert errors == []


def test_stage_command_result_references_existing_artifact_strictly():
    from research.python.researchops.orchestration.execution.contracts import (
        StageCommandResult,
    )

    report = StageCommandResult.model_validate(
        {
            "schema_version": "stage_command_result_v1",
            "outputs": {
                "receipt": {
                    "artifact_id": (
                        "artifact_mlflow_registration_receipt_"
                        "01J00000000000000000000000"
                    ),
                    "artifact_type": "mlflow_registration_receipt",
                    "manifest_sha256": "a" * 64,
                    "source_inputs": ["trained_models"],
                }
            },
            "metadata": {"receipt_reused": True},
        }
    )
    assert report.outputs["receipt"].source_inputs == ("trained_models",)
