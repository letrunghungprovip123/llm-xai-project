from __future__ import annotations

from research.python.researchops.control_plane.openapi import schema_payload


def test_openapi_has_explicit_unique_operation_ids():
    schema = schema_payload()
    ids = []
    for item in schema["paths"].values():
        for operation in item.values():
            if isinstance(operation, dict) and "operationId" in operation:
                ids.append(operation["operationId"])
    assert ids
    assert len(ids) == len(set(ids))
    assert "list_runs" in ids
    assert "get_gate_evaluation" in ids


def test_openapi_has_no_case_or_review_routes_before_their_phases():
    paths = schema_payload()["paths"]
    assert not any("/cases" in path for path in paths)
    assert not any("/reviews" in path for path in paths)


def test_openapi_declares_bearer_security_scheme():
    schema = schema_payload()
    schemes = schema["components"]["securitySchemes"]
    assert any(item.get("scheme") == "bearer" for item in schemes.values())
