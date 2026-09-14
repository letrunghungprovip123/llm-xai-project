from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from research.python.researchops.artifacts.exceptions import ArtifactValidationError

from ..repositories.protocols import OpsRepository
from .audit import record_audit


@lru_cache(maxsize=1)
def _project_root() -> Path:
    return Path(__file__).resolve().parents[5]


class LifecyclePolicy:
    def __init__(self, path: Path | None = None) -> None:
        source = path or _project_root() / "config/platform/lifecycle_states_v1.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        self.transitions = {
            resource["resource"]: {
                (item["from"], item["to"])
                for item in resource["transitions"]
            }
            for resource in payload["resources"]
        }

    def require_allowed(self, resource: str, current: str, target: str) -> None:
        if (current, target) not in self.transitions.get(resource, set()):
            raise ArtifactValidationError(
                f"Invalid {resource} transition: {current} -> {target}"
            )


class StateTransitionService:
    def __init__(self, repository: OpsRepository, policy: LifecyclePolicy | None = None) -> None:
        self.repository = repository
        self.policy = policy or LifecyclePolicy()

    def pipeline_run(self, run_id: str, *, expected: str, target: str, actor: str, reason: str) -> None:
        record = self.repository.get_pipeline_run(run_id)
        if record is None:
            raise ArtifactValidationError("Pipeline run does not exist")
        self._run_transition("pipeline_run", record, run_id, expected, target, actor, reason)

    def stage_run(self, stage_run_id: str, *, expected: str, target: str, actor: str, reason: str) -> None:
        record = self.repository.get_stage_run(stage_run_id)
        if record is None:
            raise ArtifactValidationError("Stage run does not exist")
        self._run_transition("stage_run", record, stage_run_id, expected, target, actor, reason)

    def _run_transition(self, resource: str, record, record_id: str, expected: str, target: str, actor: str, reason: str) -> None:
        if record.status != expected:
            raise ArtifactValidationError(
                f"{resource} status changed: expected={expected} observed={record.status}"
            )
        self.policy.require_allowed(resource, record.status, target)
        before = {"status": record.status}
        record.status = target
        record_audit(
            self.repository,
            actor=actor,
            action=f"{resource}.transition",
            target_type=resource,
            target_id=record_id,
            before_state=before,
            after_state={"status": target},
            metadata={"reason": reason},
        )
        self.repository.flush()

    def artifact(self, artifact_id: str, *, expected: str, target: str, actor: str, reason: str) -> None:
        record = self.repository.get_artifact(artifact_id)
        if record is None:
            raise ArtifactValidationError("Artifact does not exist")
        if record.status != expected:
            raise ArtifactValidationError(f"Artifact status changed: expected={expected} observed={record.status}")
        self.policy.require_allowed("artifact", record.status, target)
        before = {"status": record.status}
        record.status = target
        record_audit(self.repository, actor=actor, action="artifact.transition", target_type="artifact", target_id=artifact_id, before_state=before, after_state={"status": target}, metadata={"reason": reason})
        self.repository.flush()

    def release(self, release_id: str, *, expected: str, target: str, actor: str, reason: str) -> None:
        record = self.repository.get_release(release_id)
        if record is None:
            raise ArtifactValidationError("Release does not exist")
        if record.status != expected:
            raise ArtifactValidationError(f"Release status changed: expected={expected} observed={record.status}")
        self.policy.require_allowed("release", record.status, target)
        before = {"status": record.status}
        record.status = target
        record_audit(self.repository, actor=actor, action="release.transition", target_type="release", target_id=release_id, before_state=before, after_state={"status": target}, metadata={"reason": reason})
        self.repository.flush()
