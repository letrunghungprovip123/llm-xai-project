from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .models import PrefectFlowRunSnapshot, PrefectTaskRunSnapshot


PREFECT_API_MAX_PAGE_SIZE = 200


@dataclass(frozen=True)
class PrefectRuntimeSnapshot:
    flow_runs: tuple[PrefectFlowRunSnapshot, ...]
    task_runs: tuple[PrefectTaskRunSnapshot, ...]


class PrefectSnapshotGateway(Protocol):
    def snapshot(self) -> PrefectRuntimeSnapshot: ...


PageReader = Callable[..., Awaitable[list[Any]]]


class LivePrefectSnapshotGateway:
    """Read self-hosted Prefect state without mutating it.

    ``limit`` is the total number of records requested for each resource type,
    not the size of a single API request. Prefect limits list endpoints to 200
    records per request, so larger snapshots are collected with offset-based
    pagination.
    """

    def __init__(
        self,
        *,
        limit: int = 1000,
        page_size: int = PREFECT_API_MAX_PAGE_SIZE,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be a positive integer")
        if not 1 <= page_size <= PREFECT_API_MAX_PAGE_SIZE:
            raise ValueError(
                "page_size must be between 1 and "
                f"{PREFECT_API_MAX_PAGE_SIZE}"
            )
        self.limit = limit
        self.page_size = page_size
        self.client_factory = client_factory

    async def _read_pages(self, reader: PageReader) -> list[Any]:
        records: list[Any] = []
        offset = 0
        while len(records) < self.limit:
            request_limit = min(
                self.page_size,
                self.limit - len(records),
            )
            page = list(
                await reader(
                    limit=request_limit,
                    offset=offset,
                )
            )
            records.extend(page)
            if len(page) < request_limit:
                break
            offset += len(page)
        return records

    async def _read(self) -> PrefectRuntimeSnapshot:
        client_factory = self.client_factory
        if client_factory is None:
            from prefect.client.orchestration import get_client

            client_factory = get_client

        async with client_factory() as client:
            flow_runs = await self._read_pages(client.read_flow_runs)
            task_runs = await self._read_pages(client.read_task_runs)
        return PrefectRuntimeSnapshot(
            flow_runs=tuple(
                PrefectFlowRunSnapshot(
                    flow_run_id=str(item.id),
                    state_name=str(item.state_name or "UNKNOWN").upper(),
                    deployment_id=(
                        str(item.deployment_id) if item.deployment_id else None
                    ),
                    flow_name=getattr(item, "name", None),
                    parameters=dict(getattr(item, "parameters", None) or {}),
                    updated_at=(
                        item.updated.isoformat() if getattr(item, "updated", None) else None
                    ),
                )
                for item in flow_runs
            ),
            task_runs=tuple(
                PrefectTaskRunSnapshot(
                    task_run_id=str(item.id),
                    flow_run_id=str(item.flow_run_id),
                    state_name=str(item.state_name or "UNKNOWN").upper(),
                    task_name=getattr(item, "name", None),
                    updated_at=(
                        item.updated.isoformat() if getattr(item, "updated", None) else None
                    ),
                )
                for item in task_runs
            ),
        )

    def snapshot(self) -> PrefectRuntimeSnapshot:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._read())
        raise RuntimeError(
            "LivePrefectSnapshotGateway.snapshot() must be called outside an active event loop"
        )
