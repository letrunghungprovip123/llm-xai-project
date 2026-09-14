from __future__ import annotations

from dataclasses import dataclass

from research.python.researchops.artifacts.exceptions import ArtifactError
from research.python.researchops.artifacts.stores.base import ArtifactStore

from ..repositories.protocols import OpsRepository
from .artifact_registration import ArtifactRegistrationService


@dataclass(frozen=True)
class ReconciliationReport:
    orphan_objects: tuple[str, ...]
    missing_objects: tuple[str, ...]
    integrity_violations: tuple[str, ...]
    manifest_hash_mismatches: tuple[str, ...]
    incomplete_stage_runs: tuple[str, ...] = ()
    repaired_artifacts: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not (
            self.orphan_objects
            or self.missing_objects
            or self.integrity_violations
            or self.manifest_hash_mismatches
            or self.incomplete_stage_runs
        )


class ReconciliationService:
    def __init__(self, repository: OpsRepository, artifact_store: ArtifactStore) -> None:
        self.repository = repository
        self.artifact_store = artifact_store

    def inspect(self) -> ReconciliationReport:
        stored = self.artifact_store.list_artifact_ids()
        registered = self.repository.list_artifact_ids()
        integrity: list[str] = []
        mismatches: list[str] = []
        for artifact_id in sorted(stored & registered):
            result = self.artifact_store.verify(artifact_id)
            if not result.passed:
                integrity.append(artifact_id)
                continue
            record = self.repository.get_artifact(artifact_id)
            if record is not None and record.manifest_sha256 != result.manifest_sha256:
                mismatches.append(artifact_id)
        return ReconciliationReport(
            orphan_objects=tuple(sorted(stored - registered)),
            missing_objects=tuple(sorted(registered - stored)),
            integrity_violations=tuple(integrity),
            manifest_hash_mismatches=tuple(mismatches),
            incomplete_stage_runs=tuple(
                sorted(self.repository.succeeded_stage_runs_without_artifacts())
            ),
        )

    def repair_safe(self, *, actor: str) -> ReconciliationReport:
        before = self.inspect()
        repaired: list[str] = []
        registration = ArtifactRegistrationService(self.repository, self.artifact_store)
        pending = set(before.orphan_objects)
        progress = True
        while pending and progress:
            progress = False
            for artifact_id in sorted(tuple(pending)):
                try:
                    registration.register(artifact_id, actor=actor)
                except ArtifactError:
                    continue
                pending.remove(artifact_id)
                repaired.append(artifact_id)
                progress = True
        after = self.inspect()
        return ReconciliationReport(
            orphan_objects=after.orphan_objects,
            missing_objects=after.missing_objects,
            integrity_violations=after.integrity_violations,
            manifest_hash_mismatches=after.manifest_hash_mismatches,
            incomplete_stage_runs=after.incomplete_stage_runs,
            repaired_artifacts=tuple(repaired),
        )
