from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from research.python.researchops.contracts.io import project_root


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PrefectDatabaseContract(StrictModel):
    database_name: str = Field(min_length=1)
    user_name: str = Field(min_length=1)
    migration_owner: Literal["prefect"]
    managed_by: Literal["prefect_cli"]


class PrefectMessagingContract(StrictModel):
    broker: Literal["prefect_redis.messaging"]
    cache: Literal["prefect_redis.messaging"]
    redis_database: int = Field(ge=0)
    docket_database: int = Field(ge=0)

    @model_validator(mode="after")
    def databases_are_separated(self) -> "PrefectMessagingContract":
        if self.redis_database == self.docket_database:
            raise ValueError("Messaging and Docket Redis databases must be distinct")
        return self


class PrefectWorkPoolContract(StrictModel):
    name: str = Field(min_length=1)
    type: Literal["process"]
    description: str = Field(min_length=1)
    concurrency_limit: int = Field(ge=1)


class PrefectQueueContract(StrictModel):
    name: Literal["release", "provider-llm", "cpu-heavy", "verification"]
    priority: int = Field(ge=1)
    concurrency_limit: int = Field(ge=1)
    purpose: str = Field(min_length=1)


class PrefectRuntimePolicies(StrictModel):
    migration_on_server_start: Literal[False]
    separate_background_services: Literal[True]
    worker_limit: int = Field(ge=1)
    provider_default_schedule: Literal[False]
    release_default_schedule: Literal[False]


class PrefectRuntimeContract(StrictModel):
    schema_version: Literal["prefect_runtime_contract_v1"]
    status: Literal["ACTIVE"]
    prefect_version: Literal["3.7.8"]
    api_url: str
    internal_api_url: str
    database: PrefectDatabaseContract
    messaging: PrefectMessagingContract
    work_pool: PrefectWorkPoolContract
    queues: tuple[PrefectQueueContract, ...]
    policies: PrefectRuntimePolicies

    @field_validator("api_url", "internal_api_url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("Prefect API URLs must use HTTP(S)")
        if not normalized.endswith("/api"):
            raise ValueError("Prefect API URLs must end with /api")
        return normalized

    @model_validator(mode="after")
    def runtime_is_governed(self) -> "PrefectRuntimeContract":
        expected = {
            "release": (1, 1),
            "provider-llm": (2, 1),
            "cpu-heavy": (5, 1),
            "verification": (10, 4),
        }
        observed = {
            item.name: (item.priority, item.concurrency_limit)
            for item in self.queues
        }
        if observed != expected:
            raise ValueError(
                f"Prefect work-queue policy mismatch: expected={expected} "
                f"observed={observed}"
            )
        if self.policies.worker_limit != self.work_pool.concurrency_limit:
            raise ValueError("Worker and work-pool concurrency limits must match")
        return self


def load_prefect_runtime_contract() -> PrefectRuntimeContract:
    path = project_root() / "config/platform/prefect/prefect_runtime_contract_v1.json"
    return PrefectRuntimeContract.model_validate_json(path.read_text(encoding="utf-8"))


def validate_prefect_runtime_contract() -> dict[str, object]:
    contract = load_prefect_runtime_contract()
    schema_path = (
        project_root()
        / "config/platform/schemas/prefect_runtime_contract_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise RuntimeError("jsonschema is required for runtime validation") from exc
    jsonschema.Draft202012Validator(schema).validate(
        contract.model_dump(mode="json")
    )
    return {
        "schema_version": "prefect_runtime_contract_validation_v1",
        "passed": True,
        "prefect_version": contract.prefect_version,
        "work_pool": contract.work_pool.name,
        "queue_count": len(contract.queues),
        "queues": [item.model_dump(mode="json") for item in contract.queues],
    }
