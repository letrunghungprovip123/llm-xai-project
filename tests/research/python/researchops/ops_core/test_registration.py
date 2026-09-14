from pathlib import Path

import pytest

from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.ops_core.services.artifact_registration import ArtifactRegistrationService

from .fakes import FakeRepository


def test_register_verified_artifact_is_idempotent(tmp_path: Path, sample_package):
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(sample_package)
    repository = FakeRepository()
    service = ArtifactRegistrationService(repository, store)
    first = service.register(sample_package.manifest.artifact_id, actor="tester")
    second = service.register(sample_package.manifest.artifact_id, actor="tester")
    assert first.created
    assert not second.created
    assert len(repository.artifacts) == 1
    assert len(repository.files) == 2
    assert repository.audits[-1].action == "artifact.registered"


def test_unverified_manifest_status_is_rejected(tmp_path: Path, sample_package):
    from research.python.researchops.artifacts.exceptions import ArtifactValidationError
    from research.python.researchops.artifacts.models import ArtifactManifestV3

    store = FilesystemArtifactStore(tmp_path / "store")
    payload = sample_package.manifest.model_dump(mode="json")
    payload["status"] = "DRAFT"
    draft = sample_package.model_copy(
        update={"manifest": ArtifactManifestV3.model_validate(payload)}
    )
    store.put_package(draft)
    with pytest.raises(ArtifactValidationError, match="VERIFIED or CERTIFIED"):
        ArtifactRegistrationService(FakeRepository(), store).register(
            draft.manifest.artifact_id, actor="tester"
        )
