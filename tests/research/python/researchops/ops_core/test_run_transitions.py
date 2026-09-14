from research.python.researchops.ops_core.db.models import PipelineRun, StageRun
from research.python.researchops.ops_core.services.state_transitions import (
    StateTransitionService,
)

from .fakes import FakeRepository


def test_pipeline_and_stage_run_transitions():
    repo = FakeRepository()
    repo.runs["run_01J00000000000000000000000"] = PipelineRun(
        id="run_01J00000000000000000000000",
        flow_id="flow",
        status="PENDING",
        trigger_type="CLI",
        requested_by="tester",
        registry_sha256="a" * 64,
        source_commit="abc1234",
        environment_snapshot_id="env_01J00000000000000000000000",
        idempotency_key="key",
        parameters={},
    )
    repo.stage_runs["stage_run_01J00000000000000000000000"] = StageRun(
        id="stage_run_01J00000000000000000000000",
        pipeline_run_id="run_01J00000000000000000000000",
        stage_id="ml.train",
        stage_version=1,
        attempt=1,
        status="PENDING",
        command_snapshot={},
        approval_policy="EXPENSIVE",
    )
    service = StateTransitionService(repo)
    service.pipeline_run(
        "run_01J00000000000000000000000",
        expected="PENDING",
        target="RUNNING",
        actor="tester",
        reason="start",
    )
    service.stage_run(
        "stage_run_01J00000000000000000000000",
        expected="PENDING",
        target="WAITING_APPROVAL",
        actor="tester",
        reason="expensive",
    )
    assert repo.runs["run_01J00000000000000000000000"].status == "RUNNING"
    assert repo.stage_runs["stage_run_01J00000000000000000000000"].status == "WAITING_APPROVAL"
