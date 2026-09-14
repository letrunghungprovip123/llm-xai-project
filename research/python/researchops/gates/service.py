from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from research.python.researchops.artifacts.exceptions import ArtifactValidationError
from research.python.researchops.artifacts.ids import new_ulid
from research.python.researchops.contracts.io import canonical_json_sha256, project_root
from research.python.researchops.ops_core.db.models import GateEvaluation, GateResult
from research.python.researchops.ops_core.repositories.protocols import OpsRepository
from research.python.researchops.ops_core.services.audit import record_audit
from research.python.researchops.stage_registry.loader import load_gate_catalog

from .contracts import GateEvaluationDraft


class GateEvaluationError(ArtifactValidationError):
    pass


class GateEvaluationIdentityDrift(GateEvaluationError):
    pass


@dataclass(frozen=True)
class GateEvaluationResult:
    evaluation: GateEvaluation
    projection: GateResult
    created: bool


class GateEvaluationService:
    def __init__(
        self,
        repository: OpsRepository,
        *,
        root: Path | None = None,
    ) -> None:
        self.repository = repository
        self.root = (root or project_root()).resolve()
        self.gate_catalog = {
            item["gate_id"]: item
            for item in load_gate_catalog(self.root)["gates"]
        }

    def record(
        self,
        draft: GateEvaluationDraft,
        *,
        actor: str,
        request_id: str | None = None,
    ) -> GateEvaluationResult:
        if draft.gate_id not in self.gate_catalog:
            raise GateEvaluationError(f"Unknown gate ID: {draft.gate_id}")
        self._validate_scope(draft)
        self._validate_artifact_binding(draft)

        evaluation_key = canonical_json_sha256(draft.identity_payload())
        payload_sha256 = canonical_json_sha256(draft.payload_for_hash())
        existing = self.repository.get_gate_evaluation_by_key(evaluation_key)
        if existing is not None:
            if existing.payload_sha256 != payload_sha256:
                record_audit(
                    self.repository,
                    actor=actor,
                    action="gate.identity_drift_rejected",
                    target_type="gate_evaluation",
                    target_id=existing.id,
                    request_id=request_id,
                    metadata={
                        "evaluation_key": evaluation_key,
                        "existing_payload_sha256": existing.payload_sha256,
                        "observed_payload_sha256": payload_sha256,
                    },
                )
                self.repository.flush()
                raise GateEvaluationIdentityDrift(
                    "Gate evaluation identity already exists with a different payload"
                )
            projection = self._project(existing, draft, actor=actor, request_id=request_id)
            record_audit(
                self.repository,
                actor=actor,
                action="gate.evaluation_reused",
                target_type="gate_evaluation",
                target_id=existing.id,
                request_id=request_id,
                metadata={"evaluation_key": evaluation_key},
            )
            self.repository.flush()
            return GateEvaluationResult(existing, projection, False)

        evaluation = GateEvaluation(
            id=f"gate_eval_{new_ulid()}",
            evaluation_key=evaluation_key,
            payload_sha256=payload_sha256,
            gate_id=draft.gate_id,
            scope_type=draft.scope.type,
            scope_id=draft.scope.id,
            outcome=draft.outcome,
            blocking=draft.blocking,
            severity=draft.severity,
            adapter_id=draft.adapter.id,
            adapter_version=draft.adapter.version,
            policy_id=draft.policy.id,
            policy_version=draft.policy.version,
            source_artifact_id=draft.source.artifact_id,
            source_manifest_sha256=draft.source.manifest_sha256,
            source_contract=draft.source.contract,
            evidence_artifact_id=draft.evidence.artifact_id if draft.evidence else None,
            evidence_manifest_sha256=(
                draft.evidence.manifest_sha256 if draft.evidence else None
            ),
            expected=draft.expected,
            observed=draft.observed,
            checks=[item.model_dump(mode="json") for item in draft.checks],
            limitations=list(draft.limitations),
            source_contracts=list(draft.source_contracts),
            source_evaluation_ids=list(draft.source_evaluation_ids),
            origin_pipeline_run_id=draft.origin_pipeline_run_id,
            origin_stage_run_id=draft.origin_stage_run_id,
            evaluated_at=draft.evaluated_at,
        )
        self.repository.add_gate_evaluation(evaluation)
        self.repository.flush()
        projection = self._project(evaluation, draft, actor=actor, request_id=request_id)
        record_audit(
            self.repository,
            actor=actor,
            action="gate.evaluation_recorded",
            target_type="gate_evaluation",
            target_id=evaluation.id,
            request_id=request_id,
            after_state={
                "gate_id": evaluation.gate_id,
                "scope_type": evaluation.scope_type,
                "scope_id": evaluation.scope_id,
                "outcome": evaluation.outcome,
            },
            metadata={"evaluation_key": evaluation_key},
        )
        self.repository.flush()
        return GateEvaluationResult(evaluation, projection, True)

    def _project(
        self,
        evaluation: GateEvaluation,
        draft: GateEvaluationDraft,
        *,
        actor: str,
        request_id: str | None,
    ) -> GateResult:
        projection = self.repository.get_gate_result(
            draft.gate_id, draft.scope.type, draft.scope.id
        )
        before = None
        if projection is None:
            projection = GateResult(
                id=f"gate_{new_ulid()}",
                gate_id=draft.gate_id,
                scope_type=draft.scope.type,
                scope_id=draft.scope.id,
                status=draft.outcome,
                evaluation_outcome=draft.outcome,
                effective_status=draft.outcome,
                current_evaluation_id=evaluation.id,
                blocking=draft.blocking,
                severity=draft.severity,
                expected=draft.expected,
                observed=draft.observed,
                details={
                    "adapter_id": draft.adapter.id,
                    "adapter_version": draft.adapter.version,
                    "policy_id": draft.policy.id,
                    "policy_version": draft.policy.version,
                    "limitations": list(draft.limitations),
                },
                source_contracts=list(draft.source_contracts),
            )
            self.repository.add_gate_result(projection)
            action = "gate.projection_created"
        else:
            if projection.current_evaluation_id == evaluation.id:
                return projection
            before = {
                "current_evaluation_id": projection.current_evaluation_id,
                "effective_status": projection.effective_status or projection.status,
            }
            self._invalidate_stale_waivers(
                projection,
                new_evaluation_id=evaluation.id,
                actor=actor,
                request_id=request_id,
            )
            projection.current_evaluation_id = evaluation.id
            projection.evaluation_outcome = draft.outcome
            projection.effective_status = draft.outcome
            projection.status = draft.outcome
            projection.blocking = draft.blocking
            projection.severity = draft.severity
            projection.expected = draft.expected
            projection.observed = draft.observed
            projection.details = {
                "adapter_id": draft.adapter.id,
                "adapter_version": draft.adapter.version,
                "policy_id": draft.policy.id,
                "policy_version": draft.policy.version,
                "limitations": list(draft.limitations),
            }
            projection.source_contracts = list(draft.source_contracts)
            action = "gate.projection_updated"
        self.repository.flush()
        record_audit(
            self.repository,
            actor=actor,
            action=action,
            target_type="gate_result",
            target_id=projection.id,
            request_id=request_id,
            before_state=before,
            after_state={
                "current_evaluation_id": evaluation.id,
                "evaluation_outcome": draft.outcome,
                "effective_status": draft.outcome,
            },
        )
        return projection


    def _invalidate_stale_waivers(
        self,
        projection: GateResult,
        *,
        new_evaluation_id: str,
        actor: str,
        request_id: str | None,
    ) -> None:
        """Revoke waivers bound to an evaluation that is no longer current.

        A waiver is a policy decision about one immutable FAILED evaluation. It
        must never silently carry forward when the same gate/scope is evaluated
        again, even when the new outcome is also FAILED.
        """
        now = datetime.now(timezone.utc)
        for waiver in self.repository.list_gate_waivers(
            scope_type=projection.scope_type,
            scope_id=projection.scope_id,
        ):
            if waiver.gate_result_id != projection.id or waiver.status != "ACTIVE":
                continue
            if waiver.evaluation_id == new_evaluation_id:
                continue
            waiver.status = "REVOKED"
            waiver.revoked_at = now
            waiver.revoked_by = actor
            waiver.revocation_reason = (
                "Automatically revoked because the gate current evaluation changed"
            )
            record_audit(
                self.repository,
                actor=actor,
                action="gate.waiver_invalidated",
                target_type="gate_waiver",
                target_id=waiver.id,
                request_id=request_id,
                before_state={
                    "status": "ACTIVE",
                    "evaluation_id": waiver.evaluation_id,
                },
                after_state={
                    "status": "REVOKED",
                    "current_evaluation_id": new_evaluation_id,
                },
            )

    def _validate_artifact_binding(self, draft: GateEvaluationDraft) -> None:
        if draft.source.artifact_id is not None:
            record = self.repository.get_artifact(draft.source.artifact_id)
            if record is None:
                raise GateEvaluationError(
                    f"Source artifact is not registered: {draft.source.artifact_id}"
                )
            if record.manifest_sha256 != draft.source.manifest_sha256:
                raise GateEvaluationError("Source artifact manifest SHA-256 mismatch")
            if record.artifact_type != draft.source.contract:
                raise GateEvaluationError(
                    "Source artifact contract does not match the evaluation source"
                )
        if draft.evidence is not None:
            record = self.repository.get_artifact(draft.evidence.artifact_id)
            if record is None:
                raise GateEvaluationError(
                    f"Evidence artifact is not registered: {draft.evidence.artifact_id}"
                )
            if record.manifest_sha256 != draft.evidence.manifest_sha256:
                raise GateEvaluationError("Evidence artifact manifest SHA-256 mismatch")

    def _validate_scope(self, draft: GateEvaluationDraft) -> None:
        scope = draft.scope
        if scope.type == "artifact" and self.repository.get_artifact(scope.id) is None:
            raise GateEvaluationError(f"Artifact scope does not exist: {scope.id}")
        if scope.type == "release" and self.repository.get_release(scope.id) is None:
            raise GateEvaluationError(f"Release scope does not exist: {scope.id}")
        if scope.type == "pipeline_run" and self.repository.get_pipeline_run(scope.id) is None:
            raise GateEvaluationError(f"Pipeline scope does not exist: {scope.id}")
        if scope.type == "stage_run" and self.repository.get_stage_run(scope.id) is None:
            raise GateEvaluationError(f"Stage scope does not exist: {scope.id}")
        # model_version is an external MLflow identity; Phase 7B adds the resolver.
