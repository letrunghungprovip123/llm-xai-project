from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from research.python.researchops.artifacts.exceptions import ArtifactValidationError
from research.python.researchops.gates.orchestration import SemanticGateOrchestrator
from research.python.researchops.ops_core.db.models import (
    ApiIdempotencyRequest,
    ArtifactRecord,
    ControlOperation,
    OrchestrationBinding,
    StageRunOutput,
)
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
from research.python.researchops.ops_core.services.audit import record_audit
from research.python.researchops.orchestration.approvals.service import ApprovalDecisionError, ApprovalService
from research.python.researchops.orchestration.execution.contracts import DiscoveredOutput
from research.python.researchops.orchestration.flow_catalog.loader import load_flow_catalog
from research.python.researchops.orchestration.prefect_adapter.deployments import load_deployment_catalog
from research.python.researchops.promotion import (
    PromotionDecisionError,
    PromotionPolicyService,
    WaiverService,
    promotion_policy_sha256,
)
from research.python.researchops.stage_registry.loader import load_stage_registry

from ..composition import ControlPlaneComposition
from ..contracts.mutations import (
    ApprovalDecisionRequest,
    ArtifactActionRequest,
    ModelPromotionRequest,
    MutationResult,
    OperationAccepted,
    OperationView,
    ReleasePromotionRequest,
    RunCancelRequest,
    RunRetryRequest,
    RunTriggerRequest,
    WaiverGrantRequest,
    WaiverRevokeRequest,
)
from ..errors import (
    DependencyUnavailableError,
    PreconditionFailedError,
    ResourceNotFoundError,
    StateConflictError,
)
from ..security.principal import Principal
from .idempotency import ApiIdempotencyService, canonical_request_sha256
from .operations import ControlOperationService


_TERMINAL_RUN_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED"}


def _operation_view(record: ControlOperation) -> OperationView:
    return OperationView(
        id=record.id,
        operation_type=record.operation_type,
        status=record.status,
        requested_by=record.requested_by,
        target_type=record.target_type,
        target_id=record.target_id,
        prefect_flow_run_id=record.prefect_flow_run_id,
        pipeline_run_id=record.pipeline_run_id,
        promotion_decision_id=record.promotion_decision_id,
        request_id=record.request_id,
        result=dict(record.result or {}),
        error_code=record.error_code,
        error_message=record.error_message,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        updated_at=record.updated_at,
    )


class ControlCommandService:
    def __init__(
        self,
        *,
        session: Session,
        composition: ControlPlaneComposition,
        principal: Principal,
        request_id: str,
    ) -> None:
        self.session = session
        self.composition = composition
        self.principal = principal
        self.request_id = request_id
        self.repository = SqlAlchemyOpsRepository(session)
        self.idempotency = ApiIdempotencyService(session)
        self.operations = ControlOperationService(session)

    def operation(self, operation_id: str, *, reconcile: bool = True) -> OperationView:
        record = self.operations.get(operation_id)
        if record is None:
            raise ResourceNotFoundError("control operation", operation_id)
        if reconcile:
            record = self.operations.reconcile_prefect_binding(record)
            self.session.commit()
        return _operation_view(record)

    def list_operations(self, *, status: str | None = None, requested_by: str | None = None) -> list[OperationView]:
        return [_operation_view(item) for item in self.operations.list(status=status, requested_by=requested_by)]

    def _existing_operation(self, idempotency_request_id: str) -> ControlOperation | None:
        return self.session.scalar(
            select(ControlOperation).where(
                ControlOperation.idempotency_request_id == idempotency_request_id
            )
        )

    def _lookup_operation_replay(
        self,
        *,
        route_template: str,
        idempotency_key: str,
        request_payload: dict[str, Any],
        recover_pending: bool = False,
    ) -> OperationAccepted | None:
        with self.session.begin():
            reservation = self.idempotency.lookup(
                principal_subject=self.principal.subject,
                http_method="POST",
                route_template=route_template,
                idempotency_key=idempotency_key,
                request_payload=request_payload,
                allow_processing_replay=True,
            )
            if reservation is None:
                return None
            operation = self._existing_operation(reservation.record.id)
            if operation is not None:
                # A process can stop after the durable operation is created but
                # before the Prefect response is persisted. The Prefect gateway
                # uses the same server-side idempotency key, so replaying a
                # still-PENDING operation is safe and repairs this crash window.
                if recover_pending and operation.status == "PENDING":
                    return None
                return OperationAccepted(
                    operation_id=operation.id,
                    status=operation.status,
                    target_type=operation.target_type,
                    target_id=operation.target_id,
                    prefect_flow_run_id=operation.prefect_flow_run_id,
                    pipeline_run_id=operation.pipeline_run_id,
                    replayed=True,
                )
            if reservation.record.response_body:
                return OperationAccepted.model_validate(
                    reservation.record.response_body
                ).model_copy(update={"replayed": True})
            raise StateConflictError(
                "Idempotent request has no durable operation",
                {"idempotency_request_id": reservation.record.id},
            )

    def _lookup_mutation_replay(
        self,
        *,
        route_template: str,
        idempotency_key: str,
        request_payload: dict[str, Any],
    ) -> MutationResult | None:
        with self.session.begin():
            reservation = self.idempotency.lookup(
                principal_subject=self.principal.subject,
                http_method="POST",
                route_template=route_template,
                idempotency_key=idempotency_key,
                request_payload=request_payload,
            )
            if reservation is None:
                return None
            if not reservation.record.response_body:
                raise StateConflictError(
                    "Equivalent request is still processing",
                    {"idempotency_request_id": reservation.record.id},
                )
            return MutationResult.model_validate(
                reservation.record.response_body
            ).model_copy(update={"replayed": True})

    def _deployment_name(self, flow_id: str) -> str:
        catalog = load_deployment_catalog()
        for item in catalog.deployments:
            if item.flow_id == flow_id:
                return f"{item.flow_name}/{item.deployment_name}"
        raise StateConflictError("Flow has no governed deployment", {"flow_id": flow_id})

    def _verify_flow_inputs(self, flow_id: str, artifact_ids: dict[str, str]) -> None:
        flow = load_flow_catalog().by_id().get(flow_id)
        if flow is None or flow.status == "PLANNED":
            raise StateConflictError("Flow is not executable", {"flow_id": flow_id})
        expected = {item.name: item for item in flow.inputs}
        unknown = sorted(set(artifact_ids) - set(expected))
        missing = sorted(name for name, binding in expected.items() if binding.required and name not in artifact_ids)
        if unknown or missing:
            raise PreconditionFailedError("Flow input mapping is invalid", {"unknown": unknown, "missing": missing})
        for name, artifact_id in artifact_ids.items():
            verification = self.composition.artifact_store.verify(artifact_id)
            if not verification.passed:
                raise PreconditionFailedError("Input artifact verification failed", {"input": name, "artifact_id": artifact_id, "errors": list(verification.errors)})
            manifest = self.composition.artifact_store.get_manifest(artifact_id)
            if manifest.artifact_type != expected[name].contract:
                raise PreconditionFailedError("Input artifact contract mismatch", {"input": name, "expected": expected[name].contract, "observed": manifest.artifact_type})

    async def _submit_flow(
        self,
        body: RunTriggerRequest,
        *,
        idempotency_key: str,
        route_template: str,
        request_payload: dict[str, Any],
        operation_payload: dict[str, Any] | None = None,
        operation_type: str,
        target_type: str,
        target_id: str,
        requested_action: str,
        submitted_action: str,
    ) -> OperationAccepted:
        if self.composition.prefect_control_gateway is None:
            raise DependencyUnavailableError(
                "prefect", "Prefect mutation gateway is disabled"
            )
        replayed = self._lookup_operation_replay(
            route_template=route_template,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            recover_pending=True,
        )
        if replayed is not None:
            return replayed

        # Artifact-store verification can involve filesystem/S3 I/O. Keep it
        # outside the database transaction so no row locks span a network call.
        self._verify_flow_inputs(body.flow_id, body.input_artifact_ids)

        with self.session.begin():
            reservation = self.idempotency.reserve(
                principal_subject=self.principal.subject,
                http_method="POST",
                route_template=route_template,
                idempotency_key=idempotency_key,
                request_payload=request_payload,
                allow_processing_replay=True,
            )
            if reservation.replayed:
                operation = self._existing_operation(reservation.record.id)
                if operation is None:
                    if reservation.record.response_body:
                        return OperationAccepted.model_validate(
                            reservation.record.response_body
                        ).model_copy(update={"replayed": True})
                    raise StateConflictError(
                        "Idempotent request has no durable operation"
                    )
                if operation.status != "PENDING":
                    return OperationAccepted(
                        operation_id=operation.id,
                        status=operation.status,
                        target_type=operation.target_type,
                        target_id=operation.target_id,
                        prefect_flow_run_id=operation.prefect_flow_run_id,
                        pipeline_run_id=operation.pipeline_run_id,
                        replayed=True,
                    )
                # Recover a durable PENDING operation. Do not create a second
                # operation or audit request; resubmit with Prefect's real
                # idempotency key and persist the returned flow-run identity.
            else:
                operation = self.operations.create(
                    operation_type=operation_type,
                    requested_by=self.principal.subject,
                    target_type=target_type,
                    target_id=target_id,
                    request_id=self.request_id,
                    idempotency_request_id=reservation.record.id,
                    request_payload=operation_payload or request_payload,
                )
                record_audit(
                    self.repository,
                    actor=self.principal.subject,
                    action=requested_action,
                    target_type=target_type,
                    target_id=target_id,
                    request_id=self.request_id,
                    after_state={
                        "operation_id": operation.id,
                        "flow_id": body.flow_id,
                        "status": operation.status,
                    },
                    metadata={"reason": body.reason},
                )

        try:
            submission = await self.composition.prefect_control_gateway.submit_deployment(
                self._deployment_name(body.flow_id),
                parameters={
                    "input_artifact_ids": body.input_artifact_ids,
                    "parameters": body.parameters,
                    "requested_by": self.principal.subject,
                },
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            with self.session.begin():
                operation = self.session.get(ControlOperation, operation.id)
                request_record = self.session.get(
                    ApiIdempotencyRequest, reservation.record.id
                )
                assert operation is not None and request_record is not None
                self.operations.fail(
                    operation,
                    code="PREFECT_SUBMISSION_FAILED",
                    message=str(exc),
                )
                error_body = {
                    "operation_id": operation.id,
                    "status": operation.status,
                }
                self.idempotency.fail(
                    request_record,
                    code="PREFECT_SUBMISSION_FAILED",
                    response_body=error_body,
                    response_status=503,
                )
                record_audit(
                    self.repository,
                    actor=self.principal.subject,
                    action=f"{submitted_action}.failed",
                    target_type=target_type,
                    target_id=target_id,
                    request_id=self.request_id,
                    after_state=error_body,
                )
            raise DependencyUnavailableError(
                "prefect", "Prefect deployment submission failed"
            ) from exc

        with self.session.begin():
            operation = self.session.get(ControlOperation, operation.id)
            request_record = self.session.get(
                ApiIdempotencyRequest, reservation.record.id
            )
            assert operation is not None and request_record is not None
            operation.prefect_flow_run_id = submission.flow_run_id
            operation.result = {
                "deployment_name": submission.deployment_name,
                "prefect_state": submission.state_name,
                "reason": body.reason,
            }
            self.operations.mark_running(operation)
            response = OperationAccepted(
                operation_id=operation.id,
                status=operation.status,
                target_type=operation.target_type,
                target_id=operation.target_id,
                prefect_flow_run_id=operation.prefect_flow_run_id,
            )
            self.idempotency.complete(
                request_record,
                response_status=202,
                response_body=response.model_dump(mode="json"),
                resource_type="control_operation",
                resource_id=operation.id,
            )
            record_audit(
                self.repository,
                actor=self.principal.subject,
                action=submitted_action,
                target_type=target_type,
                target_id=target_id,
                request_id=self.request_id,
                after_state=response.model_dump(mode="json"),
            )
        return response

    async def submit_run(
        self, body: RunTriggerRequest, *, idempotency_key: str
    ) -> OperationAccepted:
        payload = body.model_dump(mode="json")
        return await self._submit_flow(
            body,
            idempotency_key=idempotency_key,
            route_template="/api/v1/runs",
            request_payload=payload,
            operation_type="FLOW_SUBMIT",
            target_type="flow",
            target_id=body.flow_id,
            requested_action="api.flow_submit_requested",
            submitted_action="api.flow_submitted",
        )

    def _flow_binding(self, pipeline_run_id: str) -> OrchestrationBinding:
        binding = self.session.scalar(
            select(OrchestrationBinding)
            .where(
                OrchestrationBinding.pipeline_run_id == pipeline_run_id,
                OrchestrationBinding.orchestrator == "prefect",
                OrchestrationBinding.stage_run_id.is_(None),
            )
            .order_by(OrchestrationBinding.attempt_number.desc())
            .limit(1)
        )
        if binding is None:
            raise StateConflictError("Pipeline run has no Prefect flow binding")
        return binding

    async def cancel_run(self, run_id: str, body: RunCancelRequest, *, idempotency_key: str) -> OperationAccepted:
        if self.composition.prefect_control_gateway is None:
            raise DependencyUnavailableError("prefect", "Prefect mutation gateway is disabled")
        payload = {"run_id": run_id, **body.model_dump(mode="json")}
        replayed = self._lookup_operation_replay(
            route_template="/api/v1/runs/{run_id}/cancel",
            idempotency_key=idempotency_key,
            request_payload=payload,
            recover_pending=True,
        )
        if replayed is not None:
            return replayed
        with self.session.begin():
            run = self.repository.get_pipeline_run(run_id)
            if run is None:
                raise ResourceNotFoundError("pipeline run", run_id)
            if run.status != body.expected_status:
                raise PreconditionFailedError("Pipeline status changed", {"expected": body.expected_status, "observed": run.status})
            if run.status in _TERMINAL_RUN_STATUSES:
                raise StateConflictError("Terminal pipeline cannot be cancelled")
            binding = self._flow_binding(run_id)
            reservation = self.idempotency.reserve(principal_subject=self.principal.subject, http_method="POST", route_template="/api/v1/runs/{run_id}/cancel", idempotency_key=idempotency_key, request_payload=payload, allow_processing_replay=True)
            if reservation.replayed:
                operation = self._existing_operation(reservation.record.id)
                if operation is None:
                    return OperationAccepted.model_validate(
                        reservation.record.response_body
                    ).model_copy(update={"replayed": True})
                if operation.status != "PENDING":
                    return OperationAccepted(
                        operation_id=operation.id,
                        status=operation.status,
                        target_type=operation.target_type,
                        target_id=operation.target_id,
                        prefect_flow_run_id=operation.prefect_flow_run_id,
                        pipeline_run_id=operation.pipeline_run_id,
                        replayed=True,
                    )
            else:
                operation = self.operations.create(
                    operation_type="FLOW_CANCEL",
                    requested_by=self.principal.subject,
                    target_type="pipeline_run",
                    target_id=run_id,
                    request_id=self.request_id,
                    idempotency_request_id=reservation.record.id,
                    request_payload=payload,
                )
                operation.pipeline_run_id = run_id
                operation.prefect_flow_run_id = binding.prefect_flow_run_id
        try:
            result = await self.composition.prefect_control_gateway.cancel_flow_run(binding.prefect_flow_run_id, reason=body.reason)
        except Exception as exc:
            with self.session.begin():
                op = self.session.get(ControlOperation, operation.id); req = self.session.get(ApiIdempotencyRequest, reservation.record.id)
                assert op and req
                self.operations.fail(op, code="PREFECT_CANCEL_FAILED", message=str(exc))
                self.idempotency.fail(req, code="PREFECT_CANCEL_FAILED", response_body={"operation_id": op.id, "status": op.status}, response_status=503)
            raise DependencyUnavailableError("prefect", "Prefect cancellation failed") from exc
        with self.session.begin():
            op = self.session.get(ControlOperation, operation.id); req = self.session.get(ApiIdempotencyRequest, reservation.record.id)
            assert op and req
            op.result = {**result, "reason": body.reason}
            self.operations.mark_running(op)
            response = OperationAccepted(operation_id=op.id, status=op.status, target_type=op.target_type, target_id=op.target_id, prefect_flow_run_id=op.prefect_flow_run_id, pipeline_run_id=op.pipeline_run_id)
            self.idempotency.complete(req, response_status=202, response_body=response.model_dump(mode="json"), resource_type="control_operation", resource_id=op.id)
            record_audit(self.repository, actor=self.principal.subject, action="api.flow_cancel_requested", target_type="pipeline_run", target_id=run_id, request_id=self.request_id, metadata={"reason": body.reason, "operation_id": op.id})
        return response

    async def retry_run(
        self, run_id: str, body: RunRetryRequest, *, idempotency_key: str
    ) -> OperationAccepted:
        request_payload = {"source_run_id": run_id, **body.model_dump(mode="json")}
        replayed = self._lookup_operation_replay(
            route_template="/api/v1/runs/{run_id}/retry",
            idempotency_key=idempotency_key,
            request_payload=request_payload,
        )
        if replayed is not None:
            return replayed
        with self.session.begin():
            run = self.repository.get_pipeline_run(run_id)
            if run is None:
                raise ResourceNotFoundError("pipeline run", run_id)
            if run.status != body.expected_status:
                raise PreconditionFailedError(
                    "Pipeline status changed",
                    {"expected": body.expected_status, "observed": run.status},
                )
            snapshot = dict((run.parameters or {}).get("__researchops_control") or {})
            if not snapshot:
                raise PreconditionFailedError(
                    "Pipeline lacks an immutable retry snapshot",
                    {"run_id": run_id},
                )
            stored_inputs = dict(snapshot.get("input_artifact_ids") or {})
            stored_parameters = dict(snapshot.get("flow_parameters") or {})
            effective_inputs = (
                dict(body.input_artifact_ids)
                if body.input_artifact_ids
                else stored_inputs
            )
            effective_parameters = (
                dict(body.parameters) if body.parameters else stored_parameters
            )
            if effective_inputs != stored_inputs:
                raise PreconditionFailedError(
                    "Retry input artifacts differ from the original run",
                    {"expected": stored_inputs, "observed": effective_inputs},
                )
            if effective_parameters != stored_parameters:
                raise PreconditionFailedError(
                    "Retry parameters differ from the original run",
                    {"expected": stored_parameters, "observed": effective_parameters},
                )
            if run.status == "FAILED":
                failed_stages = [
                    item
                    for item in self.repository.list_stage_runs(run_id)
                    if item.status == "FAILED"
                ]
                if not failed_stages or not any(
                    item.retryable is True for item in failed_stages
                ):
                    raise PreconditionFailedError(
                        "Pipeline failure is not retryable",
                        {
                            "run_id": run_id,
                            "failed_stages": [
                                {
                                    "stage_run_id": item.id,
                                    "stage_id": item.stage_id,
                                    "error_category": item.error_category,
                                    "retryable": item.retryable,
                                }
                                for item in failed_stages
                            ],
                        },
                    )
            flow_id = run.flow_id

        trigger = RunTriggerRequest(
            flow_id=flow_id,
            input_artifact_ids=effective_inputs,
            parameters=effective_parameters,
            reason=body.reason,
        )
        operation_payload = {
            **request_payload,
            "effective_input_artifact_ids": effective_inputs,
            "effective_parameters": effective_parameters,
        }
        return await self._submit_flow(
            trigger,
            idempotency_key=idempotency_key,
            route_template="/api/v1/runs/{run_id}/retry",
            request_payload=request_payload,
            operation_payload=operation_payload,
            operation_type="FLOW_RETRY",
            target_type="pipeline_run",
            target_id=run_id,
            requested_action="api.flow_retry_requested",
            submitted_action="api.flow_retry_submitted",
        )

    def decide_approval(self, approval_id: str, body: ApprovalDecisionRequest, *, decision: str, idempotency_key: str) -> MutationResult:
        payload = {"approval_id": approval_id, "decision": decision, **body.model_dump(mode="json")}
        with self.session.begin():
            reservation = self.idempotency.reserve(principal_subject=self.principal.subject, http_method="POST", route_template=f"/api/v1/approvals/{{approval_id}}/{'approve' if decision == 'APPROVED' else 'reject'}", idempotency_key=idempotency_key, request_payload=payload)
            if reservation.replayed:
                return MutationResult.model_validate(reservation.record.response_body).model_copy(update={"replayed": True})
            approval = self.repository.get_approval(approval_id)
            if approval is None:
                raise ResourceNotFoundError("approval", approval_id)
            if approval.status != body.expected_status:
                raise PreconditionFailedError("Approval status changed", {"expected": body.expected_status, "observed": approval.status})
            if approval.requested_by == self.principal.subject:
                raise StateConflictError("Approval requires separation of duties")
            try:
                record = ApprovalService(self.repository).decide(approval_id, decision=decision, decided_by=self.principal.subject, reason=body.reason)
            except ApprovalDecisionError as exc:
                raise StateConflictError(str(exc)) from exc
            response = MutationResult(resource_type="approval", resource_id=record.id, status=record.status)
            self.idempotency.complete(reservation.record, response_status=200, response_body=response.model_dump(mode="json"), resource_type="approval", resource_id=record.id)
            record_audit(
                self.repository,
                actor=self.principal.subject,
                action="api.approval_decided",
                target_type="approval",
                target_id=record.id,
                request_id=self.request_id,
                after_state={"status": record.status, "decision": decision},
                metadata={"reason": body.reason},
            )
        return response

    def grant_waiver(self, gate_result_id: str, body: WaiverGrantRequest, *, idempotency_key: str) -> MutationResult:
        payload = {"gate_result_id": gate_result_id, **body.model_dump(mode="json")}
        with self.session.begin():
            reservation = self.idempotency.reserve(principal_subject=self.principal.subject, http_method="POST", route_template="/api/v1/gates/{gate_result_id}/waivers", idempotency_key=idempotency_key, request_payload=payload)
            if reservation.replayed:
                return MutationResult.model_validate(reservation.record.response_body).model_copy(update={"replayed": True})
            result = self.repository.get_gate_result_by_id(gate_result_id)
            if result is None:
                raise ResourceNotFoundError("gate result", gate_result_id)
            if result.current_evaluation_id != body.evaluation_id:
                raise PreconditionFailedError("Gate evaluation changed", {"expected": body.evaluation_id, "observed": result.current_evaluation_id})
            approval = self.repository.get_approval(body.approval_id)
            if approval is None:
                raise ResourceNotFoundError("approval", body.approval_id)
            if approval.decided_by != self.principal.subject:
                raise StateConflictError("Authenticated actor did not decide the waiver approval")
            try:
                waiver = WaiverService(self.repository).grant(
                    gate_id=result.gate_id, scope_type=result.scope_type, scope_id=result.scope_id,
                    target_kind=body.target_kind, policy_id=body.policy_id,
                    approval_id=body.approval_id, requested_by=approval.requested_by,
                    decided_by=self.principal.subject, reason=body.reason,
                    expires_at=body.expires_at, request_key=canonical_request_sha256(payload),
                )
            except PromotionDecisionError as exc:
                raise StateConflictError(str(exc)) from exc
            response = MutationResult(resource_type="gate_waiver", resource_id=waiver.id, status=waiver.status, details={"gate_result_id": gate_result_id, "evaluation_id": waiver.evaluation_id})
            self.idempotency.complete(reservation.record, response_status=200, response_body=response.model_dump(mode="json"), resource_type="gate_waiver", resource_id=waiver.id)
        return response

    def revoke_waiver(self, waiver_id: str, body: WaiverRevokeRequest, *, idempotency_key: str) -> MutationResult:
        payload = {"waiver_id": waiver_id, **body.model_dump(mode="json")}
        with self.session.begin():
            reservation = self.idempotency.reserve(principal_subject=self.principal.subject, http_method="POST", route_template="/api/v1/waivers/{waiver_id}/revoke", idempotency_key=idempotency_key, request_payload=payload)
            if reservation.replayed:
                return MutationResult.model_validate(reservation.record.response_body).model_copy(update={"replayed": True})
            try:
                waiver = WaiverService(self.repository).revoke(waiver_id, actor=self.principal.subject, reason=body.reason)
            except PromotionDecisionError as exc:
                raise StateConflictError(str(exc)) from exc
            response = MutationResult(resource_type="gate_waiver", resource_id=waiver.id, status=waiver.status)
            self.idempotency.complete(reservation.record, response_status=200, response_body=response.model_dump(mode="json"), resource_type="gate_waiver", resource_id=waiver.id)
        return response

    def verify_artifact(self, artifact_id: str, body: ArtifactActionRequest, *, idempotency_key: str) -> MutationResult:
        route_template = "/api/v1/artifacts/{artifact_id}/verifications"
        payload = {"artifact_id": artifact_id, **body.model_dump(mode="json")}
        replayed = self._lookup_mutation_replay(
            route_template=route_template,
            idempotency_key=idempotency_key,
            request_payload=payload,
        )
        if replayed is not None:
            return replayed

        with self.session.begin():
            record = self.repository.get_artifact(artifact_id)
            if record is None:
                raise ResourceNotFoundError("artifact", artifact_id)
            if record.manifest_sha256 != body.expected_manifest_sha256:
                raise PreconditionFailedError(
                    "Artifact manifest changed",
                    {
                        "expected": body.expected_manifest_sha256,
                        "observed": record.manifest_sha256,
                    },
                )
            registered_manifest_sha = record.manifest_sha256

        # Store verification may touch S3/MinIO. It is deliberately outside a
        # database transaction; the registered hash is checked again below.
        try:
            verification = self.composition.artifact_store.verify(artifact_id)
        except Exception as exc:
            raise DependencyUnavailableError(
                "artifact_store", "Artifact verification dependency failed"
            ) from exc
        if (
            not verification.passed
            or verification.manifest_sha256 != registered_manifest_sha
        ):
            raise PreconditionFailedError(
                "Artifact verification failed",
                {"errors": list(verification.errors)},
            )

        with self.session.begin():
            reservation = self.idempotency.reserve(
                principal_subject=self.principal.subject,
                http_method="POST",
                route_template=route_template,
                idempotency_key=idempotency_key,
                request_payload=payload,
            )
            if reservation.replayed:
                return MutationResult.model_validate(
                    reservation.record.response_body
                ).model_copy(update={"replayed": True})
            record = self.repository.get_artifact(artifact_id)
            if record is None:
                raise ResourceNotFoundError("artifact", artifact_id)
            if record.manifest_sha256 != registered_manifest_sha:
                raise PreconditionFailedError(
                    "Artifact manifest changed during verification",
                    {
                        "expected": registered_manifest_sha,
                        "observed": record.manifest_sha256,
                    },
                )
            before = {
                "status": record.status,
                "verified_at": (
                    record.verified_at.isoformat() if record.verified_at else None
                ),
            }
            if record.status in {"DRAFT", "UPLOADED"}:
                record.status = "VERIFIED"
            record.verified_at = record.verified_at or datetime.now(timezone.utc)
            record_audit(
                self.repository,
                actor=self.principal.subject,
                action="artifact.verified_via_api",
                target_type="artifact",
                target_id=artifact_id,
                request_id=self.request_id,
                before_state=before,
                after_state={
                    "status": record.status,
                    "manifest_sha256": record.manifest_sha256,
                },
                metadata={"reason": body.reason},
            )
            response = MutationResult(
                resource_type="artifact",
                resource_id=artifact_id,
                status=record.status,
                details={"manifest_sha256": record.manifest_sha256},
            )
            self.idempotency.complete(
                reservation.record,
                response_status=200,
                response_body=response.model_dump(mode="json"),
                resource_type="artifact",
                resource_id=artifact_id,
            )
        return response

    def reevaluate_artifact(self, artifact_id: str, body: ArtifactActionRequest, *, idempotency_key: str) -> MutationResult:
        payload = {"artifact_id": artifact_id, **body.model_dump(mode="json")}
        with self.session.begin():
            reservation = self.idempotency.reserve(principal_subject=self.principal.subject, http_method="POST", route_template="/api/v1/artifacts/{artifact_id}/evaluations", idempotency_key=idempotency_key, request_payload=payload)
            if reservation.replayed:
                return MutationResult.model_validate(reservation.record.response_body).model_copy(update={"replayed": True})
            record = self.repository.get_artifact(artifact_id)
            if record is None:
                raise ResourceNotFoundError("artifact", artifact_id)
            if record.manifest_sha256 != body.expected_manifest_sha256:
                raise PreconditionFailedError("Artifact manifest changed", {"expected": body.expected_manifest_sha256, "observed": record.manifest_sha256})
            if not record.producer_stage_run_id:
                raise StateConflictError("Artifact has no producer stage run")
            stage_run = self.repository.get_stage_run(record.producer_stage_run_id)
            if stage_run is None:
                raise StateConflictError("Artifact producer stage run is missing")
            stage = load_stage_registry().by_id().get(stage_run.stage_id)
            if stage is None:
                raise StateConflictError("Artifact producer stage is no longer governed")
            output_record = self.session.scalar(select(StageRunOutput).where(StageRunOutput.stage_run_id == stage_run.id, StageRunOutput.artifact_id == artifact_id))
            if output_record is None:
                raise StateConflictError("Artifact is not a named output of its producer stage")
            output = DiscoveredOutput(name=output_record.output_name, contract=output_record.contract, artifact_id=artifact_id, manifest_sha256=output_record.manifest_sha256, file_count=1)
            try:
                evaluation = SemanticGateOrchestrator(repository=self.repository, artifact_store=self.composition.artifact_store, actor=self.principal.subject).evaluate_stage_success(stage=stage, outputs=(output,), pipeline_run_id=stage_run.pipeline_run_id, stage_run_id=stage_run.id)
            except (ArtifactValidationError, ValueError) as exc:
                raise StateConflictError(str(exc)) from exc
            response = MutationResult(resource_type="gate_evaluation", resource_id=evaluation.evaluation.id, status=evaluation.evaluation.outcome, details={"artifact_id": artifact_id, "gate_result_id": evaluation.projection.id})
            self.idempotency.complete(reservation.record, response_status=200, response_body=response.model_dump(mode="json"), resource_type="gate_evaluation", resource_id=evaluation.evaluation.id)
            record_audit(self.repository, actor=self.principal.subject, action="artifact.reevaluated_via_api", target_type="artifact", target_id=artifact_id, request_id=self.request_id, metadata={"evaluation_id": evaluation.evaluation.id, "reason": body.reason})
        return response

    async def promote_release(self, release_id: str, body: ReleasePromotionRequest, *, idempotency_key: str) -> OperationAccepted:
        domain_idempotency_key = canonical_request_sha256(
            {"release_id": release_id, **body.model_dump(mode="json")}
        )
        request_payload = {
            "release_id": release_id,
            "promotion_idempotency_key": domain_idempotency_key,
            **body.model_dump(mode="json"),
        }
        replayed = self._lookup_operation_replay(
            route_template="/api/v1/releases/{release_id}/promotions",
            idempotency_key=idempotency_key,
            request_payload=request_payload,
        )
        if replayed is not None:
            return replayed
        observed_policy_sha = promotion_policy_sha256()
        if body.policy_sha256 != observed_policy_sha:
            raise PreconditionFailedError(
                "Promotion policy changed",
                {"expected": body.policy_sha256, "observed": observed_policy_sha},
            )
        with self.session.begin():
            release = self.repository.get_release(release_id)
            if release is None:
                raise ResourceNotFoundError("release", release_id)
            if release.status != body.expected_status:
                raise PreconditionFailedError(
                    "Release status changed",
                    {"expected": body.expected_status, "observed": release.status},
                )
            if self.repository.get_artifact(release.manifest_artifact_id) is None:
                raise PreconditionFailedError(
                    "Release manifest artifact is missing",
                    {"manifest_artifact_id": release.manifest_artifact_id},
                )
            if not self.repository.release_artifact_ids(release_id):
                raise PreconditionFailedError("Release contains no registered artifacts")
            policies = PromotionPolicyService(self.repository)
            try:
                policy = policies.policy_for("release", release.release_type)
                policies.authorize(
                    policy=policy,
                    target_type="release",
                    target_id=release_id,
                    target_kind=release.release_type,
                    current_state=release.status,
                    target_state=body.target_status,
                    approval_id=body.approval_id,
                )
            except PromotionDecisionError as exc:
                raise PreconditionFailedError(
                    "Release promotion preflight failed",
                    {"reason": str(exc)},
                ) from exc
        trigger = RunTriggerRequest(
            flow_id="promote_research_release",
            input_artifact_ids={},
            parameters={
                "release_id": release_id,
                "approval_id": body.approval_id,
                "actor": self.principal.subject,
                "reason": body.reason,
                "idempotency_key": domain_idempotency_key,
                "request_id": self.request_id,
                "expected_status": body.expected_status,
                "target_status": body.target_status,
                "policy_sha256": body.policy_sha256,
            },
            reason=body.reason,
        )
        return await self._submit_flow(
            trigger,
            idempotency_key=idempotency_key,
            route_template="/api/v1/releases/{release_id}/promotions",
            request_payload=request_payload,
            operation_type="RELEASE_PROMOTION",
            target_type="release",
            target_id=release_id,
            requested_action="api.release_promotion_requested",
            submitted_action="api.release_promotion_submitted",
        )

    async def promote_model(self, model_name: str, version: str, body: ModelPromotionRequest, *, idempotency_key: str) -> OperationAccepted:
        domain_idempotency_key = canonical_request_sha256(
            {
                "model_name": model_name,
                "version": version,
                **body.model_dump(mode="json"),
            }
        )
        request_payload = {
            "model_name": model_name,
            "version": version,
            "promotion_idempotency_key": domain_idempotency_key,
            **body.model_dump(mode="json"),
        }
        replayed = self._lookup_operation_replay(
            route_template=(
                "/api/v1/models/{model_name}/versions/{version}/promotions"
            ),
            idempotency_key=idempotency_key,
            request_payload=request_payload,
        )
        if replayed is not None:
            return replayed
        observed_policy_sha = promotion_policy_sha256()
        if body.policy_sha256 != observed_policy_sha:
            raise PreconditionFailedError(
                "Promotion policy changed",
                {"expected": body.policy_sha256, "observed": observed_policy_sha},
            )
        if self.composition.mlflow_gateway is None:
            raise DependencyUnavailableError("mlflow", "MLflow is not configured")
        try:
            versions = self.composition.mlflow_gateway.list_versions(model_name)
        except Exception as exc:
            raise DependencyUnavailableError("mlflow", "MLflow model lookup failed") from exc
        current = next((item for item in versions if str(item.get("version")) == str(version)), None)
        if current is None:
            raise ResourceNotFoundError("model version", f"{model_name}:{version}")
        aliases = {str(item) for item in current.get("aliases", [])}
        if "candidate" not in aliases:
            raise PreconditionFailedError(
                "Only the current candidate may be promoted",
                {"model_name": model_name, "version": version, "aliases": sorted(aliases)},
            )
        tags = dict(current.get("tags") or {})
        if tags.get("researchops.source_manifest_verified") != "PASSED":
            raise PreconditionFailedError(
                "Candidate source manifest is not verified",
                {"model_name": model_name, "version": version},
            )
        target_id = f"{model_name}:{version}"
        with self.session.begin():
            policies = PromotionPolicyService(self.repository)
            try:
                policy = policies.policy_for("model_version", model_name)
                policies.authorize(
                    policy=policy,
                    target_type="model_version",
                    target_id=target_id,
                    target_kind=model_name,
                    current_state="CANDIDATE",
                    target_state=policy.to_state,
                    approval_id=body.approval_id,
                )
            except PromotionDecisionError as exc:
                raise PreconditionFailedError(
                    "Model promotion preflight failed",
                    {"reason": str(exc)},
                ) from exc
        trigger = RunTriggerRequest(
            flow_id="promote_model_version",
            input_artifact_ids={},
            parameters={
                "model_name": model_name,
                "version": version,
                "approval_id": body.approval_id,
                "actor": self.principal.subject,
                "reason": body.reason,
                "idempotency_key": domain_idempotency_key,
                "request_id": self.request_id,
                "policy_sha256": body.policy_sha256,
            },
            reason=body.reason,
        )
        return await self._submit_flow(
            trigger,
            idempotency_key=idempotency_key,
            route_template=(
                "/api/v1/models/{model_name}/versions/{version}/promotions"
            ),
            request_payload=request_payload,
            operation_type="MODEL_PROMOTION",
            target_type="model_version",
            target_id=target_id,
            requested_action="api.model_promotion_requested",
            submitted_action="api.model_promotion_submitted",
        )
