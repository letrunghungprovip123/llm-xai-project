from __future__ import annotations

from research.python.researchops.artifacts.exceptions import ArtifactValidationError

from ..db.models import LineageEdge
from ..repositories.protocols import OpsRepository
from .audit import record_audit


class LineageService:
    def __init__(self, repository: OpsRepository) -> None:
        self.repository = repository

    def add_edge(
        self,
        parent_artifact_id: str,
        child_artifact_id: str,
        *,
        relationship_type: str = "derived_from",
        actor: str,
    ) -> None:
        if parent_artifact_id == child_artifact_id:
            raise ArtifactValidationError("Self-lineage is forbidden")
        if self.repository.get_artifact(parent_artifact_id) is None:
            raise ArtifactValidationError("Parent artifact does not exist")
        if self.repository.get_artifact(child_artifact_id) is None:
            raise ArtifactValidationError("Child artifact does not exist")
        if parent_artifact_id in self.repository.descendants(child_artifact_id):
            raise ArtifactValidationError("Lineage edge would create a cycle")
        self.repository.add_lineage_edge(LineageEdge(
            parent_artifact_id=parent_artifact_id,
            child_artifact_id=child_artifact_id,
            relationship_type=relationship_type,
        ))
        record_audit(
            self.repository,
            actor=actor,
            action="lineage.edge_added",
            target_type="artifact",
            target_id=child_artifact_id,
            metadata={"parent_artifact_id": parent_artifact_id, "relationship": relationship_type},
        )
        self.repository.flush()

    def ancestors(self, artifact_id: str) -> set[str]:
        return self.repository.ancestors(artifact_id)

    def descendants(self, artifact_id: str) -> set[str]:
        return self.repository.descendants(artifact_id)
