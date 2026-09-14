from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from research.python.researchops.orchestration.reconciliation.cli import parser
from research.python.researchops.orchestration.reconciliation.gateway import (
    PREFECT_API_MAX_PAGE_SIZE,
    LivePrefectSnapshotGateway,
)


class FakePrefectClient:
    def __init__(self, *, flow_count: int, task_count: int) -> None:
        self.flow_runs = [
            SimpleNamespace(
                id=UUID(int=index + 1),
                state_name="COMPLETED",
                deployment_id=None,
                name=f"flow-{index}",
                updated=None,
                parameters={
                    "parameters": {"acceptance_session": "phase6-test"}
                },
            )
            for index in range(flow_count)
        ]
        self.task_runs = [
            SimpleNamespace(
                id=UUID(int=10_000 + index),
                flow_run_id=UUID(int=1),
                state_name="COMPLETED",
                name=f"task-{index}",
                updated=None,
            )
            for index in range(task_count)
        ]
        self.flow_calls: list[tuple[int, int]] = []
        self.task_calls: list[tuple[int, int]] = []

    async def read_flow_runs(self, *, limit: int, offset: int):
        assert 1 <= limit <= PREFECT_API_MAX_PAGE_SIZE
        self.flow_calls.append((limit, offset))
        return self.flow_runs[offset : offset + limit]

    async def read_task_runs(self, *, limit: int, offset: int):
        assert 1 <= limit <= PREFECT_API_MAX_PAGE_SIZE
        self.task_calls.append((limit, offset))
        return self.task_runs[offset : offset + limit]


class FakeClientContext:
    def __init__(self, client: FakePrefectClient) -> None:
        self.client = client

    async def __aenter__(self) -> FakePrefectClient:
        return self.client

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def client_factory(client: FakePrefectClient):
    return lambda: FakeClientContext(client)


def test_gateway_paginates_above_prefect_server_page_limit():
    client = FakePrefectClient(flow_count=450, task_count=405)
    gateway = LivePrefectSnapshotGateway(
        limit=450,
        client_factory=client_factory(client),
    )

    snapshot = gateway.snapshot()

    assert len(snapshot.flow_runs) == 450
    assert len(snapshot.task_runs) == 405
    assert snapshot.flow_runs[0].parameters == {
        "parameters": {"acceptance_session": "phase6-test"}
    }
    assert client.flow_calls == [(200, 0), (200, 200), (50, 400)]
    assert client.task_calls == [(200, 0), (200, 200), (50, 400)]


def test_gateway_default_total_limit_never_becomes_request_page_size():
    client = FakePrefectClient(flow_count=205, task_count=201)
    gateway = LivePrefectSnapshotGateway(
        client_factory=client_factory(client),
    )

    snapshot = gateway.snapshot()

    assert len(snapshot.flow_runs) == 205
    assert len(snapshot.task_runs) == 201
    assert client.flow_calls == [(200, 0), (200, 200)]
    assert client.task_calls == [(200, 0), (200, 200)]
    assert max(limit for limit, _ in client.flow_calls + client.task_calls) == 200


def test_gateway_rejects_invalid_limits_and_page_sizes():
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        LivePrefectSnapshotGateway(limit=0)
    with pytest.raises(ValueError, match="page_size must be between"):
        LivePrefectSnapshotGateway(page_size=201)


def test_cli_limit_is_a_positive_total_record_cap():
    args = parser().parse_args(
        [
            "--limit",
            "1000",
            "--acceptance-session",
            "phase6-current-123",
        ]
    )
    assert args.limit == 1000
    assert args.acceptance_session == "phase6-current-123"


def test_cli_rejects_invalid_acceptance_session():
    with pytest.raises(SystemExit):
        parser().parse_args(["--acceptance-session", "phase6_BAD"])

    with pytest.raises(SystemExit):
        parser().parse_args(["--limit", "0"])
