from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session

from research.python.researchops.contracts.io import canonical_json_sha256, project_root
from research.python.researchops.orchestration.flow_catalog.compiler import compile_payload as compile_flow_catalog
from research.python.researchops.orchestration.flow_catalog.loader import load_flow_catalog
from research.python.researchops.orchestration.prefect_adapter.deployments import (
    deployment_lock_matches,
    load_deployment_catalog,
)
from research.python.researchops.promotion.contracts import (
    load_promotion_policies,
    promotion_policy_sha256,
)
from research.python.researchops.stage_registry.compiler import compile_payload as compile_stage_registry
from research.python.researchops.stage_registry.loader import load_gate_catalog, load_stage_registry

from ..composition import ControlPlaneComposition
from ..contracts.common import CursorPage, PageInfo
from ..contracts.mutations import OperationView
from ..contracts.resources import (
    ApprovalView,
    ArtifactDetail,
    ArtifactFileView,
    ArtifactSummary,
    CapabilityResponse,
    DependencyState,
    GateEvaluationView,
    GateSummary,
    HealthResponse,
    LineageEdgeView,
    LineageGraph,
    LineageNode,
    ModelVersionView,
    PromotionDecisionView,
    ReadinessResponse,
    RegistryItem,
    ReleaseArtifactView,
    ReleaseDetail,
    ReleaseSummary,
    RunDetail,
    RunEventView,
    RunSummary,
    StageRunView,
    VersionResponse,
)
from ..errors import DependencyUnavailableError, ResourceNotFoundError
from ..settings import ControlPlaneSettings
from .cursor import CursorCodec, CursorPosition
from .repository import SqlAlchemyOpsReadRepository


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_state(root: Path) -> tuple[str, bool]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip())
        return commit, dirty
    except Exception:
        return "unknown", True


def _database_revision(session: Session) -> str | None:
    try:
        return session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except Exception:
        return None


def _expected_alembic_head(root: Path) -> str | None:
    config = Config(str(root / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


class ReadQueryService:
    def __init__(self, repository: SqlAlchemyOpsReadRepository, codec: CursorCodec) -> None:
        self.repository = repository
        self.codec = codec

    def _position(self, cursor: str | None, *, resource: str, filters: dict[str, Any]) -> tuple[CursorPosition | None, str]:
        filters_hash = self.codec.filters_sha256(filters)
        position = self.codec.decode(cursor, resource=resource, filters_sha256=filters_hash) if cursor else None
        return position, filters_hash

    def _page(self, *, items: list, has_more: bool, limit: int, resource: str, filters_hash: str, position_of) -> CursorPage:
        next_cursor = None
        if has_more and items:
            next_cursor = self.codec.encode(resource=resource, position=position_of(items[-1]), filters_sha256=filters_hash)
        return CursorPage(items=items, page=PageInfo(limit=limit, has_more=has_more, next_cursor=next_cursor))

    @staticmethod
    def run_summary(item) -> RunSummary:
        return RunSummary(
            id=item.id, flow_id=item.flow_id, status=item.status,
            trigger_type=item.trigger_type, requested_by=item.requested_by,
            source_commit=item.source_commit, created_at=item.created_at,
            started_at=item.started_at, ended_at=item.ended_at, updated_at=item.updated_at,
        )

    def search_runs(self, *, limit: int, cursor: str | None, **filters: Any) -> CursorPage[RunSummary]:
        clean = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in filters.items() if value is not None}
        position, filters_hash = self._position(cursor, resource="runs", filters=clean)
        page = self.repository.search_runs(limit=limit, position=position, **filters)
        items = [self.run_summary(item) for item in page.items]
        return self._page(
            items=items, has_more=page.has_more, limit=limit, resource="runs", filters_hash=filters_hash,
            position_of=lambda item: CursorPosition(item.created_at, item.id),
        )

    @staticmethod
    def operation_view(item) -> OperationView:
        return OperationView(
            id=item.id,
            operation_type=item.operation_type,
            status=item.status,
            requested_by=item.requested_by,
            target_type=item.target_type,
            target_id=item.target_id,
            prefect_flow_run_id=item.prefect_flow_run_id,
            pipeline_run_id=item.pipeline_run_id,
            promotion_decision_id=item.promotion_decision_id,
            request_id=item.request_id,
            result=dict(item.result or {}),
            error_code=item.error_code,
            error_message=item.error_message,
            created_at=item.created_at,
            started_at=item.started_at,
            completed_at=item.completed_at,
            updated_at=item.updated_at,
        )

    def search_operations(
        self,
        *,
        limit: int,
        cursor: str | None,
        **filters: Any,
    ) -> CursorPage[OperationView]:
        clean = {key: value for key, value in filters.items() if value is not None}
        position, filters_hash = self._position(
            cursor, resource="operations", filters=clean
        )
        page = self.repository.search_operations(
            limit=limit, position=position, **filters
        )
        items = [self.operation_view(item) for item in page.items]
        return self._page(
            items=items,
            has_more=page.has_more,
            limit=limit,
            resource="operations",
            filters_hash=filters_hash,
            position_of=lambda item: CursorPosition(item.created_at, item.id),
        )

    def get_run(self, run_id: str) -> RunDetail:
        item = self.repository.get_run(run_id)
        if item is None:
            raise ResourceNotFoundError("pipeline run", run_id)
        stages = self.repository.stage_runs(run_id)
        counts: dict[str, int] = {"total": len(stages)}
        for stage in stages:
            key = stage.status.lower()
            counts[key] = counts.get(key, 0) + 1
        binding = self.repository.run_prefect_binding(run_id)
        prefect = None
        if binding is not None:
            prefect = {
                "flow_run_id": binding.prefect_flow_run_id,
                "deployment_name": binding.deployment_name,
                "orchestration_key": binding.orchestration_key,
                "attempt_number": binding.attempt_number,
            }
        return RunDetail(
            **self.run_summary(item).model_dump(), registry_sha256=item.registry_sha256,
            environment_snapshot_id=item.environment_snapshot_id, idempotency_key=item.idempotency_key,
            parameters=item.parameters, error_summary=item.error_summary, stage_counts=counts, prefect=prefect,
        )

    def run_stages(self, run_id: str) -> list[StageRunView]:
        self.get_run(run_id)
        return [
            StageRunView(
                id=item.id, pipeline_run_id=item.pipeline_run_id, stage_id=item.stage_id,
                stage_version=item.stage_version, attempt=item.attempt, status=item.status,
                approval_policy=item.approval_policy, started_at=item.started_at, ended_at=item.ended_at,
                exit_code=item.exit_code, error_type=item.error_type, error_message=item.error_message,
            )
            for item in self.repository.stage_runs(run_id)
        ]

    def run_events(self, run_id: str) -> list[RunEventView]:
        self.get_run(run_id)
        return [
            RunEventView(
                id=item.id, pipeline_run_id=item.pipeline_run_id, stage_run_id=item.stage_run_id,
                event_type=item.event_type, payload=item.payload, occurred_at=item.occurred_at,
            )
            for item in self.repository.run_events(run_id)
        ]

    @staticmethod
    def artifact_summary(item) -> ArtifactSummary:
        return ArtifactSummary(
            id=item.id, artifact_type=item.artifact_type, schema_version=item.schema_version,
            status=item.status, manifest_sha256=item.manifest_sha256,
            producer_stage_run_id=item.producer_stage_run_id, source_commit=item.source_commit,
            created_at=item.created_at, verified_at=item.verified_at, certified_at=item.certified_at,
            limitations=item.limitations,
        )

    def search_artifacts(self, *, limit: int, cursor: str | None, **filters: Any) -> CursorPage[ArtifactSummary]:
        clean = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in filters.items() if value is not None}
        position, filters_hash = self._position(cursor, resource="artifacts", filters=clean)
        page = self.repository.search_artifacts(limit=limit, position=position, **filters)
        items = [self.artifact_summary(item) for item in page.items]
        return self._page(
            items=items, has_more=page.has_more, limit=limit, resource="artifacts", filters_hash=filters_hash,
            position_of=lambda item: CursorPosition(item.created_at, item.id),
        )

    def get_artifact(self, artifact_id: str) -> ArtifactDetail:
        item = self.repository.get_artifact(artifact_id)
        if item is None:
            raise ResourceNotFoundError("artifact", artifact_id)
        return ArtifactDetail(
            **self.artifact_summary(item).model_dump(), environment_snapshot_id=item.environment_snapshot_id,
            metadata=item.artifact_metadata,
        )

    def artifact_files(self, artifact_id: str) -> list[ArtifactFileView]:
        self.get_artifact(artifact_id)
        return [
            ArtifactFileView(
                id=item.id, relative_path=item.relative_path, sha256=item.sha256,
                size_bytes=item.size_bytes, row_count=item.row_count, column_count=item.column_count,
                media_type=item.media_type, download_available=False,
            )
            for item in self.repository.artifact_files(artifact_id)
        ]

    def artifact_lineage(self, artifact_id: str, *, direction: str, depth: int, max_nodes: int) -> LineageGraph:
        self.get_artifact(artifact_id)
        visited = {artifact_id}
        frontier = deque([(artifact_id, 0)])
        truncated = False
        while frontier:
            current, level = frontier.popleft()
            if level >= depth:
                continue
            neighbours: list[str] = []
            if direction in {"ancestors", "both"}:
                neighbours.extend(self.repository.direct_parents(current))
            if direction in {"descendants", "both"}:
                neighbours.extend(self.repository.direct_children(current))
            for neighbour in sorted(set(neighbours)):
                if neighbour in visited:
                    continue
                if len(visited) >= max_nodes:
                    truncated = True
                    frontier.clear()
                    break
                visited.add(neighbour)
                frontier.append((neighbour, level + 1))
        artifacts = self.repository.artifacts_by_ids(visited)
        edges = [
            edge for edge in self.repository.lineage_edges(visited)
            if edge.parent_artifact_id in visited and edge.child_artifact_id in visited
        ]
        return LineageGraph(
            root_artifact_id=artifact_id,
            nodes=[
                LineageNode(
                    artifact_id=item.id, artifact_type=item.artifact_type,
                    schema_version=item.schema_version, status=item.status,
                    manifest_sha256=item.manifest_sha256,
                )
                for item in artifacts
            ],
            edges=[
                LineageEdgeView(
                    parent_artifact_id=item.parent_artifact_id,
                    child_artifact_id=item.child_artifact_id,
                    relationship_type=item.relationship_type,
                )
                for item in edges
            ],
            truncated=truncated,
        )

    def _waiver_payload(self, item) -> dict[str, Any] | None:
        waiver = self.repository.active_waiver(item.id, item.current_evaluation_id)
        if waiver is None:
            return None
        return {
            "id": waiver.id, "status": waiver.status, "evaluation_id": waiver.evaluation_id,
            "policy_id": waiver.policy_id, "approval_id": waiver.approval_id,
            "expires_at": waiver.expires_at.isoformat(), "reason": waiver.reason,
        }

    def gate_summary(self, item) -> GateSummary:
        return GateSummary(
            id=item.id, gate_id=item.gate_id, scope_type=item.scope_type, scope_id=item.scope_id,
            status=item.status, evaluation_outcome=item.evaluation_outcome,
            effective_status=item.effective_status, current_evaluation_id=item.current_evaluation_id,
            blocking=item.blocking, severity=item.severity, updated_at=item.updated_at,
            waiver=self._waiver_payload(item),
        )

    def search_gates(self, *, limit: int, cursor: str | None, **filters: Any) -> CursorPage[GateSummary]:
        clean = {key: value for key, value in filters.items() if value is not None}
        position, filters_hash = self._position(cursor, resource="gates", filters=clean)
        page = self.repository.search_gates(limit=limit, position=position, **filters)
        items = [self.gate_summary(item) for item in page.items]
        return self._page(
            items=items, has_more=page.has_more, limit=limit, resource="gates", filters_hash=filters_hash,
            position_of=lambda item: CursorPosition(item.updated_at, item.id),
        )

    def get_gate(self, gate_result_id: str) -> GateSummary:
        item = self.repository.get_gate_result_by_id(gate_result_id)
        if item is None:
            raise ResourceNotFoundError("gate result", gate_result_id)
        return self.gate_summary(item)

    @staticmethod
    def evaluation_view(item) -> GateEvaluationView:
        return GateEvaluationView(
            id=item.id, evaluation_key=item.evaluation_key, payload_sha256=item.payload_sha256,
            gate_id=item.gate_id, scope_type=item.scope_type, scope_id=item.scope_id,
            outcome=item.outcome, blocking=item.blocking, severity=item.severity,
            adapter_id=item.adapter_id, adapter_version=item.adapter_version,
            policy_id=item.policy_id, policy_version=item.policy_version,
            source_artifact_id=item.source_artifact_id, source_manifest_sha256=item.source_manifest_sha256,
            evidence_artifact_id=item.evidence_artifact_id, evidence_manifest_sha256=item.evidence_manifest_sha256,
            source_contract=item.source_contract, expected=item.expected, observed=item.observed,
            checks=item.checks, limitations=item.limitations, source_contracts=item.source_contracts,
            source_evaluation_ids=item.source_evaluation_ids, evaluated_at=item.evaluated_at,
        )

    def gate_history(self, gate_result_id: str) -> list[GateEvaluationView]:
        gate = self.repository.get_gate_result_by_id(gate_result_id)
        if gate is None:
            raise ResourceNotFoundError("gate result", gate_result_id)
        return [self.evaluation_view(item) for item in self.repository.gate_history(gate.gate_id, gate.scope_type, gate.scope_id)]

    def get_evaluation(self, evaluation_id: str) -> GateEvaluationView:
        item = self.repository.get_gate_evaluation(evaluation_id)
        if item is None:
            raise ResourceNotFoundError("gate evaluation", evaluation_id)
        return self.evaluation_view(item)

    def scope_gates(self, scope_type: str, scope_id: str) -> list[GateSummary]:
        return [self.gate_summary(item) for item in self.repository.scope_gates(scope_type, scope_id)]

    @staticmethod
    def approval_view(item) -> ApprovalView:
        return ApprovalView(
            id=item.id, target_type=item.target_type, target_id=item.target_id, policy=item.policy,
            status=item.status, requested_by=item.requested_by, requested_at=item.requested_at,
            decided_by=item.decided_by, decided_at=item.decided_at, reason=item.reason,
            expires_at=item.expires_at, pipeline_run_id=item.pipeline_run_id,
            node_id=item.node_id, stage_id=item.stage_id, details=item.details,
        )

    def search_approvals(self, *, limit: int, cursor: str | None, **filters: Any) -> CursorPage[ApprovalView]:
        clean = {key: value for key, value in filters.items() if value is not None}
        position, filters_hash = self._position(cursor, resource="approvals", filters=clean)
        page = self.repository.search_approvals(limit=limit, position=position, **filters)
        items = [self.approval_view(item) for item in page.items]
        return self._page(
            items=items, has_more=page.has_more, limit=limit, resource="approvals", filters_hash=filters_hash,
            position_of=lambda item: CursorPosition(item.requested_at, item.id),
        )

    def get_approval(self, approval_id: str) -> ApprovalView:
        item = self.repository.get_approval(approval_id)
        if item is None:
            raise ResourceNotFoundError("approval", approval_id)
        return self.approval_view(item)

    @staticmethod
    def release_summary(item) -> ReleaseSummary:
        return ReleaseSummary(
            id=item.id, release_type=item.release_type, status=item.status,
            manifest_artifact_id=item.manifest_artifact_id, source_commit=item.source_commit,
            parent_release_id=item.parent_release_id, limitations=item.limitations,
            created_at=item.created_at, promoted_at=item.promoted_at, superseded_at=item.superseded_at,
        )

    def search_releases(self, *, limit: int, cursor: str | None, **filters: Any) -> CursorPage[ReleaseSummary]:
        clean = {key: value for key, value in filters.items() if value is not None}
        position, filters_hash = self._position(cursor, resource="releases", filters=clean)
        page = self.repository.search_releases(limit=limit, position=position, **filters)
        items = [self.release_summary(item) for item in page.items]
        return self._page(
            items=items, has_more=page.has_more, limit=limit, resource="releases", filters_hash=filters_hash,
            position_of=lambda item: CursorPosition(item.created_at, item.id),
        )

    def get_release(self, release_id: str) -> ReleaseDetail:
        item = self.repository.get_release(release_id)
        if item is None:
            raise ResourceNotFoundError("release", release_id)
        try:
            policy = load_promotion_policies().for_target("release", item.release_type)
            required = list(policy.required_gates)
            policy_id = policy.policy_id
            policy_sha = promotion_policy_sha256()
        except ValueError:
            required, policy_id, policy_sha = [], None, None
        observed = [gate.gate_id for gate in self.repository.scope_gates("release", release_id)]
        return ReleaseDetail(
            **self.release_summary(item).model_dump(), metadata=item.release_metadata,
            required_gates=required, observed_gates=sorted(observed),
            missing_gates=sorted(set(required) - set(observed)), policy_id=policy_id, policy_sha256=policy_sha,
        )

    def release_artifacts(self, release_id: str) -> list[ReleaseArtifactView]:
        self.get_release(release_id)
        return [
            ReleaseArtifactView(
                release_id=item.release_id, artifact_id=item.artifact_id, role=item.role, created_at=item.created_at,
            )
            for item in self.repository.release_artifacts(release_id)
        ]

    @staticmethod
    def promotion_view(item) -> PromotionDecisionView:
        return PromotionDecisionView(
            id=item.id, target_type=item.target_type, target_id=item.target_id,
            target_kind=item.target_kind, policy_id=item.policy_id, policy_version=item.policy_version,
            policy_sha256=item.policy_sha256, expected_state=item.expected_state,
            target_state=item.target_state, decision=item.decision, execution_status=item.execution_status,
            requested_by=item.requested_by, executed_by=item.executed_by,
            approval_id=item.approval_id, reason=item.reason, created_at=item.created_at,
            executed_at=item.executed_at,
        )

    def promotion_decisions(self, target_type: str, target_id: str) -> list[PromotionDecisionView]:
        return [self.promotion_view(item) for item in self.repository.promotion_decisions(target_type, target_id)]


class SystemQueryService:
    def __init__(self, settings: ControlPlaneSettings, composition: ControlPlaneComposition) -> None:
        self.settings = settings
        self.composition = composition
        self.root = project_root().resolve()

    def health(self) -> HealthResponse:
        return HealthResponse(service=self.settings.service_name)

    def version(self) -> VersionResponse:
        stage_lock = compile_stage_registry(self.root)
        flow_lock = compile_flow_catalog(self.root)
        gate_hash = _hash_file(self.root / "config/platform/gate_catalog_v1.json")
        commit, dirty = _git_state(self.root)
        with self.composition.session_factory() as session:
            database_revision = _database_revision(session)
        return VersionResponse(
            service=self.settings.service_name, api_version=self.settings.api_version,
            git_commit=commit, git_dirty=dirty, alembic_head=_expected_alembic_head(self.root),
            database_revision=database_revision,
            stage_registry_sha256=str(stage_lock["registry_sha256"]),
            flow_catalog_sha256=str(flow_lock["catalog_sha256"]),
            gate_catalog_sha256=gate_hash, promotion_policy_sha256=promotion_policy_sha256(),
            prefect_expected_version="3.7.8", mlflow_expected_version="3.14.0",
        )

    def capabilities(self) -> CapabilityResponse:
        return CapabilityResponse(
            auth_mode=self.settings.auth_mode, artifact_profile=self.composition.artifact_profile,
            prefect_enabled=self.composition.prefect_gateway is not None,
            mlflow_enabled=self.composition.mlflow_gateway is not None,
            mutation_api_enabled=self.composition.prefect_control_gateway is not None,
        )

    async def readiness(self) -> ReadinessResponse:
        external_timeout = self.settings.dependency_timeout_seconds
        critical_timeout = self.settings.critical_dependency_timeout_seconds

        async def run_sync_probe(
            probe,
            *,
            failure_status: str,
            timeout_seconds: float,
            detail_from_result=None,
        ) -> DependencyState:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(probe),
                    timeout=timeout_seconds,
                )
                detail = detail_from_result(result) if detail_from_result else None
                return DependencyState(status="READY", detail=detail)
            except TimeoutError:
                return DependencyState(
                    status=failure_status,
                    detail=f"timeout after {timeout_seconds:g}s",
                )
            except Exception as exc:
                return DependencyState(status=failure_status, detail=type(exc).__name__)

        async def run_async_probe(probe, *, disabled: bool = False) -> DependencyState:
            if disabled:
                return DependencyState(status="DISABLED")
            try:
                report = await asyncio.wait_for(probe(), timeout=external_timeout)
                return DependencyState(
                    status="READY" if report.get("passed") else "DEGRADED",
                )
            except TimeoutError:
                return DependencyState(
                    status="DEGRADED",
                    detail=f"timeout after {external_timeout:g}s",
                )
            except Exception as exc:
                return DependencyState(status="DEGRADED", detail=type(exc).__name__)

        def probe_database() -> str:
            with self.composition.session_factory() as session:
                session.execute(text("SELECT 1"))
                observed = _database_revision(session)
            expected = _expected_alembic_head(self.root)
            if observed != expected:
                raise RuntimeError(
                    f"database revision {observed!r} does not match head {expected!r}"
                )
            return observed or "unknown"

        def probe_governance() -> None:
            if not deployment_lock_matches(self.root):
                raise RuntimeError("Prefect deployment lock is stale")
            compile_stage_registry(self.root)
            compile_flow_catalog(self.root)

        def probe_artifact_store() -> None:
            self.composition.artifact_store.list_artifact_ids()

        database_state, governance_state, artifact_state, prefect_state, mlflow_state = (
            await asyncio.gather(
                run_sync_probe(
                    probe_database,
                    failure_status="FAILED",
                    timeout_seconds=critical_timeout,
                    detail_from_result=lambda value: str(value),
                ),
                run_sync_probe(
                    probe_governance,
                    failure_status="FAILED",
                    timeout_seconds=critical_timeout,
                ),
                run_sync_probe(
                    probe_artifact_store,
                    failure_status="FAILED",
                    timeout_seconds=critical_timeout,
                ),
                run_async_probe(
                    self.composition.prefect_gateway.health
                    if self.composition.prefect_gateway is not None
                    else None,
                    disabled=self.composition.prefect_gateway is None,
                ),
                run_async_probe(
                    self.composition.mlflow_gateway.health
                    if self.composition.mlflow_gateway is not None
                    else None,
                    disabled=self.composition.mlflow_gateway is None,
                ),
            )
        )

        dependencies = {
            "ops_database": database_state,
            "governance_locks": governance_state,
            "artifact_store": artifact_state,
            "prefect": prefect_state,
            "mlflow": mlflow_state,
        }
        critical_ok = all(
            dependencies[name].status == "READY"
            for name in ("ops_database", "governance_locks", "artifact_store")
        )
        return ReadinessResponse(
            ready=critical_ok,
            service=self.settings.service_name,
            dependencies=dependencies,
        )

    def stages(self) -> list[RegistryItem]:
        registry = load_stage_registry(root=self.root)
        return [
            RegistryItem(
                id=item.id, version=item.version, title=item.title, status=item.status,
                metadata={
                    "owner": item.owner, "runtime": item.runtime.type,
                    "approval_policy": item.behavior.approval_policy,
                    "inputs": [value.model_dump(mode="json") for value in item.inputs],
                    "outputs": [value.model_dump(mode="json") for value in item.outputs],
                    "verification": item.verification.model_dump(mode="json"),
                    "tags": list(item.tags),
                },
            )
            for item in registry.stages
        ]

    def flows(self) -> list[RegistryItem]:
        catalog = load_flow_catalog(root=self.root)
        return [
            RegistryItem(
                id=item.id, version=item.version, title=item.title, description=item.description,
                status=item.status,
                metadata={
                    "execution_mode": item.execution_mode, "work_queue": item.work_queue,
                    "approval_policies": list(item.approval_policies),
                    "terminal_gate": item.terminal_gate,
                    "node_count": len(item.nodes), "tags": list(item.tags),
                },
            )
            for item in catalog.flows
        ]

    def deployments(self) -> list[RegistryItem]:
        catalog = load_deployment_catalog(self.root)
        return [
            RegistryItem(
                id=item.flow_id, status="ACTIVE",
                metadata={
                    "flow_name": item.flow_name, "deployment_name": item.deployment_name,
                    "entrypoint": item.entrypoint, "work_queue_name": item.work_queue_name,
                    "manual_only": item.manual_only,
                },
            )
            for item in catalog.deployments
        ]

    def model_versions(self, model_name: str) -> list[ModelVersionView]:
        if self.composition.mlflow_gateway is None:
            raise DependencyUnavailableError("mlflow", "MLflow is not configured")
        try:
            raw = self.composition.mlflow_gateway.list_versions(model_name)
        except Exception as exc:
            raise DependencyUnavailableError("mlflow") from exc
        result: list[ModelVersionView] = []
        with self.composition.session_factory() as session:
            repository = SqlAlchemyOpsReadRepository(session)
            for item in raw:
                scope_id = f"{item['model_name']}:{item['version']}"
                gates = [ReadQueryService(repository, CursorCodec("unused", ttl_seconds=60)).gate_summary(g) for g in repository.scope_gates("model_version", scope_id)]
                result.append(ModelVersionView(**item, gates=gates))
        return result
