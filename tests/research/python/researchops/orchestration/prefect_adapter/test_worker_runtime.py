from __future__ import annotations

from pathlib import Path

import yaml


def test_prefect_worker_uses_authoritative_ops_database_credentials():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    worker = compose["services"]["researchops-prefect-worker"]
    environment = worker["environment"]

    assert environment["PREFECT_WORKER_LIMIT"] == "${PREFECT_WORKER_LIMIT:-4}"
    assert environment["RESEARCHOPS_DATABASE_URL"] == "${RESEARCHOPS_INTERNAL_DATABASE_URL:-}"
    assert environment["RESEARCHOPS_POSTGRES_DB"] == "${RESEARCHOPS_POSTGRES_DB:-llm_xai_ops}"
    assert environment["RESEARCHOPS_POSTGRES_USER"] == "${RESEARCHOPS_POSTGRES_USER:-researchops}"
    assert environment["RESEARCHOPS_POSTGRES_PASSWORD"] == (
        "${RESEARCHOPS_POSTGRES_PASSWORD:-researchops-local-password}"
    )
    assert "postgresql+psycopg://researchops:researchops-local-password" not in str(
        worker
    )
    assert worker["command"] == [
        "/bin/sh",
        "/workspace/infra/researchops/prefect/worker-entrypoint.sh",
    ]


def test_worker_entrypoint_fails_closed_before_starting_prefect():
    script = Path("infra/researchops/prefect/worker-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    preflight = (
        "python3 -m research.python.researchops.orchestration."
        "ops_database_preflight"
    )
    assert preflight in script
    assert script.index(preflight) < script.index("exec prefect worker start")
    assert "PREFECT_OPS_DATABASE_CONNECTIVITY=PASS" in script


def test_worker_entrypoint_defaults_and_validates_worker_limit():
    script = Path("infra/researchops/prefect/worker-entrypoint.sh").read_text(
        encoding="utf-8"
    )

    assert 'PREFECT_WORKER_LIMIT="${PREFECT_WORKER_LIMIT:-4}"' in script
    assert '*[!0-9]*' in script
    assert 'PREFECT_WORKER_LIMIT must be greater than zero.' in script
    assert '--limit "$PREFECT_WORKER_LIMIT"' in script
