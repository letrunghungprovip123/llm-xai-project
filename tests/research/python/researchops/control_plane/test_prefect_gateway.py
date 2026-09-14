from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace
from uuid import UUID

from research.python.researchops.control_plane.gateways.prefect import RealPrefectControlGateway


def test_prefect_submission_uses_server_side_idempotency(monkeypatch):
    observed = {}

    async def fake_run_deployment(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            id=UUID("11111111-2222-3333-4444-555555555555"),
            state=SimpleNamespace(name="SCHEDULED"),
        )

    prefect_module = ModuleType("prefect")
    deployments_module = ModuleType("prefect.deployments")
    deployments_module.run_deployment = fake_run_deployment
    prefect_module.deployments = deployments_module
    monkeypatch.setitem(sys.modules, "prefect", prefect_module)
    monkeypatch.setitem(sys.modules, "prefect.deployments", deployments_module)

    result = asyncio.run(
        RealPrefectControlGateway().submit_deployment(
            "verify-source-environment/local",
            parameters={"parameters": {}},
            idempotency_key="api-request-stable-key",
        )
    )

    assert result.flow_run_id == "11111111-2222-3333-4444-555555555555"
    assert observed["idempotency_key"] == "api-request-stable-key"
    assert observed["as_subflow"] is False
    assert observed["timeout"] == 0
