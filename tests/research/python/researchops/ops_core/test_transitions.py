import pytest

from research.python.researchops.artifacts.exceptions import ArtifactValidationError
from research.python.researchops.ops_core.db.models import ArtifactRecord
from research.python.researchops.ops_core.services.state_transitions import StateTransitionService

from .fakes import FakeRepository


def test_artifact_transition_uses_governed_policy():
    repo = FakeRepository()
    artifact_id = "artifact_release_metadata_01J00000000000000000000000"
    repo.artifacts[artifact_id] = ArtifactRecord(id=artifact_id, artifact_type="release_metadata", schema_version="v1", status="VERIFIED", manifest_uri="file:///x", manifest_sha256="a" * 64, source_commit="abc1234", limitations=[], artifact_metadata={})
    service = StateTransitionService(repo)
    service.artifact(artifact_id, expected="VERIFIED", target="CERTIFIED", actor="tester", reason="gates passed")
    assert repo.artifacts[artifact_id].status == "CERTIFIED"
    with pytest.raises(ArtifactValidationError):
        service.artifact(artifact_id, expected="CERTIFIED", target="DRAFT", actor="tester", reason="invalid")
