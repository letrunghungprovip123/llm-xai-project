from datetime import datetime, timedelta, timezone

import pytest

from research.python.researchops.artifacts.exceptions import ArtifactValidationError
from research.python.researchops.ops_core.db.models import (
    Approval,
    ArtifactRecord,
    GateResult,
    ReleaseArtifact,
    ReleaseRecord,
)
from research.python.researchops.ops_core.services.releases import ReleaseService

from .fakes import FakeRepository


MANIFEST_ID = "artifact_release_metadata_01J00000000000000000000000"


def _repo():
    repo = FakeRepository()
    repo.artifacts[MANIFEST_ID] = ArtifactRecord(
        id=MANIFEST_ID,
        artifact_type="release_metadata",
        schema_version="v1",
        status="VERIFIED",
        manifest_uri="file:///manifest",
        manifest_sha256="a" * 64,
        source_commit="abc1234",
        limitations=[],
        artifact_metadata={},
    )
    repo.releases["thesis-report-v1"] = ReleaseRecord(
        id="thesis-report-v1",
        release_type="thesis_report",
        status="CANDIDATE",
        manifest_artifact_id=MANIFEST_ID,
        source_commit="abc1234",
        limitations=[],
        release_metadata={},
    )
    repo.release_members.append(
        ReleaseArtifact(
            release_id="thesis-report-v1",
            artifact_id=MANIFEST_ID,
            role="manifest",
        )
    )
    return repo


def test_release_promotion_requires_gates_and_approval():
    repo = _repo()
    service = ReleaseService(repo)
    with pytest.raises(ArtifactValidationError, match="authorization"):
        service.promote(
            "thesis-report-v1",
            expected_status="CANDIDATE",
            target_status="CERTIFIED",
            actor="tester",
            reason="release",
            required_approval_policy="RELEASE",
        )
    repo.gates.append(
        GateResult(
            id="gate_1",
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id="thesis-report-v1",
            status="PASSED",
            evaluation_outcome="PASSED",
            effective_status="PASSED",
            current_evaluation_id="eval-report",
            blocking=True,
            severity="ERROR",
            expected={},
            observed={},
            details={},
            source_contracts=[],
        )
    )
    with pytest.raises(ArtifactValidationError, match="approval"):
        service.promote(
            "thesis-report-v1",
            expected_status="CANDIDATE",
            target_status="CERTIFIED",
            actor="tester",
            reason="release",
            required_approval_policy="RELEASE",
        )
    repo.approval_items.append(
        Approval(
            id="approval_1",
            target_type="release",
            target_id="thesis-report-v1",
            policy="RELEASE",
            status="APPROVED",
            requested_by="owner",
            decided_by="reviewer",
            decided_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    service.promote(
        "thesis-report-v1",
        expected_status="CANDIDATE",
        target_status="CERTIFIED",
        actor="tester",
        reason="release",
        required_approval_policy="RELEASE",
    )
    assert repo.releases["thesis-report-v1"].status == "CERTIFIED"


def test_failed_gate_blocks_release():
    repo = _repo()
    repo.gates.append(
        GateResult(
            id="gate_2",
            gate_id="REPORT_WRITING_READY",
            scope_type="release",
            scope_id="thesis-report-v1",
            status="FAILED",
            evaluation_outcome="FAILED",
            effective_status="FAILED",
            current_evaluation_id="eval-failed",
            blocking=True,
            severity="ERROR",
            expected={}, observed={}, details={}, source_contracts=[],
        )
    )
    with pytest.raises(ArtifactValidationError, match="authorization"):
        ReleaseService(repo).promote(
            "thesis-report-v1",
            expected_status="CANDIDATE",
            target_status="CERTIFIED",
            actor="tester",
            reason="release",
        )
