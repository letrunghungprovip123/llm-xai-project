from pathlib import Path

from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.ops_core.services.reconciliation import ReconciliationService

from .fakes import FakeRepository


def test_reconciliation_detects_and_repairs_orphan(tmp_path: Path, sample_package):
    store = FilesystemArtifactStore(tmp_path / "store")
    store.put_package(sample_package)
    repo = FakeRepository()
    service = ReconciliationService(repo, store)
    before = service.inspect()
    assert before.orphan_objects == (sample_package.manifest.artifact_id,)
    repaired = service.repair_safe(actor="reconciler")
    assert repaired.repaired_artifacts == (sample_package.manifest.artifact_id,)
    assert repaired.passed
