from __future__ import annotations

import asyncio
from typing import Any, Protocol


class MLflowReadGateway(Protocol):
    async def health(self) -> dict[str, Any]: ...
    def list_models(self, *, max_results: int = 100) -> list[dict[str, Any]]: ...
    def list_versions(self, model_name: str) -> list[dict[str, Any]]: ...


class RealMLflowReadGateway:
    def __init__(self, tracking_uri: str) -> None:
        self.tracking_uri = tracking_uri

    def _client(self):
        from mlflow import MlflowClient
        return MlflowClient(tracking_uri=self.tracking_uri)

    async def health(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._health_sync)

    def _health_sync(self) -> dict[str, Any]:
        import mlflow

        client = self._client()
        client.search_experiments(max_results=1)
        return {"version": mlflow.__version__, "passed": mlflow.__version__ == "3.14.0"}

    def list_models(self, *, max_results: int = 100) -> list[dict[str, Any]]:
        items = self._client().search_registered_models(max_results=max_results)
        return [
            {
                "name": item.name,
                "description": getattr(item, "description", None),
                "tags": dict(getattr(item, "tags", {}) or {}),
                "aliases": dict(getattr(item, "aliases", {}) or {}),
            }
            for item in items
        ]

    def list_versions(self, model_name: str) -> list[dict[str, Any]]:
        escaped = model_name.replace("'", "\\'")
        items = self._client().search_model_versions(f"name='{escaped}'")
        result: list[dict[str, Any]] = []
        for item in items:
            aliases = list(getattr(item, "aliases", []) or [])
            result.append(
                {
                    "model_name": item.name,
                    "version": str(item.version),
                    "aliases": sorted(aliases),
                    "status": getattr(item, "status", None),
                    "source": getattr(item, "source", None),
                    "run_id": getattr(item, "run_id", None),
                    "tags": dict(getattr(item, "tags", {}) or {}),
                }
            )
        return sorted(result, key=lambda value: int(value["version"]) if value["version"].isdigit() else value["version"], reverse=True)
