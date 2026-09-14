from __future__ import annotations

import asyncio
import pytest

from research.python.researchops.orchestration.bootstrap import (
    bootstrap_prefect_runtime,
)
from research.python.researchops.orchestration.contracts import (
    load_prefect_runtime_contract,
)
from research.python.researchops.orchestration.gateway import (
    PrefectQueueSnapshot,
    PrefectRuntimeSnapshot,
)


class FakeGateway:
    def __init__(self, *, queue_drift: bool = False):
        self.calls = 0
        self.queue_drift = queue_drift

    async def bootstrap(self, contract):
        self.calls += 1
        queues = tuple(
            PrefectQueueSnapshot(
                name=item.name,
                priority=item.priority,
                concurrency_limit=(
                    99 if self.queue_drift and item.name == "release"
                    else item.concurrency_limit
                ),
                is_paused=False,
            )
            for item in contract.queues
        )
        return PrefectRuntimeSnapshot(
            client_version="3.7.8",
            server_version="3.7.8",
            work_pool_name=contract.work_pool.name,
            work_pool_type=contract.work_pool.type,
            queues=queues,
            online_workers=("worker-1",),
        )

    async def inspect(self, contract):
        return await self.bootstrap(contract)


def test_bootstrap_is_run_twice_and_policy_is_idempotent():
    gateway = FakeGateway()
    result = asyncio.run(
        bootstrap_prefect_runtime(gateway, load_prefect_runtime_contract())
    )

    assert gateway.calls == 2
    assert result.passed
    assert len(result.queues) == 4


def test_bootstrap_rejects_observed_queue_drift():
    with pytest.raises(ValueError, match="queue policy drift"):
        asyncio.run(
            bootstrap_prefect_runtime(
                FakeGateway(queue_drift=True),
                load_prefect_runtime_contract(),
            )
        )
