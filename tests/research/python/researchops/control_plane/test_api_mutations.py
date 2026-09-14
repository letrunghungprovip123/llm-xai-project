from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

from fastapi.testclient import TestClient

from research.python.researchops.control_plane.app import create_app
from research.python.researchops.control_plane.settings import ControlPlaneSettings
from research.python.researchops.ops_core.db.models import (
    Approval,
    AuditEvent,
    GateEvaluation,
    GateResult,
    OrchestrationBinding,
    PipelineRun,
    ReleaseArtifact,
    StageRun,
    ReleaseRecord,
)
from research.python.researchops.promotion import promotion_policy_sha256


def _headers(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


def test_trigger_run_is_async_and_idempotent(client):
    body = {
        "flow_id": "verify_source_environment",
        "input_artifact_ids": {},
        "parameters": {},
        "reason": "control-plane acceptance",
    }
    first = client.post("/api/v1/runs", json=body, headers=_headers("trigger-1"))
    assert first.status_code == 202, first.text
    assert first.json()["prefect_flow_run_id"].startswith("prefect-submission-")
    assert first.json()["status"] == "RUNNING"
    second = client.post("/api/v1/runs", json=body, headers=_headers("trigger-1"))
    assert second.status_code == 202
    assert second.json()["operation_id"] == first.json()["operation_id"]
    assert second.json()["replayed"] is True
    listing = client.get("/api/v1/operations")
    assert listing.status_code == 200
    assert any(
        item["id"] == first.json()["operation_id"]
        for item in listing.json()["items"]
    )


def test_idempotency_key_payload_drift_is_rejected(client):
    base = {
        "flow_id": "verify_source_environment",
        "input_artifact_ids": {},
        "parameters": {},
        "reason": "first",
    }
    assert client.post("/api/v1/runs", json=base, headers=_headers("drift-key")).status_code == 202
    changed = {**base, "reason": "changed"}
    response = client.post("/api/v1/runs", json=changed, headers=_headers("drift-key"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_CONFLICT"


def test_missing_required_flow_input_is_rejected_before_prefect(client):
    response = client.post(
        "/api/v1/runs",
        json={"flow_id": "train_model_release", "input_artifact_ids": {}, "parameters": {}, "reason": "invalid"},
        headers=_headers("missing-input"),
    )
    assert response.status_code == 412
    assert response.json()["error"]["code"] == "PRECONDITION_FAILED"


def test_approval_decision_enforces_expected_status_and_replays(client, db):
    now = datetime.now(timezone.utc)
    with db() as session, session.begin():
        session.add(Approval(
            id="approval_pending_01J0000000000000000000",
            target_type="release", target_id="release_test_v1", policy="RELEASE",
            status="REQUESTED", requested_by="requester", requested_at=now,
            expires_at=now + timedelta(days=1), details={},
        ))
    body = {"expected_status": "REQUESTED", "reason": "reviewed"}
    first = client.post(
        "/api/v1/approvals/approval_pending_01J0000000000000000000/approve",
        json=body, headers=_headers("approval-1"),
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "APPROVED"
    second = client.post(
        "/api/v1/approvals/approval_pending_01J0000000000000000000/approve",
        json=body, headers=_headers("approval-1"),
    )
    assert second.status_code == 200
    assert second.json()["replayed"] is True


def test_stale_gate_evaluation_blocks_waiver(client):
    response = client.post(
        "/api/v1/gates/gate_result_01J0000000000000000000000/waivers",
        json={
            "evaluation_id": "gate_eval_stale",
            "target_kind": "complete_research_release",
            "policy_id": "complete_research_release_promotion",
            "approval_id": "approval_01J00000000000000000000000",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "reason": "stale",
        },
        headers=_headers("waiver-stale"),
    )
    assert response.status_code == 412
    assert response.json()["error"]["code"] == "PRECONDITION_FAILED"


def test_revoke_waiver_is_idempotent_at_api_boundary(client):
    body = {"reason": "no longer accepted"}
    first = client.post(
        "/api/v1/waivers/waiver_01J000000000000000000000000/revoke",
        json=body, headers=_headers("revoke-1"),
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "REVOKED"
    second = client.post(
        "/api/v1/waivers/waiver_01J000000000000000000000000/revoke",
        json=body, headers=_headers("revoke-1"),
    )
    assert second.status_code == 200
    assert second.json()["replayed"] is True


def test_cancel_run_uses_prefect_binding(client, db):
    now = datetime.now(timezone.utc)
    with db() as session, session.begin():
        session.add(PipelineRun(
            id="run_running_01J000000000000000000000", flow_id="verify_source_environment",
            status="RUNNING", trigger_type="API", requested_by="tester", registry_sha256="b"*64,
            source_commit="a"*40, environment_snapshot_id="env_01J00000000000000000000000",
            idempotency_key="running-key", parameters={}, created_at=now, updated_at=now,
        ))
        session.add(OrchestrationBinding(
            id="binding_running_01J000000000000000000", orchestrator="prefect",
            orchestrator_version="3.7.8", pipeline_run_id="run_running_01J000000000000000000000",
            stage_run_id=None, prefect_flow_run_id="prefect-running", prefect_task_run_id=None,
            deployment_name="verify-source-environment/local", work_pool_name="pool",
            work_queue_name="verification", orchestration_key="e"*64, attempt_number=1,
            binding_metadata={},
        ))
    response = client.post(
        "/api/v1/runs/run_running_01J000000000000000000000/cancel",
        json={"expected_status": "RUNNING", "reason": "operator cancelled"},
        headers=_headers("cancel-1"),
    )
    assert response.status_code == 202, response.text
    assert response.json()["pipeline_run_id"] == "run_running_01J000000000000000000000"


def test_viewer_only_principal_cannot_mutate(app):
    restricted = create_app(
        settings=ControlPlaneSettings(cursor_secret="x"*64, auth_mode="local", local_roles="viewer"),
        composition=app.state.composition,
    )
    with TestClient(restricted) as client:
        response = client.post(
            "/api/v1/runs",
            json={"flow_id": "verify_source_environment", "input_artifact_ids": {}, "parameters": {}, "reason": "denied"},
            headers=_headers("denied-1"),
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"



def _add_passed_gate(session, *, gate_id: str, scope_type: str, scope_id: str, suffix: str) -> None:
    now = datetime.now(timezone.utc)
    evaluation_id = f"gate_eval_{suffix}"
    session.add(GateEvaluation(
        id=evaluation_id,
        evaluation_key=hashlib.sha256(f"evaluation:{gate_id}:{scope_type}:{scope_id}:{suffix}".encode()).hexdigest(),
        payload_sha256=hashlib.sha256(f"payload:{gate_id}:{scope_type}:{scope_id}:{suffix}".encode()).hexdigest(),
        gate_id=gate_id,
        scope_type=scope_type,
        scope_id=scope_id,
        outcome="PASSED",
        blocking=True,
        severity="ERROR",
        adapter_id="test_adapter_v1",
        adapter_version=1,
        policy_id="test_policy",
        policy_version="1",
        source_contract="test_v1",
        expected={"passed": True},
        observed={"passed": True},
        checks=[],
        limitations=[],
        source_contracts=[],
        source_evaluation_ids=[],
        evaluated_at=now,
    ))
    session.add(GateResult(
        id=f"gate_result_{suffix}",
        gate_id=gate_id,
        scope_type=scope_type,
        scope_id=scope_id,
        status="PASSED",
        evaluation_outcome="PASSED",
        effective_status="PASSED",
        current_evaluation_id=evaluation_id,
        blocking=True,
        severity="ERROR",
        expected={},
        observed={},
        details={},
        source_contracts=[],
        created_at=now,
        updated_at=now,
    ))


def _add_approved_promotion(session, *, approval_id: str, target_type: str, target_id: str, policy: str) -> None:
    now = datetime.now(timezone.utc)
    session.add(Approval(
        id=approval_id,
        target_type=target_type,
        target_id=target_id,
        policy=policy,
        status="APPROVED",
        requested_by="promotion-requester",
        requested_at=now,
        decided_by="promotion-approver",
        decided_at=now,
        reason="accepted",
        expires_at=now + timedelta(days=1),
        details={},
    ))


def test_release_promotion_missing_gate_is_rejected_before_prefect(client, db, app):
    release_id = "release_claim_missing_gate"
    approval_id = "approval_release_missing_gate"
    now = datetime.now(timezone.utc)
    with db() as session, session.begin():
        session.add(ReleaseRecord(
            id=release_id,
            release_type="claim_measurement_release",
            status="CANDIDATE",
            manifest_artifact_id="artifact_test_01J00000000000000000000000",
            source_commit="a" * 40,
            limitations=[],
            release_metadata={},
            created_at=now,
        ))
        session.add(ReleaseArtifact(
            release_id=release_id,
            artifact_id="artifact_test_01J00000000000000000000000",
            role="manifest",
            created_at=now,
        ))
        _add_approved_promotion(
            session,
            approval_id=approval_id,
            target_type="release",
            target_id=release_id,
            policy="RELEASE",
        )
    before = len(app.state.composition.prefect_control_gateway.submissions)
    response = client.post(
        f"/api/v1/releases/{release_id}/promotions",
        json={
            "expected_status": "CANDIDATE",
            "target_status": "CERTIFIED",
            "approval_id": approval_id,
            "policy_sha256": promotion_policy_sha256(),
            "reason": "should fail before Prefect",
        },
        headers=_headers("release-promotion-missing-gate"),
    )
    assert response.status_code == 412, response.text
    assert response.json()["error"]["code"] == "PRECONDITION_FAILED"
    assert len(app.state.composition.prefect_control_gateway.submissions) == before


def test_release_promotion_valid_preflight_submits_governed_flow(client, db, app):
    release_id = "release_claim_candidate"
    approval_id = "approval_release_candidate"
    now = datetime.now(timezone.utc)
    with db() as session, session.begin():
        session.add(ReleaseRecord(
            id=release_id,
            release_type="claim_measurement_release",
            status="CANDIDATE",
            manifest_artifact_id="artifact_test_01J00000000000000000000000",
            source_commit="a" * 40,
            limitations=[],
            release_metadata={},
            created_at=now,
        ))
        session.add(ReleaseArtifact(
            release_id=release_id,
            artifact_id="artifact_test_01J00000000000000000000000",
            role="manifest",
            created_at=now,
        ))
        _add_passed_gate(
            session,
            gate_id="CLAIM_MEASUREMENT_RELEASE_READY",
            scope_type="release",
            scope_id=release_id,
            suffix="a1" * 16,
        )
        _add_approved_promotion(
            session,
            approval_id=approval_id,
            target_type="release",
            target_id=release_id,
            policy="RELEASE",
        )
    response = client.post(
        f"/api/v1/releases/{release_id}/promotions",
        json={
            "expected_status": "CANDIDATE",
            "target_status": "CERTIFIED",
            "approval_id": approval_id,
            "policy_sha256": promotion_policy_sha256(),
            "reason": "validated promotion",
        },
        headers=_headers("release-promotion-valid"),
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "RUNNING"
    assert response.json()["target_type"] == "release"
    assert response.json()["target_id"] == release_id
    deployment, parameters, _ = app.state.composition.prefect_control_gateway.submissions[-1]
    assert deployment == "promote-research-release/local"
    assert parameters["parameters"]["release_id"] == release_id


def test_model_promotion_missing_gates_is_rejected_before_prefect(client, db, app):
    target_id = "credit-risk-predictor:1"
    approval_id = "approval_model_missing_gates"
    with db() as session, session.begin():
        _add_approved_promotion(
            session,
            approval_id=approval_id,
            target_type="model_version",
            target_id=target_id,
            policy="MODEL_PROMOTION",
        )
    before = len(app.state.composition.prefect_control_gateway.submissions)
    response = client.post(
        "/api/v1/models/credit-risk-predictor/versions/1/promotions",
        json={
            "approval_id": approval_id,
            "policy_sha256": promotion_policy_sha256(),
            "reason": "missing gates",
        },
        headers=_headers("model-promotion-missing-gates"),
    )
    assert response.status_code == 412, response.text
    assert len(app.state.composition.prefect_control_gateway.submissions) == before


def test_model_promotion_valid_preflight_submits_governed_flow(client, db, app):
    target_id = "credit-risk-predictor:1"
    approval_id = "approval_model_candidate"
    with db() as session, session.begin():
        for index, gate_id in enumerate((
            "MODEL_READY",
            "XAI_QUALITY_READY",
            "MLFLOW_MODEL_REGISTERED",
        )):
            suffix = f"{index + 2}" * 32
            _add_passed_gate(
                session,
                gate_id=gate_id,
                scope_type="model_version",
                scope_id=target_id,
                suffix=suffix,
            )
        _add_approved_promotion(
            session,
            approval_id=approval_id,
            target_type="model_version",
            target_id=target_id,
            policy="MODEL_PROMOTION",
        )
    response = client.post(
        "/api/v1/models/credit-risk-predictor/versions/1/promotions",
        json={
            "approval_id": approval_id,
            "policy_sha256": promotion_policy_sha256(),
            "reason": "validated model promotion",
        },
        headers=_headers("model-promotion-valid"),
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "RUNNING"
    assert response.json()["target_type"] == "model_version"
    assert response.json()["target_id"] == target_id
    deployment, parameters, _ = app.state.composition.prefect_control_gateway.submissions[-1]
    assert deployment == "promote-model-version/local"
    assert parameters["parameters"]["model_name"] == "credit-risk-predictor"
    assert parameters["parameters"]["version"] == "1"



def _add_retry_run(
    session,
    *,
    run_id: str,
    retryable: bool | None,
    with_snapshot: bool = True,
) -> None:
    now = datetime.now(timezone.utc)
    parameters = {}
    if with_snapshot:
        parameters = {
            "marker": "original",
            "__researchops_control": {
                "input_artifact_ids": {},
                "flow_parameters": {"marker": "original"},
            },
        }
    session.add(PipelineRun(
        id=run_id,
        flow_id="verify_source_environment",
        status="FAILED",
        trigger_type="API",
        requested_by="tester",
        registry_sha256="b" * 64,
        source_commit="a" * 40,
        environment_snapshot_id="env_01J00000000000000000000000",
        idempotency_key=f"retry-source-{run_id}",
        parameters=parameters,
        started_at=now,
        ended_at=now,
        created_at=now,
        updated_at=now,
    ))
    session.add(StageRun(
        id=f"stage_{run_id}",
        pipeline_run_id=run_id,
        stage_id="ops.verify_source_environment",
        stage_version=2,
        attempt=1,
        status="FAILED",
        command_snapshot={},
        approval_policy="NONE",
        started_at=now,
        ended_at=now,
        exit_code=75,
        error_type="TransientNetworkError" if retryable else "SchemaContractError",
        error_category="NETWORK" if retryable else "CONTRACT",
        retryable=retryable,
        error_message="fixture failure",
        created_at=now,
        updated_at=now,
    ))


def test_retry_requires_retryable_failure_and_reuses_immutable_snapshot(client, db, app):
    run_id = "run_retryable_01J0000000000000000000"
    with db() as session, session.begin():
        _add_retry_run(session, run_id=run_id, retryable=True)
    response = client.post(
        f"/api/v1/runs/{run_id}/retry",
        json={
            "expected_status": "FAILED",
            "input_artifact_ids": {},
            "parameters": {},
            "reason": "retry transient failure",
        },
        headers=_headers("retry-valid"),
    )
    assert response.status_code == 202, response.text
    assert response.json()["target_type"] == "pipeline_run"
    assert response.json()["target_id"] == run_id
    deployment, parameters, _ = app.state.composition.prefect_control_gateway.submissions[-1]
    assert deployment == "verify-source-environment/local"
    assert parameters["parameters"] == {"marker": "original"}


def test_retry_rejects_nonretryable_failure(client, db, app):
    run_id = "run_nonretryable_01J00000000000000000"
    with db() as session, session.begin():
        _add_retry_run(session, run_id=run_id, retryable=False)
    before = len(app.state.composition.prefect_control_gateway.submissions)
    response = client.post(
        f"/api/v1/runs/{run_id}/retry",
        json={
            "expected_status": "FAILED",
            "input_artifact_ids": {},
            "parameters": {},
            "reason": "must fail closed",
        },
        headers=_headers("retry-nonretryable"),
    )
    assert response.status_code == 412
    assert len(app.state.composition.prefect_control_gateway.submissions) == before


def test_retry_rejects_parameter_drift(client, db):
    run_id = "run_retry_drift_01J000000000000000000"
    with db() as session, session.begin():
        _add_retry_run(session, run_id=run_id, retryable=True)
    response = client.post(
        f"/api/v1/runs/{run_id}/retry",
        json={
            "expected_status": "FAILED",
            "input_artifact_ids": {},
            "parameters": {"marker": "changed"},
            "reason": "drift",
        },
        headers=_headers("retry-drift"),
    )
    assert response.status_code == 412
    assert response.json()["error"]["code"] == "PRECONDITION_FAILED"


def test_retry_rejects_legacy_run_without_snapshot(client, db):
    run_id = "run_retry_legacy_01J00000000000000000"
    with db() as session, session.begin():
        _add_retry_run(session, run_id=run_id, retryable=True, with_snapshot=False)
    response = client.post(
        f"/api/v1/runs/{run_id}/retry",
        json={
            "expected_status": "FAILED",
            "input_artifact_ids": {},
            "parameters": {},
            "reason": "legacy",
        },
        headers=_headers("retry-legacy"),
    )
    assert response.status_code == 412


def test_operation_reconciles_to_terminal_pipeline(client, db):
    body = {
        "flow_id": "verify_source_environment",
        "input_artifact_ids": {},
        "parameters": {},
        "reason": "reconcile operation",
    }
    submitted = client.post(
        "/api/v1/runs", json=body, headers=_headers("operation-reconcile")
    )
    assert submitted.status_code == 202
    operation_id = submitted.json()["operation_id"]
    prefect_id = submitted.json()["prefect_flow_run_id"]
    now = datetime.now(timezone.utc)
    pipeline_id = "run_operation_terminal_01J000000000000000"
    with db() as session, session.begin():
        session.add(PipelineRun(
            id=pipeline_id,
            flow_id="verify_source_environment",
            status="SUCCEEDED",
            trigger_type="API",
            requested_by="local-developer",
            registry_sha256="b" * 64,
            source_commit="a" * 40,
            environment_snapshot_id="env_01J00000000000000000000000",
            idempotency_key="operation-terminal",
            parameters={},
            started_at=now,
            ended_at=now,
            created_at=now,
            updated_at=now,
        ))
        session.add(OrchestrationBinding(
            id="binding_operation_terminal_01J00000000000",
            orchestrator="prefect",
            orchestrator_version="3.7.8",
            pipeline_run_id=pipeline_id,
            stage_run_id=None,
            prefect_flow_run_id=prefect_id,
            prefect_task_run_id=None,
            deployment_name="verify-source-environment/local",
            work_pool_name="pool",
            work_queue_name="verification",
            orchestration_key="f" * 64,
            attempt_number=1,
            binding_metadata={},
        ))
    observed = client.get(f"/api/v1/operations/{operation_id}")
    assert observed.status_code == 200
    assert observed.json()["pipeline_run_id"] == pipeline_id
    assert observed.json()["status"] == "SUCCEEDED"


def test_cancel_replay_survives_pipeline_state_change(client, db):
    now = datetime.now(timezone.utc)
    run_id = "run_cancel_replay_01J000000000000000000"
    with db() as session, session.begin():
        session.add(PipelineRun(
            id=run_id, flow_id="verify_source_environment", status="RUNNING",
            trigger_type="API", requested_by="tester", registry_sha256="b"*64,
            source_commit="a"*40, environment_snapshot_id="env_01J00000000000000000000000",
            idempotency_key="cancel-replay-source", parameters={}, created_at=now, updated_at=now,
        ))
        session.add(OrchestrationBinding(
            id="binding_cancel_replay_01J000000000000000", orchestrator="prefect",
            orchestrator_version="3.7.8", pipeline_run_id=run_id, stage_run_id=None,
            prefect_flow_run_id="prefect-cancel-replay", prefect_task_run_id=None,
            deployment_name="verify-source-environment/local", work_pool_name="pool",
            work_queue_name="verification", orchestration_key="7"*64, attempt_number=1,
            binding_metadata={},
        ))
    body = {"expected_status": "RUNNING", "reason": "cancel once"}
    first = client.post(
        f"/api/v1/runs/{run_id}/cancel", json=body, headers=_headers("cancel-replay")
    )
    assert first.status_code == 202, first.text
    with db() as session, session.begin():
        run = session.get(PipelineRun, run_id)
        run.status = "CANCELLED"
        run.updated_at = datetime.now(timezone.utc)
    second = client.post(
        f"/api/v1/runs/{run_id}/cancel", json=body, headers=_headers("cancel-replay")
    )
    assert second.status_code == 202, second.text
    assert second.json()["operation_id"] == first.json()["operation_id"]
    assert second.json()["replayed"] is True


def test_release_promotion_replay_survives_release_state_change(client, db):
    release_id = "release_claim_replay"
    approval_id = "approval_release_replay"
    now = datetime.now(timezone.utc)
    with db() as session, session.begin():
        session.add(ReleaseRecord(
            id=release_id, release_type="claim_measurement_release", status="CANDIDATE",
            manifest_artifact_id="artifact_test_01J00000000000000000000000",
            source_commit="a" * 40, limitations=[], release_metadata={}, created_at=now,
        ))
        session.add(ReleaseArtifact(
            release_id=release_id, artifact_id="artifact_test_01J00000000000000000000000",
            role="manifest", created_at=now,
        ))
        _add_passed_gate(
            session, gate_id="CLAIM_MEASUREMENT_RELEASE_READY",
            scope_type="release", scope_id=release_id, suffix="e7" * 16,
        )
        _add_approved_promotion(
            session, approval_id=approval_id, target_type="release",
            target_id=release_id, policy="RELEASE",
        )
    body = {
        "expected_status": "CANDIDATE",
        "target_status": "CERTIFIED",
        "approval_id": approval_id,
        "policy_sha256": promotion_policy_sha256(),
        "reason": "promote once",
    }
    first = client.post(
        f"/api/v1/releases/{release_id}/promotions",
        json=body, headers=_headers("release-promotion-replay"),
    )
    assert first.status_code == 202, first.text
    with db() as session, session.begin():
        release = session.get(ReleaseRecord, release_id)
        release.status = "CERTIFIED"
    second = client.post(
        f"/api/v1/releases/{release_id}/promotions",
        json=body, headers=_headers("release-promotion-replay"),
    )
    assert second.status_code == 202, second.text
    assert second.json()["operation_id"] == first.json()["operation_id"]
    assert second.json()["replayed"] is True


def test_approval_mutation_records_audit_with_request_id(client, db):
    now = datetime.now(timezone.utc)
    approval_id = "approval_audit_01J00000000000000000000"
    with db() as session, session.begin():
        session.add(Approval(
            id=approval_id, target_type="release", target_id="release_test_v1",
            policy="RELEASE", status="REQUESTED", requested_by="requester",
            requested_at=now, expires_at=now + timedelta(days=1), details={},
        ))
    response = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"expected_status": "REQUESTED", "reason": "audited approval"},
        headers={**_headers("approval-audit"), "X-Request-ID": "req-approval-audit"},
    )
    assert response.status_code == 200, response.text
    with db() as session:
        events = list(session.query(AuditEvent).filter(AuditEvent.target_id == approval_id))
    assert events
    assert any(event.action == "api.approval_decided" for event in events)
    assert any(event.request_id == "req-approval-audit" for event in events)


def test_blank_reason_and_idempotency_key_are_rejected(client):
    blank_reason = client.post(
        "/api/v1/runs",
        json={
            "flow_id": "verify_source_environment",
            "input_artifact_ids": {},
            "parameters": {},
            "reason": "   ",
        },
        headers=_headers("blank-reason"),
    )
    assert blank_reason.status_code == 422

    blank_key = client.post(
        "/api/v1/runs",
        json={
            "flow_id": "verify_source_environment",
            "input_artifact_ids": {},
            "parameters": {},
            "reason": "valid reason",
        },
        headers={"Idempotency-Key": "   "},
    )
    assert blank_key.status_code == 422


def test_pending_flow_submission_is_recovered_with_same_durable_operation(client, db, app):
    from research.python.researchops.control_plane.commands import canonical_request_sha256
    from research.python.researchops.ops_core.db.models import ApiIdempotencyRequest, ControlOperation

    body = {
        "flow_id": "verify_source_environment",
        "input_artifact_ids": {},
        "parameters": {},
        "reason": "recover pending submission",
    }
    request_id = "api_request_pending_recovery"
    operation_id = "op_pending_recovery"
    with db() as session, session.begin():
        session.add(ApiIdempotencyRequest(
            id=request_id,
            principal_subject="local-developer",
            http_method="POST",
            route_template="/api/v1/runs",
            idempotency_key="recover-pending-flow",
            request_sha256=canonical_request_sha256(body),
            status="PROCESSING",
            response_body={},
        ))
        session.add(ControlOperation(
            id=operation_id,
            operation_type="FLOW_SUBMIT",
            status="PENDING",
            requested_by="local-developer",
            target_type="flow",
            target_id="verify_source_environment",
            request_id="req-crash-window",
            idempotency_request_id=request_id,
            request_payload=body,
            result={},
        ))

    before = len(app.state.composition.prefect_control_gateway.submissions)
    response = client.post(
        "/api/v1/runs",
        json=body,
        headers=_headers("recover-pending-flow"),
    )
    assert response.status_code == 202, response.text
    assert response.json()["operation_id"] == operation_id
    assert len(app.state.composition.prefect_control_gateway.submissions) == before + 1
    with db() as session:
        operation = session.get(ControlOperation, operation_id)
        assert operation is not None
        assert operation.status == "RUNNING"
        assert operation.prefect_flow_run_id is not None


def test_pending_cancel_is_recovered_without_creating_second_operation(client, db, app):
    from research.python.researchops.control_plane.commands import canonical_request_sha256
    from research.python.researchops.ops_core.db.models import ApiIdempotencyRequest, ControlOperation

    run_id = "run_cancel_recovery_01J00000000000000000"
    now = datetime.now(timezone.utc)
    payload = {
        "run_id": run_id,
        "expected_status": "RUNNING",
        "reason": "recover pending cancellation",
    }
    request_id = "api_request_cancel_recovery"
    operation_id = "op_cancel_recovery"
    with db() as session, session.begin():
        session.add(PipelineRun(
            id=run_id,
            flow_id="verify_source_environment",
            status="RUNNING",
            trigger_type="API",
            requested_by="tester",
            registry_sha256="b" * 64,
            source_commit="a" * 40,
            environment_snapshot_id="env_01J00000000000000000000000",
            idempotency_key="cancel-recovery-run",
            parameters={},
            created_at=now,
            updated_at=now,
        ))
        session.add(OrchestrationBinding(
            id="binding_cancel_recovery",
            orchestrator="prefect",
            orchestrator_version="3.7.8",
            pipeline_run_id=run_id,
            stage_run_id=None,
            prefect_flow_run_id="prefect-cancel-recovery",
            prefect_task_run_id=None,
            deployment_name="verify-source-environment/local",
            work_pool_name="pool",
            work_queue_name="verification",
            orchestration_key="f" * 64,
            attempt_number=1,
            binding_metadata={},
        ))
        session.add(ApiIdempotencyRequest(
            id=request_id,
            principal_subject="local-developer",
            http_method="POST",
            route_template="/api/v1/runs/{run_id}/cancel",
            idempotency_key="recover-pending-cancel",
            request_sha256=canonical_request_sha256(payload),
            status="PROCESSING",
            response_body={},
        ))
        session.add(ControlOperation(
            id=operation_id,
            operation_type="FLOW_CANCEL",
            status="PENDING",
            requested_by="local-developer",
            target_type="pipeline_run",
            target_id=run_id,
            prefect_flow_run_id="prefect-cancel-recovery",
            pipeline_run_id=run_id,
            request_id="req-cancel-crash-window",
            idempotency_request_id=request_id,
            request_payload=payload,
            result={},
        ))

    before = len(app.state.composition.prefect_control_gateway.cancellations)
    response = client.post(
        f"/api/v1/runs/{run_id}/cancel",
        json={"expected_status": "RUNNING", "reason": "recover pending cancellation"},
        headers=_headers("recover-pending-cancel"),
    )
    assert response.status_code == 202, response.text
    assert response.json()["operation_id"] == operation_id
    assert len(app.state.composition.prefect_control_gateway.cancellations) == before + 1


def test_successful_promotion_flow_without_decision_fails_closed(client, db):
    from research.python.researchops.ops_core.db.models import ApiIdempotencyRequest, ControlOperation

    now = datetime.now(timezone.utc)
    pipeline_id = "run_promotion_shell_only_01J0000000000000"
    request_id = "api_request_promotion_shell_only"
    operation_id = "op_promotion_shell_only"
    with db() as session, session.begin():
        session.add(PipelineRun(
            id=pipeline_id,
            flow_id="promote_research_release",
            status="SUCCEEDED",
            trigger_type="API",
            requested_by="release-manager",
            registry_sha256="b" * 64,
            source_commit="a" * 40,
            environment_snapshot_id="env_01J00000000000000000000000",
            idempotency_key="promotion-shell-only",
            parameters={},
            started_at=now,
            ended_at=now,
            created_at=now,
            updated_at=now,
        ))
        session.add(ApiIdempotencyRequest(
            id=request_id,
            principal_subject="local-developer",
            http_method="POST",
            route_template="/api/v1/releases/{release_id}/promotions",
            idempotency_key="promotion-shell-only",
            request_sha256="a" * 64,
            status="COMPLETED",
            response_status=202,
            response_body={},
        ))
        session.add(ControlOperation(
            id=operation_id,
            operation_type="RELEASE_PROMOTION",
            status="RUNNING",
            requested_by="local-developer",
            target_type="release",
            target_id="release_shell_only",
            pipeline_run_id=pipeline_id,
            request_id="req-promotion-shell-only",
            idempotency_request_id=request_id,
            request_payload={"promotion_idempotency_key": "missing-decision-key"},
            result={},
            started_at=now,
        ))

    response = client.get(f"/api/v1/operations/{operation_id}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "FAILED"
    assert payload["error_code"] == "PROMOTION_DECISION_MISSING"


def test_operation_listing_uses_bounded_cursor_pagination(client):
    for index in range(2):
        response = client.post(
            "/api/v1/runs",
            json={
                "flow_id": "verify_source_environment",
                "input_artifact_ids": {},
                "parameters": {"sequence": index},
                "reason": f"operation page {index}",
            },
            headers=_headers(f"operation-page-{index}"),
        )
        assert response.status_code == 202, response.text

    first = client.get("/api/v1/operations?limit=1")
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert len(first_payload["items"]) == 1
    assert first_payload["page"]["has_more"] is True
    assert first_payload["page"]["next_cursor"]

    second = client.get(
        "/api/v1/operations",
        params={"limit": 1, "cursor": first_payload["page"]["next_cursor"]},
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["items"]) == 1
    assert second.json()["items"][0]["id"] != first_payload["items"][0]["id"]
