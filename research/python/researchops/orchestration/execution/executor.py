from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from research.python.researchops.artifacts.models import (
    ArtifactParent,
    ArtifactProducer,
    ArtifactSource,
)
from research.python.researchops.artifacts.package_builder import ArtifactPackageBuilder
from research.python.researchops.artifacts.stores.base import ArtifactStore
from research.python.researchops.ops_core.db.models import GateResult
from research.python.researchops.ops_core.repositories.protocols import OpsRepository
from research.python.researchops.ops_core.services.artifact_registration import (
    ArtifactRegistrationService,
)
from research.python.researchops.stage_registry.command_renderer import render_command
from research.python.researchops.stage_registry.models import ArtifactBinding, StageDefinition

from ..evidence.builder import build_stage_execution_evidence
from ..ops_bridge.service import OpsBridgeService
from .contracts import (
    DiscoveredOutput,
    MaterializedInput,
    StageCommandOutputReference,
    StageCommandResult,
    StageExecutionResult,
)
from .redaction import redact_mapping, redact_text
from .errors import (
    ArtifactCorruptionError,
    CommandConfigurationError,
    CommandExecutionError,
    CommandTimeoutError,
    HashMismatchError,
    InfrastructureUnavailableError,
    RateLimitError,
    SchemaContractError,
    TransientProviderError,
    classify_error,
)

_SAFE_BASE_ENV = {
    "PATH",
    "HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "NODE_PATH",
    "NPM_CONFIG_CACHE",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _glob_files(root: Path, pattern: str) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                item.resolve()
                for item in root.glob(pattern)
                if item.is_file() and root.resolve() in item.resolve().parents
            ),
            key=str,
        )
    )


def _snapshot(root: Path, bindings: tuple[ArtifactBinding, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for binding in bindings:
        for pattern in binding.discovery_patterns:
            for path in _glob_files(root, pattern):
                result[path.as_posix()] = _sha256_file(path)
    return result


def _json_parameter(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class StageExecutor:
    def __init__(
        self,
        *,
        repository: OpsRepository,
        artifact_store: ArtifactStore,
        ops_bridge: OpsBridgeService,
        project_root: Path,
        execution_root: Path,
        actor: str = "prefect-worker",
        semantic_gate_orchestrator: Any | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store
        self.ops_bridge = ops_bridge
        self.project_root = project_root.resolve()
        self.execution_root = execution_root.resolve()
        self.actor = actor
        self.semantic_gate_orchestrator = semantic_gate_orchestrator

    def execute(
        self,
        *,
        stage: StageDefinition,
        node_id: str,
        pipeline_run_id: str,
        stage_run_id: str,
        orchestration_key: str,
        input_artifact_ids: Mapping[str, str],
        parameters: Mapping[str, Any],
        source_commit: str,
        environment_snapshot_id: str,
        stage_registry_sha256: str,
        flow_id: str,
        attempt: int,
    ) -> StageExecutionResult:
        started = datetime.now(timezone.utc)
        run_dir = self.execution_root / pipeline_run_id / stage_run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
        (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
        stdout_path = run_dir / "logs/stdout.log"
        stderr_path = run_dir / "logs/stderr.log"
        command = render_command(stage.runtime)
        materialized: dict[str, MaterializedInput] = {}
        parent_manifests: list[tuple[str, str]] = []
        stdout_text = ""
        stderr_text = ""
        outputs: tuple[DiscoveredOutput, ...] = ()
        command_result_metadata: dict[str, Any] = {}
        evidence_id: str | None = None
        exit_code: int | None = None
        error: BaseException | None = None
        failure_before: dict[str, str] = {}

        try:
            materialized = self._materialize_inputs(
                stage=stage,
                input_artifact_ids=input_artifact_ids,
                run_dir=run_dir,
            )
            parent_manifests = [
                (item.artifact_id, item.manifest_sha256)
                for item in materialized.values()
            ]
            before = _snapshot(self.project_root, stage.outputs)
            failure_before = self._snapshot_patterns(
                stage.verification.failure_evidence_globs
            )
            env = self._child_environment(
                stage=stage,
                node_id=node_id,
                pipeline_run_id=pipeline_run_id,
                stage_run_id=stage_run_id,
                flow_id=flow_id,
                run_dir=run_dir,
                materialized=materialized,
                parameters=parameters,
            )
            working_directory = (self.project_root / stage.runtime.working_directory).resolve()
            if self.project_root not in working_directory.parents and working_directory != self.project_root:
                raise CommandConfigurationError("Stage working directory escapes project root")
            if not working_directory.is_dir():
                raise CommandConfigurationError(
                    f"Stage working directory is missing: {working_directory}"
                )
            try:
                completed = subprocess.run(
                    list(command),
                    cwd=working_directory,
                    env=env,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=stage.behavior.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                stdout_text = exc.stdout or ""
                stderr_text = exc.stderr or ""
                raise CommandTimeoutError(
                    f"Stage timed out after {stage.behavior.timeout_seconds}s"
                ) from exc
            stdout_text = completed.stdout
            stderr_text = completed.stderr
            exit_code = completed.returncode
            stdout_path.write_text(stdout_text, encoding="utf-8")
            stderr_path.write_text(stderr_text, encoding="utf-8")
            if completed.returncode != 0:
                if completed.returncode == 75:
                    raise InfrastructureUnavailableError(
                        "Stage reported transient infrastructure unavailability"
                    )
                if completed.returncode == 76:
                    raise TransientProviderError(
                        "Stage reported a transient provider failure"
                    )
                if completed.returncode == 77:
                    raise RateLimitError("Stage reported provider rate limiting")
                message = f"Stage command exited with code {completed.returncode}"
                stderr_tail = redact_text(stderr_text.strip())[-2000:]
                if stderr_tail:
                    message = f"{message}: {stderr_tail}"
                raise CommandExecutionError(
                    message,
                    exit_code=completed.returncode,
                )
            outputs, command_result_metadata = self._register_outputs(
                stage=stage,
                stage_run_id=stage_run_id,
                run_dir=run_dir,
                before=before,
                materialized=materialized,
                parent_manifests=parent_manifests,
                source_commit=source_commit,
                environment_snapshot_id=environment_snapshot_id,
                stage_registry_sha256=stage_registry_sha256,
                parameters=parameters,
            )
            ended = datetime.now(timezone.utc)
            result = StageExecutionResult(
                pipeline_run_id=pipeline_run_id,
                stage_run_id=stage_run_id,
                node_id=node_id,
                stage_id=stage.id,
                stage_version=stage.version,
                status="SUCCEEDED",
                attempt=attempt,
                orchestration_key=orchestration_key,
                command=command,
                started_at=started,
                ended_at=ended,
                exit_code=exit_code,
                outputs=outputs,
                metadata={"command_result": command_result_metadata}
                if command_result_metadata
                else {},
            )
            self._record_execution_gate(stage, stage_run_id, outputs)
            if self.semantic_gate_orchestrator is not None:
                self.semantic_gate_orchestrator.evaluate_stage_success(
                    stage=stage,
                    outputs=outputs,
                    pipeline_run_id=pipeline_run_id,
                    stage_run_id=stage_run_id,
                )
        except BaseException as exc:  # evidence is required for every terminal attempt
            error = exc
            classification = classify_error(exc)
            ended = datetime.now(timezone.utc)
            if exit_code not in (None, 0):
                self._capture_failure_evidence(
                    run_dir=run_dir,
                    patterns=stage.verification.failure_evidence_globs,
                    before=failure_before,
                )
            result = StageExecutionResult(
                pipeline_run_id=pipeline_run_id,
                stage_run_id=stage_run_id,
                node_id=node_id,
                stage_id=stage.id,
                stage_version=stage.version,
                status="FAILED",
                attempt=attempt,
                orchestration_key=orchestration_key,
                command=command,
                started_at=started,
                ended_at=ended,
                exit_code=getattr(exc, "exit_code", exit_code),
                outputs=outputs,
                retryable=classification.retryable,
                error_type=classification.error_type,
                error_category=classification.category,
                error_message=classification.message,
            )

        try:
            evidence_id, _ = build_stage_execution_evidence(
                directory=run_dir,
                result=result,
                command_payload={
                    "argv": list(command),
                    "shell": False,
                    "working_directory": stage.runtime.working_directory,
                    "timeout_seconds": stage.behavior.timeout_seconds,
                },
                environment_payload=self._environment_evidence(stage, parameters),
                inputs_payload={
                    name: item.model_dump(mode="json")
                    for name, item in materialized.items()
                },
                outputs_payload={
                    item.name: item.model_dump(mode="json") for item in outputs
                },
                stdout_text=stdout_text,
                stderr_text=stderr_text,
                source_commit=source_commit,
                environment_snapshot_id=environment_snapshot_id,
                registry_sha256=stage_registry_sha256,
                parent_manifests=parent_manifests,
                artifact_store=self.artifact_store,
                repository=self.repository,
                actor=self.actor,
            )
            stage_record = self.repository.get_stage_run(stage_run_id)
            if stage_record is not None:
                stage_record.stdout_artifact_id = evidence_id
                stage_record.stderr_artifact_id = evidence_id
                self.repository.flush()
            result = result.model_copy(update={"evidence_artifact_id": evidence_id})
            if (
                error is not None
                and exit_code not in (None, 0)
                and self.semantic_gate_orchestrator is not None
            ):
                try:
                    self.semantic_gate_orchestrator.evaluate_stage_failure(
                        stage=stage,
                        evidence_artifact_id=evidence_id,
                        pipeline_run_id=pipeline_run_id,
                        stage_run_id=stage_run_id,
                    )
                except BaseException as semantic_error:
                    if hasattr(error, "add_note"):
                        error.add_note(
                            "Scientific failure evidence could not be normalized: "
                            f"{type(semantic_error).__name__}: {semantic_error}"
                        )
        except BaseException:
            if error is None:
                raise

        if error is not None:
            raise error
        return result

    def _snapshot_patterns(self, patterns: tuple[str, ...]) -> dict[str, str]:
        result: dict[str, str] = {}
        for pattern in patterns:
            for path in _glob_files(self.project_root, pattern):
                result[path.as_posix()] = _sha256_file(path)
        return result

    def _capture_failure_evidence(
        self,
        *,
        run_dir: Path,
        patterns: tuple[str, ...],
        before: Mapping[str, str],
    ) -> tuple[Path, ...]:
        copied: list[Path] = []
        destination_root = run_dir / "evidence" / "scientific_failure"
        for pattern in patterns:
            for path in _glob_files(self.project_root, pattern):
                if before.get(path.as_posix()) == _sha256_file(path):
                    continue
                relative = path.relative_to(self.project_root)
                target = destination_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                copied.append(target)
        return tuple(sorted(set(copied), key=str))

    def _materialize_inputs(
        self,
        *,
        stage: StageDefinition,
        input_artifact_ids: Mapping[str, str],
        run_dir: Path,
    ) -> dict[str, MaterializedInput]:
        expected_names = {item.name for item in stage.inputs}
        unknown = set(input_artifact_ids) - expected_names
        if unknown:
            raise SchemaContractError(f"Unknown stage input names: {sorted(unknown)}")
        result: dict[str, MaterializedInput] = {}
        for binding in stage.inputs:
            artifact_id = input_artifact_ids.get(binding.name)
            if artifact_id is None:
                if binding.required:
                    raise SchemaContractError(
                        f"Required stage input is missing: {stage.id}.{binding.name}"
                    )
                continue
            verification = self.artifact_store.verify(artifact_id)
            if not verification.passed:
                raise ArtifactCorruptionError("; ".join(verification.errors))
            manifest = self.artifact_store.get_manifest(artifact_id)
            if manifest.manifest_sha256 != verification.manifest_sha256:
                raise HashMismatchError(
                    f"Input manifest changed during verification: {artifact_id}"
                )
            if manifest.artifact_type != binding.contract:
                raise SchemaContractError(
                    f"Input contract mismatch for {binding.name}: "
                    f"expected={binding.contract} observed={manifest.artifact_type}"
                )
            directory = self.artifact_store.download(
                artifact_id, run_dir / "inputs" / binding.name
            )
            result[binding.name] = MaterializedInput(
                name=binding.name,
                contract=binding.contract,
                artifact_id=artifact_id,
                manifest_sha256=manifest.manifest_sha256,
                directory=directory,
            )
        return result

    def _child_environment(
        self,
        *,
        stage: StageDefinition,
        node_id: str,
        pipeline_run_id: str,
        stage_run_id: str,
        flow_id: str,
        run_dir: Path,
        materialized: Mapping[str, MaterializedInput],
        parameters: Mapping[str, Any],
    ) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if key in _SAFE_BASE_ENV}
        for secret_name in stage.secrets:
            value = os.getenv(secret_name)
            if value is None:
                raise CommandConfigurationError(
                    f"Required stage secret is missing: {secret_name}"
                )
            env[secret_name] = value
        env.update(
            {
                "RESEARCHOPS_PIPELINE_RUN_ID": pipeline_run_id,
                "RESEARCHOPS_STAGE_RUN_ID": stage_run_id,
                "RESEARCHOPS_FLOW_ID": flow_id,
                "RESEARCHOPS_NODE_ID": node_id,
                "RESEARCHOPS_STAGE_ID": stage.id,
                "RESEARCHOPS_RUN_DIR": str(run_dir),
                "RESEARCHOPS_REPORT_PATH": str(run_dir / "stage-report.json"),
                "RESEARCHOPS_INPUT_ARTIFACT_IDS": _json_parameter(
                    {
                        name: item.artifact_id
                        for name, item in sorted(materialized.items())
                    }
                ),
            }
        )
        for name, item in materialized.items():
            normalized = name.upper().replace("-", "_")
            env[f"RESEARCHOPS_INPUT_{normalized}_ARTIFACT_ID"] = item.artifact_id
            env[f"RESEARCHOPS_INPUT_{normalized}_MANIFEST_SHA256"] = (
                item.manifest_sha256
            )
            env[f"RESEARCHOPS_INPUT_{normalized}_CONTRACT"] = item.contract
            env[f"RESEARCHOPS_INPUT_{normalized}_DIR"] = str(item.directory)
        for name, value in parameters.items():
            normalized = name.upper().replace("-", "_")
            env[f"RESEARCHOPS_PARAMETER_{normalized}"] = _json_parameter(value)
        return env

    def _register_outputs(
        self,
        *,
        stage: StageDefinition,
        stage_run_id: str,
        run_dir: Path,
        before: Mapping[str, str],
        materialized: Mapping[str, MaterializedInput],
        parent_manifests: list[tuple[str, str]],
        source_commit: str,
        environment_snapshot_id: str,
        stage_registry_sha256: str,
        parameters: Mapping[str, Any],
    ) -> tuple[tuple[DiscoveredOutput, ...], dict[str, Any]]:
        command_result = self._load_stage_command_result(run_dir)
        referenced: list[DiscoveredOutput] = []
        referenced_names: set[str] = set()
        metadata: dict[str, Any] = {}
        if command_result is not None:
            binding_by_name = {item.name: item for item in stage.outputs}
            unknown = set(command_result.outputs) - set(binding_by_name)
            if unknown:
                raise SchemaContractError(
                    f"Stage command reported unknown outputs for {stage.id}: "
                    f"{sorted(unknown)}"
                )
            for name, reference in command_result.outputs.items():
                binding = binding_by_name[name]
                referenced.append(
                    self._register_referenced_output(
                        stage=stage,
                        stage_run_id=stage_run_id,
                        binding=binding,
                        reference=reference,
                        materialized=materialized,
                    )
                )
                referenced_names.add(name)
            metadata = redact_mapping(command_result.metadata)

        discovered = self._discover_and_register_outputs(
            stage=stage,
            stage_run_id=stage_run_id,
            before=before,
            parent_manifests=parent_manifests,
            source_commit=source_commit,
            environment_snapshot_id=environment_snapshot_id,
            stage_registry_sha256=stage_registry_sha256,
            parameters=parameters,
            excluded_output_names=referenced_names,
        )
        outputs_by_name = {item.name: item for item in (*referenced, *discovered)}
        missing = [
            binding.name
            for binding in stage.outputs
            if binding.required and binding.name not in outputs_by_name
        ]
        if missing:
            raise SchemaContractError(
                f"Required stage outputs are missing for {stage.id}: {missing}"
            )
        return (
            tuple(
                outputs_by_name[binding.name]
                for binding in stage.outputs
                if binding.name in outputs_by_name
            ),
            metadata,
        )

    def _load_stage_command_result(
        self, run_dir: Path
    ) -> StageCommandResult | None:
        path = run_dir / "stage-report.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SchemaContractError(
                f"Invalid stage command report: {path}"
            ) from exc
        if not isinstance(payload, dict):
            raise SchemaContractError("Stage command report must be a JSON object")
        try:
            return StageCommandResult.model_validate(payload)
        except Exception as exc:
            raise SchemaContractError(
                "Stage command report does not satisfy stage_command_result_v1"
            ) from exc

    def _register_referenced_output(
        self,
        *,
        stage: StageDefinition,
        stage_run_id: str,
        binding: ArtifactBinding,
        reference: StageCommandOutputReference,
        materialized: Mapping[str, MaterializedInput],
    ) -> DiscoveredOutput:
        if reference.artifact_type != binding.contract:
            raise SchemaContractError(
                f"Referenced output contract mismatch for {stage.id}.{binding.name}: "
                f"expected={binding.contract} observed={reference.artifact_type}"
            )
        verification = self.artifact_store.verify(reference.artifact_id)
        if not verification.passed:
            raise ArtifactCorruptionError("; ".join(verification.errors))
        manifest = self.artifact_store.get_manifest(reference.artifact_id)
        if manifest.artifact_type != binding.contract:
            raise SchemaContractError(
                f"Referenced artifact type mismatch for {binding.name}: "
                f"expected={binding.contract} observed={manifest.artifact_type}"
            )
        if manifest.manifest_sha256 != reference.manifest_sha256:
            raise HashMismatchError(
                f"Referenced output manifest mismatch: {reference.artifact_id}"
            )
        if verification.manifest_sha256 != reference.manifest_sha256:
            raise HashMismatchError(
                f"Referenced output changed during verification: "
                f"{reference.artifact_id}"
            )
        source_inputs = tuple(reference.source_inputs)
        if len(source_inputs) != len(set(source_inputs)):
            raise SchemaContractError(
                f"Referenced output declares duplicate source inputs: {source_inputs}"
            )
        expected_sources = set(materialized)
        observed_sources = set(source_inputs)
        if observed_sources != expected_sources:
            raise SchemaContractError(
                f"Referenced output source mapping mismatch for {stage.id}."
                f"{binding.name}: expected={sorted(expected_sources)} "
                f"observed={sorted(observed_sources)}"
            )
        parent_identity = {
            (item.artifact_id, item.manifest_sha256) for item in manifest.parents
        }
        for input_name in source_inputs:
            source = materialized[input_name]
            expected = (source.artifact_id, source.manifest_sha256)
            if expected not in parent_identity:
                raise SchemaContractError(
                    f"Referenced output {reference.artifact_id} does not preserve "
                    f"lineage for input {input_name}"
                )
        ArtifactRegistrationService(self.repository, self.artifact_store).register(
            reference.artifact_id, actor=self.actor
        )
        self.ops_bridge.record_stage_output(
            stage_run_id=stage_run_id,
            output_name=binding.name,
            contract=binding.contract,
            artifact_id=reference.artifact_id,
            manifest_sha256=reference.manifest_sha256,
        )
        return DiscoveredOutput(
            name=binding.name,
            contract=binding.contract,
            artifact_id=reference.artifact_id,
            manifest_sha256=reference.manifest_sha256,
            file_count=max(1, len(manifest.files)),
        )

    def _discover_and_register_outputs(
        self,
        *,
        stage: StageDefinition,
        stage_run_id: str,
        before: Mapping[str, str],
        parent_manifests: list[tuple[str, str]],
        source_commit: str,
        environment_snapshot_id: str,
        stage_registry_sha256: str,
        parameters: Mapping[str, Any],
        excluded_output_names: set[str] | None = None,
    ) -> tuple[DiscoveredOutput, ...]:
        allow_existing = bool(parameters.get("allow_existing_outputs", False))
        registered: list[DiscoveredOutput] = []
        parents = [
            ArtifactParent(
                artifact_id=artifact_id,
                manifest_sha256=manifest_sha,
                relationship="derived_from",
            )
            for artifact_id, manifest_sha in parent_manifests
        ]
        excluded = excluded_output_names or set()
        for binding in stage.outputs:
            if binding.name in excluded:
                continue
            matches_by_path: dict[str, Path] = {}
            for pattern in binding.discovery_patterns:
                for path in _glob_files(self.project_root, pattern):
                    matches_by_path[path.as_posix()] = path
            matches = tuple(matches_by_path[key] for key in sorted(matches_by_path))
            changed = [
                path
                for path in matches
                if before.get(path.as_posix()) != _sha256_file(path)
            ]
            selected = matches if allow_existing and not changed else tuple(changed)
            if not selected:
                raise SchemaContractError(
                    f"No new or changed files discovered for {stage.id}.{binding.name} "
                    f"using {binding.discovery_patterns!r}"
                )
            builder = ArtifactPackageBuilder(
                artifact_type=binding.contract,
                schema_version=f"{binding.contract}_v1",
                producer=ArtifactProducer(
                    stage_id=stage.id,
                    stage_version=stage.version,
                    stage_run_id=stage_run_id,
                    registry_sha256=stage_registry_sha256,
                ),
                source=ArtifactSource(
                    source_commit=source_commit,
                    environment_snapshot_id=environment_snapshot_id,
                ),
                parents=parents,
                metadata={
                    "output_name": binding.name,
                    "discovery_patterns": list(binding.discovery_patterns),
                    "file_count": len(selected),
                },
            )
            for path in selected:
                relative = path.relative_to(self.project_root).as_posix()
                builder.add_file(path, relative_path=f"payload/{relative}")
            package = builder.build()
            reference = self.artifact_store.put_package(package)
            ArtifactRegistrationService(self.repository, self.artifact_store).register(
                reference.artifact_id, actor=self.actor
            )
            self.ops_bridge.record_stage_output(
                stage_run_id=stage_run_id,
                output_name=binding.name,
                contract=binding.contract,
                artifact_id=reference.artifact_id,
                manifest_sha256=reference.manifest_sha256,
            )
            registered.append(
                DiscoveredOutput(
                    name=binding.name,
                    contract=binding.contract,
                    artifact_id=reference.artifact_id,
                    manifest_sha256=reference.manifest_sha256,
                    file_count=len(selected),
                )
            )
        return tuple(registered)

    def _record_execution_gate(
        self,
        stage: StageDefinition,
        stage_run_id: str,
        outputs: tuple[DiscoveredOutput, ...],
    ) -> None:
        """Record command/output success without over-claiming scientific quality."""

        gate_id = stage.verification.execution_gate
        existing = self.repository.get_gate_result(gate_id, "stage_run", stage_run_id)
        payload = {
            "exit_code": 0,
            "output_count": len(outputs),
            "artifact_ids": [item.artifact_id for item in outputs],
        }
        if existing is not None:
            if existing.status != "PASSED" or existing.observed != payload:
                raise SchemaContractError(
                    f"Execution gate identity drift for stage run {stage_run_id}"
                )
            return
        self.repository.add_gate_result(
            GateResult(
                id=f"gate_{hashlib.sha256((stage_run_id + gate_id).encode()).hexdigest()[:40]}",
                gate_id=gate_id,
                scope_type="stage_run",
                scope_id=stage_run_id,
                status="PASSED",
                blocking=True,
                severity="ERROR",
                expected={"exit_code": 0, "minimum_output_count": len(stage.outputs)},
                observed=payload,
                details={
                    "stage_id": stage.id,
                    "stage_version": stage.version,
                    "semantic_gate": stage.verification.success_gate,
                    "semantic_evaluation_deferred": True,
                },
                source_contracts=[item.contract for item in stage.outputs],
            )
        )
        self.repository.flush()

    def _environment_evidence(
        self, stage: StageDefinition, parameters: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {
            "safe_environment_names": sorted(_SAFE_BASE_ENV),
            "secret_environment_names": list(stage.secrets),
            "parameter_names": sorted(parameters),
            "python_executable": os.getenv("VIRTUAL_ENV"),
        }
