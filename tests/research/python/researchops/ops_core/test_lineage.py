import pytest

from research.python.researchops.artifacts.exceptions import ArtifactValidationError
from research.python.researchops.ops_core.db.models import ArtifactRecord
from research.python.researchops.ops_core.services.lineage import LineageService

from .fakes import FakeRepository


def _artifact(artifact_id):
    return ArtifactRecord(id=artifact_id, artifact_type="release_metadata", schema_version="v1", status="VERIFIED", manifest_uri="file:///x", manifest_sha256=("a" if artifact_id.endswith("A") else "b") * 64, source_commit="abc1234", limitations=[], artifact_metadata={})


def test_lineage_rejects_cycle():
    repo = FakeRepository()
    a = "artifact_release_metadata_01J0000000000000000000000A"
    b = "artifact_release_metadata_01J0000000000000000000000B"
    repo.artifacts[a] = _artifact(a)
    repo.artifacts[b] = _artifact(b)
    service = LineageService(repo)
    service.add_edge(a, b, actor="tester")
    assert service.descendants(a) == {b}
    with pytest.raises(ArtifactValidationError, match="cycle"):
        service.add_edge(b, a, actor="tester")
