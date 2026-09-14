from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class PrefectSubmission:
    flow_run_id: str
    deployment_name: str
    state_name: str


class PrefectReadGateway(Protocol):
    async def health(self) -> dict[str, Any]: ...


class PrefectControlGateway(PrefectReadGateway, Protocol):
    async def submit_deployment(
        self,
        deployment_name: str,
        *,
        parameters: dict[str, Any],
        idempotency_key: str,
    ) -> PrefectSubmission: ...

    async def cancel_flow_run(self, flow_run_id: str, *, reason: str) -> dict[str, Any]: ...

    async def flow_run(self, flow_run_id: str) -> dict[str, Any]: ...


class RealPrefectReadGateway:
    async def health(self) -> dict[str, Any]:
        import prefect
        from prefect.client.orchestration import get_client

        async with get_client() as client:
            version = str(await client.api_version())
        return {
            "client_version": prefect.__version__,
            "server_version": version,
            "passed": prefect.__version__ == version == "3.7.8",
        }


class RealPrefectControlGateway(RealPrefectReadGateway):
    async def submit_deployment(
        self,
        deployment_name: str,
        *,
        parameters: dict[str, Any],
        idempotency_key: str,
    ) -> PrefectSubmission:
        from prefect.deployments import run_deployment

        flow_run = await run_deployment(
            name=deployment_name,
            parameters=parameters,
            timeout=0,
            tags=["researchops-api", f"api-idempotency:{idempotency_key[:32]}"],
            idempotency_key=idempotency_key,
            as_subflow=False,
        )
        state = getattr(flow_run, "state", None)
        state_name = str(getattr(state, "name", None) or getattr(flow_run, "state_name", None) or "PENDING")
        return PrefectSubmission(
            flow_run_id=str(flow_run.id),
            deployment_name=deployment_name,
            state_name=state_name,
        )

    async def cancel_flow_run(self, flow_run_id: str, *, reason: str) -> dict[str, Any]:
        from prefect.client.orchestration import get_client
        from prefect.states import Cancelled

        async with get_client() as client:
            result = await client.set_flow_run_state(
                UUID(flow_run_id),
                Cancelled(message=reason),
                force=True,
            )
        return {
            "flow_run_id": flow_run_id,
            "accepted": True,
            "status": str(getattr(result, "status", "ACCEPT")),
        }

    async def flow_run(self, flow_run_id: str) -> dict[str, Any]:
        from prefect.client.orchestration import get_client

        async with get_client() as client:
            item = await client.read_flow_run(UUID(flow_run_id))
        state = getattr(item, "state", None)
        return {
            "flow_run_id": str(item.id),
            "state_name": str(getattr(state, "name", None) or "UNKNOWN"),
            "state_type": str(getattr(getattr(state, "type", None), "value", getattr(state, "type", "UNKNOWN"))),
        }
