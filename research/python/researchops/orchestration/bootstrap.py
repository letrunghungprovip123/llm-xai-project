from __future__ import annotations

from .contracts import PrefectRuntimeContract
from .gateway import PrefectGateway, PrefectRuntimeSnapshot


async def bootstrap_prefect_runtime(
    gateway: PrefectGateway,
    contract: PrefectRuntimeContract,
) -> PrefectRuntimeSnapshot:
    first = await gateway.bootstrap(contract)
    second = await gateway.bootstrap(contract)
    expected = {
        item.name: (item.priority, item.concurrency_limit)
        for item in contract.queues
    }
    for snapshot in (first, second):
        observed = {
            item.name: (item.priority, item.concurrency_limit)
            for item in snapshot.queues
        }
        if snapshot.work_pool_name != contract.work_pool.name:
            raise ValueError("Prefect work-pool bootstrap returned the wrong pool")
        if snapshot.work_pool_type != contract.work_pool.type:
            raise ValueError("Prefect work-pool type drift detected")
        if observed != expected:
            raise ValueError(
                f"Prefect queue policy drift: expected={expected} observed={observed}"
            )
        if not snapshot.passed:
            raise ValueError(
                f"Prefect version mismatch: client={snapshot.client_version} "
                f"server={snapshot.server_version}"
            )
    return second
