from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from research.python.researchops.orchestration.live_acceptance import (
    wait_flow_run_command,
)


def test_wait_flow_run_command_awaits_prefect_coroutine(monkeypatch) -> None:
    pytest.importorskip("prefect")
    flow_run_id = UUID("11111111-2222-3333-4444-555555555555")
    observed: dict[str, object] = {}

    async def fake_wait_for_flow_run(
        received_flow_run_id: UUID,
        *,
        timeout: int,
        log_states: bool,
    ) -> SimpleNamespace:
        observed.update(
            flow_run_id=received_flow_run_id,
            timeout=timeout,
            log_states=log_states,
        )
        return SimpleNamespace(id=received_flow_run_id, state_name="CANCELLED")

    monkeypatch.setattr(
        "prefect.flow_runs.wait_for_flow_run",
        fake_wait_for_flow_run,
    )

    report = wait_flow_run_command(flow_run_id=str(flow_run_id), timeout=45)

    assert observed == {
        "flow_run_id": flow_run_id,
        "timeout": 45,
        "log_states": True,
    }
    assert report == {
        "schema_version": "phase6_flow_run_wait_v1",
        "flow_run_id": str(flow_run_id),
        "state_name": "CANCELLED",
        "passed": True,
    }
