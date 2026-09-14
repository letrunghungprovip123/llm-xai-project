from __future__ import annotations

from pydantic import ValidationError

from research.python.researchops.orchestration.contracts import (
    PrefectRuntimeContract,
    load_prefect_runtime_contract,
    validate_prefect_runtime_contract,
)


def test_runtime_contract_is_schema_valid_and_pinned():
    contract = load_prefect_runtime_contract()
    report = validate_prefect_runtime_contract()

    assert contract.prefect_version == "3.7.8"
    assert contract.work_pool.type == "process"
    assert report["passed"] is True
    assert report["queue_count"] == 4


def test_runtime_contract_rejects_queue_policy_drift():
    payload = load_prefect_runtime_contract().model_dump(mode="json")
    payload["queues"][0]["concurrency_limit"] = 2

    try:
        PrefectRuntimeContract.model_validate(payload)
    except ValidationError as error:
        message = str(error)
    else:
        raise AssertionError("Expected queue policy drift to fail closed")

    assert "queue policy mismatch" in message


def test_runtime_contract_requires_distinct_redis_databases():
    payload = load_prefect_runtime_contract().model_dump(mode="json")
    payload["messaging"]["docket_database"] = payload["messaging"][
        "redis_database"
    ]

    try:
        PrefectRuntimeContract.model_validate(payload)
    except ValidationError as error:
        message = str(error)
    else:
        raise AssertionError("Expected Redis database overlap to fail closed")

    assert "must be distinct" in message
