from __future__ import annotations



def test_cursor_naive_database_timestamp_is_treated_as_utc():
    from datetime import datetime, timezone

    from research.python.researchops.control_plane.queries.cursor import (
        CursorCodec,
        CursorPosition,
    )

    codec = CursorCodec("x" * 64, ttl_seconds=3600)
    naive_utc = datetime(2026, 8, 8, 12, 34, 56, 123456)
    token = codec.encode(
        resource="runs",
        position=CursorPosition(created_at=naive_utc, id="run_cursor_boundary"),
        filters_sha256=codec.filters_sha256({}),
    )
    decoded = codec.decode(
        token, resource="runs", filters_sha256=codec.filters_sha256({})
    )

    assert decoded.created_at == naive_utc.replace(tzinfo=timezone.utc)


def test_health_and_security_headers(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"].startswith("req_")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_run_listing_and_cursor_are_deterministic(client):
    first = client.get("/api/v1/runs", params={"limit": 2})
    assert first.status_code == 200
    payload = first.json()
    assert len(payload["items"]) == 2
    assert payload["page"]["has_more"] is True
    cursor = payload["page"]["next_cursor"]
    second = client.get("/api/v1/runs", params={"limit": 2, "cursor": cursor})
    assert second.status_code == 200
    ids = [item["id"] for item in payload["items"] + second.json()["items"]]
    assert len(ids) == len(set(ids)) == 3


def test_cursor_filter_drift_is_rejected(client):
    first = client.get("/api/v1/runs", params={"limit": 1})
    cursor = first.json()["page"]["next_cursor"]
    response = client.get("/api/v1/runs", params={"limit": 1, "cursor": cursor, "status": "FAILED"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CURSOR"


def test_artifact_files_do_not_leak_object_uri(client):
    response = client.get("/api/v1/artifacts/artifact_test_01J00000000000000000000000/files")
    assert response.status_code == 200
    text = response.text
    assert "password" not in text
    assert "object_uri" not in text
    assert response.json()[0]["relative_path"] == "payload/report.json"


def test_lineage_is_cycle_safe_and_bounded(client):
    response = client.get("/api/v1/artifacts/artifact_test_01J00000000000000000000000/lineage")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["nodes"]) == 2
    assert len(payload["edges"]) == 1


def test_gate_preserves_failed_evaluation_and_waived_effective_status(client):
    response = client.get("/api/v1/gates/gate_result_01J0000000000000000000000")
    assert response.status_code == 200
    payload = response.json()
    assert payload["evaluation_outcome"] == "FAILED"
    assert payload["effective_status"] == "WAIVED"
    assert payload["waiver"]["evaluation_id"] == payload["current_evaluation_id"]


def test_release_exposes_required_and_missing_gate_summary(client):
    response = client.get("/api/v1/releases/release_test_v1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["release_type"] == "complete_research_release"
    assert isinstance(payload["required_gates"], list)
    assert set(payload["missing_gates"]).issubset(set(payload["required_gates"]))


def test_model_version_is_joined_with_ops_gates(client):
    response = client.get("/api/v1/models/credit-risk/versions/1")
    assert response.status_code == 200
    assert response.json()["aliases"] == ["candidate"]


def test_not_found_uses_stable_error_envelope(client):
    response = client.get("/api/v1/runs/missing")
    assert response.status_code == 404
    payload = response.json()["error"]
    assert payload["code"] == "RESOURCE_NOT_FOUND"
    assert payload["request_id"].startswith("req_")


def test_readiness_distinguishes_critical_and_external_dependencies(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["dependencies"]["ops_database"]["status"] == "READY"
    assert payload["dependencies"]["prefect"]["status"] == "READY"
    assert payload["dependencies"]["mlflow"]["status"] == "READY"


def test_version_and_registry_endpoints_do_not_leak_secrets(client):
    version = client.get("/version")
    assert version.status_code == 200
    assert version.json()["alembic_head"] == "0008_control_plane_operations"
    stages = client.get("/api/v1/stages")
    assert stages.status_code == 200
    text = stages.text.lower()
    assert "secret_key" not in text
    assert "password" not in text
    assert len(stages.json()) == 42
