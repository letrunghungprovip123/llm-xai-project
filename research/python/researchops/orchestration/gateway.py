from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import PrefectRuntimeContract


@dataclass(frozen=True)
class PrefectQueueSnapshot:
    name: str
    priority: int
    concurrency_limit: int | None
    is_paused: bool


@dataclass(frozen=True)
class PrefectRuntimeSnapshot:
    client_version: str
    server_version: str
    work_pool_name: str
    work_pool_type: str
    queues: tuple[PrefectQueueSnapshot, ...]
    online_workers: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.client_version == self.server_version == "3.7.8"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "prefect_runtime_snapshot_v1",
            "passed": self.passed,
            "client_version": self.client_version,
            "server_version": self.server_version,
            "work_pool_name": self.work_pool_name,
            "work_pool_type": self.work_pool_type,
            "queues": [item.__dict__ for item in self.queues],
            "online_workers": list(self.online_workers),
        }


class PrefectGateway(Protocol):
    async def bootstrap(self, contract: PrefectRuntimeContract) -> PrefectRuntimeSnapshot: ...
    async def inspect(self, contract: PrefectRuntimeContract) -> PrefectRuntimeSnapshot: ...


class RealPrefectGateway:
    """Thin adapter over the public Prefect orchestration client.

    Imports are intentionally lazy so contract validation and unit tests do not
    require a running Prefect installation or server.
    """

    async def bootstrap(
        self,
        contract: PrefectRuntimeContract,
    ) -> PrefectRuntimeSnapshot:
        from prefect.client.orchestration import get_client
        from prefect.client.schemas.actions import WorkPoolCreate
        from prefect.exceptions import ObjectNotFound

        async with get_client() as client:
            await client.create_work_pool(
                WorkPoolCreate(
                    name=contract.work_pool.name,
                    type=contract.work_pool.type,
                    description=contract.work_pool.description,
                    concurrency_limit=contract.work_pool.concurrency_limit,
                ),
                overwrite=True,
            )
            for expected in contract.queues:
                try:
                    observed = await client.read_work_queue_by_name(
                        expected.name,
                        work_pool_name=contract.work_pool.name,
                    )
                except ObjectNotFound:
                    await client.create_work_queue(
                        name=expected.name,
                        description=expected.purpose,
                        is_paused=False,
                        concurrency_limit=expected.concurrency_limit,
                        priority=expected.priority,
                        work_pool_name=contract.work_pool.name,
                    )
                else:
                    await client.update_work_queue(
                        observed.id,
                        description=expected.purpose,
                        is_paused=False,
                        concurrency_limit=expected.concurrency_limit,
                        priority=expected.priority,
                    )
        return await self.inspect(contract)

    async def inspect(
        self,
        contract: PrefectRuntimeContract,
    ) -> PrefectRuntimeSnapshot:
        import prefect
        from prefect.client.orchestration import get_client

        async with get_client() as client:
            server_version = await client.api_version()
            pool = await client.read_work_pool(contract.work_pool.name)
            queues = await client.read_work_queues(
                work_pool_name=contract.work_pool.name,
                limit=100,
            )
            workers = await client.read_workers_for_work_pool(
                contract.work_pool.name,
                limit=100,
            )
        snapshots = tuple(
            sorted(
                (
                    PrefectQueueSnapshot(
                        name=item.name,
                        priority=item.priority,
                        concurrency_limit=item.concurrency_limit,
                        is_paused=item.is_paused,
                    )
                    for item in queues
                    if item.name in {queue.name for queue in contract.queues}
                ),
                key=lambda item: item.priority,
            )
        )
        online = tuple(
            sorted(
                item.name
                for item in workers
                if str(item.status).split(".")[-1].upper() == "ONLINE"
            )
        )
        return PrefectRuntimeSnapshot(
            client_version=prefect.__version__,
            server_version=str(server_version),
            work_pool_name=pool.name,
            work_pool_type=pool.type,
            queues=snapshots,
            online_workers=online,
        )
