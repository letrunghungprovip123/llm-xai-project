from __future__ import annotations

import fnmatch
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from research.python.researchops.artifacts.stores.base import ArtifactStore
from research.python.researchops.gates.adapters import AdapterContext, GateAdapterRegistry
from research.python.researchops.gates.adapters.builtin import AdapterContractError
from research.python.researchops.gates.contracts import (
    GateAdapterIdentity,
    GateCheck,
    GateEvaluationDraft,
    GateEvidence,
    GatePolicyIdentity,
    GateScope,
    GateSource,
)
from research.python.researchops.gates.service import (
    GateEvaluationResult,
    GateEvaluationService,
)
from research.python.researchops.ops_core.db.models import ReleaseRecord
from research.python.researchops.ops_core.repositories.protocols import OpsRepository
from research.python.researchops.ops_core.services.releases import ReleaseService
from research.python.researchops.orchestration.execution.contracts import DiscoveredOutput
from research.python.researchops.orchestration.execution.errors import SchemaContractError
from research.python.researchops.stage_registry.models import StageDefinition

_RELEASE_ARTIFACT_TYPES = {
    "claim_measurement_release",
    "thesis_report_release",
    "baseline_comparison_release",
    "visualization_data_release",
    "dashboard_i18n_certification",
    "complete_release_bundle",
}


class SemanticGateOrchestrator:
    """Normalize verified scientific reports into immutable gate evaluations.

    This class deliberately does not decide promotion eligibility. It only records
    semantic evidence and deterministic scope projections.
    """

    def __init__(
        self,
        *,
        repository: OpsRepository,
        artifact_store: ArtifactStore,
        adapter_registry: GateAdapterRegistry | None = None,
        actor: str = "prefect-worker",
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store
        self.adapters = adapter_registry or GateAdapterRegistry()
        self.gates = GateEvaluationService(repository)
        self.actor = actor

    def evaluate_stage_success(
        self,
        *,
        stage: StageDefinition,
        outputs: tuple[DiscoveredOutput, ...],
        pipeline_run_id: str,
        stage_run_id: str,
    ) -> GateEvaluationResult:
        output, report_path, temporary = self._resolve_report(
            stage=stage, outputs=outputs
        )
        try:
            verification = self.artifact_store.verify(output.artifact_id)
            if not verification.passed:
                raise SchemaContractError(
                    "Semantic gate source artifact failed verification: "
                    + "; ".join(verification.errors)
                )
            manifest = self.artifact_store.get_manifest(output.artifact_id)
            if (
                manifest.manifest_sha256 != output.manifest_sha256
                or verification.manifest_sha256 != output.manifest_sha256
            ):
                raise SchemaContractError(
                    f"Semantic gate artifact identity drift: {output.artifact_id}"
                )
            normalized = self._evaluate_adapter(stage, output, report_path)
            draft = GateEvaluationDraft(
                gate_id=stage.verification.success_gate,
                scope=GateScope(type="artifact", id=output.artifact_id),
                outcome=normalized.outcome,
                blocking=True,
                severity="ERROR",
                adapter=GateAdapterIdentity(
                    id=stage.verification.adapter_id,
                    version=stage.verification.adapter_version,
                ),
                policy=GatePolicyIdentity(id="scientific_quality", version="1"),
                source=GateSource(
                    artifact_id=output.artifact_id,
                    manifest_sha256=output.manifest_sha256,
                    contract=output.contract,
                ),
                evidence=GateEvidence(
                    artifact_id=output.artifact_id,
                    manifest_sha256=output.manifest_sha256,
                ),
                expected=normalized.expected,
                observed=normalized.observed,
                checks=normalized.checks,
                limitations=normalized.limitations,
                source_contracts=(output.contract,),
                origin_pipeline_run_id=pipeline_run_id,
                origin_stage_run_id=stage_run_id,
                evaluated_at=datetime.now(timezone.utc),
            )
            result = self.gates.record(draft, actor=self.actor)
            self._project_to_stage_run(result, draft, stage_run_id)
            self._project_to_trained_model_ancestor(result, draft)
            if output.contract in _RELEASE_ARTIFACT_TYPES:
                release_id = self._release_id(report_path, output.artifact_id)
                self._project_to_release(
                    result=result,
                    source=draft,
                    source_commit=manifest.source.source_commit,
                    release_id=release_id,
                )
                if output.contract == "complete_release_bundle":
                    self._index_complete_bundle(
                        release_id=release_id,
                        bundle_artifact_id=output.artifact_id,
                        report_path=report_path,
                    )
            if output.contract == "mlflow_registration_receipt":
                self._project_mlflow_receipt(
                    receipt_result=result,
                    receipt_draft=draft,
                    receipt_artifact_id=output.artifact_id,
                    report_path=report_path,
                )
            if normalized.outcome != "PASSED":
                raise SchemaContractError(
                    f"Semantic gate failed for {stage.id}: "
                    f"{stage.verification.success_gate}"
                )
            return result
        finally:
            temporary.cleanup()

    def evaluate_stage_failure(
        self,
        *,
        stage: StageDefinition,
        evidence_artifact_id: str,
        pipeline_run_id: str,
        stage_run_id: str,
    ) -> GateEvaluationResult | None:
        if not stage.verification.failure_evidence_globs:
            return None
        verification = self.artifact_store.verify(evidence_artifact_id)
        if not verification.passed:
            raise SchemaContractError(
                "Failure evidence artifact failed verification: "
                + "; ".join(verification.errors)
            )
        manifest = self.artifact_store.get_manifest(evidence_artifact_id)
        with tempfile.TemporaryDirectory(
            prefix="researchops-gate-failure-"
        ) as directory:
            root = self.artifact_store.download(
                evidence_artifact_id, Path(directory)
            )
            report = self._select_report_file(
                root / "files", stage.verification.report_glob
            )
            if report is None:
                return None
            output = DiscoveredOutput(
                name="failure_evidence",
                contract="stage_execution_evidence",
                artifact_id=evidence_artifact_id,
                manifest_sha256=manifest.manifest_sha256,
                file_count=len(manifest.files),
            )
            normalized = self._evaluate_adapter(stage, output, report)
            # A failed command can never become a passed scientific evaluation.
            checks = tuple(normalized.checks)
            if not checks or all(item.passed for item in checks):
                checks = (
                    GateCheck(
                        check_id="command_exit",
                        passed=False,
                        expected=0,
                        observed="nonzero",
                    ),
                )
            draft = GateEvaluationDraft(
                gate_id=stage.verification.success_gate,
                scope=GateScope(type="stage_run", id=stage_run_id),
                outcome="FAILED",
                blocking=True,
                severity="ERROR",
                adapter=GateAdapterIdentity(
                    id=stage.verification.adapter_id,
                    version=stage.verification.adapter_version,
                ),
                policy=GatePolicyIdentity(id="scientific_quality", version="1"),
                source=GateSource(contract="stage_execution_evidence"),
                evidence=GateEvidence(
                    artifact_id=evidence_artifact_id,
                    manifest_sha256=manifest.manifest_sha256,
                ),
                expected=normalized.expected,
                observed={**normalized.observed, "command_failed": True},
                checks=checks,
                limitations=normalized.limitations,
                source_contracts=("stage_execution_evidence",),
                origin_pipeline_run_id=pipeline_run_id,
                origin_stage_run_id=stage_run_id,
                evaluated_at=datetime.now(timezone.utc),
            )
            return self.gates.record(draft, actor=self.actor)

    def _evaluate_adapter(
        self,
        stage: StageDefinition,
        output: DiscoveredOutput,
        report_path: Path,
    ):
        try:
            adapter = self.adapters.get(
                stage.verification.adapter_id,
                stage.verification.adapter_version,
            )
            return adapter.evaluate(
                AdapterContext(
                    gate_id=stage.verification.success_gate,
                    report_path=report_path,
                    artifact_id=output.artifact_id,
                    artifact_type=output.contract,
                    manifest_sha256=output.manifest_sha256,
                )
            )
        except (AdapterContractError, ValueError, TypeError, KeyError) as exc:
            raise SchemaContractError(
                f"Gate adapter {stage.verification.adapter_id}@"
                f"{stage.verification.adapter_version} rejected report for "
                f"{stage.id}: {exc}"
            ) from exc

    def _project_to_stage_run(
        self,
        result: GateEvaluationResult,
        source: GateEvaluationDraft,
        stage_run_id: str,
    ) -> GateEvaluationResult:
        draft = source.model_copy(
            update={
                "scope": GateScope(type="stage_run", id=stage_run_id),
                "adapter": GateAdapterIdentity(
                    id="artifact_to_stage_run_projection_v1", version=1
                ),
                "policy": GatePolicyIdentity(id="scope_projection", version="1"),
                "source_evaluation_ids": (result.evaluation.id,),
                "evaluated_at": datetime.now(timezone.utc),
            }
        )
        return self.gates.record(draft, actor=self.actor)

    def _project_to_trained_model_ancestor(
        self,
        result: GateEvaluationResult,
        source: GateEvaluationDraft,
    ) -> GateEvaluationResult | None:
        if source.gate_id not in {"MODEL_READY", "XAI_QUALITY_READY"}:
            return None
        trained_models = sorted(
            artifact_id
            for artifact_id in self.repository.ancestors(source.scope.id)
            if (record := self.repository.get_artifact(artifact_id)) is not None
            and record.artifact_type == "trained_model"
        )
        if not trained_models:
            return None
        if len(trained_models) != 1:
            raise SchemaContractError(
                f"Expected exactly one trained_model ancestor for "
                f"{source.scope.id}; found={trained_models}"
            )
        draft = source.model_copy(
            update={
                "scope": GateScope(type="artifact", id=trained_models[0]),
                "adapter": GateAdapterIdentity(
                    id="artifact_to_model_artifact_projection_v1", version=1
                ),
                "policy": GatePolicyIdentity(id="scope_projection", version="1"),
                "source_evaluation_ids": (result.evaluation.id,),
                "evaluated_at": datetime.now(timezone.utc),
            }
        )
        return self.gates.record(draft, actor=self.actor)

    def _project_to_release(
        self,
        *,
        result: GateEvaluationResult,
        source: GateEvaluationDraft,
        source_commit: str,
        release_id: str,
    ) -> GateEvaluationResult:
        release = self.repository.get_release(release_id)
        if release is None:
            ReleaseService(self.repository).create(
                ReleaseRecord(
                    id=release_id,
                    release_type=source.source.contract,
                    status="CANDIDATE",
                    manifest_artifact_id=source.scope.id,
                    source_commit=source_commit,
                    limitations=list(source.limitations),
                    release_metadata={
                        "indexed_from_artifact": source.scope.id,
                        "indexer_version": 1,
                    },
                ),
                actor=self.actor,
            )
        elif release.manifest_artifact_id != source.scope.id:
            raise SchemaContractError(
                f"Release identity drift for {release_id}: manifest artifact changed"
            )
        draft = source.model_copy(
            update={
                "scope": GateScope(type="release", id=release_id),
                "adapter": GateAdapterIdentity(
                    id="artifact_to_release_projection_v1", version=1
                ),
                "policy": GatePolicyIdentity(id="scope_projection", version="1"),
                "source_evaluation_ids": (result.evaluation.id,),
                "evaluated_at": datetime.now(timezone.utc),
            }
        )
        return self.gates.record(draft, actor=self.actor)

    def _index_complete_bundle(
        self,
        *,
        release_id: str,
        bundle_artifact_id: str,
        report_path: Path,
    ) -> None:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        inputs = payload.get("inputs")
        if not isinstance(inputs, dict) or not inputs:
            raise SchemaContractError("Complete release bundle has no input artifact map")
        ancestors = self.repository.ancestors(bundle_artifact_id)
        existing_members = self.repository.release_artifact_ids(release_id)
        release_service = ReleaseService(self.repository)
        for role, raw_artifact_id in sorted(inputs.items()):
            artifact_id = str(raw_artifact_id)
            if self.repository.get_artifact(artifact_id) is None:
                raise SchemaContractError(
                    f"Complete release member is not registered: {artifact_id}"
                )
            if artifact_id not in ancestors:
                raise SchemaContractError(
                    f"Complete release member is not an artifact ancestor: {artifact_id}"
                )
            if artifact_id not in existing_members:
                release_service.attach_artifact(
                    release_id,
                    artifact_id,
                    role=str(role),
                    actor=self.actor,
                )
                existing_members.add(artifact_id)
            for current in sorted(
                self.repository.blocking_gates("artifact", artifact_id),
                key=lambda item: (item.gate_id, item.id),
            ):
                if current.current_evaluation_id is None:
                    continue
                evaluation = self.repository.get_gate_evaluation(
                    current.current_evaluation_id
                )
                if evaluation is None or evaluation.source_artifact_id is None:
                    continue
                source_artifact = self.repository.get_artifact(
                    evaluation.source_artifact_id
                )
                if source_artifact is None:
                    continue
                checks = tuple(
                    GateCheck.model_validate(item) for item in evaluation.checks
                )
                projection = GateEvaluationDraft(
                    gate_id=evaluation.gate_id,
                    scope=GateScope(type="release", id=release_id),
                    outcome=evaluation.outcome,
                    blocking=evaluation.blocking,
                    severity=evaluation.severity,
                    adapter=GateAdapterIdentity(
                        id="artifact_to_release_projection_v1", version=1
                    ),
                    policy=GatePolicyIdentity(
                        id="complete_bundle_projection", version="1"
                    ),
                    source=GateSource(
                        artifact_id=source_artifact.id,
                        manifest_sha256=source_artifact.manifest_sha256,
                        contract=source_artifact.artifact_type,
                    ),
                    evidence=(
                        GateEvidence(
                            artifact_id=evaluation.evidence_artifact_id,
                            manifest_sha256=evaluation.evidence_manifest_sha256,
                        )
                        if evaluation.evidence_artifact_id
                        and evaluation.evidence_manifest_sha256
                        else None
                    ),
                    expected=evaluation.expected,
                    observed=evaluation.observed,
                    checks=checks,
                    limitations=tuple(evaluation.limitations),
                    source_contracts=tuple(evaluation.source_contracts),
                    source_evaluation_ids=(evaluation.id,),
                    evaluated_at=datetime.now(timezone.utc),
                )
                self.gates.record(projection, actor=self.actor)

    def _project_mlflow_receipt(
        self,
        *,
        receipt_result: GateEvaluationResult,
        receipt_draft: GateEvaluationDraft,
        receipt_artifact_id: str,
        report_path: Path,
    ) -> None:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        source_model = str(payload["source_model_artifact_id"])
        receipt_ancestors = self.repository.ancestors(receipt_artifact_id)
        if source_model not in receipt_ancestors:
            raise SchemaContractError(
                "MLflow receipt does not preserve lineage to source trained model"
            )
        target = f"{payload['registered_model_name']}:{payload['candidate_version']}"
        self._record_model_projection(
            gate_id="MLFLOW_MODEL_REGISTERED",
            target=target,
            source_result=receipt_result,
            source_draft=receipt_draft,
        )

        for gate_id in ("MODEL_READY", "XAI_QUALITY_READY"):
            current = self.repository.get_gate_result(
                gate_id, "artifact", source_model
            )
            if current is None or current.current_evaluation_id is None:
                continue
            source_evaluation = self.repository.get_gate_evaluation(
                current.current_evaluation_id
            )
            if source_evaluation is None or not source_evaluation.source_artifact_id:
                continue
            source_artifact = self.repository.get_artifact(
                source_evaluation.source_artifact_id
            )
            if source_artifact is None:
                continue
            checks = tuple(
                GateCheck.model_validate(item)
                for item in source_evaluation.checks
            )
            projection_draft = GateEvaluationDraft(
                gate_id=gate_id,
                scope=GateScope(type="model_version", id=target),
                outcome=source_evaluation.outcome,
                blocking=source_evaluation.blocking,
                severity=source_evaluation.severity,
                adapter=GateAdapterIdentity(
                    id="artifact_to_model_version_projection_v1", version=1
                ),
                policy=GatePolicyIdentity(id="scope_projection", version="1"),
                source=GateSource(
                    artifact_id=source_artifact.id,
                    manifest_sha256=source_artifact.manifest_sha256,
                    contract=source_artifact.artifact_type,
                ),
                evidence=(
                    GateEvidence(
                        artifact_id=source_evaluation.evidence_artifact_id,
                        manifest_sha256=source_evaluation.evidence_manifest_sha256,
                    )
                    if source_evaluation.evidence_artifact_id
                    and source_evaluation.evidence_manifest_sha256
                    else None
                ),
                expected=source_evaluation.expected,
                observed=source_evaluation.observed,
                checks=checks,
                limitations=tuple(source_evaluation.limitations),
                source_contracts=tuple(source_evaluation.source_contracts),
                source_evaluation_ids=(
                    source_evaluation.id,
                    receipt_result.evaluation.id,
                ),
                evaluated_at=datetime.now(timezone.utc),
            )
            self.gates.record(projection_draft, actor=self.actor)

    def _record_model_projection(
        self,
        *,
        gate_id: str,
        target: str,
        source_result: GateEvaluationResult,
        source_draft: GateEvaluationDraft,
    ) -> GateEvaluationResult:
        projected = source_draft.model_copy(
            update={
                "gate_id": gate_id,
                "scope": GateScope(type="model_version", id=target),
                "adapter": GateAdapterIdentity(
                    id="artifact_to_model_version_projection_v1", version=1
                ),
                "policy": GatePolicyIdentity(id="scope_projection", version="1"),
                "source_evaluation_ids": (source_result.evaluation.id,),
                "evaluated_at": datetime.now(timezone.utc),
            }
        )
        return self.gates.record(projected, actor=self.actor)

    def _resolve_report(
        self,
        *,
        stage: StageDefinition,
        outputs: tuple[DiscoveredOutput, ...],
    ) -> tuple[DiscoveredOutput, Path, tempfile.TemporaryDirectory[str]]:
        temporary = tempfile.TemporaryDirectory(prefix="researchops-gate-report-")
        found: list[tuple[DiscoveredOutput, Path]] = []
        for index, output in enumerate(outputs):
            verification = self.artifact_store.verify(output.artifact_id)
            if not verification.passed:
                temporary.cleanup()
                raise SchemaContractError(
                    f"Output artifact verification failed: {output.artifact_id}"
                )
            root = self.artifact_store.download(
                output.artifact_id, Path(temporary.name) / str(index)
            )
            report = self._select_report_file(
                root / "files", stage.verification.report_glob
            )
            if report is not None:
                found.append((output, report))
        if len(found) != 1:
            temporary.cleanup()
            raise SchemaContractError(
                f"Expected exactly one canonical semantic report for {stage.id}; "
                f"found={len(found)}"
            )
        return found[0][0], found[0][1], temporary

    @staticmethod
    def _release_id(report_path: Path, artifact_id: str) -> str:
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            candidate = payload.get("release_id")
            if isinstance(candidate, str) and candidate.strip():
                value = candidate.strip()
                return value if value.startswith("release:") else f"release:{value}"
        return f"release:{artifact_id}"

    @staticmethod
    def _select_report_file(files_root: Path, report_glob: str | None) -> Path | None:
        if not report_glob:
            return None
        matches: list[Path] = []
        basename = PurePosixPath(report_glob).name
        has_magic = any(character in report_glob for character in "*?[")
        for item in files_root.rglob("*"):
            if not item.is_file():
                continue
            relative = item.relative_to(files_root).as_posix()
            variants = {relative}
            for prefix in ("payload/", "scientific_failure/"):
                if relative.startswith(prefix):
                    variants.add(relative[len(prefix) :])
            marker = "/data/"
            if marker in f"/{relative}":
                variants.add("data/" + relative.split(marker, 1)[1])
            if any(fnmatch.fnmatch(value, report_glob) for value in variants):
                matches.append(item)
                continue
            basename_has_magic = any(character in basename for character in "*?[")
            if (
                (not has_magic and relative.endswith("/" + report_glob))
                or (not basename_has_magic and item.name == basename)
            ):
                matches.append(item)
        unique = sorted(set(matches), key=lambda item: item.as_posix())
        if not unique:
            return None
        if len(unique) > 1:
            raise SchemaContractError(
                f"Canonical report pattern is ambiguous: {report_glob}; "
                f"matches={[item.as_posix() for item in unique]}"
            )
        return unique[0]
