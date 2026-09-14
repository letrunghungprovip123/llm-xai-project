from __future__ import annotations

from pathlib import Path

import yaml


def test_prefect_compose_topology_is_separated_and_pinned():
    payload = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    services = payload["services"]
    required = {
        "researchops-prefect-db-init",
        "researchops-prefect-redis",
        "researchops-prefect-migrate",
        "researchops-prefect-server",
        "researchops-prefect-services",
        "researchops-prefect-bootstrap",
        "researchops-prefect-worker",
    }
    assert required <= set(services)
    assert services["researchops-prefect-server"]["image"].endswith("3.7.8")
    server_command = services["researchops-prefect-server"]["command"]
    assert "--no-services" in server_command
    assert services["researchops-prefect-migrate"]["command"] == [
        "prefect server database upgrade -y"
    ]
    assert (
        services["researchops-prefect-server"]["environment"][
            "PREFECT_API_DATABASE_MIGRATE_ON_START"
        ]
        == "false"
    )
    services_env = services["researchops-prefect-services"]["environment"]
    assert "PREFECT_SERVER_DOCKET_URL" in services_env
    assert services_env["PREFECT_SERVER_EVENTS_CAUSAL_ORDERING"] == (
        "prefect_redis.ordering"
    )
    assert services_env["PREFECT_SERVER_CONCURRENCY_LEASE_STORAGE"] == (
        "prefect_redis.lease_storage"
    )
    redis_health = services["researchops-prefect-redis"]["healthcheck"]["test"][-1]
    assert '"$${PREFECT_REDIS_PASSWORD}"' in redis_health


def test_prefect_dockerfile_uses_immutable_version_tag():
    dockerfile = Path("infra/researchops/prefect/Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "FROM prefecthq/prefect:3.7.8-python3.12" in dockerfile
    assert "3-latest" not in dockerfile
